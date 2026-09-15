"""Credit wallet access control; monthly usage remains an independent reporting metric."""

from __future__ import annotations

from typing import Optional

from config import (
    CREDITS_BORROW_RATIO,
    CREDITS_ENFORCEMENT_ENABLED,
)
from database import get_setting
from services.usage_meter import current_period, get_period_credits


class CreditsExceeded(Exception):
    """可用积分余额已用完。"""

    def __init__(self, quota: int, used: int):
        self.quota = quota
        self.used = used
        super().__init__(
            "积分余额已用完。可领取 GitHub Star 奖励，或等待下月额度补充。"
        )


def is_enforcement_enabled() -> bool:
    """当前是否启用 credits 拦截（灰度开关）。"""
    return CREDITS_ENFORCEMENT_ENABLED


def is_using_platform_key(user_id: str, category: str) -> bool:
    """判断用户是否在使用平台公共 Key（即用户自己的 settings 为空）。

    category: 'llm' | 'search' | 'image'
    """
    if category == "llm":
        user_key = get_setting(user_id, "llm_api_key")
    elif category == "search":
        user_key = get_setting(user_id, "tavily_api_key")
    elif category == "image":
        user_key = get_setting(user_id, "img_api_key")
    elif category == "audio":
        user_key = get_setting(user_id, "tts_api_key")
    else:
        return False

    # 用户 settings 为空或 None → 使用平台公共 Key
    return not user_key


def get_used(user_id: str, period: Optional[str] = None) -> int:
    """当期已消耗 credits（额度口径：仅平台共有 key 的消耗，
    不含系统任务与用户自配 key 的调用）。"""
    return get_period_credits(user_id, period, strict=True)


def get_remaining(user_id: str) -> int:
    """钱包可用余额，下限 0，仅供展示。"""
    from services.credit_wallet import balance

    return max(0, balance(user_id))


def assert_available(
    user_id: str, category: str = "", *, platform_key: Optional[bool] = None
) -> None:
    """事前软检查：余额 ≤ 0 则抛 ``CreditsExceeded``。

    - 关闭拦截开关时直接放行；
    - ``category`` 传入时先判断平台 Key 归属：用户自配 key 放行（平台不
      承担成本，不受限）；
    - 余额为零或负数时拒绝；不再用零表示无限额度。
    """
    if not CREDITS_ENFORCEMENT_ENABLED:
        return
    if platform_key is False:
        return
    if (
        platform_key is None
        and category
        and not is_using_platform_key(user_id, category)
    ):
        return

    from services.credit_wallet import balance

    available = balance(user_id)
    if available <= 0:
        raise CreditsExceeded(0, -available)


def budget_credits(user_id: str) -> int:
    """计算单次运行的 credits 预算（供 ``Budget.max_credits`` 熔断）。

    返回「剩余额度 + 预借余量」，使单次运行可小幅超额（默认 20%），
    在「金额事后才知道」的约束下换取实现简单。

    返回 0 表示不设 credits 预算上限，包含以下情形：
    - 拦截开关未启用；
    - 用户自配 LLM key（平台不承担成本，无需熔断）；
    """
    if not CREDITS_ENFORCEMENT_ENABLED:
        return 0
    if not is_using_platform_key(user_id, "llm"):
        return 0

    assert_available(user_id, "llm")
    remaining = get_remaining(user_id)
    return max(1, remaining + int(remaining * CREDITS_BORROW_RATIO))


def quota_overview(user_id: str) -> dict:
    from services.credit_wallet import overview

    wallet = overview(user_id)
    return {
        **wallet,
        "period": current_period(),
        "used": get_used(user_id),
        "enforcement": CREDITS_ENFORCEMENT_ENABLED,
    }
