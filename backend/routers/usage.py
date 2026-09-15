"""
API 使用量路由

旧口径（按调用次数）已废弃，credits 为唯一用量口径：
  GET /api/usage/credits        → 当期 credits 总览（按场景/类别/token 拆分）
  GET /api/usage/credits/quota  → 持久余额/当月消费/奖励状态
  GET /api/usage/credits/events → 当期用量明细
  GET /api/usage/credits/platform → 平台侧总览（含系统任务）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from dependencies import get_current_user
from services.usage_meter import (
    get_platform_overview,
    get_usage_overview,
    list_usage_events,
)

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/credits")
def credits_overview(
    period: Optional[str] = Query(None, description="计费周期 YYYY-MM，默认当期"),
    user_id: str = Depends(get_current_user),
):
    """当期 credits 用量总览：总额、按场景/类别拆分、token 构成。

    观测阶段该数据不参与拦截，仅用于评估真实成本分布。
    """
    return get_usage_overview(user_id, period)


@router.get("/credits/quota")
def credits_quota(user_id: str = Depends(get_current_user)):
    """积分钱包：跨月余额、当月消费、赠送规则和奖励状态。"""
    from services.credit_quota import quota_overview

    return quota_overview(user_id)


@router.get("/credits/events")
def credits_events(
    limit: int = Query(50, ge=1, le=500),
    period: Optional[str] = Query(None, description="计费周期 YYYY-MM，默认当期"),
    user_id: str = Depends(get_current_user),
):
    """当期用量明细，用于排查异常消耗。"""
    return {"events": list_usage_events(user_id, limit=limit, period=period)}


@router.get("/credits/platform")
def credits_platform(
    period: Optional[str] = Query(None, description="计费周期 YYYY-MM，默认当期"),
    _: str = Depends(get_current_user),
):
    """平台侧成本总览（含系统后台任务），按场景归因。

    用于回答「成本花在哪个功能上」——这是设定额度阈值的前提。
    """
    return get_platform_overview(period)
