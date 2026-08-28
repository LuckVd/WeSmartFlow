"""知识图谱视图整理接口。

核心原则：
- LLM 只生成“简化展示视图”（view_config），不删除、不合并、不重写原始图谱事实。
- 用户可在完整图谱与简化图谱之间切换。
- 图谱更新后通过 source_snapshot 判断 simplified view 是否 stale。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from dependencies import get_current_user
from services.llm_factory import get_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])

VIEW_TYPE = "simplified"
MAX_LLM_NODES = 260

DETAIL_NODE_PATTERNS = [
    "例题",
    "经典题",
    "典型题",
    "练习题",
    "真题",
    "错题",
    "作图法",
    "作图步骤",
    "作图构造",
    "构造法",
    "证明过程",
    "证明思路",
    "证明",
    "证法",
    "推导过程",
    "推导步骤",
    "目标拆解",
    "解题策略",
    "识别策略",
    "判定策略",
    "常见手法",
    "几何来源",
    "来源",
    "本质对比",
    "易错点",
    "应用场景",
    "题型",
]

CORE_CONCEPT_SUFFIXES = [
    "定理",
    "法则",
    "公式",
    "函数",
    "方程",
    "数列",
    "变换",
    "三角形",
    "四边形",
    "多边形",
    "集合",
    "系统",
    "模型",
    "算法",
    "结构",
    "机制",
    "原理",
    "理论",
    "方法",
    "点",
    "线",
    "角",
    "圆",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _node_rows(user_id: str) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, tags, relations, origins, content,
                   mastery_level, updated_at, created_at
              FROM nodes
             WHERE user_id=?
             ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = _loads(d.get("tags"), [])
        d["relations"] = _loads(d.get("relations"), [])
        d["origins"] = _loads(d.get("origins"), [])
        d["content"] = _loads(d.get("content"), {})
        result.append(d)
    return result


def _edge_count(nodes: list[dict[str, Any]]) -> int:
    return sum(len(n.get("relations") or []) for n in nodes)


def _snapshot(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for n in sorted(nodes, key=lambda x: x["id"]):
        rels = n.get("relations") or []
        items.append(
            {
                "id": n["id"],
                "title": n.get("title", ""),
                "updated_at": n.get("updated_at", ""),
                "relations": rels,
            }
        )
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return {
        "node_count": len(nodes),
        "edge_count": _edge_count(nodes),
        "latest_node_updated_at": max(
            (n.get("updated_at") or "" for n in nodes), default=""
        ),
        "node_ids_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def _is_stale(profile: dict[str, Any] | None, current_snapshot: dict[str, Any]) -> bool:
    if not profile:
        return False
    old = _loads(profile.get("source_snapshot"), {})
    return (
        old.get("node_count") != current_snapshot.get("node_count")
        or old.get("edge_count") != current_snapshot.get("edge_count")
        or old.get("latest_node_updated_at")
        != current_snapshot.get("latest_node_updated_at")
        or old.get("node_ids_hash") != current_snapshot.get("node_ids_hash")
    )


def _profile_for_user(user_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM graph_view_profiles WHERE user_id=? AND view_type=?",
            (user_id, VIEW_TYPE),
        ).fetchone()
    return dict(row) if row else None


def _fallback_simplify(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    visible: list[str] = []
    hidden: list[str] = []
    meta: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    for n in nodes:
        title = str(n.get("title") or "")
        strong_detail = any(key in title for key in DETAIL_NODE_PATTERNS)
        core_like = any(title.endswith(suffix) for suffix in CORE_CONCEPT_SUFFIXES)
        # 通用保护：标准概念后缀与短标题优先保留；明确例题/证明/作图步骤才隐藏。
        display_level = "detail" if strong_detail and not core_like else "core"
        node_kind = "detail" if display_level == "detail" else "core_concept"
        item = {
            "node_kind": node_kind,
            "display_level": display_level,
            "confidence": 0.55,
            "reason": "规则兜底：按标题粒度、关系数和来源数判断",
            "classified_at": _utcnow(),
        }
        meta[n["id"]] = item
        if display_level == "detail":
            hidden.append(n["id"])
            reasons[n["id"]] = item["reason"]
        else:
            visible.append(n["id"])
    return {
        "visible_node_ids": visible,
        "hidden_node_ids": hidden,
        "node_meta": meta,
        "hidden_reasons": reasons,
        "groups": [],
        "edge_policy": {
            "show_only_between_visible_nodes": True,
            "hide_related_edges": True,
        },
        "generated_by": "fallback_rules",
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        return json.loads(text[start : end + 1])
    # 兼容模型只返回数组的情况：视为 node_meta 数组
    a0 = text.find("[")
    a1 = text.rfind("]")
    if a0 >= 0 and a1 >= a0:
        arr = json.loads(text[a0 : a1 + 1])
        if isinstance(arr, list):
            return {"node_meta": arr}
    raise ValueError("LLM 未返回 JSON 对象")


def _normalize_view_config(
    raw: dict[str, Any], nodes: list[dict[str, Any]]
) -> dict[str, Any]:
    ids = {n["id"] for n in nodes}
    visible = [x for x in raw.get("visible_node_ids", []) if x in ids]
    hidden = [
        x for x in raw.get("hidden_node_ids", []) if x in ids and x not in visible
    ]
    missing = [x for x in ids if x not in visible and x not in hidden]
    # 保守原则：LLM 漏掉的节点默认展示，不误隐藏。
    visible.extend(missing)

    node_meta = {}
    raw_meta = raw.get("node_meta") or {}
    if isinstance(raw_meta, list):
        raw_meta = {m.get("node_id"): m for m in raw_meta if isinstance(m, dict)}
    now = _utcnow()
    reasons = raw.get("hidden_reasons") or {}
    for nid in ids:
        item = dict(raw_meta.get(nid) or {})
        item.setdefault("node_kind", "core_concept" if nid in visible else "detail")
        item.setdefault("display_level", "core" if nid in visible else "detail")
        item.setdefault("confidence", 0.5)
        item.setdefault("reason", reasons.get(nid) or "LLM 未给出理由，按可见性兜底")
        item["classified_at"] = now
        node_meta[nid] = item

    return {
        "visible_node_ids": visible,
        "hidden_node_ids": hidden,
        "node_meta": node_meta,
        "hidden_reasons": {k: str(v) for k, v in reasons.items() if k in ids},
        "groups": raw.get("groups") or [],
        "edge_policy": raw.get("edge_policy")
        or {"show_only_between_visible_nodes": True, "hide_related_edges": True},
        "generated_by": raw.get("generated_by") or "llm",
    }


async def _llm_simplify(user_id: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """分批调用 LLM 生成简化视图，避免单次输出过长导致模型返回空内容/截断 JSON。"""
    llm = get_llm(user_id)
    hidden: list[str] = []
    reasons: dict[str, str] = {}
    batch_size = 15
    system = """你是通用个人知识图谱整理器，用户可能学习数学、语言、计算机、物理、历史、职业技能等任何内容。
你只生成“简化展示视图”的隐藏节点列表，不修改、不删除、不合并原始图谱。
隐藏：例题、证明过程、操作步骤、案例、易错点、应用细节、解题策略等依附于核心知识的材料碎片。
保留：可独立复习、可迁移、能连接其它知识的核心概念/原理/方法。不确定就保留。
只输出合法 JSON 对象，格式必须是 {"hidden_node_ids":[...],"hidden_reasons":{...}}，不要 markdown、不要解释。"""

    for start in range(0, min(len(nodes), MAX_LLM_NODES), batch_size):
        batch = nodes[start : start + batch_size]
        sample = []
        for n in batch:
            content = n.get("content") or {}
            sample.append(
                {
                    "id": n["id"],
                    "title": n.get("title", ""),
                    "tags": n.get("tags") or [],
                    "relations_count": len(n.get("relations") or []),
                    "origins_count": len(n.get("origins") or []),
                    "aliases": content.get("aliases", []),
                }
            )
        prompt = json.dumps({"nodes": sample}, ensure_ascii=False)
        resp = await llm.async_think(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            config={"temperature": 0.1, "max_tokens": 4000},
        )
        if resp.is_error:
            raise RuntimeError(resp.content)
        try:
            data = _extract_json_object(resp.content)
        except Exception as exc:
            logger.warning(
                "LLM 简化图谱批次解析失败 batch=%s preview=%r err=%s",
                start // batch_size,
                (resp.content or "")[:500],
                exc,
            )
            # 单批失败时用规则兜底该批，整体仍继续。
            data = _fallback_simplify(batch)
        hidden.extend(
            [x for x in data.get("hidden_node_ids", []) if isinstance(x, str)]
        )
        raw_reasons = data.get("hidden_reasons") or {}
        if isinstance(raw_reasons, dict):
            reasons.update({str(k): str(v) for k, v in raw_reasons.items()})

    hidden = list(dict.fromkeys(hidden))
    return _normalize_view_config(
        {
            "hidden_node_ids": hidden,
            "hidden_reasons": reasons,
            "generated_by": "llm_batched",
        },
        nodes,
    )


def _save_profile(
    user_id: str, snapshot: dict[str, Any], view_config: dict[str, Any]
) -> dict[str, Any]:
    now = _utcnow()
    pid = str(uuid4())
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO graph_view_profiles
              (id, user_id, view_type, name, status, source_snapshot, view_config, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            ON CONFLICT(user_id, view_type) DO UPDATE SET
              status='active', source_snapshot=excluded.source_snapshot,
              view_config=excluded.view_config, updated_at=excluded.updated_at
            """,
            (
                pid,
                user_id,
                VIEW_TYPE,
                "简化图谱",
                json.dumps(snapshot, ensure_ascii=False),
                json.dumps(view_config, ensure_ascii=False),
                now,
                now,
            ),
        )
        for node_id, meta in (view_config.get("node_meta") or {}).items():
            row = conn.execute(
                "SELECT content FROM nodes WHERE id=? AND user_id=?", (node_id, user_id)
            ).fetchone()
            if not row:
                continue
            content = _loads(row["content"], {})
            content["graph_meta"] = meta
            conn.execute(
                "UPDATE nodes SET content=?, updated_at=? WHERE id=? AND user_id=?",
                (json.dumps(content, ensure_ascii=False), now, node_id, user_id),
            )
    return _profile_for_user(user_id) or {}


@router.get("/simplified")
def get_simplified_graph(user_id: str = Depends(get_current_user)):
    logger.info("GET /api/graph/simplified user=%s", user_id)
    nodes = _node_rows(user_id)
    current = _snapshot(nodes)
    profile = _profile_for_user(user_id)
    if not profile:
        return {
            "exists": False,
            "stale": False,
            "current_snapshot": current,
            "profile": None,
        }
    return {
        "exists": True,
        "stale": _is_stale(profile, current),
        "current_snapshot": current,
        "profile": {
            **profile,
            "source_snapshot": _loads(profile.get("source_snapshot"), {}),
            "view_config": _loads(profile.get("view_config"), {}),
        },
    }


@router.post("/simplify")
async def simplify_graph(user_id: str = Depends(get_current_user)):
    logger.info("POST /api/graph/simplify user=%s 开始整理图谱", user_id)
    nodes = _node_rows(user_id)
    if not nodes:
        raise HTTPException(400, "当前没有可整理的知识节点")
    current = _snapshot(nodes)
    try:
        view_config = await _llm_simplify(user_id, nodes)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("LLM 简化图谱失败，使用规则兜底: %s", exc, exc_info=True)
        view_config = _fallback_simplify(nodes)
        view_config["warning"] = f"LLM 失败，已使用规则兜底：{exc}"
    profile = _save_profile(user_id, current, view_config)
    logger.info(
        "POST /api/graph/simplify user=%s 完成：可见=%d 隐藏=%d 来源=%s",
        user_id,
        len(view_config.get("visible_node_ids") or []),
        len(view_config.get("hidden_node_ids") or []),
        view_config.get("generated_by"),
    )
    return {
        "ok": True,
        "stale": False,
        "profile": {
            **profile,
            "source_snapshot": _loads(profile.get("source_snapshot"), {}),
            "view_config": _loads(profile.get("view_config"), {}),
        },
        "summary": {
            "visible": len(view_config.get("visible_node_ids") or []),
            "hidden": len(view_config.get("hidden_node_ids") or []),
            "generated_by": view_config.get("generated_by"),
        },
    }
