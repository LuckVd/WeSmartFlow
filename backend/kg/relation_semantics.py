"""
关系语义嵌入模块

核心思想：
  把"图上的边类型"和"内容类型（展示 vs 证据）"也看作可被 embedding 的语义。
  query 来了之后，用同一个 embedder 把 query 向量化，再与各类语义 probe 的均值向量
  做余弦相似度，得到一张连续的"权重表"，驱动 Graph RAG 的扩展和内容选取。

为什么这么做：
  - 复用 query embedding（Stage 1 已经算过），增量成本几乎为 0
  - 输出连续权重，比离散意图分类更细腻、天然支持复合意图
  - 易扩展：加新关系只要写一段 probe，无需训练
  - 全链路只用一个核心算子：余弦相似度

probe 设计原则：
  - 每个语义类型给 4~6 句"用户可能怎么问"
  - 用学生口语 + 一点数学术语，不要写抽象定义
  - 多角度覆盖（动机/操作/对比/疑问），降低单句偏置
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

from .embedder import get_embedder

logger = logging.getLogger(__name__)

_SD_EPS = 1e-9


# ============================================================
# 关系类型 probe
# ============================================================
# 注：覆盖 models.VALID_RELATION_TYPES 中定义的全部关系类型
# 设计 query 时刻意写"学生口吻"，避免学术化句子带偏 embedding。
# ============================================================

RELATION_PROBES: dict[str, list[str]] = {
    "prerequisite": [
        "学这个之前需要先掌握什么",
        "这个概念依赖哪些基础知识",
        "前置知识有哪些",
        "学之前要会什么",
        "需要先学会哪些内容",
    ],
    "part_of": [
        "这个是哪一章的内容",
        "属于哪个大主题",
        "整体框架里它在哪个位置",
        "它是更大概念的一部分吗",
    ],
    "related": [
        "和这个相关的概念有哪些",
        "顺带可以了解什么",
        "周边知识点",
        "类似话题",
    ],
    "contrasts": [
        "这两个有什么区别",
        "对比一下",
        "容易混淆的概念",
        "和它相反的是什么",
        "区别和联系",
    ],
    "application_of": [
        "怎么用这个解题",
        "实际应用是什么",
        "怎么用在实际问题里",
        "举个应用例子",
        "用在哪里",
    ],
    "special_case_of": [
        "这是不是某个更一般概念的特殊情况",
        "特例",
        "更一般的形式是什么",
    ],
    "generalizes": [
        "这个能推广到什么",
        "更一般的版本",
        "推广形式",
        "扩展形式",
    ],
    "equivalent_to": [
        "这两个是不是等价的",
        "另一种说法",
        "同义概念",
        "另一种表达",
    ],
}


# ============================================================
# 内容类型 probe（展示 vs 证据）
# ============================================================
# 在我们的 schema 里：
#   exhibit (markdown_note/quiz/viz/card/...) = 展示型（讲解、直觉、例子）
#   chunk   (来自 textbook/paper/article)      = 证据型（严谨表述、推导、出处）
# ============================================================

CONTENT_PROBES: dict[str, list[str]] = {
    "display": [
        "通俗讲解一下",
        "直观理解",
        "举个例子",
        "怎么操作",
        "给我讲讲",
        "怎么用",
        "是什么意思",
    ],
    "evidence": [
        "严格定义是什么",
        "为什么成立",
        "怎么证明",
        "定理表述",
        "课本上怎么说",
        "原文",
        "理论依据",
        "推导过程",
    ],
}


# ============================================================
# 内部工具
# ============================================================


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _mean_vec(vecs: list[list[float]]) -> list[float]:
    """求一组向量的逐元素平均，跳过空向量。"""
    valid = [v for v in vecs if v]
    if not valid:
        return []
    dim = len(valid[0])
    out = [0.0] * dim
    for v in valid:
        for i, x in enumerate(v):
            out[i] += x
    n = float(len(valid))
    return [x / n for x in out]


# ============================================================
# 单例：离线一次性计算 probe 均值向量
# ============================================================


class _SemanticProbes:
    """离线建表：每个类型 → 多条 probe 的均值 embedding。"""

    def __init__(self) -> None:
        self.relation_emb: dict[str, list[float]] = {}
        self.content_emb: dict[str, list[float]] = {}
        self.enabled: bool = False
        self._build()

    def _build(self) -> None:
        embedder = get_embedder()
        if not embedder or getattr(embedder, "dim", 0) <= 0:
            logger.info("relation_semantics: embedder 未启用，关系语义打分关闭")
            self.enabled = False
            return

        # 一次性把所有 probe 文本批量送进 embedder，省 API 调用
        flat_texts: list[str] = []
        index_map: list[tuple[str, str]] = []  # [(category, key)]，每条 probe 对应

        for rel, probes in RELATION_PROBES.items():
            for p in probes:
                flat_texts.append(p)
                index_map.append(("relation", rel))

        for ct, probes in CONTENT_PROBES.items():
            for p in probes:
                flat_texts.append(p)
                index_map.append(("content", ct))

        try:
            vecs = embedder.embed_many(flat_texts)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("relation_semantics: probe 嵌入失败 err=%s", exc)
            self.enabled = False
            return

        # 按 (category, key) 聚合
        bucket: dict[tuple[str, str], list[list[float]]] = {}
        for (cat, key), v in zip(index_map, vecs):
            bucket.setdefault((cat, key), []).append(v)

        for (cat, key), vs in bucket.items():
            mean = _mean_vec(vs)
            if not mean:
                continue
            if cat == "relation":
                self.relation_emb[key] = mean
            else:
                self.content_emb[key] = mean

        self.enabled = bool(self.relation_emb and self.content_emb)
        if self.enabled:
            logger.info(
                "relation_semantics: 已加载 %d 种关系 probe + %d 种内容 probe",
                len(self.relation_emb),
                len(self.content_emb),
            )


@lru_cache(maxsize=1)
def get_probes() -> _SemanticProbes:
    return _SemanticProbes()


def reload_probes() -> _SemanticProbes:
    """清空 probe 缓存并强制重新构建。

    什么时候调:
      - 切换 embedder 模型/维度后(env 改了,但进程没重启)
      - reindex 脚本在 vec_store DROP 重建后,probe 也需要重新 embed
      - 单元测试要在不重启进程的情况下重置状态

    这里直接清 lru_cache,下次 get_probes() 会触发重新 embed。
    """
    get_probes.cache_clear()
    _entry_relation_vecs.cache_clear()
    return get_probes()


# ============================================================
# 对外打分 API
# ============================================================


def score_relations(query_emb: list[float]) -> dict[str, float]:
    """对 query 给出每种关系类型的余弦相似度。
    返回值范围 [-1, 1]，未启用时返回空 dict。
    """
    probes = get_probes()
    if not probes.enabled or not query_emb:
        return {}
    return {rel: _cos(query_emb, vec) for rel, vec in probes.relation_emb.items()}


def score_content_types(query_emb: list[float]) -> dict[str, float]:
    """对 query 给出每种内容类型的余弦相似度。
    返回 {'display': float, 'evidence': float}；未启用时返回空 dict。
    """
    probes = get_probes()
    if not probes.enabled or not query_emb:
        return {}
    return {ct: _cos(query_emb, vec) for ct, vec in probes.content_emb.items()}


def softmax_normalize(
    scores: dict[str, float], temperature: float = 0.1
) -> dict[str, float]:
    """把余弦相似度（差距通常很小）归一化为概率分布。
    温度越低，分布越尖锐——更倾向于挑出最相关的关系/内容类型。
    """
    if not scores:
        return {}
    max_s = max(scores.values())
    exps = {
        k: math.exp((v - max_s) / max(1e-6, temperature)) for k, v in scores.items()
    }
    z = sum(exps.values()) or 1.0
    return {k: v / z for k, v in exps.items()}


# ============================================================
# 入口条件化的关系语义打分
# ============================================================


@lru_cache(maxsize=1024)
def _entry_relation_vecs(
    entry_name: str, relations: tuple[str, ...]
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    """把「入口概念名 + 每条 probe 文本」逐条嵌入，按关系取未归一化均值向量。

    返回 ``((relation, mean_vec), …)``（不可变元组，满足 lru_cache 要求）。

    ★ 调用方必须传 **排序去重** 后的 ``relations`` 元组（缓存正确性）。
      同一 relations 集合的不同顺序会各占一个缓存槽并重复 embed，
      ``tuple(sorted(set(...)))`` 是标准写法。

    ★ 均值向量**不归一化**：消费方 ``score_relations_from_entry`` 用 ``_cos``
      （数量 A：先逐条算余弦再平均），端点鲁棒（不依赖 embedder 输出已归一化）。

    ★ 关系无 probe 时退回关系名本身（``RELATION_PROBES.get(rel) or [rel]``），
      保留与固定 8 种关系的兼容，也防御未来自由命名关系。

    ★ embedding 失败时**直接抛出**而不是返回 ``()``：``lru_cache`` 不缓存异常，
      下次检索可以重试；若在此吞掉异常返回空元组，一次瞬时超时会让该入口概念
      的关系打分在整个进程生命周期内静默失效。吞异常放在调用方
      :func:`score_relations_from_entry`。
    """
    embedder = get_embedder()
    if not embedder or getattr(embedder, "dim", 0) <= 0:
        return ()

    flat: list[str] = []
    index: list[str] = []
    for rel in relations:
        for p in RELATION_PROBES.get(rel) or [rel]:
            flat.append(f"{entry_name} {p}")
            index.append(rel)

    if not flat:
        return ()

    vecs = embedder.embed_many(flat)

    bucket: dict[str, list[list[float]]] = {}
    for rel, v in zip(index, vecs):
        if v:
            bucket.setdefault(rel, []).append(v)

    out: list[tuple[str, tuple[float, ...]]] = []
    for rel, vs in bucket.items():
        mean = _mean_vec(vs)
        if mean:
            out.append((rel, tuple(mean)))
    return tuple(out)


def score_relations_from_entry(
    query_emb: list[float],
    entry_name: str,
    *,
    relations: tuple[str, ...] | None = None,
) -> dict[str, float]:
    """站在 ``entry_name`` 这个概念上，给出每种关系的入口内 z-score 权重。

    原始分 = mean_i cos( embed(query), embed(entry_name + probe_i) )
    权重   = (原始分 − 本入口均值) / 本入口标准差        ← 入口内 z-score

    **返回值可为负数**（"低于本入口均值几个标准差"）。消费方（``_expand_subgraph``）
    先调 ``softmax_normalize`` 把 z 转成正的概率权重，再代入乘法打分公式，
    保证不引入负 candidate_score。

    **为什么必须做 z-score**：共同的入口名前缀把各条拼接文本压到高相似区，
    原始余弦差异只剩小数点后两位（实测带宽 ~0.05），softmax 后各关系概率差
    仅约 1.1 倍（≈均匀分布）——关系语义打分名存实亡。z-score 把带宽拉到 ~3，
    softmax 后头尾概率差 ~25 倍，区分度恢复正常。

    ``relations`` 为 None 时退回 ``RELATION_PROBES`` 的全部关系；
    调用方显式传入时必须传 **排序去重** 元组（``lru_cache`` 正确性要求）。
    """
    if not query_emb or not entry_name:
        return {}
    if relations is None:
        relations = tuple(sorted(RELATION_PROBES))
    if not relations:
        return {}

    try:
        pairs = _entry_relation_vecs(entry_name, relations)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "relation_semantics: 入口条件 probe 嵌入失败 entry=%r err=%s（本次不打关系分，下次重试）",
            entry_name,
            exc,
        )
        return {}
    if not pairs:
        return {}

    raw = {rel: _cos(query_emb, list(vec)) for rel, vec in pairs}
    if len(raw) < 2:
        # 单关系无参照组（标准差无意义）→ 返回 0.0，与本组均值齐平
        return {rel: 0.0 for rel in raw}

    vals = list(raw.values())
    mu = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))
    if sd <= _SD_EPS:
        # 所有关系同分（probe 退化 / embedding 异常）→ 全 0，softmax 退回均匀分布
        return {rel: 0.0 for rel in raw}

    return {rel: (v - mu) / sd for rel, v in raw.items()}
