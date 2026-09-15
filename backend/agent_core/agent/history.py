"""OpenAI 格式消息构造器 —— 框架内唯一的一份。

这些函数此前有两份实现：``loop.py`` 内的 ``_assistant_message`` /
``_tool_message``（供 ReAct 使用），以及 ``SystemPromptBuilder`` 上的
``add_user_message`` / ``add_assistant_message`` / ``add_tool_result``
（供同步范式使用）。

两份实现意味着消息格式可能悄悄分叉，且"拼装 history"本不属于
system prompt builder 的职责（它只负责 system prompt）。因此统一收敛到此处：
纯函数，只负责构造单条消息，不持有状态、不做追加——追加由 ``memory``
负责。

.. note::
   ``assistant_message`` 必须保留 ``tool_calls`` 字段，否则后续 ``tool``
   消息将失去配对依据，OpenAI 兼容 API 会直接返回 400。
"""

from __future__ import annotations

from typing import Any, Dict

from ..llm.base import LLMResponse

Message = Dict[str, Any]


def user_message(content: str) -> Message:
    """构造 user 消息。"""
    return {"role": "user", "content": content}


def assistant_message(response: LLMResponse) -> Message:
    """把 LLMResponse 转为 assistant 消息（含 tool_calls）。"""
    msg: Message = {"role": "assistant", "content": response.content or ""}
    if response.tool_calls:
        msg["tool_calls"] = [tc.to_openai_tool_call() for tc in response.tool_calls]
    return msg


def tool_message(tool_call_id: str, name: str, result: Any) -> Message:
    """构造 tool 结果消息（``tool_call_id`` 用于与 assistant 配对）。"""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": result if isinstance(result, (str, list)) else str(result),
    }


__all__ = [
    "Message",
    "assistant_message",
    "tool_message",
    "user_message",
]
