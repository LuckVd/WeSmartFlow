"""运行链路追踪（trace）。

Agent 系统的调用树可能很深：父 Agent → 工具 → 子 Agent → 工具……
只有框架能看见这棵树的完整形状，因此 trace 必须做在框架层。

设计取向：
- ``Tracer`` 是协议，默认实现 :class:`NullTracer` 零开销（不分配对象）。
- :class:`MemoryTracer` 收集 span 树，运行结束后可一次性导出，
  供日志、计量、性能分析使用。
- 不引入 OpenTelemetry 依赖，但 span 字段刻意与其对齐，便于将来桥接。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable

# span 类型常量
SPAN_AGENT = "agent"
SPAN_LLM = "llm"
SPAN_TOOL = "tool"
SPAN_WORKFLOW = "workflow"
SPAN_NODE = "node"


@dataclass
class Span:
    """一次可计时的操作。

    Attributes:
        name:       操作名，如 ``"llm.think"`` / ``"tool.generate_card"``。
        kind:       操作类型，取 ``SPAN_*`` 常量之一。
        span_id:    本 span 唯一 id。
        parent_id:  父 span id，根 span 为 None。
        attrs:      自由属性（token 数、模型名、步数等），可在 span 存续期间写入。
        error:      异常信息，正常结束为 None。
    """

    name: str
    kind: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_id: Optional[str] = None
    start: float = field(default_factory=time.monotonic)
    end: Optional[float] = None
    attrs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        """耗时（毫秒）；未结束时按当前时刻计算。"""
        finish = self.end if self.end is not None else time.monotonic()
        return (finish - self.start) * 1000.0

    def set(self, **attrs: Any) -> "Span":
        """批量写入属性，返回自身以便链式调用。"""
        self.attrs.update(attrs)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "duration_ms": round(self.duration_ms, 2),
            "attrs": dict(self.attrs),
            "error": self.error,
        }


@runtime_checkable
class Tracer(Protocol):
    """追踪器协议。

    实现方需保证 ``span()`` 是可重入的上下文管理器，且异常安全
    （span 在异常时也要正确关闭并记录 error）。
    """

    def span(self, name: str, kind: str = SPAN_AGENT, **attrs: Any) -> Any:
        """开启一个 span，返回上下文管理器（``__enter__`` 产出 :class:`Span`）。"""
        ...


class _NullSpanCtx:
    """零开销 span 上下文：复用同一个哑 Span 实例，不做任何记录。"""

    __slots__ = ()

    _SHARED = Span(name="", kind="", span_id="")

    def __enter__(self) -> Span:
        return self._SHARED

    def __exit__(self, *exc_info) -> bool:
        return False


class NullTracer:
    """不做任何记录的追踪器（框架默认值）。"""

    __slots__ = ()

    _CTX = _NullSpanCtx()

    def span(self, name: str, kind: str = SPAN_AGENT, **attrs: Any) -> _NullSpanCtx:
        return self._CTX


#: 进程级共享的空追踪器实例。
NULL_TRACER = NullTracer()


class _MemorySpanCtx:
    """MemoryTracer 的 span 上下文，负责维护父子关系与异常记录。"""

    __slots__ = ("_tracer", "_span")

    def __init__(self, tracer: "MemoryTracer", span: Span):
        self._tracer = tracer
        self._span = span

    def __enter__(self) -> Span:
        self._tracer._stack.append(self._span)
        return self._span

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._span.end = time.monotonic()
        if exc is not None:
            self._span.error = f"{exc_type.__name__}: {exc}"
        if self._tracer._stack and self._tracer._stack[-1] is self._span:
            self._tracer._stack.pop()
        return False  # 不吞异常


class MemoryTracer:
    """在内存中收集 span 树的追踪器。

    适用于单次请求级别的追踪：运行结束后调用 :meth:`export` 拿到扁平
    span 列表（含 parent_id，可重建树形），写入日志或上报。

    注意：本类**不是线程安全的**，但对同一 asyncio 事件循环内的并发
    工具执行是安全的（协程切换点不会打断 ``__enter__``/``__exit__``）。
    并行工具产生的 span 其 parent_id 归属以进入顺序为准，属于可接受的近似。
    """

    def __init__(self, trace_id: str = ""):
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self._spans: List[Span] = []
        self._stack: List[Span] = []

    def span(self, name: str, kind: str = SPAN_AGENT, **attrs: Any) -> _MemorySpanCtx:
        parent = self._stack[-1] if self._stack else None
        sp = Span(
            name=name,
            kind=kind,
            parent_id=parent.span_id if parent else None,
            attrs=dict(attrs),
        )
        self._spans.append(sp)
        return _MemorySpanCtx(self, sp)

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    def export(self) -> List[Dict[str, Any]]:
        """导出所有 span（扁平列表，按开始顺序）。"""
        return [s.to_dict() for s in self._spans]

    def summary(self) -> Dict[str, Any]:
        """汇总统计：各类型 span 的数量与总耗时。"""
        by_kind: Dict[str, Dict[str, Any]] = {}
        for s in self._spans:
            entry = by_kind.setdefault(s.kind, {"count": 0, "total_ms": 0.0})
            entry["count"] += 1
            entry["total_ms"] = round(entry["total_ms"] + s.duration_ms, 2)
        return {
            "trace_id": self.trace_id,
            "span_count": len(self._spans),
            "by_kind": by_kind,
            "errors": [s.name for s in self._spans if s.error],
        }

    def render_tree(self) -> str:
        """渲染为缩进树形文本，便于日志排查。"""
        children: Dict[Optional[str], List[Span]] = {}
        for s in self._spans:
            children.setdefault(s.parent_id, []).append(s)

        lines: List[str] = []

        def walk(parent_id: Optional[str], depth: int) -> None:
            for s in children.get(parent_id, []):
                mark = " !" if s.error else ""
                lines.append(
                    f"{'  ' * depth}{s.kind}:{s.name} {s.duration_ms:.0f}ms{mark}"
                )
                walk(s.span_id, depth + 1)

        walk(None, 0)
        return "\n".join(lines)


def iter_spans(tracer: Tracer) -> Iterator[Span]:
    """遍历追踪器收集的 span（仅 MemoryTracer 有内容）。"""
    spans = getattr(tracer, "_spans", None)
    if spans:
        yield from spans


__all__ = [
    "MemoryTracer",
    "NULL_TRACER",
    "NullTracer",
    "SPAN_AGENT",
    "SPAN_LLM",
    "SPAN_NODE",
    "SPAN_TOOL",
    "SPAN_WORKFLOW",
    "Span",
    "Tracer",
    "iter_spans",
]
