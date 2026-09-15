"""Persistent promotional credit wallet. All grants and debits are transactional."""

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
"""


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
