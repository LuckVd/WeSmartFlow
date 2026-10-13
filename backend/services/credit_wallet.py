"""Persistent promotional credit wallet. All grants and debits are transactional."""

import hashlib
import secrets
import string
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SIGNUP_CREDITS = 5_000_000
MONTHLY_CREDITS = 1_000_000
MONTHLY_CAP = 5_000_000
GITHUB_CREDITS = 5_000_000
REPOSITORY = "Tencent/WeSmartFlow"

SCHEMA = """
CREATE TABLE IF NOT EXISTS credit_wallets (
    user_id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL,
    last_month TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    unique_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_user ON credit_transactions(user_id, id);
CREATE TABLE IF NOT EXISTS github_oauth_states (
    nonce TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_cards (
    code_hash TEXT PRIMARY KEY,
    code_plain TEXT NOT NULL DEFAULT '',
    code_preview TEXT NOT NULL,
    mode TEXT NOT NULL,
    amount INTEGER NOT NULL,
    max_redemptions INTEGER NOT NULL DEFAULT 0,
    redeemed_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    disabled INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credit_card_email_deliveries (
    card_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    recipient_user_id TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    recipient_email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    attempt_id TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS credit_card_redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT NOT NULL,
    user_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (code_hash, user_id)
);
CREATE TABLE IF NOT EXISTS credit_card_email_history (
    request_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    delivery_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credit_card_redemptions_user
    ON credit_card_redemptions(user_id, id);
"""


class CreditCardError(ValueError):
    """积分卡兑换失败。"""


def ensure_credit_card_columns(conn):
    """补齐旧数据库里的积分卡字段。"""
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(credit_cards)").fetchall()
    }
    if "code_plain" not in columns:
        conn.execute(
            "ALTER TABLE credit_cards ADD COLUMN code_plain TEXT NOT NULL DEFAULT ''"
        )
    if "disabled" not in columns:
        conn.execute(
            "ALTER TABLE credit_cards ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0"
        )


def _clock(now=None):
    dt = now or datetime.now(timezone.utc)
    return dt.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m"), dt.isoformat()


def _post(conn, user_id, kind, amount, key, timestamp):
    if conn.execute(
        "SELECT 1 FROM credit_transactions WHERE unique_key=?", (key,)
    ).fetchone():
        return False
    conn.execute(
        "UPDATE credit_wallets SET balance=balance+? WHERE user_id=?", (amount, user_id)
    )
    balance = conn.execute(
        "SELECT balance FROM credit_wallets WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO credit_transactions(user_id,kind,amount,balance_after,unique_key,created_at) VALUES (?,?,?,?,?,?)",
        (user_id, kind, amount, balance, key, timestamp),
    )
    return True


def _normalize_code(code: str) -> str:
    return "".join(str(code or "").upper().split())


def _code_hash(code: str) -> str:
    normalized = _normalize_code(code)
    if not normalized:
        raise CreditCardError("请输入积分卡兑换码")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _new_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return "WSF-" + "-".join(parts)


def create_credit_card(
    *,
    mode: str,
    amount: int,
    max_redemptions: int = 0,
    expires_at: str | None = None,
    note: str = "",
    created_by: str = "admin",
    recipient_user_id: str | None = None,
    email_request_id: str | None = None,
):
    """管理员生成积分卡。mode=add 表示加积分，mode=reset 表示把余额重置为 amount。"""
    from database import get_db

    mode = (mode or "").strip().lower()
    if mode not in {"add", "reset"}:
        raise CreditCardError("积分卡类型必须是 add 或 reset")
    amount = int(amount or 0)
    if amount <= 0:
        raise CreditCardError("积分数量必须大于 0")
    max_redemptions = max(0, int(max_redemptions or 0))
    if recipient_user_id:
        from services.credit_card_mail import (
            check_mail_config,
            recipient,
            public_delivery,
            find_delivery_request,
        )

        check_mail_config()
        if not email_request_id:
            raise CreditCardError("邮件请求缺少唯一标识")
    timestamp = _clock()[1]

    with get_db() as conn:
        ensure_credit_card_columns(conn)
        conn.execute("BEGIN IMMEDIATE")
        recipient_info = None
        if recipient_user_id:
            existing = find_delivery_request(conn, email_request_id)
            if existing:
                card = conn.execute(
                    "SELECT * FROM credit_cards WHERE code_hash=?",
                    (existing["card_id"],),
                ).fetchone()
                if (
                    not card
                    or existing["recipient_user_id"] != recipient_user_id
                    or (
                        card["mode"],
                        card["amount"],
                        card["max_redemptions"],
                        card["expires_at"],
                        card["note"],
                    )
                    != (
                        mode,
                        amount,
                        max_redemptions,
                        expires_at or None,
                        (note or "")[:200],
                    )
                ):
                    raise CreditCardError("请求已处理，请重新打开生成面板后创建新卡")
                return {
                    "card_id": card["code_hash"],
                    "code": card["code_plain"],
                    "mode": card["mode"],
                    "amount": card["amount"],
                    "delivery": public_delivery(existing),
                }
            recipient_info = recipient(conn, recipient_user_id)
        for _ in range(10):
            code = _new_code()
            digest = _code_hash(code)
            if not conn.execute(
                "SELECT 1 FROM credit_cards WHERE code_hash=?", (digest,)
            ).fetchone():
                conn.execute(
                    """
                    INSERT INTO credit_cards(
                        code_hash, code_plain, code_preview, mode, amount, max_redemptions,
                        redeemed_count, expires_at, note, disabled, created_by, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        digest,
                        code,
                        code[-4:],
                        mode,
                        amount,
                        max_redemptions,
                        0,
                        (expires_at or None),
                        (note or "")[:200],
                        0,
                        created_by,
                        timestamp,
                    ),
                )
                delivery = None
                if recipient_info:
                    conn.execute(
                        """INSERT INTO credit_card_email_deliveries
                        (card_id,request_id,recipient_user_id,recipient_name,recipient_email,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?)""",
                        (
                            digest,
                            email_request_id,
                            recipient_user_id,
                            recipient_info["name"],
                            recipient_info["email"],
                            timestamp,
                            timestamp,
                        ),
                    )
                    delivery = public_delivery(
                        conn.execute(
                            "SELECT * FROM credit_card_email_deliveries WHERE card_id=?",
                            (digest,),
                        ).fetchone()
                    )
                return {
                    "card_id": digest,
                    "delivery": delivery,
                    "code": code,
                    "mode": mode,
                    "amount": amount,
                    "max_redemptions": max_redemptions,
                    "expires_at": expires_at or "",
                    "note": note or "",
                    "created_at": timestamp,
                }
    raise CreditCardError("生成积分卡失败，请重试")


def redeem_credit_card(user_id: str, code: str):
    """普通用户兑换积分卡，同一用户对同一卡码只允许兑换一次。"""
    from database import get_db

    digest = _code_hash(code)
    timestamp = _clock()[1]
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE code_hash=?", (digest,)
        ).fetchone()
        if not card:
            raise CreditCardError("积分卡不存在或兑换码错误")
        if card["disabled"]:
            raise CreditCardError("这张积分卡已停用")
        if card["expires_at"] and card["expires_at"] < timestamp:
            raise CreditCardError("这张积分卡已过期")
        if (
            card["max_redemptions"] > 0
            and card["redeemed_count"] >= card["max_redemptions"]
        ):
            raise CreditCardError("这张积分卡已被兑换完")
        if conn.execute(
            "SELECT 1 FROM credit_card_redemptions WHERE code_hash=? AND user_id=?",
            (digest, user_id),
        ).fetchone():
            raise CreditCardError("你已经兑换过这张积分卡")

        ensure_wallet(conn, user_id)
        before = conn.execute(
            "SELECT balance FROM credit_wallets WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        target_amount = int(card["amount"])
        if card["mode"] == "reset":
            delta = target_amount - int(before)
        else:
            delta = target_amount
        _post(
            conn,
            user_id,
            "credit_card_reset" if card["mode"] == "reset" else "credit_card_add",
            delta,
            f"credit_card:{digest}:{user_id}",
            timestamp,
        )
        after = conn.execute(
            "SELECT balance FROM credit_wallets WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO credit_card_redemptions(
                code_hash, user_id, amount, balance_after, created_at
            ) VALUES (?,?,?,?,?)
            """,
            (digest, user_id, delta, after, timestamp),
        )
        conn.execute(
            "UPDATE credit_cards SET redeemed_count=redeemed_count+1 WHERE code_hash=?",
            (digest,),
        )
        return {
            "ok": True,
            "mode": card["mode"],
            "amount": delta,
            "card_amount": target_amount,
            "balance": after,
            "remaining": max(0, after),
        }


def ensure_wallet(conn, user_id, now=None):
    """Caller must hold a write transaction. Catch up each missed calendar month once."""
    month, timestamp = _clock(now)
    conn.execute(
        "INSERT OR IGNORE INTO credit_wallets VALUES (?,0,?,?)",
        (user_id, month, timestamp),
    )
    _post(conn, user_id, "signup", SIGNUP_CREDITS, f"signup:{user_id}", timestamp)
    row = conn.execute(
        "SELECT balance,last_month FROM credit_wallets WHERE user_id=?", (user_id,)
    ).fetchone()
    last = row["last_month"]
    while last < month:
        year, number = map(int, last.split("-"))
        last = f"{year + (number == 12):04d}-{number % 12 + 1:02d}"
        balance = conn.execute(
            "SELECT balance FROM credit_wallets WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        amount = max(0, min(MONTHLY_CREDITS, MONTHLY_CAP - balance))
        _post(conn, user_id, "monthly", amount, f"monthly:{user_id}:{last}", timestamp)
    conn.execute(
        "UPDATE credit_wallets SET last_month=? WHERE user_id=?",
        (max(month, last), user_id),
    )
    return conn.execute(
        "SELECT balance FROM credit_wallets WHERE user_id=?", (user_id,)
    ).fetchone()[0]


def balance(user_id, now=None):
    from database import get_db

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return ensure_wallet(conn, user_id, now)


def debit(conn, user_id, amount, event_id, now=None):
    ensure_wallet(conn, user_id, now)
    _post(
        conn,
        user_id,
        "usage",
        -max(0, int(amount)),
        f"usage:{event_id}",
        _clock(now)[1],
    )


def grant_github(user_id, github_id):
    from database import get_db

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        linked = conn.execute(
            "SELECT github_id FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not linked or str(linked[0]) != str(github_id):
            raise ValueError("GitHub 身份与当前账户不一致")
        ensure_wallet(conn, user_id)
        # Both the application account and immutable GitHub ID can claim only once.
        if conn.execute(
            "SELECT 1 FROM credit_transactions WHERE user_id=? AND kind='github_star'",
            (user_id,),
        ).fetchone():
            return False
        return _post(
            conn,
            user_id,
            "github_star",
            GITHUB_CREDITS,
            f"github:{github_id}",
            _clock()[1],
        )


def overview(user_id):
    from database import get_db

    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        amount = ensure_wallet(conn, user_id)
        claimed = (
            conn.execute(
                "SELECT 1 FROM credit_transactions WHERE user_id=? AND kind='github_star'",
                (user_id,),
            ).fetchone()
            is not None
        )
        user = conn.execute(
            "SELECT github_id FROM users WHERE id=?", (user_id,)
        ).fetchone()
        entries = [
            dict(r)
            for r in conn.execute(
                "SELECT kind,amount,balance_after,created_at FROM credit_transactions WHERE user_id=? ORDER BY id DESC LIMIT 30",
                (user_id,),
            )
        ]
    return {
        "balance": amount,
        "remaining": max(0, amount),
        "signup_credits": SIGNUP_CREDITS,
        "monthly_credits": MONTHLY_CREDITS,
        "monthly_cap": MONTHLY_CAP,
        "github_reward_credits": GITHUB_CREDITS,
        "github_reward_claimed": claimed,
        "github_linked": bool(user and user[0]),
        "transactions": entries,
    }


def initialize_existing(conn):
    """Old consumption stays historical; migration grants each existing user five yuan once."""
    for row in conn.execute("SELECT id FROM users WHERE id != '__system__'").fetchall():
        ensure_wallet(conn, row[0])
