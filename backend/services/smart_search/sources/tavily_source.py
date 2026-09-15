"""Tavily 搜索源 — AI 优化的通用网络搜索"""

from __future__ import annotations

import asyncio
import os
import logging
from typing import Optional

from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)


class TavilySource(BaseSource):
    source_id = "tavily"
    display_name = "Tavily AI Search"
    description = "AI 优化的通用网络搜索，返回经 AI 提炼的高质量结果 + 答案摘要"
    modalities = ["text"]
    languages = ["zh", "en"]

    def __init__(self, api_key: Optional[str] = None, client=None, user_id: str = ""):
        """
        Args:
            api_key: 未注入 client 时的回退 Key。
            client:  工厂产出的 ``BaseSearchClient``（已挂额度拦截 + 记账
                     hook，见 services/search_factory）。注入后本源的
                     实际调用走该 client，治理随 client 生效。
        """
        if client is None and user_id:
            from services.search_factory import get_search_client

            client = get_search_client(user_id)
        self._client = client
        self._api_key = api_key or os.getenv("TAVILY_API_KEY", "")

    def is_available(self) -> bool:
        return self._client is not None or bool(self._api_key)

    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        if self._client is not None:
            # 工厂注入的 client：同步实现，放线程池避免阻塞事件循环
            try:
                r = await asyncio.to_thread(
                    self._client.search,
                    query,
                    max_results=max_results,
                    search_depth=kwargs.get("search_depth", "basic"),
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.error("[Tavily] 搜索异常: %s", e)
                return []
            return self._to_results(r)

        raise RuntimeError("Tavily 搜索需要注入受用量治理的客户端或 user_id")

    @staticmethod
    def _to_results(r) -> list[SearchResult]:
        """把 BaseSearchClient 的 SearchResult 转为本模块的 SearchResult。"""
        results = []
        if r.answer:
            results.append(
                SearchResult(
                    title="[AI 综合摘要]",
                    content=r.answer,
                    url="",
                    source_id="tavily",
                    score=0.95,
                    language=_detect_lang(r.answer),
                    metadata={"type": "ai_answer"},
                )
            )
        for item in r.results or []:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    content=(item.get("content", "") or "")[:500],
                    url=item.get("url", ""),
                    source_id="tavily",
                    score=item.get("score", 0.5),
                    language=_detect_lang(item.get("content", "")),
                    metadata={},
                )
            )
        return results

    @staticmethod
    def _to_raw_results(data: dict) -> list[SearchResult]:
        """把 Tavily 原始响应 dict 转为结果列表（无 client 注入时的路径）。"""
        results = []

        # AI 答案摘要作为第一条（可信度最高因为是 AI 综合的）
        answer = data.get("answer")
        if answer:
            results.append(
                SearchResult(
                    title="[AI 综合摘要]",
                    content=answer,
                    url="",
                    source_id="tavily",
                    score=0.95,
                    language=_detect_lang(answer),
                    metadata={"type": "ai_answer"},
                )
            )

        # 逐条结果
        for r in data.get("results", []):
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    content=r.get("content", "")[:500],
                    url=r.get("url", ""),
                    source_id="tavily",
                    score=r.get("score", 0.5),
                    language=_detect_lang(r.get("content", "")),
                    metadata={},
                )
            )

        return results


def _detect_lang(text: str) -> str:
    """简单中英文检测"""
    if not text:
        return "unknown"
    cn_chars = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn_chars > len(text[:200]) * 0.1 else "en"
