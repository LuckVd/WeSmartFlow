"""Read-only administrator views. Never invoke lazy wallet grant helpers."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from database import get_db
from utils.admin_auth import require_admin
from services.usage_meter import current_period

router = APIRouter(
    prefix="/api/admin/users", tags=["admin"], dependencies=[Depends(require_admin)]
)

USER_FIELDS = """u.id,u.name,u.email,u.avatar_url,u.github_id,u.github_username,
    CASE WHEN u.wechat_openid IS NOT NULL AND u.wechat_openid != '' THEN 1 ELSE 0 END AS wechat_bound,
    u.created_at,w.balance,w.last_month AS wallet_month"""


def _month():
    return current_period()


def _user(row):
    item = dict(row)
    item["wallet_initialized"] = item["balance"] is not None
    item["bindings"] = [
        label
        for label, present in (
            ("email", item["email"]),
            ("github", item["github_id"]),
            ("wechat", item["wechat_bound"]),
        )
        if present
    ]
    return item


def _require_user(conn, user_id):
    row = conn.execute(
        f"SELECT {USER_FIELDS} FROM users u LEFT JOIN credit_wallets w ON w.user_id=u.id WHERE u.id=? AND u.id!='__system__'",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "用户不存在")
    return _user(row)


@router.get("")
def users(
    q: str = Query("", max_length=200),
    binding: Literal["", "email", "github", "wechat"] = "",
    created_from: date | None = None,
    created_to: date | None = None,
    min_balance: int | None = None,
    max_balance: int | None = None,
    sort_by: Literal["created_at", "balance", "used"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if created_from and created_to and created_from > created_to:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if (
        min_balance is not None
        and max_balance is not None
        and min_balance > max_balance
    ):
        raise HTTPException(400, "最低余额不能高于最高余额")
    conditions, params = ["u.id!='__system__'"], []
    if q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            "("
            + " OR ".join(
                f"{column} LIKE ? ESCAPE '\\'"
                for column in ("u.id", "u.name", "u.email", "u.github_username")
            )
            + ")"
        )
        params.extend([f"%{term}%"] * 4)
    if binding:
        column = {"email": "email", "github": "github_id", "wechat": "wechat_openid"}[
            binding
        ]
        conditions.append(f"u.{column} IS NOT NULL AND u.{column}!=''")
    for value, condition in (
        (created_from, "substr(u.created_at,1,10)>=?"),
        (created_to, "substr(u.created_at,1,10)<=?"),
        (min_balance, "w.balance>=?"),
        (max_balance, "w.balance<=?"),
    ):
        if value is not None:
            conditions.append(condition)
            params.append(value.isoformat() if isinstance(value, date) else value)
    where = " AND ".join(conditions)
    order = {
        "created_at": "u.created_at",
        "balance": "w.balance",
        "used": "COALESCE(s.credits,0)",
    }[sort_by]
    period = _month()
    with get_db() as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        total = conn.execute(
            f"SELECT COUNT(*) FROM users u LEFT JOIN credit_wallets w ON w.user_id=u.id WHERE {where}",
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT {USER_FIELDS}, COALESCE(s.credits,0) AS used
            FROM users u LEFT JOIN credit_wallets w ON w.user_id=u.id
            LEFT JOIN usage_summary s ON s.user_id=u.id AND s.period=?
            WHERE {where} ORDER BY {order} {sort_order},u.id ASC LIMIT ? OFFSET ?""",
            [period, *params, limit, offset],
        ).fetchall()
    return {
        "items": [_user(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "period": period,
    }


@router.get("/{user_id}")
def user_detail(user_id: str):
    with get_db() as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        user = _require_user(conn, user_id)
        counts = {
            table: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            for table in ("sessions", "documents", "nodes", "quizzes")
        }
        counts["courses"] = conn.execute(
            "SELECT COUNT(DISTINCT generated_from_session_id) FROM documents WHERE user_id=? AND file_type='course_outline'",
            (user_id,),
        ).fetchone()[0]
        profile = conn.execute(
            """SELECT overall_judgement,interests,learning_level,knowledge_scope,dialogue_preference,
            learning_behavior,weakness_summary,strategy_summary,updated_at FROM user_profile_overview WHERE user_id=?""",
            (user_id,),
        ).fetchone()
        rewards = [
            dict(row)
            for row in conn.execute(
                "SELECT kind,SUM(amount) AS amount FROM credit_transactions WHERE user_id=? AND kind!='usage' GROUP BY kind",
                (user_id,),
            )
        ]
    return {
        "user": user,
        "counts": counts,
        "profile": dict(profile) if profile else None,
        "rewards": rewards,
    }


@router.get("/{user_id}/usage")
def user_usage(
    user_id: str, period: str = Query("", pattern=r"^(?:\d{4}-(?:0[1-9]|1[0-2]))?$")
):
    period = period or _month()
    with get_db() as conn:
        conn.execute("PRAGMA query_only=ON")
        _require_user(conn, user_id)
        rows = conn.execute(
            """SELECT e.category,e.scene,COUNT(*) AS calls,SUM(e.credits) AS credits,
            SUM(CASE WHEN d.counts_quota=1 AND e.is_system=0 THEN e.credits ELSE 0 END) AS charged,
            SUM(e.prompt_tokens) AS prompt_tokens,SUM(e.completion_tokens) AS completion_tokens
            FROM usage_events e LEFT JOIN usage_details d ON d.event_id=e.id
            WHERE e.user_id=? AND e.period=? GROUP BY e.category,e.scene ORDER BY credits DESC""",
            (user_id, period),
        ).fetchall()
        used = conn.execute(
            "SELECT credits FROM usage_summary WHERE user_id=? AND period=?",
            (user_id, period),
        ).fetchone()
    return {
        "period": period,
        "used": used[0] if used else 0,
        "items": [dict(row) for row in rows],
    }


_RECORDS = {
    "transactions": (
        "credit_transactions",
        "id,kind,amount,balance_after,created_at",
        "created_at",
    ),
    "redemptions": (
        "credit_card_redemptions",
        "id,amount,balance_after,created_at",
        "created_at",
    ),
    "sessions": (
        "sessions",
        "id,title,topic,status,message_count,created_at",
        "created_at",
    ),
    "documents": ("documents", "id,title,file_type,status,created_at", "created_at"),
    "nodes": ("nodes", "id,title,mastery_level,created_at", "created_at"),
    "quizzes": ("quizzes", "id,score,is_correct,answered_at,created_at", "created_at"),
    "courses": (
        "documents",
        "id,title,status,generated_from_session_id,created_at",
        "created_at",
    ),
}


@router.get("/{user_id}/records")
def user_records(
    user_id: str,
    kind: Literal[
        "transactions",
        "redemptions",
        "sessions",
        "documents",
        "nodes",
        "quizzes",
        "courses",
    ] = "transactions",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    table, fields, order = _RECORDS[kind]
    extra = " AND file_type='course_outline'" if kind == "courses" else ""
    with get_db() as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        _require_user(conn, user_id)
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id=?{extra}", (user_id,)
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT {fields} FROM {table} WHERE user_id=?{extra} ORDER BY {order} DESC,id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
