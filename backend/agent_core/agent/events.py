"""Agent 流式事件类型与枚举。

本模块刻意保持"叶子"地位：
- 不导入 ``agent.base`` / ``tool.registry`` / ``llm.base`` 等任何项目内部模块
- 仅依赖标准库与 ``agent_core.runtime.events``（同样是叶子模块）

这样 ``agent.base``（``BaseAgent`` 实现）与 ``tool.registry``
（执行工具时 yield 事件）都可以单向依赖本模块，避免互相 import 形成环。

**业务事件的归属**：框架只认识 :class:`DomainEvent` 这个不透明信封，
不解释其 ``kind`` 含义。具体业务事件（卡片生成、掌握度更新等）由业务层
在 ``agents/events.py`` 中定义。本模块底部保留的三个具名业务事件属于
**兼容遗留**，新代码请改用 ``DomainEvent``。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Union

from ..runtime.events import DomainEvent


# ============================================================
# 枚举
# ============================================================


class AgentFinishReason(Enum):
    """Agent 结束原因。"""

    STOP = "stop"  # 正常结束
    MAX_STEPS = "max_steps"  # 达到最大步数
    ERROR = "error"  # 运行时错误
    CANCELLED = "cancelled"  # 调用方主动取消
    BUDGET = "budget"  # 超出运行预算（token / 成本 / 时限）


# ============================================================
# 流式事件类型
# ============================================================


@dataclass
class AgentThinkChunkEvent:
    """LLM 思考过程的单个文本分片（流式输出）。"""

    delta: str  # 本次新增的文本片段
    content: str  # 截至本分片已累积的完整文本
    step: int  # 当前推理步数（从 1 开始）


@dataclass
class AgentThinkEvent:
    """LLM 完成本轮思考，汇总输出（流式结束后触发）。"""

    content: str  # LLM 输出的完整文本（Thought / 中间推理）
    step: int  # 当前推理步数（从 1 开始）


@dataclass
class AgentToolCallChunkEvent:
    """tool_call arguments 的单个分片事件（流式输出）。

    对应 LLM 层的 ToolCallDeltaEvent，透传给调用方以避免长参数静默等待。
    """

    index: int  # tool_call 在本次响应中的下标
    id: str  # tool_call id（仅首个分片携带）
    tool_name: str  # 函数名（仅首个分片携带）
    arguments_delta: str  # 本次新增的 arguments 片段
    arguments_so_far: str  # 截至本分片已累积的完整 arguments 字符串
    step: int  # 当前推理步数


@dataclass
class AgentToolCallEvent:
    """Agent 即将调用某个工具（tool_call 完整信息，流式结束后触发）。"""

    id: str
    tool_name: str
    arguments: Dict[str, Any]
    step: int
    index: int = 0  # 该工具调用在本轮 tool_calls 中的顺序（从 0 开始）


@dataclass
class AgentToolRunEvent:
    """工具执行过程中的流式事件。

    content 可以是：
    - str：普通工具输出的文本片段
    - AgentStreamEvent：AgentTool 嵌套时，子 Agent 透传上来的事件
    """

    id: str  # tool_call id，用于关联到对应的 AgentToolCallEvent
    tool_name: str
    step: int
    content: "Union[str, list, AgentStreamEvent]"
    index: int = 0  # 该工具调用在本轮 tool_calls 中的顺序（从 0 开始）


@dataclass
class AgentToolResultEvent:
    """工具执行完毕，返回最终结果。

    result 是工具产出的最后一个事件：
    - str：普通工具的完整文本结果
    - AgentStreamEvent：AgentTool 嵌套时子 Agent 的最后一个事件
    """

    id: str
    tool_name: str
    arguments: Dict[str, Any]
    result: "Union[str, list, AgentStreamEvent]"
    step: int
    index: int = 0  # 该工具调用在本轮 tool_calls 中的顺序（从 0 开始）


@dataclass
class AgentFinalEvent:
    """Agent 推理结束，产出最终回复。"""

    content: str
    finish_reason: AgentFinishReason
    detail: str = ""  # 补充说明（如超出的预算维度、取消原因）


# ============================================================
# 业务语义事件（遗留，新代码请用 DomainEvent）
# ============================================================
#
# 这三个类把教育业务概念（卡片类型、知识节点、掌握度）写进了框架的事件
# 协议里，属于层次污染。它们保留在此仅为兼容既有 import，等业务侧迁移到
# ``DomainEvent`` 后即可删除。
#
# 迁移方式::
#
#     # 旧
#     yield FileCreatedEvent(file_id=fid, title=t, file_type="html")
#     # 新（业务侧在 agents/events.py 定义构造器）
#     ctx.emit(DomainEvent("file_created", {"file_id": fid, "title": t,
#                                           "file_type": "html"}))


@dataclass
class FileCreatedEvent:
    """[遗留] 文件（PDF 卡片等）生成完毕。"""

    file_id: str  # 相对路径，如 "{uuid}.pdf"
    title: str = ""  # 文件标题（如卡片标题）
    file_type: str = ""  # 文件类型：html / quiz / viz


@dataclass
class NodeCreatedEvent:
    """[遗留] 知识节点被创建。"""

    node_id: str
    title: str


@dataclass
class MasteryUpdatedEvent:
    """[遗留] 节点掌握度发生变化。"""

    node_id: str
    delta: float  # 本次变化量


# 所有流式事件的联合类型
AgentStreamEvent = Union[
    AgentThinkChunkEvent,
    AgentThinkEvent,
    AgentToolCallChunkEvent,
    AgentToolCallEvent,
    AgentToolRunEvent,
    AgentToolResultEvent,
    AgentFinalEvent,
    DomainEvent,
    # --- 遗留业务事件 ---
    FileCreatedEvent,
    NodeCreatedEvent,
    MasteryUpdatedEvent,
]


def extract_event_text(result: "Union[str, list, AgentStreamEvent]") -> str:
    """从工具结果中提取可写入 history 的文本字符串。

    - str：直接返回
    - 带 content 字段的事件（AgentFinalEvent / AgentThinkEvent 等）：返回 content
    - 其他事件（含 DomainEvent）：返回空字符串（业务事件不携带文本，不应写入 history）
    """
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join(
            block.get("text", "")
            for block in result
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if isinstance(result, DomainEvent):
        return ""
    return getattr(result, "content", "")


def is_domain_event(event: Any) -> bool:
    """判断是否为业务语义事件（含遗留三类）。

    框架在写入 history 时需要跳过业务事件——它们是副作用通知，不是对话内容。
    """
    return isinstance(
        event,
        (DomainEvent, FileCreatedEvent, NodeCreatedEvent, MasteryUpdatedEvent),
    )


__all__ = [
    "AgentFinishReason",
    "AgentThinkChunkEvent",
    "AgentThinkEvent",
    "AgentToolCallChunkEvent",
    "AgentToolCallEvent",
    "AgentToolRunEvent",
    "AgentToolResultEvent",
    "AgentFinalEvent",
    "DomainEvent",
    "FileCreatedEvent",
    "NodeCreatedEvent",
    "MasteryUpdatedEvent",
    "AgentStreamEvent",
    "extract_event_text",
    "is_domain_event",
]
