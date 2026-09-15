"""装配 —— 上下文工程的核心动作。

**本模块是框架内唯一产生最终 messages 的地方。**

为什么需要一个明确的拥有者
--------------------------

改造前 messages 由调用方就地拼接（``[system] + memory.render()``），没有
任何一方拥有"成品"，于是出现两类无人负责的缺陷：

1. :class:`SummaryMemory` 在 ``render()`` 里额外返回一条 system 摘要，
   与拼接方产生的 system 叠加成**两条 system**——部分模型原生 API 直接拒绝。
2. ``WindowMemory.max_tokens`` 只统计 history，看不到 system 与 tool schema。
   预算设 8000、history 裁到 7900 就放行，加上几千 token 的 system 段后
   照样溢出。**约束针对成品，却由半成品的生产者施加。**

把装配收敛到一处后，两者都变成可强制的规则：system 只有这里能产生，
预算在这里扣除固定开销后下发。

上下文的四个来源
----------------

=========  ==========================================  ==================
来源        提供方                                       进入位置
=========  ==========================================  ==================
指令        ``SystemPromptBuilder``（含 provider 片段）        system 段
知识        ``ContextProvider``（含长期记忆读取）         system 段
历史        ``BaseMemory.render()``                     history 段
工具        ``ToolRegistry.get_definitions()``          tools 参数（计入预算）
=========  ==========================================  ==================
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..memory.base import (
    Message,
    contains_system,
    estimate_tokens,
    estimate_tools,
)
from ..runtime.budget import BudgetExceeded

if TYPE_CHECKING:
    from ..memory.base import BaseMemory
    from ..runtime.run_context import RunContext

logger = logging.getLogger(__name__)

#: 为模型输出预留的 token 数。上下文窗口需同时容纳输入与输出，
#: 若把整个窗口都分给输入，模型将没有空间生成回复。
DEFAULT_OUTPUT_RESERVE = 4096

#: 兼容旧导出的建议值；不再允许以该值为由突破上下文窗口。
MIN_HISTORY_BUDGET = 512

#: 记忆摘要在 system 段中的小标题。
SUMMARY_HEADING = "## 既往对话摘要"


async def assemble(
    system_prompt: str,
    memory: "BaseMemory",
    ctx: "RunContext",
    *,
    tool_schemas: Optional[List[Dict[str, Any]]] = None,
    context_window: Optional[int] = None,
    output_reserve: int = DEFAULT_OUTPUT_RESERVE,
) -> List[Message]:
    """把 system 文本与 history 装配为最终 messages。

    Args:
        system_prompt:  已渲染好的 system 文本（由 SystemPromptBuilder 产出）。
        memory:         对话记忆，提供 history 段。
        ctx:            运行上下文。
        tool_schemas:   本次随请求发送的工具定义。**计入 token 预算**——
                        工具定义每次请求都完整发送，是常被忽略的固定开销。
        context_window: 模型上下文窗口。``None`` 表示不做预算控制。
        output_reserve: 为模型输出预留的 token 数。

    Returns:
        ``[system] + history``，其中 system **最多一条**。
    """
    # 先按已有摘要分配；render 生成新摘要后再检查最终成品。
    token_budget = _history_budget(
        system_prompt=_merge_summary(system_prompt, memory),
        tool_schemas=tool_schemas,
        context_window=context_window,
        output_reserve=output_reserve,
    )

    history = await memory.render(ctx, token_budget)

    # render() 可能刚刚生成/更新了摘要，因此在其之后再取一次。
    # 摘要是"背景信息"而非"用户发言"，语义上属于 system；但产生 system
    # 消息的权力只在本函数——所以记忆通过属性暴露文本，由这里合并。
    system_text = _merge_summary(system_prompt, memory)

    # 约束 1：system 段只能由本模块产生。
    # 记忆若越界返回 system，与下面拼入的 system 会叠成两条。这里主动
    # 剔除并告警，而非静默放过——静默会让问题在模型侧以 400 的形式浮现。
    if contains_system(history):
        logger.error(
            "%s.render() 返回了 role='system' 消息，已剔除。"
            "记忆只应产出 history，system 段由 context.assemble 负责。",
            type(memory).__name__,
        )
        history = [m for m in history if m.get("role") != "system"]

    messages: List[Message] = []
    if system_text and system_text.strip():
        messages.append({"role": "system", "content": system_text})
    messages.extend(history)
    if context_window is not None:
        used = measure(messages, tool_schemas)
        if used + output_reserve > context_window:
            raise BudgetExceeded(
                "context_window",
                f"上下文估算 {used} tokens + 输出预留 {output_reserve}，"
                f"超过窗口 {context_window}；请缩短输入或工具结果",
            )
    return messages


def _merge_summary(system_prompt: str, memory: "BaseMemory") -> str:
    """把记忆的压缩摘要合并进 system 文本。

    通过鸭子类型探测 ``summary`` 属性，避免装配层依赖具体记忆策略。
    """
    summary = getattr(memory, "summary", "") or ""
    summary = summary.strip() if isinstance(summary, str) else ""
    if not summary:
        return system_prompt

    section = f"{SUMMARY_HEADING}\n\n{summary}"
    return f"{system_prompt}\n\n---\n\n{section}" if system_prompt.strip() else section


def _history_budget(
    *,
    system_prompt: str,
    tool_schemas: Optional[List[Dict[str, Any]]],
    context_window: Optional[int],
    output_reserve: int,
) -> Optional[int]:
    """计算下发给 memory 的 history token 预算。

    ``context_window - system - tools - 输出预留``。
    返回 ``None`` 表示不限制，固定开销占满窗口则中止。
    """
    if context_window is None:
        return None

    fixed = estimate_tokens([{"role": "system", "content": system_prompt}])
    fixed += estimate_tools(tool_schemas)

    budget = context_window - fixed - output_reserve
    if budget <= 0:
        raise BudgetExceeded(
            "context_window", "system、工具定义与输出预留已占满上下文窗口"
        )
    return budget


def measure(
    messages: List[Message],
    tool_schemas: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """粗估一次请求的输入 token 总量（含 system 与 tool schema）。

    memory 负责裁剪，assemble 使用该估算对最终请求做预算检查。
    """
    return estimate_tokens(messages) + estimate_tools(tool_schemas)


__all__ = [
    "DEFAULT_OUTPUT_RESERVE",
    "MIN_HISTORY_BUDGET",
    "SUMMARY_HEADING",
    "assemble",
    "measure",
]
