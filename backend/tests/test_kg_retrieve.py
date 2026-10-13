"""KG 前置检索的回归测试。

全部使用 fake embedder / vector store / repo，不联网、不依赖真实 KG 数据：
  - 空库短路：不发任何 embedding 请求
  - 一次检索只 embed 一次 query（锚定与图扩展共用向量）
  - 入口 probe 嵌入失败不会被 lru_cache 永久缓存
  - 前置检索不阻塞事件循环、超时即放弃、request_id 上下文透传
"""

from __future__ import annotations

import asyncio
import contextvars
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kg import relation_semantics as rs  # noqa: E402
from kg.models import ConceptBrief, RetrieveRequest, RetrieveResponse  # noqa: E402
from kg.services.retrieve_service import RetrieveService  # noqa: E402

_DIM = 8


class _FakeEmbedder:
    dim = _DIM

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def embed_one(self, text: str) -> list[float]:
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("boom")
        return [0.1] * _DIM


class _FakeStore:
    enabled = True

    def __init__(self, hits: list[dict] | None = None) -> None:
        self.hits = hits or []
        self.text_calls: list[tuple] = []
        self.vector_calls: list[tuple] = []

    def search(self, *args, **kwargs):  # 旧路径：会在内部再 embed 一次
        self.text_calls.append(args)
        return []

    def search_by_vector(self, collection, vec, top_k=10):
        self.vector_calls.append((collection, vec, top_k))
        return self.hits


class _FakeConceptRepo:
    def __init__(self, has_data: bool = True, concepts: dict | None = None) -> None:
        self.has_data = has_data
        self.concepts = concepts or {}

    def exists_any_approved(self) -> bool:
        return self.has_data

    def follow_merge(self, concept_id):
        return self.concepts.get(concept_id)


def _concept(cid: str = "c1", name: str = "链式法则"):
    return SimpleNamespace(
        id=cid,
        slug="chain-rule",
        canonical_name=name,
        summary="复合函数求导",
        subject="math",
        difficulty=3,
        access_count=0,
        status="approved",
    )


class _FakeFacetRepo:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def search(self, **kwargs):
        self.kwargs = kwargs
        return []


def _service(repo: _FakeConceptRepo, facet_repo=None) -> RetrieveService:
    svc = object.__new__(RetrieveService)  # 绕开 __init__（不触碰真实 DB）
    svc.concept_repo = repo
    svc.edge_repo = None
    svc.facet_repo = facet_repo
    return svc


def _req() -> RetrieveRequest:
    return RetrieveRequest(
        query="  链式法则怎么用  ", need_facets=False, graph_expand=False
    )


class RetrieveServiceTests(unittest.TestCase):
    def _run(self, svc, emb, store, req=None):
        with (
            patch("kg.services.retrieve_service.get_embedder", return_value=emb),
            patch("kg.services.retrieve_service.get_vector_store", return_value=store),
        ):
            return svc.retrieve(req or _req())

    def test_empty_kg_short_circuits_without_any_embedding(self):
        emb, store = _FakeEmbedder(), _FakeStore()
        resp = self._run(_service(_FakeConceptRepo(has_data=False)), emb, store)

        self.assertEqual(emb.calls, [])
        self.assertEqual(store.vector_calls, [])
        self.assertEqual(store.text_calls, [])
        self.assertTrue(resp.degraded)
        self.assertIn("尚未建档", resp.degraded_reason)
        self.assertEqual(resp.concepts, [])

    def test_query_is_embedded_exactly_once_and_reused_for_anchor(self):
        emb = _FakeEmbedder()
        store = _FakeStore(
            hits=[{"biz_id": "c1", "score": 0.99, "payload": {"concept_id": "c1"}}]
        )
        svc = _service(_FakeConceptRepo(concepts={"c1": _concept()}))

        resp = self._run(svc, emb, store)

        self.assertEqual(emb.calls, ["链式法则怎么用"])  # 只 embed 一次，且已 strip
        self.assertEqual(store.text_calls, [])  # 不再走会二次 embed 的 search()
        self.assertEqual(len(store.vector_calls), 1)
        self.assertEqual(store.vector_calls[0][1], [0.1] * _DIM)  # 复用同一向量
        self.assertFalse(resp.degraded)
        self.assertEqual([c.canonical_name for c in resp.concepts], ["链式法则"])

    def test_facet_recall_reuses_the_same_query_vector(self):
        emb = _FakeEmbedder()
        store = _FakeStore(
            hits=[{"biz_id": "c1", "score": 0.99, "payload": {"concept_id": "c1"}}]
        )
        facets = _FakeFacetRepo()
        svc = _service(_FakeConceptRepo(concepts={"c1": _concept()}), facet_repo=facets)
        req = RetrieveRequest(
            query="链式法则怎么用", need_facets=True, graph_expand=False
        )

        self._run(svc, emb, store, req)

        self.assertEqual(len(emb.calls), 1)  # facet 召回没有再 embed 一次
        self.assertEqual(facets.kwargs["query_vec"], [0.1] * _DIM)

    def test_embedding_failure_degrades_without_retry(self):
        emb, store = _FakeEmbedder(fail=True), _FakeStore()
        resp = self._run(_service(_FakeConceptRepo()), emb, store)

        self.assertEqual(len(emb.calls), 1)  # 失败后不再重试
        self.assertEqual(store.vector_calls, [])
        self.assertEqual(store.text_calls, [])
        self.assertTrue(resp.degraded)
        self.assertTrue(resp.degraded_reason.startswith("query 嵌入失败"))
        self.assertEqual(resp.concepts, [])


class EntryProbeCacheTests(unittest.TestCase):
    def setUp(self):
        rs._entry_relation_vecs.cache_clear()

    def tearDown(self):
        rs._entry_relation_vecs.cache_clear()

    def test_failed_probe_embedding_is_not_cached(self):
        class _Emb:
            dim = 4

            def __init__(self):
                self.calls = 0

            def embed_many(self, texts):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("upstream timeout")
                # 前 5 条（prerequisite）与后 4 条（related）方向不同，保证 z-score 非退化
                return [
                    [1.0, 0.0, 0.0, 0.0] if i < 5 else [0.0, 1.0, 0.0, 0.0]
                    for i in range(len(texts))
                ]

        emb = _Emb()
        rels = ("prerequisite", "related")
        with patch.object(rs, "get_embedder", return_value=emb):
            first = rs.score_relations_from_entry(
                [1.0, 0.0, 0.0, 0.0], "链式法则", relations=rels
            )
            second = rs.score_relations_from_entry(
                [1.0, 0.0, 0.0, 0.0], "链式法则", relations=rels
            )

        self.assertEqual(first, {})  # 瞬时失败：本次不打分
        self.assertEqual(set(second), set(rels))  # 下次能重试成功
        self.assertEqual(emb.calls, 2)  # 失败没有被缓存


class TutorKGPreContextTests(unittest.TestCase):
    @staticmethod
    def _tutor():
        from services.tutor_service import TutorService

        return object.__new__(TutorService)  # 绕开 __init__（不触碰真实 DB）

    def test_timeout_skips_injection_without_blocking_event_loop(self):
        def slow_retrieve(req):
            time.sleep(1.0)
            return RetrieveResponse(degraded=True)

        async def scenario():
            ticks = 0

            async def ticker():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.01)
                    ticks += 1

            task = asyncio.create_task(ticker())
            started = time.monotonic()
            result = await self._tutor()._build_kg_pre_context("链式法则怎么用")
            elapsed = time.monotonic() - started
            task.cancel()
            return result, elapsed, ticks

        with (
            patch("kg.config.KG_CHAT_PRERAG_TIMEOUT_MS", 150),
            patch("services.kg_facade.retrieve", slow_retrieve),
        ):
            result, elapsed, ticks = asyncio.run(scenario())

        self.assertIsNone(result)
        self.assertLess(elapsed, 0.8)  # 到点即走，不等检索线程跑完
        self.assertGreaterEqual(ticks, 5)  # 等待期间事件循环仍在正常调度

    def test_hit_returns_system_message_and_propagates_request_context(self):
        request_id = contextvars.ContextVar("test_request_id", default="-")
        seen: dict[str, str] = {}

        def fake_retrieve(req):
            seen["request_id"] = request_id.get()
            return RetrieveResponse(
                concepts=[
                    ConceptBrief(
                        id="c1",
                        slug="chain-rule",
                        canonical_name="链式法则",
                        summary="复合函数求导",
                    )
                ]
            )

        async def scenario():
            request_id.set("web_req-123")
            return await self._tutor()._build_kg_pre_context("链式法则怎么用")

        with patch("services.kg_facade.retrieve", fake_retrieve):
            msg = asyncio.run(scenario())

        self.assertIsNotNone(msg)
        self.assertEqual(msg.role, "system")
        self.assertIn("链式法则", msg.content)
        self.assertEqual(
            seen["request_id"], "web_req-123"
        )  # 工作线程里 request_id 不丢


if __name__ == "__main__":
    unittest.main()
