"""quizzes 表拆分迁移：题目本体 → question_bank，作答记录 → quizzes。

背景
----
旧 quizzes 表把「题目本体」（quiz_type/question/options/correct_answer/explanation）
与「作答记录」（user_answer/is_correct/score/answered_at）混存在一张表里，
同一道题被出 N 次就冗余 N 份题干。

本脚本把两者拆开：
  - question_bank：题目本体，按 (user_id, node_id, question) 去重
  - quizzes：只保留作答字段 + question_id 外键

用法
----
    python backend/migrate_quiz_split.py            # 迁移默认数据库
    python backend/migrate_quiz_split.py --dry-run  # 只看会发生什么
    python backend/migrate_quiz_split.py --db /path/to/x.db

脚本幂等：已迁移过的库（quizzes 已含 question_id 列）会直接跳过。
迁移前自动备份为 <db>.bak-quizsplit-<timestamp>。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_OLD_BODY_COLUMNS = {
    "quiz_type",
    "question",
    "options",
    "correct_answer",
    "explanation",
}


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate(db_path: Path, *, dry_run: bool = False) -> int:
    if not db_path.exists():
        print(f"数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if not _table_exists(conn, "quizzes"):
        print("quizzes 表不存在，无需迁移。")
        return 0

    cols = set(_columns(conn, "quizzes"))
    if "question_id" in cols and not (_OLD_BODY_COLUMNS & cols):
        print("已是新结构（quizzes 含 question_id 且无题目本体列），跳过。")
        return 0
    if not (_OLD_BODY_COLUMNS & cols):
        print(f"quizzes 结构异常，既非旧结构也非新结构: {sorted(cols)}")
        return 1

    rows = [dict(r) for r in conn.execute("SELECT * FROM quizzes").fetchall()]
    print(f"待迁移作答记录: {len(rows)} 行")

    # (user_id, node_id, question) → question_bank.id
    bank: dict[tuple[str, str, str], str] = {}
    bank_rows: list[tuple] = []
    quiz_rows: list[tuple] = []
    skipped = 0

    # 已存在的 question_bank 行先纳入映射，避免重复插入
    if _table_exists(conn, "question_bank"):
        for r in conn.execute(
            "SELECT id, user_id, node_id, question FROM question_bank"
        ).fetchall():
            bank[(r["user_id"], r["node_id"], r["question"])] = r["id"]

    for r in rows:
        question = (r.get("question") or "").strip()
        answer = (r.get("correct_answer") or "").strip()
        if not question or not answer:
            skipped += 1
            continue

        key = (r["user_id"], r["node_id"], question)
        qid = bank.get(key)
        if qid is None:
            qid = str(uuid.uuid4())
            bank[key] = qid
            bank_rows.append(
                (
                    qid,
                    r["user_id"],
                    r["node_id"],
                    "llm",
                    r.get("quiz_type") or "multiple_choice",
                    question,
                    r.get("options"),
                    answer,
                    r.get("explanation") or "",
                    "medium",
                    r.get("created_at") or _utcnow(),
                )
            )

        quiz_rows.append(
            (
                r["id"],
                r["user_id"],
                r["node_id"],
                qid,
                r.get("session_id"),
                r.get("user_answer"),
                r.get("is_correct"),
                r.get("score"),
                r.get("answered_at"),
                r.get("created_at") or _utcnow(),
            )
        )

    print(f"将写入题库: {len(bank_rows)} 道去重后的题目")
    print(f"将写入作答: {len(quiz_rows)} 条")
    if skipped:
        print(f"跳过残缺记录（题干或答案为空）: {skipped} 条")

    if dry_run:
        print("\n--dry-run，未做任何修改。")
        return 0

    backup = db_path.with_suffix(
        db_path.suffix + f".bak-quizsplit-{datetime.now():%Y%m%d%H%M%S}"
    )
    shutil.copy2(db_path, backup)
    print(f"已备份: {backup}")

    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS question_bank (
                    id              TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    node_id         TEXT NOT NULL,
                    source          TEXT NOT NULL DEFAULT 'llm',
                    quiz_type       TEXT NOT NULL,
                    question        TEXT NOT NULL,
                    options         TEXT,
                    correct_answer  TEXT NOT NULL,
                    explanation     TEXT NOT NULL DEFAULT '',
                    difficulty      TEXT NOT NULL DEFAULT 'medium',
                    use_count       INTEGER NOT NULL DEFAULT 0,
                    last_used_at    TEXT,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (node_id) REFERENCES nodes(id),
                    UNIQUE (user_id, node_id, question)
                )
                """
            )
            conn.executemany(
                "INSERT OR IGNORE INTO question_bank "
                "(id,user_id,node_id,source,quiz_type,question,options,"
                "correct_answer,explanation,difficulty,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                bank_rows,
            )

            conn.execute("DROP TABLE IF EXISTS quizzes_new")
            conn.execute(
                """
                CREATE TABLE quizzes_new (
                    id              TEXT PRIMARY KEY,
                    user_id         TEXT NOT NULL,
                    node_id         TEXT NOT NULL,
                    question_id     TEXT NOT NULL,
                    session_id      TEXT,
                    user_answer     TEXT,
                    is_correct      INTEGER,
                    score           REAL,
                    answered_at     TEXT,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (node_id) REFERENCES nodes(id),
                    FOREIGN KEY (question_id) REFERENCES question_bank(id)
                )
                """
            )
            conn.executemany(
                "INSERT INTO quizzes_new "
                "(id,user_id,node_id,question_id,session_id,user_answer,"
                "is_correct,score,answered_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                quiz_rows,
            )
            conn.execute("DROP TABLE quizzes")
            conn.execute("ALTER TABLE quizzes_new RENAME TO quizzes")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_question_bank_pick "
                "ON question_bank(user_id, node_id, quiz_type, use_count)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_quizzes_user_node "
                "ON quizzes(user_id, node_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_quizzes_question "
                "ON quizzes(question_id)"
            )
    finally:
        conn.execute("PRAGMA foreign_keys=ON")

    bad = conn.execute(
        "SELECT COUNT(*) FROM quizzes q "
        "LEFT JOIN question_bank b ON b.id=q.question_id WHERE b.id IS NULL"
    ).fetchone()[0]
    n_bank = conn.execute("SELECT COUNT(*) FROM question_bank").fetchone()[0]
    n_quiz = conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0]
    conn.close()

    if bad:
        print(f"警告：{bad} 条作答记录的 question_id 无法在题库中定位，请检查备份。")
        return 1

    print(
        f"\n迁移完成：question_bank={n_bank} 行，quizzes={n_quiz} 行，外键全部可解析。"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="拆分 quizzes 表：题目本体 / 作答记录")
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
