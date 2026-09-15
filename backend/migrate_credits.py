"""credits 用量体系建表迁移。

为已有数据库补建 usage_events / usage_summary / credit_quotas 表及索引。

背景
----
曾按「调用次数」计费（一次 200 token 与一次 200k token 记为同一次），
成本失真可达三个数量级。现在按 token 与真实定价折算 credits，并保留
场景/模型维度用于成本归因。

用法
----
    python backend/migrate_credits.py            # 迁移默认数据库
    python backend/migrate_credits.py --dry-run  # 只看会做什么
    python backend/migrate_credits.py --db /path/to/x.db

脚本幂等，可重复执行。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS usage_events (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    period            TEXT NOT NULL,
    category          TEXT NOT NULL,
    scene             TEXT NOT NULL DEFAULT 'unknown',
    model             TEXT NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
    cached_tokens     INTEGER NOT NULL DEFAULT 0,
    credits           INTEGER NOT NULL DEFAULT 0,
    is_system         INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_events_user_period
    ON usage_events(user_id, period);
CREATE INDEX IF NOT EXISTS idx_usage_events_scene
    ON usage_events(period, scene);
CREATE INDEX IF NOT EXISTS idx_usage_events_created
    ON usage_events(created_at);

CREATE TABLE IF NOT EXISTS usage_details (
    event_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    units REAL NOT NULL DEFAULT 0,
    pricing_version TEXT NOT NULL DEFAULT '',
    estimated INTEGER NOT NULL DEFAULT 0,
    counts_quota INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS usage_summary (
    user_id  TEXT NOT NULL,
    period   TEXT NOT NULL,
    credits  INTEGER NOT NULL DEFAULT 0,
    calls    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, period)
);

-- 旧月度配额表，保留兼容；新的赠送及余额控制使用 credit_wallets
CREATE TABLE IF NOT EXISTS credit_quotas (
    user_id        TEXT PRIMARY KEY,
    period_credits INTEGER NOT NULL,
    updated_by     TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
"""

_TABLES = ("usage_events", "usage_summary", "credit_quotas", "usage_details")


def _exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def ensure_detail_columns(conn: sqlite3.Connection) -> None:
    """Upgrade early usage_details installations without rewriting history."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(usage_details)")}
    if "estimated" not in columns:
        conn.execute(
            "ALTER TABLE usage_details ADD COLUMN estimated INTEGER NOT NULL DEFAULT 0"
        )


def migrate(db_path: Path, *, dry_run: bool = False) -> int:
    if not db_path.exists():
        print(f"数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    missing = [t for t in _TABLES if not _exists(conn, t)]

    needs_columns = _exists(conn, "usage_details") and "estimated" not in {
        r[1] for r in conn.execute("PRAGMA table_info(usage_details)")
    }
    if not missing and not needs_columns:
        print("credits 相关表均已存在，无需迁移。")
        conn.close()
        return 0

    print(f"待创建表: {', '.join(missing)}")
    if dry_run:
        print("--dry-run，未做任何修改。")
        conn.close()
        return 0

    with conn:
        conn.executescript(_DDL)
        ensure_detail_columns(conn)

    ok = all(_exists(conn, t) for t in _TABLES)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(usage_events)").fetchall()]
    conn.close()

    if not ok:
        print("建表失败，请检查数据库权限。")
        return 1

    print(f"迁移完成。usage_events 字段: {', '.join(cols)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="创建 credits 用量体系相关表")
    parser.add_argument("--db", default="", help="数据库路径，默认取 config.DB_PATH")
    parser.add_argument("--dry-run", action="store_true", help="只预演，不修改")
    args = parser.parse_args()

    if args.db:
        db_path = Path(args.db)
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from config import DB_PATH  # noqa: PLC0415

        db_path = Path(DB_PATH)

    print(f"目标数据库: {db_path}")
    return migrate(db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
