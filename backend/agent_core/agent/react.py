"""ReAct Agent 实现。

范式：Reason + Act
每一步：LLM 推理（可能包含 Thought）→ 若有工具调用则执行 → 将结果追加 history
→ 继续推理，直到 LLM 不再调用工具（输出最终答案）或触发预算上限。

**实现说明**：本类不再自己写循环。真正的循环在
:func:`~agent_core.agent.loop.tool_calling_loop` 中只有一份（流式实现），
``async_stream`` 直接返回它，``async_run`` / ``run`` 通过消费它并只取终态
来实现。这样三个入口的行为必然一致——改造前三份独立循环已经出现工具
``index`` 传递不一致的静默 bug。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..context.builder import SystemPromptBuilder
from ..context.static import StaticPromptBuilder
from ..llm.base import BaseLLM
from ..memory.base import Message
from ..runtime.run_context import RunContext
from ..tool.registry import ToolRegistry
from .base import AgentResult, BaseAgent
from .events import (
    AgentStreamEvent,
)
from .loop import tool_calling_loop

logger = logging.getLogger(__name__)

# ReActAgent 默认 system prompt
_DEFAULT_REACT_SYSTEM_PROMPT = """你是一个智能助手，能够借助工具逐步解决复杂问题。

## 工作流程

每一步你必须先思考，再决定行动：

Thought: <分析当前情况，明确已知信息、缺少什么、下一步应该做什么>

然后：
- 如果需要更多信息 → 调用合适的工具
- 如果信息已经足够 → 直接给出完整、准确的最终答案

## 规则

1. 每次调用工具前必须先写 Thought，不得省略。
2. 工具结果返回后，继续写 Thought 分析结果，再决定下一步。
3. 不要重复调用已经得到结果的工具。
4. 最终答案要直接回答用户问题，简洁清晰，不要包含 Thought 标记。"""


class ReActAgent(BaseAgent):
    """ReAct 范式 Agent。

    ``prompt_builder`` 可选，不传时自动使用内置的 ReAct 专用 system prompt。

    子类可覆写 ``_async_on_tool_result()`` 在每次工具返回后插入额外逻辑。
    """

    def __init__(
        self,
        llm: BaseLLM,
        prompt_builder: Optional[SystemPromptBuilder] = None,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 20,
        llm_config: Optional[Dict[str, Any]] = None,
        memory_factory: Optional[Any] = None,
        context_window: Optional[int] = None,
    ):
        """
        Args:
            llm:             LLM 实例。
            prompt_builder: system prompt 构建器。为 None 时使用内置 ReAct 专用 prompt。
            tool_registry:   工具注册表，为 None 时表示无工具。
            max_steps:       推理循环最大步数（未显式传入 ctx 时作为默认预算）。
            llm_config:      每次调用 LLM 时透传的额外参数（temperature 等）。
            memory_factory:  记忆工厂，签名 ``() -> BaseMemory``。
                             默认 :class:`FullMemory`（不裁剪）。
                             长对话场景可传 ``lambda: WindowMemory(30)`` 等。
            context_window:  模型上下文窗口（token）。传入后装配层会扣除
                             system 与 tool schema 的开销，把剩余预算下发给
                             记忆用于裁剪。为 None 时从
                             ``ctx.settings.llm.context_window`` 取值；
                             仍为 0 则不做预算控制。
        """
        if prompt_builder is None:
            prompt_builder = StaticPromptBuilder(_DEFAULT_REACT_SYSTEM_PROMPT)
        super().__init__(
            llm=llm,
            prompt_builder=prompt_builder,
            tool_registry=tool_registry,
            max_steps=max_steps,
            llm_config=llm_config,
            memory_factory=memory_factory,
        )
        self.context_window = context_window

    # ------------------------------------------------------------------
    # 流式推理 —— 唯一的真实实现
    # ------------------------------------------------------------------

    async def async_stream(
        self,
        user_input: str,
        ctx: Optional[RunContext] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """异步流式推理，每个关键节点 yield 一个事件。

        事件类型（按发生顺序）：
        - AgentThinkChunkEvent    — LLM 思考文本的实时分片
        - AgentToolCallChunkEvent — tool_call 参数分片
        - AgentThinkEvent         — 本轮思考完成汇总
        - AgentToolCallEvent      — 即将调用某个工具
        - AgentToolRunEvent       — 工具执行过程
        - DomainEvent             — 工具 hook 产出的业务事件
        - AgentToolResultEvent    — 工具执行完毕
        - AgentFinalEvent         — 最终回复（推理结束）

        Args:
            user_input:   用户输入文本。
            ctx:          运行上下文。为 None 时按 ``max_steps`` 构造默认上下文。
            **kwargs:     透传给 prompt_builder；其中 ``chat_history``
                          会被预置进对话记忆（见 :meth:`_prepare_memory`）。

        Yields:
            AgentStreamEvent
        """
        ctx = self._prepare_context(ctx)
        memory = self._prepare_memory(ctx, **kwargs)
        memory.append({"role": "user", "content": user_input})
        # 挂回 ctx（per-run 对象，并发安全），供 _async_run 回填 history
        ctx.memory = memory

        async for event in tool_calling_loop(
            llm=self.llm,
            tools=self.tool_registry,
            ctx=ctx,
            memory=memory,
            system_prompt=self._system_prompt_fn(user_input=user_input, **kwargs),
            llm_config=self.llm_config or None,
            on_tool_result=self._make_tool_result_callback(**kwargs),
            context_window=self._resolve_context_window(ctx),
        ):
            yield event

    # ------------------------------------------------------------------
    # 非流式入口
    # ------------------------------------------------------------------
    #
    # 复用 BaseAgent._async_run（消费 async_stream 取终态），仅补上
    # history 字段——这样循环调用代码始终只有一份。

    async def _async_run(
        self, user_input: str, ctx: Optional[RunContext] = None, **kwargs: Any
    ) -> AgentResult:
        """异步推理：消费 ``async_stream`` 并补齐 history。"""
        ctx = self._prepare_context(ctx)
        result = await super()._async_run(user_input, ctx, **kwargs)
        if ctx.memory is not None:
            result.history = ctx.memory.all_messages()
        return result

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _resolve_context_window(self, ctx: RunContext) -> Optional[int]:
        """确定本次运行的上下文窗口。

        优先级：构造参数 > ``ctx.settings.llm.context_window`` > 不限制。

        返回 None 表示不做预算控制——此时装配层退化为"全量塞入"，
        与未接入预算前的行为一致。
        """
        if self.context_window:
            return self.context_window
        window = getattr(ctx.settings.llm, "context_window", 0)
        return window or None

    def _make_tool_result_callback(self, **kwargs: Any):
        """把子类的 ``_async_on_tool_result`` 适配为循环所需的回调。"""

        async def _callback(
            tool_name: str,
            arguments: Dict[str, Any],
            result: str,
            history: List[Message],
        ) -> None:
            await self._async_on_tool_result(
                tool_name, arguments, result, history, **kwargs
            )

        return _callback

    # ------------------------------------------------------------------
    # 扩展钩子
    # ------------------------------------------------------------------

    def _on_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: str,
        history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """每次工具执行完成后的同步钩子，子类可覆写。

        Args:
            tool_name:  工具名称。
            arguments:  工具调用参数。
            result:     工具执行结果字符串。
            history:    当前 history（已包含本次 tool result）。
        """

    async def _async_on_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: str,
        history: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> None:
        """每次工具执行完成后的异步钩子，子类可覆写。

        默认调用同步版 ``_on_tool_result()``。
        """
        self._on_tool_result(tool_name, arguments, result, history, **kwargs)


__all__ = ["ReActAgent"]
