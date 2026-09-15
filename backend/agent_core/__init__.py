"""agent_core — 与业务解耦的通用 Agent 框架。

定位介于 LangChain 与裸写循环之间：提供必要的抽象，但不引入组合子代数。

四层结构::

    runtime/   运行期基础设施（上下文、预算、配置、追踪、事件）
    llm/       LLM 适配（无状态）
    tool/      工具定义、注册、执行
    memory/    记忆工程：短期对话历史与压缩
    agent/     编排：ReAct 循环与工作流 DAG
    context/   上下文工程：装配最终 messages（system + history + tools）
    skills/    渐进式技能加载

最小可用示例::

    from agent_core import ReActAgent, ToolRegistry, Budget, new_context

    ctx = new_context(
        principal="user:42",
        scope="demo",
        budget=Budget.with_timeout(120, max_steps=10),
        is_cancelled=request.is_disconnected,
    )
    agent = ReActAgent(llm=llm, tool_registry=ToolRegistry([my_tool]))
    async for event in agent.async_stream("帮我查一下天气", ctx=ctx):
        ...

设计约束：本包不导入任何业务模块（``services`` / ``config`` /
``repositories`` 等）。需要业务能力时通过协议注入，由业务层提供实现。
"""

# --- Agent 范式与结果 ---
from .agent import (
    AgentFinalEvent,
    AgentFinishReason,
    AgentResult,
    AgentStreamEvent,
    AgentThinkChunkEvent,
    AgentThinkEvent,
    AgentToolCallChunkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentToolRunEvent,
    BaseAgent,
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
    ReActAgent,
    Workflow,
    WorkflowAbortedEvent,
    WorkflowDoneEvent,
    WorkflowEvent,
    WorkflowStartEvent,
    extract_event_text,
    is_domain_event,
    tool_calling_loop,
)

# --- 上下文工程 ---
from .context import (
    SystemPromptBuilder,
    CallableProvider,
    ContextProvider,
    FileProvider,
    StaticPromptBuilder,
    LayeredPromptBuilder,
    StaticProvider,
    assemble,
    measure,
)

# --- 工作空间 ---
from .layout import AgentWorkspace

# --- LLM ---
from .llm.base import (
    BaseLLM,
    LLMResponse,
    MessageRole,
    StreamChunkEvent,
    StreamEvent,
    StreamFinishEvent,
    ToolCallDeltaEvent,
    ToolCallRequest,
)

# --- 记忆 ---
from .memory import (
    BaseMemory,
    FullMemory,
    SummaryMemory,
    WindowMemory,
)

# --- 运行期 ---
from .runtime import (
    NULL_TRACER,
    AgentSettings,
    Budget,
    BudgetExceeded,
    CancelledByCaller,
    DomainEvent,
    MemoryTracer,
    RunContext,
    Span,
    Tracer,
    default_settings,
    new_context,
)

# --- 技能 ---
from .skills import SkillsLoader

# --- 结构化输出 ---
from .structured import StructuredOutputError, extract_json, structured_think

# --- 工具 ---
from .tool.base import BaseTool
from .tool.decorator import FunctionTool, tool
from .tool.registry import ToolRegistry

__all__ = [
    # 运行期
    "RunContext",
    "new_context",
    "Budget",
    "BudgetExceeded",
    "CancelledByCaller",
    "AgentSettings",
    "default_settings",
    "Tracer",
    "MemoryTracer",
    "NULL_TRACER",
    "Span",
    "DomainEvent",
    # Agent
    "BaseAgent",
    "AgentResult",
    "ReActAgent",
    "tool_calling_loop",
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
    # 结构化输出
    "structured_think",
    "extract_json",
    "StructuredOutputError",
    # 事件
    "AgentFinishReason",
    "AgentStreamEvent",
    "AgentThinkChunkEvent",
    "AgentThinkEvent",
    "AgentToolCallChunkEvent",
    "AgentToolCallEvent",
    "AgentToolRunEvent",
    "AgentToolResultEvent",
    "AgentFinalEvent",
    "extract_event_text",
    "is_domain_event",
    # LLM
    "BaseLLM",
    "LLMResponse",
    "MessageRole",
    "ToolCallRequest",
    "StreamEvent",
    "StreamChunkEvent",
    "StreamFinishEvent",
    "ToolCallDeltaEvent",
    # 工具
    "BaseTool",
    "ToolRegistry",
    "FunctionTool",
    "tool",
    # 记忆
    "BaseMemory",
    "FullMemory",
    "WindowMemory",
    "SummaryMemory",
    # 上下文与技能
    "assemble",
    "measure",
    "SystemPromptBuilder",
    "StaticPromptBuilder",
    "LayeredPromptBuilder",
    "ContextProvider",
    "StaticProvider",
    "CallableProvider",
    "FileProvider",
    "SkillsLoader",
    # 工作空间
    "AgentWorkspace",
]
