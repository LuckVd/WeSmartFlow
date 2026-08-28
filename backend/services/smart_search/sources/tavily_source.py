"""Tavily 搜索源 — AI 优化的通用网络搜索"""

from __future__ import annotations

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

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("TAVILY_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        if not self._api_key:
            logger.warning("[Tavily] 未配置 API Key，跳过")
            return []

        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self._api_key,
                        "query": query,
                        "search_depth": kwargs.get("search_depth", "basic"),
                        "max_results": max_results,
                        "include_answer": True,
                        "include_raw_content": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

        except Exception as e:
            logger.error("[Tavily] 搜索异常: %s", e)
            return []

        results = []

        # AI 答案摘要作为第一条（可信度最高因为是 AI 综合的）
        answer = data.get("answer")
        if answer:
            results.append(
                SearchResult(
                    title="[AI 综合摘要]",
                    content=answer,
                    url="",
                    source_id=self.source_id,
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
                    source_id=self.source_id,
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
