"""
工具注册中心 (ToolRegistry)

负责工具的注册、查找、执行和批量管理：
- 批量注册 (register_many)
- 同步/异步/流式三种执行模式
- 错误提示引导 LLM 重试
- 运行上下文透传（预算检查、业务事件出口、配置注入）
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Union,
)

from ..agent.events import AgentToolResultEvent, AgentToolRunEvent, is_domain_event
from ..runtime.budget import AgentRunError
from ..runtime.events import DomainEvent
from .base import BaseTool, ToolResultHook

if TYPE_CHECKING:
    from ..runtime.run_context import RunContext

logger = logging.getLogger(__name__)

# 追加在错误信息末尾，引导 LLM 换个方式重试
_HINT = "\n\n[请分析上述错误并尝试其他方式。]"


def _normalize_hook_events(ret: Any, source: str = "") -> List[Any]:
    """把 ``on_result_hook`` 的返回值规整为事件列表。

    hook 的返回值有三种合法形态，均予支持：
    - ``None``：无事件（旧签名，绝大多数 hook 属于此类）
    - 单个事件对象
    - 事件列表 / 元组

    非事件返回值（如误返回字符串）会被忽略并告警，避免污染事件流。
    """
    if ret is None:
        return []

    candidates = list(ret) if isinstance(ret, (list, tuple)) else [ret]

    events: List[Any] = []
    for item in candidates:
        if is_domain_event(item):
            if isinstance(item, DomainEvent) and source and not item.source:
                item.source = source
            events.append(item)
        else:
            logger.warning(
                "工具 %s 的 on_result_hook 返回了非事件对象 %s，已忽略",
                source,
                type(item).__name__,
            )
    return events


def _fire_sync(ret: Any) -> Any:
    """在同步上下文中兑现可能是协程的 hook 返回值。

    同步路径下若 hook 是 async 函数，尽力在当前/新事件循环中执行完毕。
    已在运行的事件循环中无法同步等待，此时降级为后台任务（返回 None）。
    """
    if not asyncio.iscoroutine(ret):
        return ret
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(ret)
    loop.create_task(ret)
    logger.debug("同步路径中的 async hook 已转为后台任务，其返回事件不会被收集")
    return None


def _bind_ctx(tool: BaseTool, ctx: Optional["RunContext"]) -> BaseTool:
    """把运行上下文绑定到支持它的工具上。

    目前只有 ``AgentTool`` 需要（用于派生子 Agent 上下文），通过鸭子类型
    探测以避免 registry 反向依赖 agent_tool 模块。
    """
    from copy import copy

    binder = getattr(tool, "bind_context", None)
    if callable(binder):
        # 注册实例可被并发复用；只在调用专属的浅拷贝上绑定上下文。
        # 即使 ctx=None 也必须清除旧绑定。
        tool = copy(tool)
        tool.bind_context(ctx)
    return tool


class ToolRegistry:
    """
    工具注册中心，管理所有可用工具及其治理 hook。

    功能：
    - 注册 / 注销 / 查找工具
    - 获取所有工具的 OpenAI Function Calling 定义
    - 同步 / 异步 / 流式执行工具调用
    - **统一触发治理 hook**（额度检查、业务事件产出）

    Hook 归属
    ---------
    工具实例本身不持有 hook，由本类在注册时显式绑定：

    .. code-block:: python

        registry.register(SmartSearchTool(...), before_call=search_quota_hook)
        registry.register(CreateQuizTool(...), on_result=domain_event_hook)

    这样 hook 的触发点只有一处（:meth:`_fire_before_call` /
    :meth:`_fire_on_result`），三条执行路径共用，不会出现「同一 hook
    走不同入口行为不同」的问题。
    """

    def __init__(
        self,
        tools: Optional[List[BaseTool]] = None,
        *,
        before_call: Optional[Callable[[], Union[None, Awaitable[None]]]] = None,
        on_result: Optional[ToolResultHook] = None,
    ):
        """
        Args:
            tools:       待注册的工具列表。
            before_call: 为 ``tools`` 中所有工具统一绑定的前置 hook。
            on_result:   为 ``tools`` 中所有工具统一绑定的结果 hook。

        单个工具的差异化绑定请改用 :meth:`register`。
        """
        self._tools: Dict[str, BaseTool] = {}
        # 工具名 → hook，与工具实例解耦
        self._before_hooks: Dict[str, Callable[[], Union[None, Awaitable[None]]]] = {}
        self._result_hooks: Dict[str, ToolResultHook] = {}
        if tools:
            self.register_many(tools, before_call=before_call, on_result=on_result)

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(
        self,
        tool: BaseTool,
        *,
        before_call: Optional[Callable[[], Union[None, Awaitable[None]]]] = None,
        on_result: Optional[ToolResultHook] = None,
    ) -> BaseTool:
        """
        注册一个工具，并可选地绑定治理 hook。

        Args:
            tool:        工具实例。
            before_call: 执行前回调（如额度检查），签名 ``() -> None``，
                         支持同步与 async。抛异常会阻断本次工具执行。
            on_result:   执行后回调，签名
                         ``(tool_name, params, result, index) -> None | DomainEvent | list``。
                         返回的业务事件会被并入 Agent 事件流。

        Returns:
            注册的工具实例（方便链式调用）
        """
        if tool.name in self._tools:
            logger.warning("工具 '%s' 已存在，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        # 覆盖注册时同步清理旧 hook，避免残留绑定
        self._before_hooks.pop(tool.name, None)
        self._result_hooks.pop(tool.name, None)
        if before_call is not None:
            self._before_hooks[tool.name] = before_call
        if on_result is not None:
            self._result_hooks[tool.name] = on_result
        logger.debug("注册工具: %s", tool.name)
        return tool

    def register_many(
        self,
        tools: List[BaseTool],
        *,
        before_call: Optional[Callable[[], Union[None, Awaitable[None]]]] = None,
        on_result: Optional[ToolResultHook] = None,
    ) -> None:
        """批量注册工具，可为所有工具统一绑定同一组 hook。"""
        for t in tools:
            self.register(t, before_call=before_call, on_result=on_result)

    def unregister(self, name: str) -> None:
        """移除一个工具及其 hook 绑定。"""
        self._tools.pop(name, None)
        self._before_hooks.pop(name, None)
        self._result_hooks.pop(name, None)
        logger.debug("注销工具: %s", name)

    # ------------------------------------------------------------------
    # Hook 触发（三条执行路径共用的唯一入口）
    # ------------------------------------------------------------------

    def _fire_before_call_sync(self, name: str) -> None:
        """同步路径触发前置 hook。

        hook 返回协程时必须就地跑完——额度检查这类「必须先完成才能继续」
        的语义不能 fire-and-forget，否则形同虚设。
        """
        hook = self._before_hooks.get(name)
        if hook is None:
            return
        ret = hook()
        if asyncio.iscoroutine(ret):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(ret)
                return
            ret.close()
            raise RuntimeError(
                f"工具 {name} 的 before_call hook 是 async，但当前处于同步执行路径"
                "且已有运行中的事件循环，无法安全等待。请改用 async_execute / "
                "async_stream_execute，或提供同步版 hook。"
            )

    async def _fire_before_call_async(self, name: str) -> None:
        """异步路径触发前置 hook，兼容同步与 async 实现。"""
        hook = self._before_hooks.get(name)
        if hook is None:
            return
        ret = hook()
        if asyncio.iscoroutine(ret):
            await ret

    def _fire_on_result(
        self, name: str, params: Dict[str, Any], result: Any, index: int
    ) -> List[Any]:
        """触发结果 hook，返回需要并入事件流的业务事件列表。

        hook 返回协程时不在此等待——原样放进返回列表，
        由调用方（同步路径就地跑完 / 异步路径 await）负责消费。
        """
        hook = self._result_hooks.get(name)
        if hook is None:
            return []
        ret = hook(name, params, result, index)
        if asyncio.iscoroutine(ret):
            return [ret]
        return _normalize_hook_events(ret, source=name)

    async def _await_result_events(
        self, name: str, params: Dict[str, Any], result: Any, index: int
    ) -> List[Any]:
        """异步路径下触发结果 hook 并解析出业务事件列表。"""
        hook = self._result_hooks.get(name)
        if hook is None:
            return []
        ret = hook(name, params, result, index)
        if asyncio.iscoroutine(ret):
            ret = await ret
        return _normalize_hook_events(ret, source=name)

    # ------------------------------------------------------------------
    # 查找
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[BaseTool]:
        """根据名称获取工具，不存在返回 None。"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """判断工具是否已注册。"""
        return name in self._tools

    def list_tools(self) -> List[BaseTool]:
        """返回所有已注册的工具列表。"""
        return list(self._tools.values())

    @property
    def tool_names(self) -> List[str]:
        """获取所有已注册工具的名称列表。"""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Schema 输出
    # ------------------------------------------------------------------

    def get_definitions(self) -> List[Dict[str, Any]]:
        """
        获取所有工具的 OpenAI tools 格式 JSON Schema。

        Returns::

            [{"type": "function", "function": {...}}, ...]
        """
        return [tool.to_schema() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def execute(
        self,
        name: str,
        params: Dict[str, Any],
        ctx: Optional["RunContext"] = None,
        index: int = 0,
    ) -> str:
        """
        同步执行一个工具调用。

        hook 触发由本方法统一负责（而非依赖 ``BaseTool.__call__``），因此
        ``index`` 能正确传递给 ``on_result_hook``——改造前同步路径把 index
        硬编码为 0，依赖 index 做顺序插槽的业务逻辑会静默丢数据。

        Args:
            name:   工具名称
            params: 工具调用参数
            ctx:    运行上下文（可选），提供时做预算检查并转发业务事件
            index:  该工具调用的全局序号

        Returns:
            str: 工具执行结果（字符串化）
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: 未找到工具 '{name}'，可用工具: {', '.join(self.tool_names)}"

        try:
            if ctx is not None:
                ctx.checkpoint()
            tool = _bind_ctx(tool, ctx)

            casted = tool.cast_params(params)
            errors = tool.validate_params(casted)
            if errors:
                return f"Error: 工具 {name} 参数校验失败: {'; '.join(errors)}" + _HINT

            self._fire_before_call_sync(name)

            result = tool.run(**casted)

            # 同步路径无法把业务事件并入事件流（没有 yield 通道），
            # 但仍需触发 hook——它可能有落库等副作用。
            # 需要消费业务事件请改用 async_stream_execute。
            for event in self._fire_on_result(name, casted, result, index):
                if asyncio.iscoroutine(event):
                    # 就地跑完，避免协程未被 await 而告警
                    _fire_sync(event)

            return self._stringify_result(result, name)
        except AgentRunError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("工具 %s 执行失败", name)
            return f"Error: 工具 {name} 执行失败: {e}" + _HINT

    async def async_stream_execute(
        self,
        tc_id: str,
        name: str,
        params: Dict[str, Any],
        step: int,
        index: int = 0,
        ctx: Optional["RunContext"] = None,
    ):
        """
        异步流式执行工具。

        - 每个 chunk 实时 yield AgentToolRunEvent（过程事件，零滞后）
        - hook 返回的业务事件直接并入事件流（顺序由框架保证）
        - 所有 chunk 结束后额外 yield 一次 AgentToolResultEvent（终态标记）

        Args:
            tc_id:  tool_call id。
            name:   工具名称。
            params: 工具调用参数。
            step:   当前推理步数。
            index:  该工具调用的全局序号（由 ``ctx.next_tool_indices()`` 分配）。
            ctx:    运行上下文；提供时会做预算检查并把业务事件送入 ``ctx.emit``。

        Yields:
            AgentToolRunEvent | AgentToolResultEvent | DomainEvent
        """
        tool = self._tools.get(name)
        if not tool:
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=params,
                step=step,
                result=f"Error: 未找到工具 '{name}'，可用工具: {', '.join(self.tool_names)}"
                + _HINT,
                index=index,
            )
            return

        try:
            if ctx is not None:
                ctx.checkpoint()

            # AgentTool 需要父上下文以派生子上下文（预算共享、取消传导）
            tool = _bind_ctx(tool, ctx)

            logger.debug(
                "[ToolRegistry] 工具 %s 参数 type=%s value=%r",
                name,
                type(params).__name__,
                params,
            )
            casted = tool.cast_params(params)

            # 执行前 hook
            await self._fire_before_call_async(name)

            # 流式执行（validate_params 由 async_stream_call 统一处理）
            last_chunk = None
            async for chunk in tool.async_stream_call(**params):
                yield AgentToolRunEvent(
                    id=tc_id, tool_name=name, step=step, content=chunk, index=index
                )
                last_chunk = chunk

            result = last_chunk if last_chunk is not None else ""

            # 触发结果 hook；hook 产出的业务事件由此并入事件流
            for event in await self._await_result_events(name, casted, result, index):
                yield event

            # 额外 yield ToolResultEvent 标记终态
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=casted,
                step=step,
                result=result,
                index=index,
            )

        except ValueError as e:
            # async_stream_call 内部参数校验失败会抛 ValueError
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=params,
                step=step,
                result=f"Error: {e}" + _HINT,
                index=index,
            )
        except AgentRunError:
            # 取消 / 预算超限属于可预期中止，交由循环层统一处理终态，
            # 不在此处降级为"工具执行失败"（那会让 LLM 收到误导性错误文本）
            raise
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("工具 %s 流式执行失败", name)
            yield AgentToolResultEvent(
                id=tc_id,
                tool_name=name,
                arguments=params,
                step=step,
                result=f"Error: 工具 {name} 执行失败: {e}" + _HINT,
                index=index,
            )

    async def async_execute(
        self,
        name: str,
        params: Dict[str, Any],
        ctx: Optional["RunContext"] = None,
        index: int = 0,
    ) -> str:
        """
        异步执行一个工具调用。

        与 :meth:`execute` 同理，hook 触发收归此处以正确传递 ``index``。

        Args:
            name:   工具名称
            params: 工具调用参数
            ctx:    运行上下文（可选）
            index:  该工具调用的全局序号

        Returns:
            str: 工具执行结果（字符串化）
        """
        tool = self._tools.get(name)
        if not tool:
            return f"Error: 未找到工具 '{name}'，可用工具: {', '.join(self.tool_names)}"

        try:
            if ctx is not None:
                ctx.checkpoint()
            tool = _bind_ctx(tool, ctx)

            casted = tool.cast_params(params)
            errors = tool.validate_params(casted)
            if errors:
                return f"Error: 工具 {name} 参数校验失败: {'; '.join(errors)}" + _HINT

            await self._fire_before_call_async(name)

            result = await tool.async_run(**casted)

            # 非流式路径没有 yield 通道，业务事件无处可去；
            # 仍触发 hook 以保留其副作用（落库等）。
            # 需要消费业务事件请改用 async_stream_execute。
            await self._await_result_events(name, casted, result, index)

            return self._stringify_result(result, name)
        except AgentRunError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("工具 %s 执行失败", name)
            return f"Error: 工具 {name} 执行失败: {e}" + _HINT

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _stringify_result(result: Any, tool_name: str) -> str:
        """将工具执行结果转换为字符串。"""
        if isinstance(result, str):
            # 如果结果以 Error 开头，追加提示
            if result.startswith("Error"):
                return result + _HINT
            return result
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(result)

    # ------------------------------------------------------------------
    # 魔术方法
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        tools = ", ".join(self._tools.keys())
        return f"<ToolRegistry tools=[{tools}]>"
