"""运行期预算与中止信号。

``Budget`` 把"一次运行能消耗多少资源"显式化：步数、工具调用数、token、
成本、墙钟时限五个维度。父子 Agent **共享同一个 Budget 实例**（按引用传递），
因此子 Agent 的消耗会直接计入父预算——这是防止 ``as_tool()`` 嵌套绕过
成本上限的关键。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class AgentRunError(Exception):
    """Agent 运行期可预期的中止类异常基类。"""


class CancelledByCaller(AgentRunError):
    """调用方主动取消（如客户端断开 SSE 连接）。"""


class BudgetExceeded(AgentRunError):
    """超出运行预算。

    Attributes:
        limit_name: 触发的限制名，如 ``"max_steps"`` / ``"deadline"``。
    """

    def __init__(self, limit_name: str, detail: str = ""):
        self.limit_name = limit_name
        super().__init__(detail or f"超出运行预算：{limit_name}")


@dataclass
class Budget:
    """一次运行（含所有子 Agent）的资源上限与实时消耗。

    上限为 ``None`` 表示该维度不限制。``deadline`` 使用
    ``time.monotonic()`` 基准，不受系统时间调整影响。

    Attributes:
        max_steps:      推理循环最大步数。
        max_tool_calls: 工具调用总次数上限。
        max_tokens:     token 总量上限。
        max_credits:    成本上限，单位与计量层保持一致。
        deadline:       绝对截止时刻（``time.monotonic()`` 基准）。
    """

    max_steps: Optional[int] = 20
    max_tool_calls: Optional[int] = 50
    max_tokens: Optional[int] = None
    max_credits: Optional[int] = None
    deadline: Optional[float] = None

    # --- 实时消耗（由框架累加，调用方只读）---
    steps: int = field(default=0)
    tool_calls: int = field(default=0)
    tokens: int = field(default=0)
    credits: int = field(default=0)

    # 成本折算回调：(model_name, usage) -> credits，由业务层注入。
    # 为 None 时框架不累加 credits（max_credits 熔断仅在注入时生效）。
    # 放在这里是为了避免框架层反向依赖业务计价表（services.pricing）。
    credits_fn: Optional[Callable[[str, Any], int]] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # 构造辅助
    # ------------------------------------------------------------------

    @classmethod
    def with_timeout(cls, seconds: float, **kwargs) -> "Budget":
        """构造带相对超时的预算。

        Args:
            seconds: 从当前时刻起的可用秒数。
        """
        return cls(deadline=time.monotonic() + seconds, **kwargs)

    # ------------------------------------------------------------------
    # 检查
    # ------------------------------------------------------------------

    def exceeded(self) -> Optional[str]:
        """返回首个被突破的限制名，未超限返回 None。"""
        if self.max_steps is not None and self.steps > self.max_steps:
            return "max_steps"
        if self.max_tool_calls is not None and self.tool_calls > self.max_tool_calls:
            return "max_tool_calls"
        if self.max_tokens is not None and self.tokens > self.max_tokens:
            return "max_tokens"
        if self.max_credits is not None and self.credits > self.max_credits:
            return "max_credits"
        if self.deadline is not None and time.monotonic() > self.deadline:
            return "deadline"
        return None

    def check(self) -> None:
        """超限则抛 :class:`BudgetExceeded`。"""
        name = self.exceeded()
        if name is not None:
            raise BudgetExceeded(name, self.describe(name))

    def describe(self, name: str) -> str:
        """生成人类可读的超限说明。"""
        mapping = {
            "max_steps": (self.steps, self.max_steps, "步"),
            "max_tool_calls": (self.tool_calls, self.max_tool_calls, "次工具调用"),
            "max_tokens": (self.tokens, self.max_tokens, "tokens"),
            "max_credits": (self.credits, self.max_credits, "credits"),
        }
        if name in mapping:
            used, limit, unit = mapping[name]
            return f"已消耗 {used} {unit}，超出上限 {limit}"
        if name == "deadline":
            return "已超过运行时限"
        return name

    @property
    def remaining_seconds(self) -> Optional[float]:
        """距 deadline 的剩余秒数，无 deadline 时返回 None。"""
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())

    # ------------------------------------------------------------------
    # 累加（框架内部使用）
    # ------------------------------------------------------------------

    def add_tokens(self, count: int) -> None:
        if count > 0:
            self.tokens += count

    def add_credits(self, count: int) -> None:
        if count > 0:
            self.credits += count

    def snapshot(self) -> dict:
        """导出当前消耗，便于日志与 trace 记录。"""
        return {
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "tokens": self.tokens,
            "credits": self.credits,
        }


#: 不设任何限制的预算，用于框架内部默认值。
def unlimited_budget() -> Budget:
    """构造无限制预算（仅保留一个防御性的极大步数上限）。"""
    return Budget(
        max_steps=1000,
        max_tool_calls=None,
        max_tokens=None,
        max_credits=None,
        deadline=None,
    )


__all__ = [
    "AgentRunError",
    "Budget",
    "BudgetExceeded",
    "CancelledByCaller",
    "unlimited_budget",
]
