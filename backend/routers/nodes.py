"""
知识节点路由
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from models import NodeUpdate, NodeReviewResult, NodeSchema, NodeBrief
from services import MemoryService, NodeService
from dependencies import get_current_user
from database import get_db

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


def _loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


@router.get("", response_model=list[NodeBrief])
def list_nodes(user_id: str = Depends(get_current_user)):
    return NodeService().list_nodes(user_id)


@router.get("/due", response_model=list[NodeBrief])
def due_today(user_id: str = Depends(get_current_user)):
    return NodeService().list_due_today(user_id)


@router.get("/{node_id}", response_model=NodeSchema)
def get_node(node_id: str, user_id: str = Depends(get_current_user)):
    node = NodeService().get_node(user_id, node_id)
    if not node:
        raise HTTPException(404, "节点不存在")
    return node


@router.get("/{node_id}/evidence")
def get_node_evidence(node_id: str, user_id: str = Depends(get_current_user)):
    """聚合节点来源证据：创建来源 + 最近测验 + 学习记录。轻量版不改表结构。"""
    node = NodeService().get_node(user_id, node_id)
    if not node:
        raise HTTPException(404, "节点不存在")

    origins = [o.model_dump(mode="json") for o in (node.origins or [])]
    source_details = []
    with get_db() as conn:
        for origin in origins:
            stype = origin.get("source_type")
            sid = origin.get("source_id")
            detail = {
                "source_type": stype,
                "source_id": sid,
                "source_title": origin.get("source_title"),
            }
            if stype == "session":
                row = conn.execute(
                    "SELECT id,title,topic,status,message_count,created_at,ended_at FROM sessions WHERE id=? AND user_id=?",
                    (sid, user_id),
                ).fetchone()
                if row:
                    detail.update(dict(row))
            elif stype == "document":
                row = conn.execute(
                    "SELECT id,title,file_name,file_type,status,total_pages,created_at,processed_at FROM documents WHERE id=? AND user_id=?",
                    (sid, user_id),
                ).fetchone()
                if row:
                    detail.update(dict(row))
            source_details.append(detail)

        quizzes = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, session_id, quiz_type, question, options, correct_answer,
                       explanation, user_answer, is_correct, score, answered_at, created_at
                  FROM quizzes
                 WHERE user_id=? AND node_id=?
                 ORDER BY COALESCE(answered_at, created_at) DESC
                 LIMIT 5
                """,
                (user_id, node_id),
            ).fetchall()
        ]
        for q in quizzes:
            q["options"] = _loads(q.get("options"), [])
            if q.get("session_id"):
                s = conn.execute(
                    "SELECT title, topic FROM sessions WHERE id=? AND user_id=?",
                    (q["session_id"], user_id),
                ).fetchone()
                if s:
                    q["session_title"] = s["topic"] or s["title"]

        study_logs = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, date, minutes, session_id, node_ids, created_at
                  FROM study_logs
                 WHERE user_id=? AND node_ids LIKE ?
                 ORDER BY date DESC, created_at DESC
                 LIMIT 5
                """,
                (user_id, f"%{node_id}%"),
            ).fetchall()
        ]
        for log in study_logs:
            log["node_ids"] = _loads(log.get("node_ids"), [])

    return {
        "node_id": node.id,
        "origins": origins,
        "source_details": source_details,
        "quizzes": quizzes,
        "study_logs": study_logs,
        "memory": node.memory.model_dump(mode="json"),
    }


@router.patch("/{node_id}", response_model=NodeSchema)
def update_node(
    node_id: str,
    data: NodeUpdate,
    user_id: str = Depends(get_current_user),
):
    node = NodeService().update_node(user_id, node_id, data)
    if not node:
        raise HTTPException(404, "节点不存在")
    return node


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: str, user_id: str = Depends(get_current_user)):
    ok = NodeService().delete_node(user_id, node_id)
    if not ok:
        raise HTTPException(404, "节点不存在")


@router.post("/{node_id}/review", response_model=dict)
def review_node(
    node_id: str,
    body: NodeReviewResult,
    user_id: str = Depends(get_current_user),
):
    try:
        return MemoryService().review_node_for_user(user_id, node_id, body.quality)
    except ValueError as e:
        raise HTTPException(404, str(e))
