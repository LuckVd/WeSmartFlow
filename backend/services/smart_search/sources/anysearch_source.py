"""AnySearch 搜索源 — 23 个垂直领域智能路由搜索

API 文档：https://www.anysearch.com/docs
请求方式：POST /v1/search（不是 GET！）
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)


class AnySearchSource(BaseSource):
    source_id = "anysearch"
    display_name = "AnySearch"
    description = (
        "垂直领域智能路由搜索（代码/CVE/学术/金融等），能搜到 Google 搜不到的深层数据"
    )
    modalities = ["text"]
    languages = ["zh", "en"]

    API_URL = "https://api.anysearch.com/v1/search"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("ANYSEARCH_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        if not self._api_key:
            logger.warning("[AnySearch] 未配置 API Key，跳过")
            return []

        try:
            import httpx

            # ⚠️ AnySearch API 是 POST，body 是 JSON
            # 不是 GET + params！（之前的 404 就是因为用了 GET）
            request_body = {
                "query": query,
                "max_results": max_results,
            }
            # 可选：指定领域（代码/学术等）
            if kwargs.get("domains"):
                request_body["domains"] = kwargs["domains"]
            if kwargs.get("language"):
                request_body["language"] = kwargs["language"]

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    self.API_URL,
                    json=request_body,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

        except Exception as e:
            logger.error("[AnySearch] 搜索异常: %s", e)
            return []

        results = []
        # 返回格式：{ "results": [...], "metadata": {...} }
        items = data.get("results") or []
        if isinstance(items, dict):
            items = [items]

        for item in items[:max_results]:
            title = item.get("title") or item.get("name") or ""
            content = (
                item.get("content")
                or item.get("description")
                or item.get("snippet")
                or ""
            )
            url = item.get("url") or item.get("link") or ""
            score = item.get("score") or item.get("quality_score") or 0.7
            published = item.get("published_at") or None

            results.append(
                SearchResult(
                    title=title,
                    content=content[:500],
                    url=url,
                    source_id=self.source_id,
                    score=float(score) if score else 0.7,
                    timestamp=published,
                    language=_detect_lang(content) if content else "en",
                    metadata={"source_type": item.get("source", "")},
                )
            )

        return results


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
