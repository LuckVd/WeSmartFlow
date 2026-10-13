"""
RetrieveService：Graph RAG 两段式检索（concept + facet）

流水线：
  Stage 1 [Anchor]   query → 入口 concept（整句 embedding 在 concept 向量库做近邻检索）
                     拿不到强候选时，cos∈[weak, min) 的概念会作为 weak_candidates 返回。
  Stage 2 [Expand]   入口 → 沿"被 query 激活的关系类型"扩展邻居 → 子图
  Stage 3 [Facets]   在子图概念集合内召回相关 facet（教法 + 共性反馈）

设计要点：
  - 原 exhibit / chunk 二级体系退役，统一用 facet 承载所有可检索内容
  - 子图为空 = 知识范围外，直接空（不做"假兜底"）
"""

from __future__ import annotations

import logging
import math
import random
from typing import Optional

from ..config import (
    KG_ANCHOR_GAP_RATIO,
    KG_ANCHOR_MAX_ENTRIES,
    KG_ANCHOR_MIN_SCORE,
    KG_ANCHOR_TOPK,
    KG_ANCHOR_WEAK_SCORE,
    KG_EXPAND_MAX_HOPS,
    KG_EXPAND_SAMPLING,
    KG_EXPAND_TEMPERATURE,
    KG_EXPAND_TOP_P,
    KG_NEIGHBOR_FANOUT,
)
from ..embedder import get_embedder
from ..models import (
    ConceptBrief,
    FacetBrief,
    RetrieveRequest,
    RetrieveResponse,
    SubgraphConcept,
)
from ..relation_semantics import (
    score_relations,
    score_relations_from_entry,
    softmax_normalize,
)
from ..repositories import (
    ConceptEdgeRepository,
    ConceptRepository,
    FacetRepository,
)
from ..vector_store import COLLECTION_CONCEPT, get_vector_store

logger = logging.getLogger(__name__)

_ENTRY_BASE_SCORE = 1.0  # 入口节点固定分


class RetrieveService:
    def __init__(self) -> None:
        self.concept_repo = ConceptRepository()
        self.edge_repo = ConceptEdgeRepository()
        self.facet_repo = FacetRepository()

    # ============================================================
    # 主入口
    # ============================================================

    def retrieve(self, req: RetrieveRequest) -> RetrieveResponse:
        degraded = False
        degraded_reason = ""

        # ---- Stage 0: 空库短路 ----
        # 库里没有任何 approved concept 时，后续的 query embedding、关系 probe
        # 冷启动全是白花钱白等时间，直接返回空结果（原因文案与旧行为一致）。
        # 探测本身失败（None）不阻断，继续走原流程。
        try:
            has_data: Optional[bool] = self.concept_repo.exists_any_approved()
        except Exception:  # pylint: disable=broad-except
            has_data = None
        if has_data is False:
            return RetrieveResponse(
                degraded=True,
                degraded_reason="KG 库内无 approved concept(尚未建档)",
            )

        # ---- query 向量：整次检索只 embed 一次 ----
        # 锚定（Stage 1）与关系打分/图扩展（Stage 2）共用同一个 q_emb。
        embedder = get_embedder()
        q_emb: list[float] = []
        query = (req.query or "").strip()
        if query and embedder and getattr(embedder, "dim", 0) > 0:
            try:
                q_emb = embedder.embed_one(query)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("retrieve: query 嵌入失败，无法锚定入口 err=%s", exc)
                q_emb = []
                degraded = True
                degraded_reason = f"query 嵌入失败: {exc}"

        # ---- Stage 1: 锚定入口 ----
        entry_briefs, weak_candidates, anchor_reason = self._anchor(req, q_emb)
        entry_ids = [c.id for c in entry_briefs]
        if not entry_briefs:
            degraded = True
            degraded_reason = degraded_reason or (
                anchor_reason or "未找到符合阈值的入口概念"
            )

        # 记录被走过的边,稍后异步累加 support_count
        traversed_edge_ids: list[str] = []

        # ---- 关系语义打分 ----
        # 仅图扩展模式需要关系语义（graph_expand=False 时不触发 probe 构建）
        rel_scores = score_relations(q_emb) if (req.graph_expand and q_emb) else {}
        rel_dist = softmax_normalize(rel_scores, temperature=0.08)

        # ---- Stage 2: 图扩展 ----
        neighbor_budget = max(0, req.max_subgraph_size - len(entry_ids))
        if entry_ids and req.graph_expand and q_emb and neighbor_budget > 0:
            subgraph_nodes = self._expand_subgraph(
                entry_briefs=entry_briefs,
                q_emb=q_emb,
                hops=max(1, min(req.expand_hops, KG_EXPAND_MAX_HOPS)),
                neighbor_budget=neighbor_budget,
                traversed_edge_ids=traversed_edge_ids,
            )
        else:
            subgraph_nodes = [
                SubgraphConcept(concept=c, is_entry=True, score=_ENTRY_BASE_SCORE)
                for c in entry_briefs
            ]

        subgraph_concept_ids = [n.concept.id for n in subgraph_nodes]

        # ---- Stage 3: 召回 facet ----
        facets: list[FacetBrief] = []
        if req.need_facets and subgraph_concept_ids:
            facets = self._select_facets(
                req=req, subgraph_concept_ids=subgraph_concept_ids, q_emb=q_emb
            )

        # ---- 反馈强化:被走过的 edge 累加 support_count(失败不影响响应) ----
        if traversed_edge_ids:
            self._increment_edge_support_async(traversed_edge_ids)

        # ---- 反馈强化:被进入子图的出口概念累加 access_count(概念级检索强度) ----
        accessed_concept_ids = [n.concept.id for n in subgraph_nodes if not n.is_entry]
        if accessed_concept_ids:
            self._increment_concept_access_async(accessed_concept_ids)

        return RetrieveResponse(
            concepts=entry_briefs,
            facets=facets,
            subgraph=subgraph_nodes,
            relation_weights=rel_scores,
            relation_dist=rel_dist,
            weak_candidates=weak_candidates,
            degraded=degraded,
            degraded_reason=degraded_reason,
        )

    # ============================================================
    # Stage 1: 入口锚定
    # ============================================================

    def _anchor(
        self, req: RetrieveRequest, q_emb: list[float]
    ) -> tuple[list[ConceptBrief], list[ConceptBrief], str]:
        """入口锚定。``q_emb`` 为调用方已算好的 query 向量（避免重复 embed）。"""
        results: list[ConceptBrief] = []
        weak: list[ConceptBrief] = []
        seen: set[str] = set()

        query = (req.query or "").strip()
        if not query:
            return results, weak, "query 为空"

        store = get_vector_store()
        if not store.enabled:
            logger.warning("_anchor: vector store 未启用，无法锚定入口")
            return results, weak, "向量库未启用（embedder 不可用）"

        if not q_emb:
            # query 嵌入失败/不可用：原因已由 retrieve 记录，这里不再重试 embed
            return results, weak, "query 向量不可用，无法锚定入口"

        min_score = (
            req.anchor_min_score
            if req.anchor_min_score is not None
            else KG_ANCHOR_MIN_SCORE
        )
        max_entries = (
            req.anchor_max_entries
            if req.anchor_max_entries is not None
            else KG_ANCHOR_MAX_ENTRIES
        )

        try:
            hits = store.search_by_vector(
                COLLECTION_CONCEPT, q_emb, top_k=KG_ANCHOR_TOPK
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("_anchor: 向量召回失败 err=%s", exc)
            return results, weak, f"向量召回异常: {exc}"

        if not hits:
            # 区分两种空召回:库内根本没 concept vs 召回路径异常但无报错
            try:
                with_data = self.concept_repo.exists_any_approved()
            except Exception:  # pylint: disable=broad-except
                with_data = None
            if with_data is False:
                return results, weak, "KG 库内无 approved concept(尚未建档)"
            return results, weak, "向量库无任何返回"

        top_score = float(hits[0]["score"])
        score_floor = max(min_score, top_score * KG_ANCHOR_GAP_RATIO)

        for h in hits:
            score = float(h["score"])
            cid = h["payload"].get("concept_id") or h["biz_id"]
            if not cid or cid in seen:
                continue
            c = self.concept_repo.follow_merge(cid)
            if not c or c.status != "approved":
                continue
            brief = _to_brief(c)

            if score >= score_floor and len(results) < max_entries:
                seen.add(c.id)
                results.append(brief)
            elif score >= KG_ANCHOR_WEAK_SCORE:
                if len(weak) < 5:
                    seen.add(c.id)
                    weak.append(brief)

        reason = ""
        if not results:
            reason = (
                f"top1 cos={top_score:.3f} 低于阈值 {min_score:.2f}"
                if top_score < min_score
                else "无候选通过筛选"
            )
        else:
            weak = []
        return results, weak, reason

    # ============================================================
    # Stage 2: 图扩展
    # ============================================================

    def _sample_edges(self, cands: list, k: int) -> list:
        """softmax(得分/温度) → top-p 核采样 → ×k → 逐边独立伯努利试验。

        cands : [(src_id, edge, nbr_id, nbr, score), ...]
        k     : 本跳 frontier 中产生候选边的入口数
        返回被采样的子集（同一 nbr_id 可能出现多次，调用方自行去重取最优）。
        score 在元组最后一项（c[-1]），nbr 对象随元组透传，调用方直接复用。

        ×k 的作用：Σp=1 是"互斥选择题"形式（谁来走这条边），而"每条边值不值得走"
        本该是独立判断。乘 k 后，每跳期望新增节点数 ≈ k（每个入口约 1 个）；
        不乘时，frontier 越大、每个入口反而越探不动。
        """
        if not cands:
            return []
        scores = [c[-1] for c in cands]
        mx = max(scores)
        temp = max(KG_EXPAND_TEMPERATURE, 1e-6)
        weights = [math.exp((s - mx) / temp) for s in scores]
        total = sum(weights)
        if total <= 0:
            return []
        probs = [(c, w / total) for c, w in zip(cands, weights)]

        top_p = KG_EXPAND_TOP_P
        if top_p < 1.0:
            probs.sort(key=lambda cp: -cp[1])
            kept: list = []
            acc = 0.0
            for cand, p in probs:
                kept.append((cand, p))
                acc += p
                if acc >= top_p:
                    break
            kept_total = sum(p for _, p in kept)
            probs = [(c, p / kept_total) for c, p in kept] if kept_total > 0 else []

        return [cand for cand, p in probs if random.random() < min(p * k, 1.0)]

    def _expand_subgraph(
        self,
        entry_briefs: list[ConceptBrief],
        q_emb: list[float],
        hops: int,
        neighbor_budget: int,
        traversed_edge_ids: Optional[list[str]] = None,
    ) -> list[SubgraphConcept]:
        nodes: dict[str, SubgraphConcept] = {}
        for c in entry_briefs:
            nodes[c.id] = SubgraphConcept(
                concept=c, is_entry=True, score=_ENTRY_BASE_SCORE
            )

        if neighbor_budget <= 0 or not q_emb:
            return list(nodes.values())

        # id → 概念名，多跳时随邻居入队扩展
        name_by_id: dict[str, str] = {
            c.id: (c.canonical_name or c.slug) for c in entry_briefs
        }

        neighbor_pool: dict[str, SubgraphConcept] = {}
        neighbor_via_edge: dict[str, str] = {}
        frontier: list[str] = [c.id for c in entry_briefs]

        for hop in range(hops):
            # ── 阶段 A：取本跳全部边 ──
            hop_edges = []
            for src_id in frontier:
                for e in self.edge_repo.neighbors(
                    concept_id=src_id,
                    relation_types=None,
                    direction="both",
                    limit=KG_NEIGHBOR_FANOUT,
                ):
                    hop_edges.append((src_id, e))

            if not hop_edges:
                break

            hop_relations = tuple(
                sorted({e.relation_type for _, e in hop_edges if e.relation_type})
            )
            if not hop_relations:
                break

            # ── 阶段 B：z + ln(1+access_count) 复合得分 ──
            z_cache: dict[str, dict[str, float]] = {}
            # nbr_id → ConceptSchema（带 access_count），follow_merge 带缓存避免重复查
            nbr_concept_cache: dict[str, Optional[object]] = {}
            cands: list = []

            for src_id, e in hop_edges:
                nbr_id = e.dst_id if e.src_id == src_id else e.src_id
                if nbr_id == src_id or nbr_id in nodes:
                    continue

                # 出口概念：follow_merge 解析到生效概念（带 access_count）
                if nbr_id not in nbr_concept_cache:
                    nbr_concept_cache[nbr_id] = self.concept_repo.follow_merge(nbr_id)
                nbr = nbr_concept_cache[nbr_id]
                if not nbr or nbr.status != "approved":
                    continue

                if src_id not in z_cache:
                    entry_name = name_by_id.get(src_id, src_id)
                    z = score_relations_from_entry(
                        q_emb, entry_name, relations=hop_relations
                    )
                    z_cache[src_id] = z if z else {}

                z_rel = z_cache[src_id].get(e.relation_type, 0.0)
                # ln(1 + access_count)：出口节点的概念级检索强度（被进入子图次数）。
                # access_count=0 时 ln(1)=0（中性起点）；被检索越多，该节点越倾向被展开。
                score = z_rel + math.log(1.0 + float(getattr(nbr, "access_count", 0)))
                cands.append((src_id, e, nbr_id, nbr, score))

            if not cands:
                break

            # ── 阶段 C：选边（概率采样 or 确定性 top-N）──
            k = len({c[0] for c in cands})

            if KG_EXPAND_SAMPLING:
                # _sample_edges 透传完整 5 元组，用最后一项 score 计算采样概率
                picked = self._sample_edges(cands, k=k)
            else:
                # 确定性：去重后按得分取 top-N
                best: dict[str, tuple] = {}
                for c in cands:
                    if c[2] not in best or c[4] > best[c[2]][4]:
                        best[c[2]] = c
                picked = sorted(best.values(), key=lambda c: -c[4])[:neighbor_budget]

            if not picked:
                break

            # ── 阶段 D：去重取最优路径，加入子图 ──
            # 概念对象已在阶段 B follow_merge 拿到，这里直接复用，不再重复查询
            best_by_nbr: dict[str, tuple] = {}
            for c in picked:
                nbr_id = c[2]
                if nbr_id not in best_by_nbr or c[-1] > best_by_nbr[nbr_id][-1]:
                    best_by_nbr[nbr_id] = c

            next_frontier: list[str] = []
            for nbr_id, cand in best_by_nbr.items():
                src_id, e, _nbr_id, nbr, score = cand
                if nbr_id in nodes or nbr_id in neighbor_pool:
                    continue

                nbr_brief = _to_brief(nbr)
                neighbor_pool[nbr_id] = SubgraphConcept(
                    concept=nbr_brief,
                    is_entry=False,
                    via_relation=e.relation_type,
                    via_concept_id=src_id,
                    score=score,
                )
                neighbor_via_edge[nbr_id] = e.id
                next_frontier.append(nbr_id)
                name_by_id[nbr_id] = nbr_brief.canonical_name or nbr_brief.slug

            if not next_frontier:
                break
            frontier = list(dict.fromkeys(next_frontier))

        top_neighbors = sorted(neighbor_pool.values(), key=lambda n: -n.score)[
            :neighbor_budget
        ]
        if traversed_edge_ids is not None:
            for n in top_neighbors:
                eid = neighbor_via_edge.get(n.concept.id)
                if eid:
                    traversed_edge_ids.append(eid)
        return list(nodes.values()) + top_neighbors

    # ============================================================
    # Stage 3: facet 召回
    # ============================================================

    def _select_facets(
        self,
        req: RetrieveRequest,
        subgraph_concept_ids: list[str],
        q_emb: Optional[list[float]] = None,
    ) -> list[FacetBrief]:
        per_concept = max(1, req.top_k_facets_per_concept)
        # 总预算 = 每个概念配额 × 概念数(再做向量重排,留点余量)
        total_budget = per_concept * max(1, len(subgraph_concept_ids))

        return self.facet_repo.search(
            query=req.query,
            concept_ids=subgraph_concept_ids,
            kinds=req.facet_kinds or None,
            top_k=total_budget,
            per_concept_cap=per_concept,
            # 复用本次检索已算好的 query 向量，不在 facet 召回里重复 embed
            query_vec=q_emb or None,
        )

    # ============================================================
    # 反馈强化:异步累加 edge support_count
    # ============================================================

    def _increment_edge_support_async(self, edge_ids: list[str]) -> None:
        """开后台线程累加被本次检索走过的边 support_count。

        - 不阻塞读路径,失败仅打 warning;
        - 单线程处理一次性的小列表,避免引入复杂调度。
        """
        import threading

        def _worker(ids: list[str]) -> None:
            for eid in ids:
                try:
                    self.edge_repo.increment_support(eid, by=1)
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning(
                        "retrieve: edge support_count 累加失败 eid=%s err=%s",
                        eid,
                        exc,
                    )

        try:
            t = threading.Thread(target=_worker, args=(list(edge_ids),), daemon=True)
            t.start()
        except Exception:  # pylint: disable=broad-except
            logger.exception("retrieve: 启动 support_count 累加线程失败,跳过")

    def _increment_concept_access_async(self, concept_ids: list[str]) -> None:
        """开后台线程批量累加出口概念的 access_count（概念级检索强度）。

        与 edge.support_count 同样异步、失败仅打 warning、不阻塞读路径。
        用一次批量 UPDATE，比逐条快得多。
        """
        import threading

        def _worker(ids: list[str]) -> None:
            try:
                self.concept_repo.increment_access(ids, by=1)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("retrieve: concept access_count 累加失败 err=%s", exc)

        try:
            t = threading.Thread(target=_worker, args=(list(concept_ids),), daemon=True)
            t.start()
        except Exception:  # pylint: disable=broad-except
            logger.exception("retrieve: 启动 access_count 累加线程失败,跳过")


# ============================================================
# 工具函数
# ============================================================


def _to_brief(c) -> ConceptBrief:
    return ConceptBrief(
        id=c.id,
        slug=c.slug,
        canonical_name=c.canonical_name,
        summary=c.summary,
        subject=c.subject,
        difficulty=c.difficulty,
        access_count=getattr(c, "access_count", 0),
    )
