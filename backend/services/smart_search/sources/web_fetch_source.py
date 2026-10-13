"""WebFetch 源 — 对指定 URL 深度抓取（用于二次获取详情）"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import urljoin

from integrations import IntegrationHttpClient, IntegrationPolicy
from integrations.http import redact_url, validate_public_http_url
from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)


class WebFetchSource(BaseSource):
    source_id = "web_fetch"
    display_name = "Web Fetch"
    description = "抓取指定 URL 的完整内容（用于对搜索结果做深度获取）"
    modalities = ["text"]
    languages = ["zh", "en"]

    def __init__(self, http_client: Any = None):
        self._http = http_client or IntegrationHttpClient(
            IntegrationPolicy(
                name="web_fetch",
                timeout_seconds=15.0,
                max_retries=1,
                retry_safe=True,
                # Redirects are followed below, after each target passes the
                # public-address guard. Delegating them to httpx would allow a
                # public host to redirect a request to a private address.
                follow_redirects=False,
                max_redirects=0,
                max_concurrency=4,
            )
        )

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
            import trafilatura

            html = await self._fetch_public_html(url)

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
            # A pasted URL can contain signed-query credentials. Keep diagnostics
            # useful without allowing those credentials into application logs.
            logger.warning("[WebFetch] 抓取失败 %s: %s", redact_url(url), e)
            return None

    async def _fetch_public_html(self, url: str) -> str:
        """Fetch a public page while validating every redirect destination."""

        current_url = await validate_public_http_url(url)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SmartSearch/1.0)"}
        for redirect_count in range(4):
            response = await self._http.request("GET", current_url, headers=headers)
            try:
                if not response.is_redirect:
                    return response.text
                location = response.headers.get("location")
                if not location:
                    raise ValueError("重定向响应缺少目标地址")
                if redirect_count >= 3:
                    raise ValueError("重定向次数超过上限")
                # urljoin correctly handles relative Location headers, then the
                # result is checked before the next network request.
                current_url = await validate_public_http_url(
                    urljoin(str(response.url), location)
                )
            finally:
                await response.aclose()
        raise ValueError("重定向次数超过上限")  # pragma: no cover - loop guard


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
