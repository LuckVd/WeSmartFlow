"""
Router: 检索路由决策

职责：
  1. 分析 query 意图（学术/代码/图片/视频/通用）
  2. 判断复杂度（simple/medium/complex）
  3. 选择数据源 + 为每个源生成定制化 sub-query
  4. 决策优先级：规则优先（0ms）→ LLM 兜底 → Fallback

源列表（当前）：
  文本：tavily / anysearch / arxiv / web_fetch
  图片：wikimedia / flickr
  视频：youtube

设计原则：
  - 简单 query 不调 LLM（纯规则路由）
  - 复杂 / 多模态 query 才用 LLM 路由
  - 失败时 fallback（默认 tavily）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .models import SearchPlan

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# 关键词触发规则
# ═══════════════════════════════════════════════════════════════════════

_ACADEMIC_KEYWORDS = re.compile(
    r"论文|paper|arxiv|学术|研究|algorithm|theorem|proof|"
    r"模型|model|方法|method|原理|principle|公式|定理",
    re.I,
)
_CODE_KEYWORDS = re.compile(
    r"代码|code|实现|implement|github|开源|库|library|框架|framework|"
    r"bug|error|报错|api|sdk|package",
    re.I,
)
_NEWS_KEYWORDS = re.compile(
    r"最新|latest|新闻|news|今天|today|昨天|recently|发布|release|"
    r"更新|update|动态|趋势|trend",
    re.I,
)
# 图片/示意图/可视化触发词
_IMAGE_KEYWORDS = re.compile(
    r"图片|图像|image|photo|图解|示意图|流程图|架构图|diagram|"
    r"visualization|可视化|插图|illustration|截图|screenshot|"
    r"长什么样|画出来|看看图|图形|结构图|原理图",
    re.I,
)
# 视频/教程触发词
_VIDEO_KEYWORDS = re.compile(
    r"视频|video|教程|tutorial|讲解|演示|demo|youtube|b站|bilibili|"
    r"播放|看看视频|有没有视频|视频讲解|手把手|实战演示|录屏",
    re.I,
)

_CHINESE_HEAVY = re.compile(r"[\u4e00-\u9fff]")


# ═══════════════════════════════════════════════════════════════════════
# 规则路由（主路径，0ms，覆盖 ~85% case）
# ═══════════════════════════════════════════════════════════════════════


def rule_based_route(query: str, available_sources: list[str]) -> Optional[SearchPlan]:
    """
    基于关键词的快速路由，不调 LLM。
    匹配到任何条件就选对应的源，最后必加 tavily 作通用文本兜底。
    """
    sources: list[str] = []
    sub_queries: dict[str, str] = {}
    complexity = "simple"

    cn_ratio = len(_CHINESE_HEAVY.findall(query)) / max(len(query), 1)
    is_chinese = cn_ratio > 0.3

    # ── 学术 → arXiv ──────────────────────────────────────────────────
    if _ACADEMIC_KEYWORDS.search(query):
        if "arxiv" in available_sources:
            sources.append("arxiv")
            en_q = query if not is_chinese else _zh_to_en_hint(query)
            sub_queries["arxiv"] = en_q
        complexity = "medium"

    # ── 代码 → AnySearch ─────────────────────────────────────────────
    if _CODE_KEYWORDS.search(query):
        if "anysearch" in available_sources:
            sources.append("anysearch")
            sub_queries["anysearch"] = query
        complexity = "medium"

    # ── 图片/示意图 → Wikimedia + Flickr ──────────────────────────────
    if _IMAGE_KEYWORDS.search(query):
        for src in ("wikimedia", "flickr"):
            if src in available_sources:
                sources.append(src)
                sub_queries[src] = query
        complexity = "medium"

    # ── 视频/教程 → YouTube ──────────────────────────────────────────
    if _VIDEO_KEYWORDS.search(query):
        if "youtube" in available_sources:
            sources.append("youtube")
            sub_queries["youtube"] = query
        complexity = "medium"

    # ── 通用文本：Tavily 作为必选兜底 ────────────────────────────────
    if "tavily" in available_sources:
        sources.append("tavily")
        sub_queries["tavily"] = query

    # 去重，保持顺序
    seen: set[str] = set()
    sources = [s for s in sources if not (s in seen or seen.add(s))]  # type: ignore[func-returns-value]

    if sources:
        return SearchPlan(
            sources=sources,
            sub_queries=sub_queries,
            complexity=complexity,
            expected_count=10,
            reason="rule_based",
        )

    return None  # 触发 LLM 路由


def _zh_to_en_hint(query: str) -> str:
    """简单去除中文停用词，给英文学术源用。"""
    for w in "的了是在我要怎么什么为什么请问帮我讲讲介绍一下":
        query = query.replace(w, " ")
    return query.strip()


# ═══════════════════════════════════════════════════════════════════════
# LLM 路由（精细，处理复杂/多模态 case）
# ═══════════════════════════════════════════════════════════════════════

_ROUTER_PROMPT = """你是一个搜索路由器。分析用户 query，从可用数据源中选择最合适的 2-5 个。

## 可用数据源（含模态）
{sources_desc}

## 模态路由规则
- query 含"图片/示意图/图解/diagram/流程图" → 必选图片源（wikimedia / flickr）
- query 含"视频/教程/讲解/tutorial/demo" → 必选视频源（youtube）
- query 含"论文/学术/paper/原理" → 必选 arxiv（sub_query 须为英文）
- query 含"代码/实现/框架/github" → 必选 anysearch
- 通用问题 → 选 tavily
- 多个维度同时匹配 → 多源并选

## 输出 JSON（严格格式，不输出其他内容）
{{
  "sources": ["source_id_1", "source_id_2"],
  "sub_queries": {{
    "source_id_1": "针对该源优化的搜索词",
    "source_id_2": "..."
  }},
  "complexity": "simple|medium|complex",
  "reason": "一句话决策理由"
}}

用户 Query: {query}
"""


async def llm_route(
    query: str,
    available_sources: dict[str, str],  # {source_id: description}
    llm_func,  # async (prompt: str) -> str
) -> Optional[SearchPlan]:
    """调 LLM 做精细路由（规则路由覆盖不了时使用）。"""
    sources_desc = "\n".join(
        f"- **{sid}** [{src_modality(sid)}]: {desc}"
        for sid, desc in available_sources.items()
    )
    prompt = _ROUTER_PROMPT.format(sources_desc=sources_desc, query=query)

    try:
        raw = await llm_func(prompt)
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        start = raw.find("{")
        if start >= 0:
            raw = raw[start:]
        data = json.loads(raw)
        return SearchPlan(
            sources=data.get("sources", []),
            sub_queries=data.get("sub_queries", {}),
            complexity=data.get("complexity", "medium"),
            expected_count=10,
            reason=data.get("reason", "llm_routed"),
        )
    except Exception as e:
        logger.warning("[Router] LLM 路由失败: %s，降级 fallback", e)
        return None


def src_modality(source_id: str) -> str:
    """源 ID → 模态标签（用于 LLM 路由提示）"""
    _map = {
        "tavily": "文本",
        "anysearch": "文本",
        "arxiv": "文本",
        "web_fetch": "文本",
        "wikimedia": "图片",
        "flickr": "图片",
        "youtube": "视频",
    }
    return _map.get(source_id, "文本")


# ═══════════════════════════════════════════════════════════════════════
# Fallback（最保守兜底）
# ═══════════════════════════════════════════════════════════════════════


def fallback_plan(query: str, available_sources: list[str]) -> SearchPlan:
    """规则 + LLM 均失败时的默认策略：只用最可靠的文本源。"""
    sources: list[str] = []
    sub_queries: dict[str, str] = {}

    for preferred in ("tavily", "anysearch", "arxiv"):
        if preferred in available_sources:
            sources.append(preferred)
            sub_queries[preferred] = query
            break

    if not sources and available_sources:
        s = available_sources[0]
        sources.append(s)
        sub_queries[s] = query

    return SearchPlan(
        sources=sources,
        sub_queries=sub_queries,
        complexity="simple",
        expected_count=5,
        reason="fallback",
    )
