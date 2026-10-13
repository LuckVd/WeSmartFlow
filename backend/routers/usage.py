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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.contracts import ProviderMetricsResponse, standard_error_responses
from dependencies import get_current_user
from utils.admin_auth import require_admin
from services.usage_meter import (
    get_platform_overview,
    get_usage_overview,
    list_usage_events,
)

router = APIRouter(prefix="/api/usage", tags=["usage"])


class CreditCardRedeemRequest(BaseModel):
    code: str


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


@router.post("/credits/cards/redeem")
def redeem_credit_card(
    body: CreditCardRedeemRequest,
    user_id: str = Depends(get_current_user),
):
    """兑换积分卡：支持增加积分或把当前余额重置为卡片额度。"""
    from services.credit_wallet import (
        CreditCardError,
        redeem_credit_card as redeem_card,
    )

    try:
        return redeem_card(user_id, body.code)
    except CreditCardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    _: str = Depends(require_admin),
):
    """平台侧成本总览（含系统后台任务），按场景归因。

    用于回答「成本花在哪个功能上」——这是设定额度阈值的前提。
    """
    return get_platform_overview(period)


@router.get(
    "/providers/metrics",
    operation_id="get_provider_metrics",
    response_model=ProviderMetricsResponse,
    responses=standard_error_responses(401, 422),
)
def provider_metrics(
    category: Optional[str] = Query(
        None,
        pattern="^(llm|embedding|image|search|audio|integration)$",
        description="可选的供应商或外部集成类别",
    ),
    _: str = Depends(require_admin),
):
    """供应商及外部集成调用观测快照，供管理员排查超时、失败与重试。

    指标仅保存在当前进程的有界内存中，重启后清空；请求或用户密钥不会
    出现在响应中。持久化监控将在 exporter 接入后复用同一事件结构。
    """
    from services.provider_gateway import get_provider_gateway

    return get_provider_gateway().metrics.snapshot_for(category=category)
