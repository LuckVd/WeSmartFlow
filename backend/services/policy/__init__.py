"""业务策略层。

把"根据输入决定系统行为"的判定逻辑从 Service 中独立出来，使其可单独测试、
单独调优，而不必启动整条对话链路。
"""

from .interaction import (
    MODE_CARD,
    MODE_CHAT,
    MODE_QUIZ,
    MODE_VIZ,
    InteractionDecision,
    InteractionPolicy,
    KeywordTable,
    has_recent_card,
    is_first_turn,
)

__all__ = [
    "InteractionPolicy",
    "InteractionDecision",
    "KeywordTable",
    "MODE_CHAT",
    "MODE_CARD",
    "MODE_QUIZ",
    "MODE_VIZ",
    "is_first_turn",
    "has_recent_card",
]
