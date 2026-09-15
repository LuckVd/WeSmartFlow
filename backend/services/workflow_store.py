"""基于数据库的 Workflow checkpoint 存储。

让长任务（课程生成、案件锻造）具备**重启续跑**能力：每个节点完成即持久化
输出，进程重启后从最后一个成功节点继续，而非全部重跑。

改造前 ``court/forge.py`` 用 ``daemon=True`` 的裸线程跑长任务，进程退出
任务直接蒸发，用户会永久卡在 pending 状态。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from database import get_db

logger = logging.getLogger(__name__)

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    run_id     TEXT NOT NULL,
    node_id    TEXT NOT NULL,
    output     TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, node_id)
)
"""


def ensure_table() -> None:
    """确保 checkpoint 表存在（幂等）。"""
    try:
        with get_db() as conn:
            conn.execute(_TABLE_DDL)
    except Exception:  # pylint: disable=broad-except
        logger.warning("创建 workflow_checkpoints 表失败", exc_info=True)


class SqlCheckpointStore:
    """把节点输出持久化到 SQLite 的 checkpoint 存储。

    输出以 JSON 文本存储，因此节点输出必须可 JSON 序列化。不可序列化的
    中间对象（如文件句柄）应改为传递路径字符串。
    """

    def __init__(self, auto_create: bool = True):
        if auto_create:
            ensure_table()

    async def load(self, run_id: str) -> Dict[str, Any]:
        """载入该次运行已完成的所有节点输出。"""
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT node_id, output FROM workflow_checkpoints WHERE run_id = ?",
                    (run_id,),
                ).fetchall()
        except Exception:  # pylint: disable=broad-except
            logger.warning("载入 checkpoint 失败 run_id=%s", run_id, exc_info=True)
            return {}

        result: Dict[str, Any] = {}
        for row in rows:
            try:
                result[row["node_id"]] = json.loads(row["output"])
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "checkpoint 输出解析失败，忽略该节点 run_id=%s node=%s",
                    run_id,
                    row["node_id"],
                )
        return result

    async def save(self, run_id: str, node_id: str, output: Dict[str, Any]) -> None:
        """持久化单个节点输出（同一节点重复保存则覆盖）。"""
        try:
            payload = json.dumps(output or {}, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            logger.warning(
                "节点输出无法 JSON 序列化，checkpoint 记为空 node=%s", node_id
            )
            payload = "{}"

        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO workflow_checkpoints (run_id, node_id, output, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(run_id, node_id)
                    DO UPDATE SET output = excluded.output,
                                  created_at = excluded.created_at
                    """,
                    (
                        run_id,
                        node_id,
                        payload,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "保存 checkpoint 失败 run_id=%s node=%s", run_id, node_id, exc_info=True
            )

    async def clear(self, run_id: str) -> None:
        """清除该次运行的所有 checkpoint。"""
        try:
            with get_db() as conn:
                conn.execute(
                    "DELETE FROM workflow_checkpoints WHERE run_id = ?", (run_id,)
                )
        except Exception:  # pylint: disable=broad-except
            logger.warning("清除 checkpoint 失败 run_id=%s", run_id, exc_info=True)


__all__ = ["SqlCheckpointStore", "ensure_table"]
