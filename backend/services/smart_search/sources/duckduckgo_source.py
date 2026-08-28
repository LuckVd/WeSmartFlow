"""DuckDuckGo 搜索源 — 免费无 key 的兜底搜索

注意：DDG 有 rate limit（尤其是通过代理时），需要：
1. 控制请求间隔
2. 遇到 202 Ratelimit 时自动退避重试
3. 使用 proxy 时设置环境变量让 DDGS 也走代理
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)


class DuckDuckGoSource(BaseSource):
    source_id = "duckduckgo"
    display_name = "DuckDuckGo"
    description = "免费通用搜索（无需 API Key），中英文均可，用于兜底"
    modalities = ["text"]
    languages = ["zh", "en"]

    # 类级别的上次请求时间（避免连续请求被 rate limit）
    _last_request_time: float = 0
    _MIN_INTERVAL: float = 2.0  # 至少间隔 2 秒

    def is_available(self) -> bool:
        try:
            from duckduckgo_search import DDGS  # noqa: F401

            return True
        except ImportError:
            return False

    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning(
                "[DDG] duckduckgo-search 未安装，pip install duckduckgo-search"
            )
            return []

        # 控制请求间隔，避免被 rate limit
        now = time.time()
        elapsed = now - DuckDuckGoSource._last_request_time
        if elapsed < self._MIN_INTERVAL:
            await asyncio.sleep(self._MIN_INTERVAL - elapsed)

        try:
            # 设置代理（从环境变量读取，DDGS 内部使用 httpx）
            proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY") or None

            def _do_search():
                # DDGS 支持 proxy 参数
                with DDGS(proxy=proxy, timeout=10) as ddgs:
                    return list(
                        ddgs.text(
                            query,
                            max_results=max_results,
                            region=kwargs.get("region", "wt-wt"),
                        )
                    )

            raw = await asyncio.to_thread(_do_search)
            DuckDuckGoSource._last_request_time = time.time()

        except Exception as e:
            err_msg = str(e)
            DuckDuckGoSource._last_request_time = time.time()

            # Ratelimit 时等待后重试一次
            if "Ratelimit" in err_msg or "202" in err_msg:
                logger.warning("[DDG] Rate limited，等 5s 后重试...")
                await asyncio.sleep(5.0)
                try:
                    proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY") or None

                    def _retry_search():
                        with DDGS(proxy=proxy, timeout=10) as ddgs:
                            return list(ddgs.text(query, max_results=3, region="wt-wt"))

                    raw = await asyncio.to_thread(_retry_search)
                    DuckDuckGoSource._last_request_time = time.time()
                except Exception as e2:
                    logger.error("[DDG] 重试也失败: %s", e2)
                    return []
            else:
                logger.error("[DDG] 搜索异常: %s", e)
                return []

        results = []
        for r in raw or []:
            content = r.get("body", "") or r.get("snippet", "")
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    content=content[:500],
                    url=r.get("href", "") or r.get("link", ""),
                    source_id=self.source_id,
                    score=0.5,
                    language=_detect_lang(content),
                    metadata={},
                )
            )

        return results


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
