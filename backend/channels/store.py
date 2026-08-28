"""weclaw bot 凭证 & 会话映射存储（SQLite）。

多租户：每个 edu-agent 用户扫码绑定自己的 weclaw bot，凭证按 ``user_id`` 存储。
表在首次使用时惰性创建（``CREATE TABLE IF NOT EXISTS``），不改动 ``init_db``。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from database import get_db

logger = logging.getLogger(__name__)

_SCHEMA_READY = False


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weclaw_bots (
                user_id         TEXT PRIMARY KEY,      -- edu-agent 用户（bot 归属）
                account_id      TEXT NOT NULL,
                token           TEXT NOT NULL,
                base_url        TEXT DEFAULT '',
                cdn_base_url    TEXT DEFAULT '',
                route_tag       TEXT DEFAULT '',
                allow_from      TEXT DEFAULT '["*"]',  -- JSON 数组白名单
                login_user_id   TEXT DEFAULT '',
                get_updates_buf TEXT DEFAULT '',
                enabled         INTEGER DEFAULT 1,
                updated_at      TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weclaw_peer_sessions (
                owner_user_id TEXT NOT NULL,   -- bot 归属的 edu-agent 用户
                peer_id       TEXT NOT NULL,   -- 微信对端 openid/user_id
                session_id    TEXT NOT NULL,   -- edu-agent 会话 id
                updated_at    TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (owner_user_id, peer_id)
            )
            """
        )
    _SCHEMA_READY = True


@dataclass
class WeclawBot:
    user_id: str
    account_id: str
    token: str
    base_url: str = ""
    cdn_base_url: str = ""
    route_tag: str = ""
    allow_from: list[str] = field(default_factory=lambda: ["*"])
    login_user_id: str = ""
    get_updates_buf: str = ""
    enabled: bool = True


def _row_to_bot(row) -> WeclawBot:
    try:
        allow = json.loads(row["allow_from"] or "[]")
        if not isinstance(allow, list):
            allow = ["*"]
    except (TypeError, json.JSONDecodeError):
        allow = ["*"]
    return WeclawBot(
        user_id=row["user_id"],
        account_id=row["account_id"],
        token=row["token"],
        base_url=row["base_url"] or "",
        cdn_base_url=row["cdn_base_url"] or "",
        route_tag=row["route_tag"] or "",
        allow_from=allow or ["*"],
        login_user_id=row["login_user_id"] or "",
        get_updates_buf=row["get_updates_buf"] or "",
        enabled=bool(row["enabled"]),
    )


def upsert_bot(bot: WeclawBot) -> None:
    _ensure_schema()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO weclaw_bots
                (user_id, account_id, token, base_url, cdn_base_url, route_tag,
                 allow_from, login_user_id, get_updates_buf, enabled, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                account_id=excluded.account_id,
                token=excluded.token,
                base_url=excluded.base_url,
                cdn_base_url=excluded.cdn_base_url,
                route_tag=excluded.route_tag,
                allow_from=excluded.allow_from,
                login_user_id=excluded.login_user_id,
                enabled=excluded.enabled,
                updated_at=datetime('now')
            """,
            (
                bot.user_id,
                bot.account_id,
                bot.token,
                bot.base_url,
                bot.cdn_base_url,
                bot.route_tag,
                json.dumps(bot.allow_from, ensure_ascii=False),
                bot.login_user_id,
                bot.get_updates_buf,
                1 if bot.enabled else 0,
            ),
        )


def get_bot(user_id: str) -> Optional[WeclawBot]:
    _ensure_schema()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM weclaw_bots WHERE user_id=?", (user_id,)
        ).fetchone()
    return _row_to_bot(row) if row else None


def list_enabled_bots() -> list[WeclawBot]:
    _ensure_schema()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM weclaw_bots WHERE enabled=1").fetchall()
    return [_row_to_bot(r) for r in rows]


def set_enabled(user_id: str, enabled: bool) -> None:
    _ensure_schema()
    with get_db() as conn:
        conn.execute(
            "UPDATE weclaw_bots SET enabled=?, updated_at=datetime('now') WHERE user_id=?",
            (1 if enabled else 0, user_id),
        )


def save_get_updates_buf(user_id: str, buf: str) -> None:
    _ensure_schema()
    with get_db() as conn:
        conn.execute(
            "UPDATE weclaw_bots SET get_updates_buf=? WHERE user_id=?", (buf, user_id)
        )


def save_login_user_id(user_id: str, login_user_id: str, allow_from: list[str]) -> None:
    _ensure_schema()
    with get_db() as conn:
        conn.execute(
            "UPDATE weclaw_bots SET login_user_id=?, allow_from=? WHERE user_id=?",
            (login_user_id, json.dumps(allow_from, ensure_ascii=False), user_id),
        )


# ── 对端 → edu-agent 会话映射 ────────────────────────────────────


def get_peer_session(owner_user_id: str, peer_id: str) -> Optional[str]:
    _ensure_schema()
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_id FROM weclaw_peer_sessions WHERE owner_user_id=? AND peer_id=?",
            (owner_user_id, peer_id),
        ).fetchone()
    return row["session_id"] if row else None


def set_peer_session(owner_user_id: str, peer_id: str, session_id: str) -> None:
    _ensure_schema()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO weclaw_peer_sessions (owner_user_id, peer_id, session_id, updated_at)
            VALUES (?,?,?, datetime('now'))
            ON CONFLICT(owner_user_id, peer_id) DO UPDATE SET
                session_id=excluded.session_id, updated_at=datetime('now')
            """,
            (owner_user_id, peer_id, session_id),
        )
