"""
SmartSearchService: 多源并行检索的核心调度器

完整流程：
  1. Router 决策（选源 + 生成 sub-query）
  2. asyncio.gather 并行调用各源 adapter
  3. Filter 筛选去重 + 交叉验证
  4. 排序输出 SmartSearchResult（文本+图片+视频分组）

当前支持的模态：
  文本：tavily / anysearch / arxiv / web_fetch
  图片：wikimedia / flickr
  视频：youtube
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional, Callable, Awaitable

from .models import SearchPlan, SearchResult, SmartSearchResult
from .router import rule_based_route, llm_route, fallback_plan
from .filter import filter_and_rank
from .sources.base_source import BaseSource
from .sources.tavily_source import TavilySource
from .sources.anysearch_source import AnySearchSource
from .sources.arxiv_source import ArxivSource
from .sources.web_fetch_source import WebFetchSource
from .sources.flickr_source import FlickrSource
from .sources.wikimedia_source import WikimediaSource
from .sources.youtube_source import YouTubeSource

logger = logging.getLogger(__name__)


class SmartSearchService:
    """
    多源并行检索服务。

    Usage:
        service = SmartSearchService(
            tavily_key="tvly-xxx",
            anysearch_key="as_sk_xxx",
        )
        result = await service.search("Transformer 位置编码原理")
        print(result.to_markdown())
    """

    def __init__(
        self,
        tavily_client=None,
        tavily_key: Optional[str] = None,
        anysearch_key: Optional[str] = None,
        llm_func: Optional[Callable[[str], Awaitable[str]]] = None,
        top_k: int = 8,
        user_id: str = "",
    ):
        """
        Args:
            tavily_client: 工厂产出的 BaseSearchClient（已挂治理 hook，
                           见 services/search_factory）。
            tavily_key:    未注入 client 时的回退 Key（可从 env 读）。
            anysearch_key: AnySearch API Key（可从 env 读）
            llm_func:      异步 LLM 调用函数 (prompt: str) -> str，用于复杂路由
                           为 None 时只用规则路由
            top_k:         最终返回 top-k 条
        """
        self._user_id = user_id
        self._top_k = top_k
        self._llm_func = llm_func

        # 初始化所有源 adapter
        self._sources: dict[str, BaseSource] = {}
        self._init_sources(tavily_client, tavily_key, anysearch_key)

    def _init_sources(
        self,
        tavily_client,
        tavily_key: Optional[str],
        anysearch_key: Optional[str],
    ):
        """注册所有可用的搜索源（文本 + 图片 + 视频）。"""
        _tavily_key = tavily_key or os.getenv("TAVILY_API_KEY", "")
        _anysearch_key = anysearch_key or os.getenv("ANYSEARCH_API_KEY", "")
        _youtube_key = os.getenv("YOUTUBE_API_KEY", "")  # 可选，无 key 走降级

        candidates = [
            # ── 文本源 ──────────────────────────────────────────────
            TavilySource(
                api_key=_tavily_key, client=tavily_client, user_id=self._user_id
            ),
            AnySearchSource(api_key=_anysearch_key, user_id=self._user_id),
            ArxivSource(),
            WebFetchSource(),
            # ── 图片源（无需 Key）────────────────────────────────────
            WikimediaSource(),
            FlickrSource(),
            # ── 视频源（有 Key 走 API，无 Key 走降级）──────────────
            YouTubeSource(api_key=_youtube_key),
        ]

        for src in candidates:
            if src.is_available():
                self._sources[src.source_id] = src
                logger.info("[SmartSearch] 源注册成功: %s", src.source_id)
            else:
                logger.info("[SmartSearch] 源不可用（缺依赖/Key）: %s", src.source_id)

    @property
    def available_sources(self) -> dict[str, str]:
        """返回当前可用源 {id: description}"""
        return {sid: src.description for sid, src in self._sources.items()}

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        force_sources: Optional[list[str]] = None,
    ) -> SmartSearchResult:
        """
        执行多源并行检索。

        Args:
            query: 用户搜索词
            top_k: 覆盖默认 top_k
            force_sources: 强制指定源（跳过 Router）

        Returns:
            SmartSearchResult（含 .to_markdown() / .to_agent_text() 方法）
        """
        t0 = time.time()
        k = top_k or self._top_k
        available_ids = list(self._sources.keys())
        errors: list[str] = []

        # ─── Step 1: 路由决策 ───────────────────────────────────────
        plan: Optional[SearchPlan] = None

        if force_sources:
            # 强制指定源
            plan = SearchPlan(
                sources=force_sources,
                sub_queries={s: query for s in force_sources},
                complexity="manual",
                reason="force_specified",
            )
        else:
            # 先试规则路由（快，不调 LLM）
            plan = rule_based_route(query, available_ids)

            # 规则覆盖不了 → LLM 路由
            if plan is None and self._llm_func:
                plan = await llm_route(query, self.available_sources, self._llm_func)

            # 全失败 → fallback
            if plan is None:
                plan = fallback_plan(query, available_ids)

        # 确保 plan 里的源都存在
        plan.sources = [s for s in plan.sources if s in self._sources]
        if not plan.sources:
            plan = fallback_plan(query, available_ids)

        logger.info(
            "[SmartSearch] 路由决策: sources=%s complexity=%s reason=%s",
            plan.sources,
            plan.complexity,
            plan.reason,
        )

        # ─── Step 2: 并行检索 ──────────────────────────────────────
        async def _call_source(source_id: str) -> list[SearchResult]:
            src = self._sources[source_id]
            sub_query = plan.sub_queries.get(source_id, query)
            try:
                return await asyncio.wait_for(
                    src.search(sub_query, max_results=5),
                    timeout=30.0,  # 单源最大 30 秒超时（内网走代理延迟高）
                )
            except asyncio.TimeoutError:
                errors.append(f"{source_id}: 超时(>12s)")
                logger.warning("[SmartSearch] 源超时: %s", source_id)
                return []
            except Exception as e:
                errors.append(f"{source_id}: {str(e)[:50]}")
                logger.error("[SmartSearch] 源异常 %s: %s", source_id, e)
                return []

        # 并行执行
        tasks = [_call_source(sid) for sid in plan.sources]
        all_results_lists = await asyncio.gather(*tasks)

        # 合并所有结果
        raw_results: list[SearchResult] = []
        for result_list in all_results_lists:
            raw_results.extend(result_list)

        total_raw = len(raw_results)
        logger.info(
            "[SmartSearch] 并行检索完成: %d 个源返回 %d 条",
            len(plan.sources),
            total_raw,
        )

        # ─── Step 3: 筛选排序 ──────────────────────────────────────
        filtered = filter_and_rank(raw_results, top_k=k)
        total_filtered = len(filtered)

        # ─── 组装输出 ────────────────────────────────────────────
        latency_ms = int((time.time() - t0) * 1000)

        result = SmartSearchResult(
            query=query,
            results=filtered,
            plan=plan,
            total_raw=total_raw,
            total_filtered=total_filtered,
            latency_ms=latency_ms,
            errors=errors,
        )

        logger.info(
            "[SmartSearch] 完成: %d→%d条, %dms, errors=%d",
            total_raw,
            total_filtered,
            latency_ms,
            len(errors),
        )

        return result
