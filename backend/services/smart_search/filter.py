"""
Filter: 搜索结果筛选、评分、去重、验证

三道防线：
  L1: 来源可信度评分（纯计算，0 延迟）
  L2: 去重（URL + 标题相似度）
  L3: 多源交叉验证（同一事实多源确认 → 可信度提升）

最终输出排序：final_score = credibility × relevance × freshness
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from .models import SearchResult

logger = logging.getLogger(__name__)

# ─── L1: 来源可信度评分 ───────────────────────────────────────────────

# 域名 → 基础可信度（0-1）
_CREDIBILITY_MAP = {
    # 顶级学术
    "arxiv.org": 0.95,
    "nature.com": 0.95,
    "science.org": 0.95,
    "ieee.org": 0.92,
    "acm.org": 0.92,
    "springer.com": 0.90,
    "sciencedirect.com": 0.90,
    # 技术权威
    "github.com": 0.85,
    "stackoverflow.com": 0.82,
    "docs.python.org": 0.90,
    "pytorch.org": 0.88,
    "tensorflow.org": 0.88,
    "huggingface.co": 0.85,
    # 百科/知识
    "wikipedia.org": 0.80,
    "en.wikipedia.org": 0.82,
    "zh.wikipedia.org": 0.78,
    "wikiwand.com": 0.78,
    # 可信媒体
    "bbc.com": 0.80,
    "reuters.com": 0.82,
    "nytimes.com": 0.80,
    "theverge.com": 0.75,
    # 中文技术社区
    "zhihu.com": 0.65,
    "juejin.cn": 0.60,
    "segmentfault.com": 0.60,
    "cnblogs.com": 0.55,
    "csdn.net": 0.50,
    "jianshu.com": 0.45,
    # 低可信
    "baidu.com": 0.40,
    "baijiahao.baidu.com": 0.35,
}

# AI 搜索源的答案摘要（已经过 AI 综合）高可信
_SOURCE_AGENT_CREDIBILITY = {
    "tavily": 0.80,  # Tavily 的 AI 答案
    "anysearch": 0.78,
    "duckduckgo": 0.55,
    "arxiv": 0.92,
    "web_fetch": 0.60,
}


def score_credibility(result: SearchResult) -> float:
    """计算单条结果的来源可信度分。"""
    # 如果是 AI 生成的摘要（无 URL），按源默认分
    if not result.url or result.metadata.get("type") == "ai_answer":
        return _SOURCE_AGENT_CREDIBILITY.get(result.source_id, 0.5)

    # 提取域名
    try:
        domain = urlparse(result.url).netloc.lower()
        # 去掉 www.
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        domain = ""

    # 精确匹配
    base = _CREDIBILITY_MAP.get(domain, None)

    # 尝试主域名匹配（如 docs.python.org → python.org）
    if base is None:
        parts = domain.split(".")
        if len(parts) > 2:
            main_domain = ".".join(parts[-2:])
            base = _CREDIBILITY_MAP.get(main_domain, None)

    if base is None:
        base = 0.45  # 未知域名默认

    # 时效衰减：内容超过 1 年 -0.05，超过 3 年 -0.10
    if result.timestamp:
        try:
            pub_date = datetime.fromisoformat(result.timestamp.replace("Z", "+00:00"))
            days_old = (datetime.now(timezone.utc) - pub_date).days
            if days_old > 1095:  # 3 年
                base -= 0.10
            elif days_old > 365:  # 1 年
                base -= 0.05
        except (ValueError, TypeError):
            pass

    return max(0.1, min(1.0, base))


# ─── L2: 去重 ─────────────────────────────────────────────────────────


def deduplicate(results: list[SearchResult]) -> list[SearchResult]:
    """
    去除重复结果：
    1. URL 完全相同 → 保留 score 高的
    2. 标题高度相似（简化版 Jaccard > 0.7）→ 保留 score 高的
    """
    if not results:
        return []

    # Phase 1: URL 去重
    url_map: dict[str, SearchResult] = {}
    no_url: list[SearchResult] = []

    for r in results:
        url_key = _normalize_url(r.url) if r.url else None
        if not url_key:
            no_url.append(r)
            continue
        if url_key in url_map:
            # 保留 score 高的
            if r.score > url_map[url_key].score:
                url_map[url_key].is_duplicate = True
                url_map[url_key] = r
            else:
                r.is_duplicate = True
        else:
            url_map[url_key] = r

    unique = list(url_map.values()) + no_url

    # Phase 2: 标题相似度去重
    final = []
    for r in unique:
        if r.is_duplicate:
            continue
        is_dup = False
        for existing in final:
            if _title_similarity(r.title, existing.title) > 0.7:
                # 保留 credibility 高的
                if r.credibility > existing.credibility:
                    final.remove(existing)
                    final.append(r)
                is_dup = True
                break
        if not is_dup:
            final.append(r)

    return final


def _normalize_url(url: str) -> str:
    """标准化 URL（去 trailing slash、去 fragment、统一 http/https）"""
    url = url.strip().rstrip("/")
    url = re.sub(r"#.*$", "", url)
    url = re.sub(r"^https?://", "", url)
    return url.lower()


def _title_similarity(a: str, b: str) -> float:
    """简化版标题相似度（字符 bigram Jaccard）"""
    if not a or not b:
        return 0.0
    a_set = set(_bigrams(a.lower()))
    b_set = set(_bigrams(b.lower()))
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


def _bigrams(text: str) -> list[str]:
    """提取连续 2 字符组"""
    text = re.sub(r"\s+", "", text)
    return [text[i : i + 2] for i in range(len(text) - 1)]


# ─── L3: 多源交叉验证 ──────────────────────────────────────────────────


def cross_verify(results: list[SearchResult]) -> list[SearchResult]:
    """
    多源交叉验证：
    - 同一个事实/主题被 2+ 不同源确认 → verification_status = "verified"
    - 只有 1 个源 → "unverified"
    - （暂不做"disputed"检测，需要 LLM 判断矛盾，后续加）

    判定"确认"的标准：不同 source_id 的结果标题相似度 > 0.4（比较宽松）
    """
    for i, r in enumerate(results):
        confirming_sources = {r.source_id}  # 自己算一个
        for j, other in enumerate(results):
            if i == j or other.source_id == r.source_id:
                continue
            # 标题或内容有一定重叠 → 算确认
            if (
                _title_similarity(r.title, other.title) > 0.4
                or _content_overlap(r.content, other.content) > 0.3
            ):
                confirming_sources.add(other.source_id)

        if len(confirming_sources) >= 3:
            r.verification_status = "verified"
            r.credibility = min(1.0, r.credibility + 0.15)  # 多源确认加分
        elif len(confirming_sources) >= 2:
            r.verification_status = "verified"
            r.credibility = min(1.0, r.credibility + 0.08)
        else:
            r.verification_status = "unverified"

    return results


def _content_overlap(a: str, b: str) -> float:
    """内容关键词重叠度（粗略）"""
    if not a or not b:
        return 0.0
    # 提取关键词（去标点、分词简化）
    words_a = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", a[:300].lower()))
    words_b = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", b[:300].lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ─── 综合排序 ──────────────────────────────────────────────────────────


def rank_results(results: list[SearchResult], top_k: int = 10) -> list[SearchResult]:
    """
    综合排序：final_score = relevance × credibility × freshness_bonus

    freshness_bonus：有时间戳且 <7 天 → ×1.2，<30 天 → ×1.1
    """
    for r in results:
        fresh_bonus = 1.0
        if r.timestamp:
            try:
                pub = datetime.fromisoformat(r.timestamp.replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - pub).days
                if days < 7:
                    fresh_bonus = 1.2
                elif days < 30:
                    fresh_bonus = 1.1
            except (ValueError, TypeError):
                pass

        r.final_score = r.score * r.credibility * fresh_bonus

    # 按 final_score 降序排
    results.sort(key=lambda x: x.final_score, reverse=True)
    return results[:top_k]


# ─── 主流程 ───────────────────────────────────────────────────────────


def filter_and_rank(
    raw_results: list[SearchResult], top_k: int = 10
) -> list[SearchResult]:
    """
    完整筛选流程：评分 → 去重 → 交叉验证 → 排序 → 取 top-k

    Args:
        raw_results: 各源返回的原始合并结果
        top_k: 最终保留几条

    Returns:
        筛选排序后的 top-k 结果
    """
    if not raw_results:
        return []

    # L1: 打可信度分
    for r in raw_results:
        r.credibility = score_credibility(r)

    # L2: 去重
    unique = deduplicate(raw_results)

    # L3: 多源交叉验证
    verified = cross_verify(unique)

    # 综合排序
    ranked = rank_results(verified, top_k=top_k)

    logger.info(
        "[Filter] 原始 %d 条 → 去重 %d 条 → 最终 %d 条",
        len(raw_results),
        len(unique),
        len(ranked),
    )

    return ranked
