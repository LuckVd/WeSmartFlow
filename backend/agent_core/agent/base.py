"""Agent 抽象基类。

只定义骨架：依赖注入 + 运行入口 + 通用工具方法。
具体的推理范式由子类实现 ``async_stream``。

三个入口的关系::

    async_stream()   ← 子类实现的唯一真实循环（流式是超集）
        ↑
    async_run()      ← 消费 async_stream，只取终态
        ↑
    run()            ← 在新事件循环中运行 async_run
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from ..context.builder import SystemPromptBuilder
from ..llm.base import BaseLLM, LLMResponse
from ..memory.base import BaseMemory, normalize_history
from ..memory.strategies import FullMemory
from ..runtime.budget import Budget
from ..runtime.run_context import RunContext, new_context
from ..tool.registry import ToolRegistry

# 事件类型独立维护在 .events 中，本模块仅按需引入用作类型注解 / 默认值。
# 不在此处对外 re-export，业务方应统一从 ``agent_core.agent`` 包出口或
# ``agent_core.agent.events`` 导入。
from .events import AgentFinishReason, AgentStreamEvent

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================


@dataclass
class AgentResult:
    """Agent 完整运行结果。"""

    finish_reason: AgentFinishReason
    final_response: Optional[LLMResponse]
    history: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def output(self) -> str:
        """最终输出文本，出错时返回错误信息。"""
        if self.error:
            return f"[Error] {self.error}"
        return self.final_response.content if self.final_response else ""

    @property
    def ok(self) -> bool:
        """是否正常完成（未出错、未被取消、未超预算）。"""
        return self.finish_reason is AgentFinishReason.STOP and not self.error


# ============================================================
# BaseAgent
# ============================================================


class BaseAgent(ABC):
    """Agent 抽象基类。

    职责：
    - 持有核心依赖（llm / prompt_builder / tool_registry / memory_factory）
    - 提供统一的 ``run`` / ``async_run`` / ``async_stream`` 入口
    - 提供上下文与记忆的装配辅助（``_prepare_context`` / ``_prepare_memory``）

    子类必须实现 ``async_stream()``：流式推理循环。
    ``async_run()`` 与 ``run()`` 默认基于它派生，通常无需覆写。
    """

    def __init__(
        self,
        llm: BaseLLM,
        prompt_builder: SystemPromptBuilder,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 20,
        llm_config: Optional[Dict[str, Any]] = None,
        memory_factory: Optional[Callable[[], BaseMemory]] = None,
    ):
        """
        Args:
            llm:             LLM 实例。
            prompt_builder: system prompt 构建器实例。
            tool_registry:   工具注册表，为 None 时表示无工具。
            max_steps:       推理循环最大步数上限（未传 ctx 时作为默认预算）。
            llm_config:      每次调用 LLM 时透传的额外参数（temperature 等）。
            memory_factory:  记忆工厂，默认 :class:`FullMemory`（不裁剪）。
        """
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_steps = max_steps
        self.llm_config = llm_config or {}
        self.memory_factory: Callable[[], BaseMemory] = memory_factory or FullMemory

    # ------------------------------------------------------------------
    # 子类实现点
    # ------------------------------------------------------------------

    async def async_stream(
        self,
        user_input: str,
        ctx: Optional[RunContext] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """流式推理循环 —— 子类**必须**实现的唯一入口。

        ``async_run`` / ``run`` 都基于它派生，因此三个入口的行为天然一致。
        不提供同步实现点：流式是超集，任何范式都应以流式表达，否则
        中间过程事件会丢失。

        Args:
            user_input: 用户输入文本。
            ctx:        运行上下文，为 None 时使用默认预算构造。
            **kwargs:   子类自定义的额外参数。

        Yields:
            AgentStreamEvent
        """
        raise NotImplementedError(f"{self.__class__.__name__} 必须实现 async_stream()")
        # pylint: disable=unreachable
        yield  # 使本方法成为 async generator，保证子类签名一致

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    async def async_run(
        self, user_input: str, ctx: Optional[RunContext] = None, **kwargs: Any
    ) -> AgentResult:
        """异步运行 Agent，返回汇总结果。

        Args:
            user_input: 用户输入文本。
            ctx:        运行上下文。
            **kwargs:   透传给子类的额外参数。

        Returns:
            AgentResult
        """
        try:
            return await self._async_run(user_input, ctx, **kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Agent 异步运行异常")
            return AgentResult(
                finish_reason=AgentFinishReason.ERROR,
                final_response=None,
                error=str(e),
            )

    def run(
        self, user_input: str, ctx: Optional[RunContext] = None, **kwargs: Any
    ) -> AgentResult:
        """同步运行 Agent。

        Args:
            user_input: 用户输入文本。
            ctx:        运行上下文。
            **kwargs:   透传给子类的额外参数。

        Returns:
            AgentResult
        """
        try:
            return self._run(user_input, ctx, **kwargs)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Agent 运行异常")
            return AgentResult(
                finish_reason=AgentFinishReason.ERROR,
                final_response=None,
                error=str(e),
            )

    # ------------------------------------------------------------------
    # 默认派生实现（子类通常无需覆写）
    # ------------------------------------------------------------------

    async def _async_run(
        self, user_input: str, ctx: Optional[RunContext] = None, **kwargs: Any
    ) -> AgentResult:
        """消费 ``async_stream`` 并汇总为 AgentResult。"""
        from .events import AgentFinalEvent  # 局部导入避免顶层循环

        final = None
        async for event in self.async_stream(user_input, ctx, **kwargs):
            if isinstance(event, AgentFinalEvent):
                final = event

        if final is None:
            return AgentResult(
                finish_reason=AgentFinishReason.ERROR,
                final_response=None,
                error="推理循环未产出终态事件",
            )

        return AgentResult(
            finish_reason=final.finish_reason,
            final_response=(
                LLMResponse(content=final.content) if final.content else None
            ),
            error=getattr(final, "detail", "") or None,
        )

    def _run(
        self, user_input: str, ctx: Optional[RunContext] = None, **kwargs: Any
    ) -> AgentResult:
        """在新事件循环中运行异步实现。"""
        ctx_ready = self._prepare_context(ctx)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._async_run(user_input, ctx_ready, **kwargs))

        raise RuntimeError(
            f"{self.__class__.__name__}.run() 不能在已运行的事件循环中调用，"
            "请改用 await agent.async_run(...) 或 agent.async_stream(...)"
        )

    # ------------------------------------------------------------------
    # 上下文与记忆装配
    # ------------------------------------------------------------------

    def _prepare_context(self, ctx: Optional[RunContext]) -> RunContext:
        """确保有可用的 RunContext。

        未传入时按 ``self.max_steps`` 构造默认上下文——这保证了改造前不带
        ctx 的调用方行为不变（默认无取消、无成本上限、零开销 tracer）。
        """
        if ctx is not None:
            return ctx
        return new_context(budget=Budget(max_steps=self.max_steps))

    def _prepare_memory(self, ctx: RunContext, **kwargs: Any) -> BaseMemory:
        """取得本次运行的记忆实例，并预置历史消息。

        优先使用 ``ctx.memory``（调用方显式指定，可跨轮次复用其摘要状态），
        否则用 ``memory_factory`` 新建。

        ``kwargs["chat_history"]`` 中的历史消息会被规整并预置进新建的记忆——
        这是多轮对话生效的关键：history 只从 ``memory.render()`` 取。

        历史消息支持字典与业务侧的 Pydantic 模型（如 ``MessageSchema``）两种形态。
        """
        if ctx.memory is not None:
            return ctx.memory

        memory = self.memory_factory()

        history = normalize_history(kwargs.get("chat_history"))
        if history:
            for msg in history:
                memory.append(msg)
            logger.debug("[Agent] 预置 %d 条历史消息进记忆", len(history))

        return memory

    def _system_prompt_fn(self, user_input: str = "", **kwargs: Any):
        """构造循环所需的 system prompt 回调。

        每步调用一次，因此支持动态内容。若 prompt_builder 实现了
        ``build_system_prompt_async``（支持 ContextProvider 注入），优先走
        异步路径——这样 provider 可以做 IO（查库、检索）。
        """
        builder = self.prompt_builder
        async_build = getattr(builder, "build_system_prompt_async", None)

        async def _build(ctx: RunContext) -> Optional[str]:
            try:
                if callable(async_build):
                    return await async_build(ctx, user_input, **kwargs)
                return builder.build_system_prompt(**kwargs)
            except Exception:  # pylint: disable=broad-except
                logger.exception("构建 system prompt 失败，本步降级为无 system 消息")
                return None

        return _build

    # ------------------------------------------------------------------
    # 通用工具方法（子类可直接调用）
    # ------------------------------------------------------------------

    def think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
    ) -> LLMResponse:
        """同步调用 LLM 推理，返回 LLMResponse。

        Args:
            messages:    传给 LLM 的完整消息列表（= system + history + 可选 user）。
            tools:       工具 schema 列表，为 None 时不传工具。
            tool_choice: 工具选择策略，如 "auto"、"none" 或指定函数。

        Returns:
            LLMResponse
        """
        return self.llm.think(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            config=self.llm_config or None,
        )

    async def async_think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
    ) -> LLMResponse:
        """异步调用 LLM 推理，返回 LLMResponse。

        Args:
            messages:    传给 LLM 的完整消息列表。
            tools:       工具 schema 列表，为 None 时不传工具。
            tool_choice: 工具选择策略。

        Returns:
            LLMResponse
        """
        return await self.llm.async_think(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            config=self.llm_config or None,
        )

    # ------------------------------------------------------------------
    # Agent-as-Tool
    # ------------------------------------------------------------------

    def as_tool(
        self,
        name: str,
        description: str,
        run_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """将当前 Agent 包装为一个 AgentTool，供父 Agent 作为工具调用。

        这是实现多 Agent 层级协作的核心方法：任意 Agent 都可以通过
        ``as_tool()`` 变成一个工具，注册到父 Agent 的 ToolRegistry 中。

        子 Agent 会自动获得父级派生的子上下文（``ctx.child()``），因此
        **预算共享**（子消耗计入父）、**取消信号传导**、**事件出口共用**。

        用法示例::

            sub_agent = ReActAgent(llm=llm, tool_registry=sub_tools)
            tool = sub_agent.as_tool(
                name="researcher",
                description="负责信息检索的子 Agent",
            )
            parent = ReActAgent(llm=llm, tool_registry=ToolRegistry([tool]))

        Args:
            name:        工具名称，供父 Agent 在 Function Calling 中识别。
            description: 工具描述，告知父 Agent 何时调用、输入什么。
            run_kwargs:  每次调用子 Agent 时透传的额外关键字参数。

        Returns:
            AgentTool 实例。
        """
        from ..tool.agent_tool import AgentTool

        return AgentTool(
            agent=self,
            name=name,
            description=description,
            run_kwargs=run_kwargs,
        )

    # ------------------------------------------------------------------
    # 魔术方法
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"llm={self.llm.model_name!r} "
            f"tools={self.tool_registry.tool_names}>"
        )


__all__ = ["AgentResult", "BaseAgent"]
