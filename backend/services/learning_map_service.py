"""学生知识地图：兼容旧节点，同时为证据驱动状态提供统一读写入口。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from database import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw: Any, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


_ACTIVITY_DIMENSION = {
    "recall": "recall_score",
    "predict": "application_score",
    "operate": "application_score",
    "apply": "application_score",
    "explain": "explanation_score",
    "transfer": "transfer_score",
}


class LearningMapService:
    """将旧 ``nodes`` 适配为学习地图，并逐步转向 evidence/state。"""

    def build_brain(self, user_id: str) -> dict[str, Any]:
        with get_db() as conn:
            node_rows = conn.execute(
                """
                SELECT id, title, description, tags, relations, mastery_level,
                       due_date, last_review_at, repetitions, created_at, updated_at
                  FROM nodes WHERE user_id=? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            states = {
                row["legacy_node_id"]: dict(row)
                for row in conn.execute(
                    "SELECT * FROM learner_concept_states WHERE user_id=? AND legacy_node_id IS NOT NULL",
                    (user_id,),
                ).fetchall()
            }
            mappings = {
                row["node_id"]: dict(row)
                for row in conn.execute(
                    "SELECT * FROM legacy_node_concept_map", ()
                ).fetchall()
            }

        concepts: list[dict[str, Any]] = []
        ids = {row["id"] for row in node_rows}
        raw_relations: list[dict[str, str]] = []
        for row in node_rows:
            node_id = row["id"]
            state = states.get(node_id)
            mapping = mappings.get(node_id, {})
            evidence_count = int(state["evidence_count"]) if state else 0
            mastery = _clamp(
                state["mastery"] if state and evidence_count else row["mastery_level"]
            )
            relations = []
            relation_keys: set[tuple[str, str]] = set()
            for relation in _loads(row["relations"], []):
                target = (
                    relation.get("target_node_id")
                    if isinstance(relation, dict)
                    else None
                )
                relation_type = (
                    relation.get("relation_type", "related")
                    if isinstance(relation, dict)
                    else "related"
                )
                key = (str(target), str(relation_type))
                if (
                    not target
                    or target not in ids
                    or target == node_id
                    or key in relation_keys
                ):
                    continue
                relation_keys.add(key)
                relations.append(
                    {"target_node_id": target, "relation_type": relation_type}
                )
                raw_relations.append(
                    {
                        "source": node_id,
                        "target": target,
                        "relation_type": relation_type,
                    }
                )
            concepts.append(
                {
                    "id": node_id,
                    "concept_key": state["concept_key"]
                    if state
                    else f"legacy:{node_id}",
                    "canonical_concept_id": mapping.get("canonical_concept_id")
                    or (state["canonical_concept_id"] if state else None),
                    "title": row["title"],
                    "description": row["description"],
                    "tags": _loads(row["tags"], []),
                    "relations": relations,
                    "mastery_level": mastery,
                    "confidence": _clamp(state["confidence"]) if state else 0.0,
                    "evidence_count": evidence_count,
                    "source_types": _loads(state["source_types"], []) if state else [],
                    "next_action": state["next_action"] if state else "积累学习证据",
                    "due_date": state["due_at"]
                    if state and state["due_at"]
                    else row["due_date"],
                    "data_status": "evidenced" if evidence_count else "legacy_trace",
                }
            )

        connections = self._unique_connections(raw_relations)
        frontier = self._frontier(concepts)
        return {
            "source": "compatibility_nodes",
            "migration_notice": "当前显示历史知识痕迹；新学习活动将逐步沉淀为可追溯证据。",
            "concepts": concepts,
            "connections": connections,
            "frontier": frontier,
            "recommended_path": frontier[:3],
        }

    @staticmethod
    def _unique_connections(relations: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[tuple[str, str, str]] = set()
        result: list[dict[str, str]] = []
        for relation in relations:
            source, target, kind = (
                relation["source"],
                relation["target"],
                relation["relation_type"],
            )
            key = tuple(sorted((source, target))) + (kind,)
            if key in seen:
                continue
            seen.add(key)
            result.append(relation)
        return result

    @staticmethod
    def _frontier(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {concept["id"]: concept for concept in concepts}
        candidates: list[dict[str, Any]] = []
        for concept in concepts:
            if concept["mastery_level"] >= 0.55:
                continue
            prereqs = [
                relation["target_node_id"]
                for relation in concept["relations"]
                if relation["relation_type"] == "prerequisite"
            ]
            ready = [
                pid
                for pid in prereqs
                if by_id.get(pid, {}).get("mastery_level", 0) >= 0.45
            ]
            missing = [pid for pid in prereqs if pid not in ready]
            if len(missing) > 1:
                continue
            reason = (
                "没有标注前置条件，可以从一次短体验开始。"
                if not prereqs
                else f"已具备 {len(ready)}/{len(prereqs)} 个关键前置条件。"
            )
            candidates.append(
                {
                    "concept_id": concept["id"],
                    "title": concept["title"],
                    "readiness": round(len(ready) / len(prereqs), 2)
                    if prereqs
                    else 0.7,
                    "reason": reason,
                    "ready_prerequisites": ready,
                    "missing_prerequisites": missing,
                    "next_action": "开启微体验或继续对话学习",
                }
            )
        return sorted(candidates, key=lambda item: (-item["readiness"], item["title"]))[
            :8
        ]

    def record_evidence(
        self,
        user_id: str,
        *,
        node_id: str,
        source_type: str,
        source_id: str,
        activity_type: str,
        score: float | None,
        payload: dict[str, Any] | None = None,
        assessment_method: str = "rule",
        verified_by: str = "system",
    ) -> dict[str, Any]:
        score_value = _clamp(score if score is not None else 0.5)
        now = _now()
        with get_db() as conn:
            node = conn.execute(
                "SELECT id, mastery_level FROM nodes WHERE id=? AND user_id=?",
                (node_id, user_id),
            ).fetchone()
            if not node:
                raise ValueError("知识节点不存在")
            concept_key = f"legacy:{node_id}"
            state = conn.execute(
                "SELECT * FROM learner_concept_states WHERE user_id=? AND concept_key=?",
                (user_id, concept_key),
            ).fetchone()
            if state:
                current = dict(state)
            else:
                current = {
                    "exposure_count": 0,
                    "recall_score": 0.0,
                    "application_score": 0.0,
                    "explanation_score": 0.0,
                    "transfer_score": 0.0,
                    "evidence_count": 0,
                    "source_types": "[]",
                    "misconceptions": "[]",
                    "canonical_concept_id": None,
                }
            values = {
                key: _clamp(current.get(key, 0.0))
                for key in (
                    "recall_score",
                    "application_score",
                    "explanation_score",
                    "transfer_score",
                )
            }
            dimension = _ACTIVITY_DIMENSION.get(activity_type)
            if dimension:
                values[dimension] = round(
                    values[dimension] * 0.45 + score_value * 0.55, 4
                )
            sources = set(_loads(current.get("source_types"), []))
            sources.add(source_type)
            evidence_count = int(current.get("evidence_count", 0)) + 1
            exposure_count = int(current.get("exposure_count", 0)) + 1
            mastery = round(
                min(
                    1.0,
                    0.15 * min(1.0, exposure_count / 5)
                    + 0.20 * values["recall_score"]
                    + 0.25 * values["application_score"]
                    + 0.25 * values["explanation_score"]
                    + 0.15 * values["transfer_score"],
                ),
                4,
            )
            confidence = round(min(1.0, evidence_count * 0.14 + len(sources) * 0.10), 4)
            due_days = 1 if mastery < 0.35 else 3 if mastery < 0.65 else 7
            due_at = (datetime.now(timezone.utc) + timedelta(days=due_days)).isoformat()
            action = (
                "复习基础直觉"
                if mastery < 0.35
                else "进入应用任务"
                if mastery < 0.65
                else "尝试迁移挑战"
            )
            conn.execute(
                """
                INSERT INTO learner_concept_states (
                    user_id, concept_key, canonical_concept_id, legacy_node_id, discovered_at,
                    exposure_count, recall_score, application_score, explanation_score,
                    transfer_score, mastery, confidence, evidence_count, source_types,
                    misconceptions, next_action, last_evidence_at, due_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id, concept_key) DO UPDATE SET
                    exposure_count=excluded.exposure_count,
                    recall_score=excluded.recall_score,
                    application_score=excluded.application_score,
                    explanation_score=excluded.explanation_score,
                    transfer_score=excluded.transfer_score,
                    mastery=excluded.mastery,
                    confidence=excluded.confidence,
                    evidence_count=excluded.evidence_count,
                    source_types=excluded.source_types,
                    next_action=excluded.next_action,
                    last_evidence_at=excluded.last_evidence_at,
                    due_at=excluded.due_at,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    concept_key,
                    current.get("canonical_concept_id"),
                    node_id,
                    now,
                    exposure_count,
                    values["recall_score"],
                    values["application_score"],
                    values["explanation_score"],
                    values["transfer_score"],
                    mastery,
                    confidence,
                    evidence_count,
                    json.dumps(sorted(sources), ensure_ascii=False),
                    current.get("misconceptions", "[]"),
                    action,
                    now,
                    due_at,
                    now,
                ),
            )
            evidence_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO learning_evidence (
                    id,user_id,concept_key,canonical_concept_id,legacy_node_id,source_type,
                    source_id,activity_type,payload,score,assessment_method,verified_by,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    evidence_id,
                    user_id,
                    concept_key,
                    current.get("canonical_concept_id"),
                    node_id,
                    source_type,
                    source_id,
                    activity_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    score_value,
                    assessment_method,
                    verified_by,
                    now,
                ),
            )
        return {
            "evidence_id": evidence_id,
            "node_id": node_id,
            "mastery": mastery,
            "confidence": confidence,
            "next_action": action,
            "due_at": due_at,
        }

    def record_evidence_for_nodes(
        self,
        user_id: str,
        *,
        node_ids: list[str],
        source_type: str,
        source_id: str,
        activity_type: str,
        score: float | None,
        payload: dict[str, Any] | None = None,
        assessment_method: str = "rule",
        verified_by: str = "system",
    ) -> list[dict[str, Any]]:
        """为一组已关联节点记录同一次学习活动。

        课程章节与课程完成通常只知道覆盖的节点集合。该方法保持每个节点
        独立 evidence，同时跳过已删除或不属于该用户的历史节点。
        """
        results: list[dict[str, Any]] = []
        for node_id in dict.fromkeys(node_ids or []):
            try:
                results.append(
                    self.record_evidence(
                        user_id,
                        node_id=node_id,
                        source_type=source_type,
                        source_id=source_id,
                        activity_type=activity_type,
                        score=score,
                        payload=payload,
                        assessment_method=assessment_method,
                        verified_by=verified_by,
                    )
                )
            except ValueError:
                continue
        return results
