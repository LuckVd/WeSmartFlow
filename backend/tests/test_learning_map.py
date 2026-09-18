"""Focused regression tests for the evidence-driven learning-map compatibility API.

The first implementation deliberately reads legacy ``nodes`` while new learning
evidence accumulates in separate tables.  These tests keep that bridge safe:
graph output must not render malformed historical edges, the frontier must be
limited by prerequisite readiness, and evidence must become the source of the
learner state rather than directly mutating a legacy node score.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from services import learning_map_service
from services.learning_map_service import LearningMapService


class LearningMapServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "learning-map.db"

        @contextmanager
        def isolated_db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self.db = isolated_db
        self.patches = [
            # Patch both paths: the service imported get_db directly, while
            # production callers and future helper code access database.get_db.
            patch.object(database, "get_db", isolated_db),
            patch.object(learning_map_service, "get_db", isolated_db),
        ]
        for item in self.patches:
            item.start()

        with self.db() as conn:
            conn.executescript(database._CREATE_TABLES_SQL)
            conn.executescript(database._LEARNING_MAP_SCHEMA)
            conn.execute(
                "INSERT INTO users(id,name,password_hash,created_at) VALUES (?,?,?,?)",
                ("learner", "Learner", "x", "2026-09-15T00:00:00+00:00"),
            )
        self.service = LearningMapService()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def seed_node(self, node_id, title, mastery=0.0, relations=None):
        with self.db() as conn:
            conn.execute(
                """
                INSERT INTO nodes (
                    id,user_id,title,description,tags,content,origins,relations,
                    ease_factor,interval,repetitions,due_date,last_review_at,
                    mastery_level,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    node_id,
                    "learner",
                    title,
                    "test concept",
                    json.dumps(["math"]),
                    "{}",
                    "[]",
                    json.dumps(relations or []),
                    2.5,
                    1,
                    0,
                    None,
                    None,
                    mastery,
                    "2026-09-15T00:00:00+00:00",
                    "2026-09-15T00:00:00+00:00",
                ),
            )

    @staticmethod
    def concept(result, node_id):
        return next(item for item in result["concepts"] if item["id"] == node_id)

    def test_brain_excludes_dangling_self_and_duplicate_connections(self):
        self.seed_node("base", "基础概念", mastery=0.8)
        self.seed_node(
            "target",
            "目标概念",
            relations=[
                {"target_node_id": "base", "relation_type": "prerequisite"},
                {"target_node_id": "base", "relation_type": "prerequisite"},
                {"target_node_id": "missing", "relation_type": "prerequisite"},
                {"target_node_id": "target", "relation_type": "related"},
                {"target_node_id": "base", "relation_type": "related"},
            ],
        )

        brain = self.service.build_brain("learner")
        pairs = {
            (edge["source"], edge["target"], edge["relation_type"])
            for edge in brain["connections"]
        }

        self.assertEqual(
            pairs,
            {
                ("target", "base", "prerequisite"),
                ("target", "base", "related"),
            },
        )
        rendered_relations = self.concept(brain, "target")["relations"]
        self.assertEqual(
            rendered_relations,
            [
                {"target_node_id": "base", "relation_type": "prerequisite"},
                {"target_node_id": "base", "relation_type": "related"},
            ],
        )
        self.assertNotIn("missing", {r["target_node_id"] for r in rendered_relations})

    def test_frontier_includes_ready_concept_and_blocks_two_missing_prerequisites(self):
        self.seed_node("solid-base", "已掌握基础", mastery=0.8)
        self.seed_node("weak-base-a", "薄弱前置 A", mastery=0.2)
        self.seed_node("weak-base-b", "薄弱前置 B", mastery=0.1)
        self.seed_node(
            "ready-next",
            "可开启的新节点",
            relations=[
                {"target_node_id": "solid-base", "relation_type": "prerequisite"}
            ],
        )
        self.seed_node(
            "blocked-next",
            "尚不可开启的节点",
            relations=[
                {"target_node_id": "weak-base-a", "relation_type": "prerequisite"},
                {"target_node_id": "weak-base-b", "relation_type": "prerequisite"},
            ],
        )

        frontier = self.service.build_brain("learner")["frontier"]
        by_id = {item["concept_id"]: item for item in frontier}

        self.assertIn("ready-next", by_id)
        self.assertEqual(by_id["ready-next"]["ready_prerequisites"], ["solid-base"])
        self.assertEqual(by_id["ready-next"]["missing_prerequisites"], [])
        self.assertNotIn("blocked-next", by_id)

    def test_evidence_creates_traceable_state_and_replaces_legacy_display_mastery(self):
        # The old node score is intentionally high.  Once verified evidence
        # exists, the brain must display the calculated state instead.
        self.seed_node("derivative", "导数", mastery=0.9)

        first = self.service.record_evidence(
            "learner",
            node_id="derivative",
            source_type="quiz",
            source_id="quiz-1",
            activity_type="explain",
            score=0.8,
            payload={"answer": "瞬时变化率"},
        )
        second = self.service.record_evidence(
            "learner",
            node_id="derivative",
            source_type="experience",
            source_id="lab-1",
            activity_type="transfer",
            score=0.9,
            payload={"artifact_id": "orbit-note"},
        )

        self.assertLess(first["mastery"], 0.9)
        self.assertGreater(second["mastery"], first["mastery"])
        self.assertGreater(second["confidence"], first["confidence"])

        with self.db() as conn:
            state = conn.execute(
                "SELECT * FROM learner_concept_states WHERE user_id=? AND legacy_node_id=?",
                ("learner", "derivative"),
            ).fetchone()
            evidence = conn.execute(
                "SELECT source_type,activity_type,score FROM learning_evidence "
                "WHERE user_id=? AND legacy_node_id=? ORDER BY created_at",
                ("learner", "derivative"),
            ).fetchall()
        self.assertEqual(state["evidence_count"], 2)
        self.assertEqual(state["exposure_count"], 2)
        self.assertGreater(state["explanation_score"], 0)
        self.assertGreater(state["transfer_score"], 0)
        self.assertEqual(
            {row["source_type"] for row in evidence}, {"quiz", "experience"}
        )
        self.assertEqual(
            {row["activity_type"] for row in evidence}, {"explain", "transfer"}
        )

        rendered = self.concept(self.service.build_brain("learner"), "derivative")
        self.assertEqual(rendered["data_status"], "evidenced")
        self.assertEqual(rendered["evidence_count"], 2)
        self.assertEqual(rendered["mastery_level"], second["mastery"])
        self.assertEqual(set(rendered["source_types"]), {"quiz", "experience"})


class LearningMapBatchEvidenceTests(LearningMapServiceTests):
    def test_batch_evidence_skips_unknown_nodes_and_records_each_known_node(self):
        self.seed_node("known-a", "概念 A")
        self.seed_node("known-b", "概念 B")

        records = self.service.record_evidence_for_nodes(
            "learner",
            node_ids=["known-a", "missing", "known-a", "known-b"],
            source_type="course",
            source_id="course-1:chapter-1",
            activity_type="recall",
            score=0.75,
            payload={"chapter_id": 1},
            assessment_method="chapter_quiz",
        )

        self.assertEqual({item["node_id"] for item in records}, {"known-a", "known-b"})
        with self.db() as conn:
            rows = conn.execute(
                "SELECT legacy_node_id,source_type,activity_type FROM learning_evidence "
                "WHERE user_id=? ORDER BY legacy_node_id",
                ("learner",),
            ).fetchall()
        self.assertEqual(
            [
                (row["legacy_node_id"], row["source_type"], row["activity_type"])
                for row in rows
            ],
            [("known-a", "course", "recall"), ("known-b", "course", "recall")],
        )


if __name__ == "__main__":
    unittest.main()
