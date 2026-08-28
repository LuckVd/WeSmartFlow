"""WebFetch 源 — 对指定 URL 深度抓取（用于二次获取详情）"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)


class WebFetchSource(BaseSource):
    source_id = "web_fetch"
    display_name = "Web Fetch"
    description = "抓取指定 URL 的完整内容（用于对搜索结果做深度获取）"
    modalities = ["text"]
    languages = ["zh", "en"]

    async def search(
        self, query: str, max_results: int = 1, **kwargs
    ) -> list[SearchResult]:
        """
        对于 WebFetch，query 应该是一个 URL（或逗号分隔的多个 URL）。
        返回抓取后的正文。
        """
        urls = [u.strip() for u in query.split(",") if u.strip().startswith("http")]
        if not urls:
            return []

        results = []
        for url in urls[:max_results]:
            content = await self._fetch_one(url)
            if content:
                results.append(
                    SearchResult(
                        title=f"[抓取] {url[:60]}",
                        content=content[:800],
                        url=url,
                        source_id=self.source_id,
                        score=0.6,
                        language=_detect_lang(content),
                        metadata={"full_length": len(content)},
                    )
                )

        return results

    async def _fetch_one(self, url: str) -> Optional[str]:
        """抓取单个 URL"""
        try:
            import httpx
            import trafilatura

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; SmartSearch/1.0)"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                html = resp.text

            # trafilatura 提取正文
            text = await asyncio.to_thread(
                trafilatura.extract,
                html,
                include_tables=True,
                include_links=False,
                favor_recall=True,
            )
            return text or ""

        except Exception as e:
            logger.warning("[WebFetch] 抓取失败 %s: %s", url, e)
            return None


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
