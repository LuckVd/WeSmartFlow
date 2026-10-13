"""
用量记账：供应商成本明细及额度汇总

设计约束
--------
1. **绝不影响业务**：记账是旁路观测，任何异常都必须被吞掉并降级为日志。
   业务链路不应因为统计写库失败而中断。
2. **明细 + 汇总双写**：usage_events 保留可审计流水与归因维度，
   usage_summary 供热路径快速读取当期总量。
3. **系统任务单独标记**：is_system=1 的调用不计入用户额度，
   但仍写入明细，使平台侧成本保持可观测。

credit_quota 在每次付费调用前读取汇总并执行额度拦截。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_db
from repositories.base import new_id, utcnow_str
from services.pricing import (
    PRICING_VERSION,
    calc_llm_credits,
    calc_unit_credits,
    credits_to_yuan,
    normalize_usage,
)

logger = logging.getLogger(__name__)

# 合法计费类别与场景，用于防止打点处写错字导致维度污染
# ``embedding`` is deliberately distinct from ``llm`` in the ledger: it has a
# different operational path and lets platform-cost reports answer how much the
# KG itself costs.  It is still token-priced through ``calc_llm_credits``.
VALID_CATEGORIES = frozenset({"llm", "embedding", "search", "image", "audio"})

# 场景维度：用于回答「成本花在哪个功能上」
VALID_SCENES = frozenset(
    {
        "quiz",  # 出题 / 判题
        "chat",  # 辅导对话
        "immersive",  # 沉浸式课程生成
        "profile",  # 用户画像抽取
        "kg",  # 知识图谱构建与聚合
        "court",  # 庭审模块
        "search",  # 搜索工具
        "media",  # 图像 / 语音
        "system",  # 其他后台任务
        "magic-town",
        "chemistry-lab",
        "live-science",
        "math-garden",
        "moderation",
        "unknown",  # 未标注（应尽量消除）
    }
)


def current_period(now: Optional[datetime] = None) -> str:
    """返回当前计费周期标识 'YYYY-MM'（UTC）。"""
    dt = now or datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def _normalize_dims(category: str, scene: str) -> tuple[str, str]:
    """校验并归一化 category / scene，非法值降级但仍记账。"""
    cat = (category or "").strip().lower()
    if cat not in VALID_CATEGORIES:
        logger.warning("未知计费类别 %r，仍记账但请修正打点", category)
        cat = cat or "llm"

    sc = (scene or "").strip().lower()
    if sc not in VALID_SCENES:
        logger.warning("未知场景 %r，归入 unknown", scene)
        sc = "unknown"
    return cat, sc


def record_usage(
    user_id: str,
    *,
    category: str = "llm",
    scene: str = "unknown",
    model: str = "",
    usage: Optional[Dict[str, Any]] = None,
    units: float = 1,
    provider: str = "",
    region: str = "beijing",
    counts_quota: Optional[bool] = None,
    credits: Optional[int] = None,
    is_system: bool = False,
) -> int:
    """记录一次用量，返回本次折算的 credits（失败返回 0）。

    Args:
        category:  llm / embedding / search / image / audio
        scene:     业务场景，见 VALID_SCENES
        model:     token 模型名（category 为 llm 或 embedding 时用于计价）
        usage:     token API 返回的 usage 字典，支持各家字段别名
        units:     非 token 调用的计量单位数（audio 为供应商计费字符数）
        credits:   显式指定 credits，跳过自动计算（用于特殊计费）
        is_system: 系统内部任务，不计入用户额度但仍记明细

    额度累加口径（usage_summary，决定剩余免费额度）：
        只累加「平台共有 key」的消耗。用户自配 key 的调用平台不承担
        成本，明细（usage_events）照记以保持可观测，但不占用免费额度。
        归属以**调用时刻**为准（用户中途换 key 不影响历史累计）。

    Returns:
        本次 credits。任何异常都不会抛出，仅记录日志并返回 0。
    """
    try:
        cat, sc = _normalize_dims(category, scene)

        # 是否计入用户当期额度汇总：系统任务不计；
        # 用户自配 key（平台不承担成本）同样不计。
        if is_system:
            counts_quota = False
        if counts_quota is None:
            from services.credit_quota import (
                is_using_platform_key,
            )  # 延迟 import 避免循环依赖

            counts_quota = is_using_platform_key(user_id, cat)

        if credits is None:
            if cat in {"llm", "embedding"}:
                cost = calc_llm_credits(model, usage)
            else:
                cost = calc_unit_credits(
                    cat, units, model=model, provider=provider, region=region
                )
        else:
            cost = max(0, int(credits))

        tokens = (
            normalize_usage(usage)
            if cat in {"llm", "embedding"}
            else normalize_usage(None)
        )
        period = current_period()

        event_id = new_id()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO usage_events
                  (id, user_id, period, category, scene, model,
                   prompt_tokens, completion_tokens, reasoning_tokens,
                   cached_tokens, credits, is_system, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_id,
                    user_id,
                    period,
                    cat,
                    sc,
                    (model or "")[:120],
                    tokens["prompt_tokens"],
                    tokens["completion_tokens"],
                    tokens["reasoning_tokens"],
                    tokens["cached_tokens"],
                    cost,
                    1 if is_system else 0,
                    utcnow_str(),
                ),
            )
            conn.execute(
                "INSERT INTO usage_details (event_id, provider, region, units, pricing_version, estimated, counts_quota) VALUES (?,?,?,?,?,?,?)",
                (
                    event_id,
                    provider,
                    region,
                    units,
                    PRICING_VERSION,
                    int(bool((usage or {}).get("estimated"))),
                    int(counts_quota),
                ),
            )
            # 系统任务与用户自配 key 的调用不计入当期额度汇总
            if counts_quota:
                from services.credit_wallet import debit

                debit(conn, user_id, cost, event_id)
                conn.execute(
                    """
                    INSERT INTO usage_summary (user_id, period, credits, calls)
                    VALUES (?,?,?,1)
                    ON CONFLICT(user_id, period) DO UPDATE SET
                      credits = credits + excluded.credits,
                      calls   = calls + 1
                    """,
                    (user_id, period, cost),
                )
        return cost
    except Exception:  # pylint: disable=broad-except
        # 观测失败不得影响业务
        logger.warning(
            "记账失败（user=%s scene=%s category=%s）",
            user_id,
            scene,
            category,
            exc_info=True,
        )
        return 0


def get_period_credits(
    user_id: str, period: Optional[str] = None, *, strict: bool = False
) -> int:
    """读取用户当期已消耗 credits（不含系统任务）。

    后续接入额度拦截时，用它与配额比较即可。
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT credits FROM usage_summary WHERE user_id=? AND period=?",
                (user_id, period or current_period()),
            ).fetchone()
        return int(row["credits"]) if row else 0
    except Exception:  # pylint: disable=broad-except
        logger.warning("读取当期用量失败（user=%s）", user_id, exc_info=True)
        if strict:
            raise
        return 0


def get_usage_overview(user_id: str, period: Optional[str] = None) -> Dict[str, Any]:
    """用户当期用量总览：总量 + 按场景/类别拆分。"""
    p = period or current_period()
    empty = {
        "period": p,
        "credits": 0,
        "yuan": 0.0,
        "calls": 0,
        "by_scene": [],
        "by_category": [],
        "tokens": {
            "prompt": 0,
            "completion": 0,
            "reasoning": 0,
            "cached": 0,
        },
    }
    try:
        with get_db() as conn:
            total = conn.execute(
                "SELECT credits, calls FROM usage_summary WHERE user_id=? AND period=?",
                (user_id, p),
            ).fetchone()

            by_scene = conn.execute(
                """
                SELECT scene, SUM(credits) AS credits, COUNT(*) AS calls
                  FROM usage_events
                 WHERE user_id=? AND period=? AND is_system=0
                   AND COALESCE((SELECT counts_quota FROM usage_details d WHERE d.event_id=usage_events.id), 1)=1
                 GROUP BY scene ORDER BY credits DESC
                """,
                (user_id, p),
            ).fetchall()

            by_cat = conn.execute(
                """
                SELECT category, SUM(credits) AS credits, COUNT(*) AS calls
                  FROM usage_events
                 WHERE user_id=? AND period=? AND is_system=0
                   AND COALESCE((SELECT counts_quota FROM usage_details d WHERE d.event_id=usage_events.id), 1)=1
                 GROUP BY category ORDER BY credits DESC
                """,
                (user_id, p),
            ).fetchall()

            tok = conn.execute(
                """
                SELECT COALESCE(SUM(prompt_tokens),0)     AS p,
                       COALESCE(SUM(completion_tokens),0) AS c,
                       COALESCE(SUM(reasoning_tokens),0)  AS r,
                       COALESCE(SUM(cached_tokens),0)     AS k
                  FROM usage_events
                 WHERE user_id=? AND period=? AND is_system=0
                   AND COALESCE((SELECT counts_quota FROM usage_details d WHERE d.event_id=usage_events.id), 1)=1
                """,
                (user_id, p),
            ).fetchone()

        credits = int(total["credits"]) if total else 0
        return {
            "period": p,
            "credits": credits,
            "yuan": credits_to_yuan(credits),
            "calls": int(total["calls"]) if total else 0,
            "by_scene": [
                {
                    "scene": r["scene"],
                    "credits": int(r["credits"] or 0),
                    "calls": int(r["calls"]),
                }
                for r in by_scene
            ],
            "by_category": [
                {
                    "category": r["category"],
                    "credits": int(r["credits"] or 0),
                    "calls": int(r["calls"]),
                }
                for r in by_cat
            ],
            "tokens": {
                "prompt": int(tok["p"]),
                "completion": int(tok["c"]),
                "reasoning": int(tok["r"]),
                "cached": int(tok["k"]),
            },
        }
    except Exception:  # pylint: disable=broad-except
        logger.warning("读取用量总览失败（user=%s）", user_id, exc_info=True)
        return empty


def list_usage_events(
    user_id: str, *, limit: int = 50, period: Optional[str] = None
) -> List[Dict[str, Any]]:
    """最近的用量明细，供排查与看板展示。"""
    try:
        limit = max(1, min(500, int(limit)))
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT scene, category, model, prompt_tokens, completion_tokens,
                       reasoning_tokens, cached_tokens, credits, is_system, created_at,
                       d.provider, d.region, d.units, d.pricing_version, d.estimated, d.counts_quota
                  FROM usage_events LEFT JOIN usage_details d ON d.event_id=usage_events.id
                 WHERE user_id=? AND period=?
                 ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, period or current_period(), limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:  # pylint: disable=broad-except
        logger.warning("读取用量明细失败（user=%s）", user_id, exc_info=True)
        return []


def get_platform_overview(period: Optional[str] = None) -> Dict[str, Any]:
    """平台侧总览：含系统任务，用于评估整体成本结构。"""
    p = period or current_period()
    try:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT scene,
                       SUM(credits) AS credits,
                       COUNT(*)     AS calls,
                       SUM(reasoning_tokens) AS reasoning,
                       SUM(is_system)        AS system_calls
                  FROM usage_events
                 WHERE period=? AND (is_system=1 OR COALESCE((SELECT counts_quota FROM usage_details d WHERE d.event_id=usage_events.id), 1)=1)
                 GROUP BY scene ORDER BY credits DESC
                """,
                (p,),
            ).fetchall()
            total = conn.execute(
                "SELECT COALESCE(SUM(credits),0) AS c FROM usage_events WHERE period=? AND (is_system=1 OR COALESCE((SELECT counts_quota FROM usage_details d WHERE d.event_id=usage_events.id), 1)=1)",
                (p,),
            ).fetchone()
        credits = int(total["c"])
        return {
            "period": p,
            "credits": credits,
            "yuan": credits_to_yuan(credits),
            "by_scene": [
                {
                    "scene": r["scene"],
                    "credits": int(r["credits"] or 0),
                    "calls": int(r["calls"]),
                    "reasoning_tokens": int(r["reasoning"] or 0),
                    "system_calls": int(r["system_calls"] or 0),
                }
                for r in rows
            ],
        }
    except Exception:  # pylint: disable=broad-except
        logger.warning("读取平台用量总览失败", exc_info=True)
        return {"period": p, "credits": 0, "yuan": 0.0, "by_scene": []}
