"""RunContext — 贯穿一次 Agent 运行的上下文。

这是整个框架的**承载中枢**。此前散落无处安放的东西，现在统一挂在它上面：

======================  ==========================================
以前寄生的位置            现在的归属
======================  ==========================================
``llm.tool_call_count``  ``ctx.tool_seq``（循环状态回归运行期）
各工具 ``os.getenv``      ``ctx.settings``（配置注入）
Service 手工维护的队列    ``ctx.emit``（业务事件出口）
（无）                    ``ctx.budget``（预算与熔断）
（无）                    ``ctx.is_cancelled``（客户端断开即停）
（无）                    ``ctx.tracer``（调用树追踪）
======================  ==========================================

沿 ``Agent → ToolRegistry → Tool → 子 Agent`` 单向传递。子上下文通过
:meth:`RunContext.child` 派生：预算、追踪器、事件出口**共享**，
对话记忆**隔离**。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field, replace
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    TypeVar,
)

from .budget import Budget, BudgetExceeded, CancelledByCaller, unlimited_budget
from .events import DomainEvent
from .settings import AgentSettings, default_settings
from .trace import NULL_TRACER, Tracer

if TYPE_CHECKING:  # 仅类型注解，避免运行时循环导入
    from ..memory.base import BaseMemory

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _noop_emit(event: DomainEvent) -> None:
    """默认事件出口：丢弃（无人订阅时不应报错）。"""


def _never_cancelled() -> bool:
    return False


@dataclass
class RunContext:
    """一次 Agent 运行的上下文。

    Attributes:
        run_id:       本次运行唯一 id。
        trace_id:     贯穿整条请求链路的 id（可由上游 HTTP 请求透传）。
        settings:     外部配置，替代工具层直读环境变量。
        budget:       资源预算，父子 Agent 共享同一实例。
        principal:    配额归属主体，如 ``"user:42"``。框架仅透传不解释。
        scope:        业务场景标识，如 ``"tutor"`` / ``"demo:court"``，用于计量分账。
        tracer:       调用树追踪器，默认零开销。
        emit:         业务事件出口，由框架在正确位置调用以保证顺序。
        is_cancelled: 中止探测回调，返回 True 时循环在下一个检查点退出。
        memory:       对话记忆，None 表示由 Agent 使用自身默认记忆。
        tool_seq:     全局工具调用序号分配器（跨轮次单调递增，不重叠）。
        depth:        Agent 嵌套深度，根为 0。
        metadata:     业务自定义透传数据，框架不读取。
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str = ""
    settings: AgentSettings = field(default_factory=default_settings)
    budget: Budget = field(default_factory=unlimited_budget)

    principal: str = ""
    scope: str = ""

    tracer: Tracer = NULL_TRACER
    emit: Callable[[DomainEvent], None] = _noop_emit
    is_cancelled: Callable[[], bool] = _never_cancelled

    memory: Optional["BaseMemory"] = None

    tool_seq: int = 0
    depth: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trace_id:
            self.trace_id = self.run_id

    # ------------------------------------------------------------------
    # 检查点
    # ------------------------------------------------------------------

    def checkpoint(self) -> None:
        """在循环每步、每次工具调用前调用。

        Raises:
            CancelledByCaller: 调用方已取消。
            BudgetExceeded:    超出运行预算。
        """
        if self.is_cancelled():
            raise CancelledByCaller("调用方已取消运行")
        self.budget.check()

    def cancelled(self) -> bool:
        """非抛异常版本的中止探测（用于需要优雅收尾的位置）。"""
        try:
            return bool(self.is_cancelled())
        except Exception:  # pylint: disable=broad-except
            logger.warning("is_cancelled 回调异常，视为未取消", exc_info=True)
            return False

    async def wait(self, awaitable: Awaitable[T]) -> T:
        """等待异步操作，deadline 到达时取消等待并报告预算中止。"""
        remaining = self.budget.remaining_seconds
        if remaining is None:
            return await awaitable
        try:
            return await asyncio.wait_for(awaitable, timeout=remaining)
        except asyncio.TimeoutError as exc:
            if self.budget.remaining_seconds == 0:
                raise BudgetExceeded("deadline", "已超过运行时限") from exc
            raise

    # ------------------------------------------------------------------
    # 序号分配
    # ------------------------------------------------------------------

    def next_tool_indices(self, count: int) -> int:
        """为本轮 ``count`` 个并行工具调用分配连续的全局起始序号。

        取代原先挂在 LLM 实例上的 ``tool_call_count``——那里既有层次错乱
        问题，也会在复用 LLM 客户端时被并发 Agent 互相污染。

        Returns:
            本轮起始序号；第 i 个工具的全局序号为 ``起始 + i``。
        """
        base = self.tool_seq
        self.tool_seq += max(0, count)
        self.budget.tool_calls += max(0, count)
        return base

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def emit_domain(self, event: DomainEvent, source: str = "") -> None:
        """发出业务事件（自动补 source，并隔离订阅方异常）。"""
        if source and not event.source:
            event.source = source
        try:
            self.emit(event)
        except Exception:  # pylint: disable=broad-except
            logger.warning("业务事件订阅方异常 kind=%s", event.kind, exc_info=True)

    # ------------------------------------------------------------------
    # 派生
    # ------------------------------------------------------------------

    def child(self, *, scope: str = "", **overrides: Any) -> "RunContext":
        """派生子上下文，供子 Agent / 子工作流使用。

        共享（按引用）：``budget`` / ``tracer`` / ``emit`` / ``is_cancelled``
        —— 因此子 Agent 的消耗计入父预算，取消信号也会传导下去。

        隔离：``memory`` 置空（子 Agent 有独立对话历史）、``tool_seq`` 归零、
        ``run_id`` 重新生成、``depth`` 加一。

        Args:
            scope: 子上下文的业务标识，为空则继承父级。
        """
        return replace(
            self,
            run_id=uuid.uuid4().hex[:16],
            trace_id=self.trace_id,
            scope=scope or self.scope,
            memory=None,
            tool_seq=0,
            depth=self.depth + 1,
            metadata=dict(self.metadata),
            **overrides,
        )

    # ------------------------------------------------------------------
    # 诊断
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """导出运行状态摘要，便于日志与错误上报。"""
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "principal": self.principal,
            "scope": self.scope,
            "depth": self.depth,
            "tool_seq": self.tool_seq,
            **self.budget.snapshot(),
        }

    def __repr__(self) -> str:
        return (
            f"<RunContext run_id={self.run_id} scope={self.scope!r} "
            f"depth={self.depth} steps={self.budget.steps}>"
        )


# ----------------------------------------------------------------------
# 便捷构造
# ----------------------------------------------------------------------


def new_context(
    *,
    principal: str = "",
    scope: str = "",
    budget: Optional[Budget] = None,
    settings: Optional[AgentSettings] = None,
    tracer: Optional[Tracer] = None,
    emit: Optional[Callable[[DomainEvent], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    memory: Optional["BaseMemory"] = None,
    trace_id: str = "",
    **metadata: Any,
) -> RunContext:
    """构造 RunContext 的便捷入口，未指定项使用框架默认值。

    Example::

        ctx = new_context(
            principal=f"user:{user_id}",
            scope="tutor",
            budget=Budget.with_timeout(120, max_steps=20, max_credits=3000),
            emit=queue.put_nowait,
            is_cancelled=request.is_disconnected,
        )
    """
    return RunContext(
        trace_id=trace_id,
        settings=settings or default_settings(),
        budget=budget if budget is not None else unlimited_budget(),
        principal=principal,
        scope=scope,
        tracer=tracer or NULL_TRACER,
        emit=emit or _noop_emit,
        is_cancelled=is_cancelled or _never_cancelled,
        memory=memory,
        metadata=metadata,
    )


def collect_events() -> tuple[List[DomainEvent], Callable[[DomainEvent], None]]:
    """创建一个把事件收集到列表的 ``emit``（测试与批处理场景常用）。

    Returns:
        ``(事件列表, emit 回调)``；列表随回调调用实时增长。
    """
    bucket: List[DomainEvent] = []
    return bucket, bucket.append


__all__ = [
    "Budget",
    "BudgetExceeded",
    "CancelledByCaller",
    "RunContext",
    "collect_events",
    "new_context",
]
