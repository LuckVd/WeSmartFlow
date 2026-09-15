"""Agent 模块。"""

from .base import AgentResult, BaseAgent
from .events import (
    AgentFinalEvent,
    AgentFinishReason,
    AgentStreamEvent,
    AgentThinkChunkEvent,
    AgentThinkEvent,
    AgentToolCallChunkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentToolRunEvent,
    DomainEvent,
    FileCreatedEvent,
    MasteryUpdatedEvent,
    NodeCreatedEvent,
    extract_event_text,
    is_domain_event,
)
from .history import assistant_message, tool_message, user_message
from .loop import tool_calling_loop
from .react import ReActAgent
from .workflow import (
    CheckpointStore,
    MemoryCheckpointStore,
    NeedApproval,
    Node,
    NodeDoneEvent,
    NodeFailed,
    NodeFailedEvent,
    NodeSkippedEvent,
    NodeStartEvent,
    NullCheckpointStore,
    Workflow,
    WorkflowAbortedEvent,
    WorkflowDoneEvent,
    WorkflowEvent,
    WorkflowStartEvent,
)

__all__ = [
    # 基类与结果
    "BaseAgent",
    "AgentResult",
    # 范式
    "ReActAgent",
    # 循环
    "tool_calling_loop",
    # 消息构造
    "user_message",
    "assistant_message",
    "tool_message",
    # 工作流
    "Workflow",
    "Node",
    "NodeFailed",
    "NeedApproval",
    "CheckpointStore",
    "MemoryCheckpointStore",
    "NullCheckpointStore",
    "WorkflowEvent",
    "WorkflowStartEvent",
    "WorkflowDoneEvent",
    "WorkflowAbortedEvent",
    "NodeStartEvent",
    "NodeDoneEvent",
    "NodeSkippedEvent",
    "NodeFailedEvent",
    # 事件
    "AgentFinishReason",
    "AgentStreamEvent",
    "AgentThinkChunkEvent",
    "AgentThinkEvent",
    "AgentToolCallChunkEvent",
    "AgentToolCallEvent",
    "AgentToolResultEvent",
    "AgentToolRunEvent",
    "AgentFinalEvent",
    "DomainEvent",
    "extract_event_text",
    "is_domain_event",
    # 遗留业务事件（待业务侧迁移到 DomainEvent 后移除）
    "FileCreatedEvent",
    "NodeCreatedEvent",
    "MasteryUpdatedEvent",
]
