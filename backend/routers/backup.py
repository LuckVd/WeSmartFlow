"""数据备份与恢复路由。

第一版目标：导出/导入“当前用户的记忆与知识库”JSON，不导出密码、token、API key、日志。
覆盖范围：
- 主库：用户非敏感资料、结构化画像、知识节点、测验、学习日志、会话元数据、文档元数据、日报/计划缓存
- 文件：data/sessions/{session_id}.json 与 {session_id}_workspace.json
- KG 库：concept / concept_edge / facet / observation / proposal

导入策略：merge into current user。同 id upsert；所有 user_id 重写为当前登录用户。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from config import SESSIONS_DIR
from database import get_db
from dependencies import get_current_user
from kg.database import get_kg_db

router = APIRouter(prefix="/api/backup", tags=["backup"])

SCHEMA_VERSION = 1
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

MAIN_EXPORT_TABLES = {
    "profile": {
        "facts": "user_profile_facts",
        "fact_history": "user_profile_fact_history",
        "overview": "user_profile_overview",
        "skills": "user_profile_skills",
    },
    "knowledge": {
        "nodes": "nodes",
        "quizzes": "quizzes",
        "study_logs": "study_logs",
        "daily_plans": "daily_plans",
        "daily_briefs": "daily_briefs",
    },
    "documents": {
        "metadata": "documents",
    },
    "graph_views": {
        "profiles": "graph_view_profiles",
    },
}

KG_EXPORT_TABLES = {
    "concepts": "concept",
    "concept_edges": "concept_edge",
    "facets": "facet",
    "observations": "observation",
    "proposals": "proposal",
}

MAIN_IMPORT_ORDER = [
    "user_profile_facts",
    "user_profile_fact_history",
    "user_profile_overview",
    "user_profile_skills",
    "nodes",
    "sessions",
    "quizzes",
    "study_logs",
    "daily_plans",
    "daily_briefs",
    "documents",
    "graph_view_profiles",
]

KG_IMPORT_ORDER = ["concept", "concept_edge", "facet", "observation", "proposal"]

MAIN_USER_TABLES = {
    "user_profile_facts",
    "user_profile_fact_history",
    "user_profile_overview",
    "user_profile_skills",
    "nodes",
    "sessions",
    "quizzes",
    "study_logs",
    "daily_plans",
    "daily_briefs",
    "documents",
    "graph_view_profiles",
}

SENSITIVE_MAIN_COLUMNS = {
    "users": {
        "password_hash",
        "wechat_openid",
        "github_id",
        "github_username",
        "email",
    },
    "settings": {"value"},
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(conn, table: str, user_id: str | None = None) -> list[dict[str, Any]]:
    if user_id and table in MAIN_USER_TABLES:
        data = conn.execute(
            f"SELECT * FROM {table} WHERE user_id=?", (user_id,)
        ).fetchall()
    else:
        data = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(r) for r in data]


def _table_info(conn, table: str) -> list[Any]:
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


def _table_columns(conn, table: str) -> list[str]:
    return [r[1] for r in _table_info(conn, table)]


def _table_pk_columns(conn, table: str) -> list[str]:
    info = _table_info(conn, table)
    pk = sorted([(r[5], r[1]) for r in info if r[5]])
    return [name for _idx, name in pk]


def _upsert_row(
    conn, table: str, row: dict[str, Any], *, user_id: str | None = None
) -> None:
    cols = _table_columns(conn, table)
    if not cols:
        return
    cleaned = {k: v for k, v in row.items() if k in cols}
    if user_id and "user_id" in cols:
        cleaned["user_id"] = user_id
    if not cleaned:
        return
    keys = list(cleaned.keys())
    placeholders = ",".join("?" for _ in keys)
    columns = ",".join(keys)
    unique_conflicts = {
        "user_profile_facts": ["user_id", "category", "key"],
        "user_profile_skills": ["user_id", "skill_name"],
        "user_profile_overview": ["user_id"],
        "daily_plans": ["user_id", "date"],
        "daily_briefs": ["user_id", "date"],
        "graph_view_profiles": ["user_id", "view_type"],
        "concept": ["slug"],
        "concept_edge": ["src_id", "dst_id", "relation_type"],
    }
    preferred = unique_conflicts.get(table, [])
    pk_cols = _table_pk_columns(conn, table)
    conflict_cols = (
        preferred
        if preferred and all(c in cleaned for c in preferred)
        else (pk_cols or (["id"] if "id" in cols else []))
    )
    update_keys = [k for k in keys if k not in conflict_cols]
    if not conflict_cols or not update_keys:
        sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
    else:
        updates = ",".join(f"{k}=excluded.{k}" for k in update_keys)
        conflict = ",".join(conflict_cols)
        sql = (
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {updates}"
        )
    conn.execute(sql, tuple(cleaned[k] for k in keys))


def _safe_session_path(session_id: str, suffix: str) -> Path:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"非法 session_id: {session_id}")
    root = SESSIONS_DIR.resolve()
    path = (root / f"{session_id}{suffix}").resolve()
    if path.parent != root:
        raise HTTPException(400, f"非法 session_id 路径: {session_id}")
    return path


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/export")
def export_backup(user_id: str = Depends(get_current_user)):
    """导出当前用户的记忆与知识库为 JSON。"""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "app": "WeSmartFlow",
        "export_type": "memory_knowledge_backup",
        "exported_at": _utcnow(),
        "source_user_id": user_id,
        "notes": {
            "excluded": [
                "password_hash",
                "api keys and settings values",
                "tokens/cookies",
                "logs",
                "document file bodies in data/documents",
            ]
        },
        "user": {},
        "profile": {},
        "knowledge": {},
        "sessions": {"metadata": [], "messages": {}, "workspaces": {}},
        "kg": {},
        "documents": {},
    }

    with get_db() as conn:
        user_row = conn.execute(
            "SELECT id, name, avatar_url, preferences, about, created_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        payload["user"] = dict(user_row) if user_row else {"id": user_id}

        for section, mapping in MAIN_EXPORT_TABLES.items():
            for key, table in mapping.items():
                payload[section][key] = _rows(conn, table, user_id)

        session_rows = _rows(conn, "sessions", user_id)
        payload["sessions"]["metadata"] = session_rows
        for session in session_rows:
            sid = session["id"]
            payload["sessions"]["messages"][sid] = _read_json_file(
                _safe_session_path(sid, ".json"), []
            )
            payload["sessions"]["workspaces"][sid] = _read_json_file(
                _safe_session_path(sid, "_workspace.json"), {}
            )

    with get_kg_db() as conn:
        for key, table in KG_EXPORT_TABLES.items():
            payload["kg"][key] = _rows(conn, table, None)

    content = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"wesmartflow-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
def import_backup(payload: dict[str, Any], user_id: str = Depends(get_current_user)):
    """导入备份 JSON。第一版仅支持 merge into current user。"""
    if not isinstance(payload, dict):
        raise HTTPException(400, "备份文件必须是 JSON 对象")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise HTTPException(400, "不支持的备份 schema_version")
    if payload.get("export_type") != "memory_knowledge_backup":
        raise HTTPException(400, "不是 WeSmartFlow 记忆/知识库备份")

    stats: dict[str, int] = {
        "main_rows": 0,
        "kg_rows": 0,
        "session_message_files": 0,
        "session_workspace_files": 0,
    }

    with get_db() as conn:
        user_payload = payload.get("user") or {}
        if user_payload:
            # 只恢复非认证资料，不碰 password_hash / oauth / email / settings。
            conn.execute(
                """
                UPDATE users
                   SET name=COALESCE(?, name),
                       avatar_url=COALESCE(?, avatar_url),
                       preferences=COALESCE(?, preferences),
                       about=COALESCE(?, about)
                 WHERE id=?
                """,
                (
                    user_payload.get("name"),
                    user_payload.get("avatar_url"),
                    user_payload.get("preferences"),
                    user_payload.get("about"),
                    user_id,
                ),
            )

        for section, mapping in MAIN_EXPORT_TABLES.items():
            section_data = payload.get(section) or {}
            for key, table in mapping.items():
                for row in section_data.get(key) or []:
                    _upsert_row(conn, table, dict(row), user_id=user_id)
                    stats["main_rows"] += 1

        for row in (payload.get("sessions") or {}).get("metadata") or []:
            _upsert_row(conn, "sessions", dict(row), user_id=user_id)
            stats["main_rows"] += 1

    sessions = payload.get("sessions") or {}
    for sid, messages in (sessions.get("messages") or {}).items():
        _write_json_file(
            _safe_session_path(sid, ".json"),
            messages if isinstance(messages, list) else [],
        )
        stats["session_message_files"] += 1
    for sid, workspace in (sessions.get("workspaces") or {}).items():
        _write_json_file(
            _safe_session_path(sid, "_workspace.json"),
            workspace if isinstance(workspace, dict) else {},
        )
        stats["session_workspace_files"] += 1

    with get_kg_db() as conn:
        kg_payload = payload.get("kg") or {}
        for key, table in KG_EXPORT_TABLES.items():
            for row in kg_payload.get(key) or []:
                row = dict(row)
                if table == "observation" and "user_id" in row and row.get("user_id"):
                    row["user_id"] = user_id
                _upsert_row(conn, table, row, user_id=None)
                stats["kg_rows"] += 1

    return {"ok": True, "mode": "merge", "stats": stats}
