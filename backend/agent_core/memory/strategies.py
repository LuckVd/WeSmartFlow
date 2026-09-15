"""记忆策略实现。

三种：

- :class:`FullMemory`    — 不裁剪，保留全部（框架默认值，保证向后兼容）
- :class:`WindowMemory`  — 滑动窗口，按轮次边界安全裁剪
- :class:`SummaryMemory` — 滚动摘要：窗口外的旧消息用 LLM 增量压缩成一段摘要

三者共同遵守 :mod:`agent_core.memory.base` 声明的约束：``render()`` 只出
history（绝不含 ``role="system"``），token 预算由装配层下发而非自行决定。

:class:`SummaryMemory` 的策略源自业务侧已验证的实现（阈值触发防 N+1、
保留最近窗口原文、``summarized_until`` 增量游标），此处上提为框架能力，
使任何长对话 Agent 都能直接复用。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from .base import BaseMemory, Message, estimate_tokens, safe_cut

if TYPE_CHECKING:
    from ..llm.base import BaseLLM
    from ..runtime.run_context import RunContext

logger = logging.getLogger(__name__)


def _fit_budget(
    messages: List[Message],
    window: int,
    token_budget: Optional[int],
) -> List[Message]:
    """按窗口裁剪，并在超出 token 预算时继续收缩。

    收缩起点取 ``min(window, 实际条数)``——若从 ``window`` 起步，当消息数
    远小于 window 时，首次折半后条数不变会误判为"无法继续收缩"而提前退出，
    导致预算完全失效。

    收缩下界为 2 条：再少模型就看不到任何有效上下文了，此时宁可略微超出
    预算也要保住最后一轮问答。
    """
    rendered = safe_cut(messages, window)

    if not token_budget or token_budget <= 0:
        return rendered

    keep = min(window, len(rendered))
    while estimate_tokens(rendered) > token_budget and keep > 2:
        keep = max(2, keep // 2)
        shrunk = safe_cut(messages, keep)
        if len(shrunk) >= len(rendered):
            break  # 已无法继续收缩（轮次边界对齐所限）
        rendered = shrunk

    return rendered


class FullMemory(BaseMemory):
    """保留全部消息，不做任何裁剪。

    框架默认值。``token_budget`` 会被**刻意忽略**——本类的语义就是"不裁剪"，
    需要按预算收缩请换用 :class:`WindowMemory` 或 :class:`SummaryMemory`。
    """

    def __init__(self, messages: Optional[List[Message]] = None):
        self._messages: List[Message] = list(messages or [])

    def append(self, message: Message) -> None:
        self._messages.append(message)

    async def render(
        self, ctx: "RunContext", token_budget: Optional[int] = None
    ) -> List[Message]:
        return list(self._messages)

    def all_messages(self) -> List[Message]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return f"<FullMemory messages={len(self._messages)}>"


class WindowMemory(BaseMemory):
    """滑动窗口记忆：只保留最近 N 条（按轮次边界对齐）。

    超出装配层下发的 ``token_budget`` 时，在 window 基础上继续折半收缩。

    .. note::
       此前本类有 ``max_tokens`` 构造参数，语义是"单次请求 history 上限"，
       但它只统计 history、看不到 system 与 tool schema，因此预算形同虚设
       （加上几千 token 的 system 段后照样溢出）。现改由装配层扣除固定开销
       后下发真实可用预算。

    Attributes:
        window: 期望保留的消息条数下界。
    """

    def __init__(
        self,
        window: int = 30,
        messages: Optional[List[Message]] = None,
    ):
        self.window = max(2, window)
        self._messages: List[Message] = list(messages or [])

    def append(self, message: Message) -> None:
        self._messages.append(message)

    async def render(
        self, ctx: "RunContext", token_budget: Optional[int] = None
    ) -> List[Message]:
        return _fit_budget(self._messages, self.window, token_budget)

    def all_messages(self) -> List[Message]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return f"<WindowMemory window={self.window} messages={len(self._messages)}>"


_SUMMARY_SYSTEM = (
    "你是对话摘要助手。请把【既有摘要】与【新增对话】整合为一段连贯的摘要，"
    "保留对后续对话有价值的信息：用户的目标、已达成的结论、"
    "用户表现出的偏好或困难点、待办或悬而未决的问题。"
    "去除寒暄与冗余，控制在 {limit} 字以内，只输出摘要正文。"
)


class SummaryMemory(BaseMemory):
    """滚动摘要记忆：窗口外的旧消息增量压缩为一段摘要。

    ``render()`` 只返回**最近 window 条原文**；摘要文本通过 :attr:`summary`
    属性暴露，由装配层合并进 system 段。

    .. note::
       此前本类的 ``render()`` 会额外返回一条 ``role="system"`` 的摘要消息，
       与装配层产生的 system 叠加成两条——部分模型原生 API 直接拒绝，且
       "往 system 段写内容"本不属于记忆的职责。现改为属性暴露：记忆只管
       "记住了什么"，呈现方式交给装配层。

    触发策略（防止每轮都调 LLM）：仅当总消息数超过 ``trigger``、
    且自上次摘要以来又积累了新的"窗口外旧消息"时，才执行一次压缩。
    压缩失败静默跳过，下一轮重试——摘要是增强而非必需。

    Attributes:
        llm:           用于压缩的 LLM（建议用小模型以降本）。
        window:        保留原文的最近消息条数。
        trigger:       总消息数达到此值才开始摘要。
        summary_limit: 摘要字数上限。
    """

    def __init__(
        self,
        llm: "BaseLLM",
        window: int = 20,
        trigger: int = 40,
        summary_limit: int = 300,
        summary: str = "",
        summarized_until: int = 0,
        messages: Optional[List[Message]] = None,
    ):
        self.llm = llm
        self.window = max(2, window)
        self.trigger = max(trigger, self.window * 2)
        self.summary_limit = summary_limit

        self._summary = summary
        self._summarized_until = summarized_until
        self._messages: List[Message] = list(messages or [])

    # ------------------------------------------------------------------
    # 状态存取（便于业务侧持久化到会话 workspace）
    # ------------------------------------------------------------------

    @property
    def summary(self) -> str:
        return self._summary

    @property
    def summarized_until(self) -> int:
        return self._summarized_until

    def state(self) -> dict:
        """导出可持久化的摘要状态。"""
        return {
            "summary": self._summary,
            "summarized_until": self._summarized_until,
        }

    # ------------------------------------------------------------------
    # BaseMemory
    # ------------------------------------------------------------------

    def append(self, message: Message) -> None:
        self._messages.append(message)

    async def render(
        self, ctx: "RunContext", token_budget: Optional[int] = None
    ) -> List[Message]:
        """产出最近窗口内的原文。

        摘要不在此处注入——它通过 :attr:`summary` 属性暴露，由装配层合并
        进 system 段（见类文档）。
        """
        await self._maybe_compress(ctx)
        return _fit_budget(self._messages, self.window, token_budget)

    def all_messages(self) -> List[Message]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()
        self._summary = ""
        self._summarized_until = 0

    # ------------------------------------------------------------------
    # 压缩
    # ------------------------------------------------------------------

    async def _maybe_compress(self, ctx: "RunContext") -> None:
        """按需把窗口外的旧消息追加压缩进既有摘要。"""
        total = len(self._messages)
        if total < self.trigger:
            return

        cutoff = total - self.window
        if cutoff <= self._summarized_until:
            return  # 没有新的可摘要内容

        pending = self._messages[self._summarized_until : cutoff]
        convo = self._format(pending)
        if not convo.strip():
            self._summarized_until = cutoff
            return

        try:
            with ctx.tracer.span("memory.summarize", "llm", messages=len(pending)):
                response = await self.llm.async_think(
                    [
                        {
                            "role": "system",
                            "content": _SUMMARY_SYSTEM.format(limit=self.summary_limit),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"## 既有摘要\n{self._summary or '（无）'}\n\n"
                                f"## 新增对话\n{convo}"
                            ),
                        },
                    ],
                    config={"temperature": 0.3},
                )
        except Exception:  # pylint: disable=broad-except
            logger.warning("滚动摘要生成异常，跳过本轮", exc_info=True)
            return

        if response.is_error or not (response.content or "").strip():
            logger.warning("滚动摘要生成失败，跳过本轮")
            return

        ctx.budget.add_tokens((response.usage or {}).get("total_tokens", 0))

        self._summary = response.content.strip()
        self._summarized_until = cutoff
        logger.info(
            "[Memory] 滚动摘要更新 cutoff=%d summary=%dch", cutoff, len(self._summary)
        )

    @staticmethod
    def _format(messages: List[Message]) -> str:
        """把消息列表格式化为 ``role: content`` 文本供摘要 LLM 阅读。"""
        lines: List[str] = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "tool":
                continue  # 工具原始输出通常冗长且无摘要价值
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            content = str(content).strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return (
            f"<SummaryMemory window={self.window} messages={len(self._messages)} "
            f"summarized_until={self._summarized_until}>"
        )


__all__ = ["FullMemory", "SummaryMemory", "WindowMemory"]
