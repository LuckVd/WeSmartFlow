"""Idempotent wallet migration. Does not reprice or debit historical usage."""

from database import get_db
from services.credit_wallet import SCHEMA, initialize_existing


def migrate():
    with get_db() as conn:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        initialize_existing(conn)
    print("余额系统已初始化；已有钱包和历史消费保留。")


if __name__ == "__main__":
    migrate()
