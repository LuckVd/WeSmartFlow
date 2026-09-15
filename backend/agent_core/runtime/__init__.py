"""Agent 运行期基础设施。

本包提供贯穿一次运行的横切能力，与具体推理范式无关：

- :class:`RunContext`   — 运行上下文，承载下列一切
- :class:`Budget`       — 步数/工具/token/成本/时限预算
- :class:`AgentSettings` — 配置注入，替代工具层直读环境变量
- :class:`Tracer`       — 调用树追踪（默认零开销）
- :class:`DomainEvent`  — 业务语义事件信封（框架不解释其内容）

设计约束：本包只依赖 Python 标准库，不导入 ``agent_core`` 内其他子包
（``memory`` 仅作类型注解），因此可作为最底层的叶子依赖被任意模块引用。
"""

from .budget import (
    AgentRunError,
    Budget,
    BudgetExceeded,
    CancelledByCaller,
    unlimited_budget,
)
from .run_context import RunContext, collect_events, new_context
from .events import DomainEvent
from .settings import (
    AgentSettings,
    ProviderSettings,
    default_settings,
    reset_default_settings,
)
from .trace import (
    NULL_TRACER,
    SPAN_AGENT,
    SPAN_LLM,
    SPAN_NODE,
    SPAN_TOOL,
    SPAN_WORKFLOW,
    MemoryTracer,
    NullTracer,
    Span,
    Tracer,
)

__all__ = [
    # 上下文
    "RunContext",
    "new_context",
    "collect_events",
    # 预算与中止
    "Budget",
    "BudgetExceeded",
    "CancelledByCaller",
    "AgentRunError",
    "unlimited_budget",
    # 配置
    "AgentSettings",
    "ProviderSettings",
    "default_settings",
    "reset_default_settings",
    # 追踪
    "Tracer",
    "NullTracer",
    "NULL_TRACER",
    "MemoryTracer",
    "Span",
    "SPAN_AGENT",
    "SPAN_LLM",
    "SPAN_TOOL",
    "SPAN_WORKFLOW",
    "SPAN_NODE",
    # 事件
    "DomainEvent",
]
