"""对话记忆抽象（记忆工程 · 短期）。

记忆负责两件事：

1. 累积对话消息（``append``）
2. 在**给定预算内**产出送给 LLM 的 history（``render``）

第 2 点是关键——此前 ReAct 循环每步都把**全部** history 塞进 messages，
多步推理时线性膨胀，步数一多必然撞 context limit。记忆层把"如何裁剪/压缩"
变成可替换策略。

职责边界（三条硬约束）
----------------------

1. **``render()`` 返回值绝不含 ``role="system"``。** system 段只能由
   :mod:`agent_core.context.assemble` 产生；记忆只出 history。
   违反会导致一次请求出现两条 system——部分模型原生 API 直接拒绝。
2. **记忆不决定自己能占多少 token。** 只有装配层知道 system 与 tool
   schema 占了多少，因此预算由 ``render(ctx, token_budget=...)`` 下发。
3. **压缩产物（摘要）以属性暴露**（``summary``），由装配层决定如何呈现，
   记忆不自行往消息流里注入。

.. note::
   本包只管**短期**记忆（本次会话的对话历史）。长期记忆（用户画像、
   知识图谱）属于业务领域，应通过
   :class:`~agent_core.context.provider.ContextProvider` 注入，不要混入此处。

**截断安全**：OpenAI 兼容 API 要求 ``assistant(tool_calls)`` 与其后的
``tool`` 消息严格配对。裁剪时若切断配对会直接收到 400。因此本模块提供
:func:`safe_cut` 统一处理边界，所有实现都必须使用它。
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

if TYPE_CHECKING:
    from ..runtime.run_context import RunContext

Message = Dict[str, Any]


@runtime_checkable
class BaseMemory(Protocol):
    """对话记忆协议。"""

    def append(self, message: Message) -> None:
        """追加一条消息（OpenAI 格式）。"""
        ...

    async def render(
        self,
        ctx: "RunContext",
        token_budget: Optional[int] = None,
    ) -> List[Message]:
        """产出送给 LLM 的 history。

        Args:
            ctx:          运行上下文。
            token_budget: 本次 history 可用的 token 上限，由装配层扣除
                          system 与 tool schema 后下发。``None`` 表示不限。

        Returns:
            history 消息列表。**保证不含 ``role="system"``。**
        """
        ...

    def all_messages(self) -> List[Message]:
        """返回完整未裁剪的消息列表（用于持久化与调试）。"""
        ...

    def clear(self) -> None:
        """清空记忆。"""
        ...


# ----------------------------------------------------------------------
# 截断安全
# ----------------------------------------------------------------------


def safe_cut(messages: List[Message], keep: int) -> List[Message]:
    """保留末尾约 ``keep`` 条消息，并把起点前移到安全的轮次边界。

    安全边界的定义：结果的第一条消息不能是 ``tool`` 角色，也不能让某个
    ``assistant(tool_calls)`` 的配对 ``tool`` 消息落在切点之外。

    做法是从初步切点向前回退，直到起点落在一个"不含 tool_calls 的
    assistant"或"user"消息上。

    Args:
        messages: 完整消息列表。
        keep:     期望保留的条数（下界，实际可能因对齐而多保留）。

    Returns:
        裁剪后的消息列表（原列表不变）。
    """
    if keep <= 0 or len(messages) <= keep:
        return list(messages)

    start = len(messages) - keep

    # 向前回退到安全边界：跳过 tool 消息，并回退到发起调用的 assistant 之前
    while start > 0:
        msg = messages[start]
        role = msg.get("role")
        if role == "tool":
            start -= 1
            continue
        if role == "assistant" and msg.get("tool_calls"):
            # 该 assistant 的 tool 结果在其后，一起保留是安全的；
            # 但它本身可能紧跟在 user 之后，继续前移一格更自然
            break
        break

    # 若回退后起点仍是 tool（说明前面全是 tool），继续前移到非 tool
    while start > 0 and messages[start].get("role") == "tool":
        start -= 1

    return list(messages[start:])


def is_pair_complete(messages: List[Message]) -> bool:
    """校验消息列表中 ``tool_calls`` 与 ``tool`` 响应是否完整配对。

    用于单测与调试；生产路径依赖 :func:`safe_cut` 保证正确性。
    """
    expected: set[str] = set()
    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            if expected:
                return False  # 上一轮 tool_calls 未被响应完
            for tc in msg.get("tool_calls") or []:
                tc_id = tc.get("id") if isinstance(tc, dict) else None
                if tc_id:
                    expected.add(tc_id)
        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id not in expected:
                return False
            expected.discard(tc_id)
    return not expected


def estimate_tokens(messages: List[Message]) -> int:
    """粗估消息列表的 token 数。

    经验系数：中文约 1.5 字符/token，英文约 4 字符/token；这里取 2.5
    作为混合文本的折中值，并为每条消息加 4 token 的角色开销。
    精确计数需要 tokenizer，但记忆裁剪只需要量级正确。
    """
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, list):  # 多模态内容
            content = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        total += int(len(str(content)) / 2.5) + 4
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            total += int(len(str(fn.get("arguments", ""))) / 2.5) + 8
    return total


def estimate_tools(tool_schemas: Optional[List[Dict[str, Any]]]) -> int:
    """粗估工具 schema 占用的 token 数。

    工具定义**每次请求都会完整发送**，是常被忽略的固定开销：一个中等规模
    的工具集（文件系统 + shell + 检索 + 图像 + TTS）轻易占用上千 token。
    只统计 history 而漏掉 schema，会让"token 预算"形同虚设。
    """
    if not tool_schemas:
        return 0
    total = 0
    for schema in tool_schemas:
        # 序列化长度是对 schema 体积最直接的近似（含嵌套参数定义）
        total += int(len(str(schema)) / 2.5) + 4
    return total


def contains_system(messages: Iterable[Message]) -> bool:
    """是否含 ``role="system"`` 消息。

    供装配层校验 ``render()`` 的返回值——system 段只能由装配层产生。
    """
    return any(m.get("role") == "system" for m in messages)


def normalize_message(msg: Any) -> Optional[Message]:
    """把各种形态的历史消息规整为 OpenAI 格式字典。

    支持三种输入：
    - 已是字典：原样透传（只做必要字段过滤）
    - Pydantic 模型（如业务侧的 ``MessageSchema``）：取 role / content
    - 其他对象：按属性读取 role / content

    Returns:
        规整后的消息；无法识别或内容为空时返回 None。
    """
    if msg is None:
        return None

    if isinstance(msg, dict):
        role = msg.get("role")
        if not role:
            return None
        out: Message = {"role": role, "content": msg.get("content") or ""}
        # 保留 tool-calling 相关字段，否则配对会断
        for key in ("tool_calls", "tool_call_id", "name"):
            if msg.get(key) is not None:
                out[key] = msg[key]
        return out

    role = getattr(msg, "role", None)
    if not role:
        return None
    content = getattr(msg, "content", "") or ""
    return {"role": str(role), "content": str(content)}


def normalize_history(messages: Optional[Iterable[Any]]) -> List[Message]:
    """批量规整历史消息，跳过无法识别的条目。"""
    if not messages:
        return []
    result: List[Message] = []
    for msg in messages:
        norm = normalize_message(msg)
        if norm is not None:
            result.append(norm)
    return result


__all__ = [
    "BaseMemory",
    "Message",
    "contains_system",
    "estimate_tokens",
    "estimate_tools",
    "is_pair_complete",
    "normalize_history",
    "normalize_message",
    "safe_cut",
]
