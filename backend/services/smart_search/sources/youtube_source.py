"""
YouTube 视频搜索源（无需 API Key）

使用 YouTube Data API 搜索视频，也提供无 key 的降级方案。
有 API Key：准确、字段完整，每天 10,000 单位免费配额
无 API Key：通过 yt-dlp 或 RSS 搜索，稳定性差一些

适合场景：搜索教学视频、讲解视频、实验演示

如需 API Key，去 console.cloud.google.com 申请
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from integrations import IntegrationHttpClient, IntegrationPolicy
from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)

_YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
# 无 key 时通过 RSS 搜索（不依赖 API）
_YOUTUBE_RSS_SEARCH = "https://www.youtube.com/feeds/videos.xml"
# yt-dlp 搜索 URL
_YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"


class YouTubeSource(BaseSource):
    """YouTube 视频搜索。有 YOUTUBE_API_KEY 时走官方 API，否则走无 key 方案。"""

    source_id = "youtube"
    display_name = "YouTube Videos"
    description = "YouTube 教学视频搜索，返回视频标题、简介、时长、链接"
    modalities = ["video"]
    languages = ["zh", "en"]

    def __init__(self, api_key: str | None = None, http_client: Any = None):
        self._api_key = api_key or os.getenv("YOUTUBE_API_KEY", "")
        self._http = http_client or IntegrationHttpClient(
            IntegrationPolicy(
                name="youtube",
                timeout_seconds=12.0,
                max_retries=1,
                retry_safe=True,
                max_concurrency=4,
            )
        )

    def is_available(self) -> bool:
        try:
            import httpx  # noqa

            return True
        except ImportError:
            return False

    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        if self._api_key:
            return await self._search_with_api(query, max_results)
        else:
            return await self._search_without_key(query, max_results)

    # ─── 有 API Key ───────────────────────────────────────────────────
    async def _search_with_api(
        self, query: str, max_results: int
    ) -> list[SearchResult]:
        """使用 YouTube Data API v3 搜索（官方，精准）"""
        try:
            data = await self._http.get_json(
                _YOUTUBE_SEARCH_API,
                params={
                    "key": self._api_key,
                    "q": query,
                    "part": "snippet",
                    "type": "video",
                    "maxResults": max_results,
                    "relevanceLanguage": "zh" if _is_chinese(query) else "en",
                    "videoEmbeddable": "true",
                },
            )

        except Exception as e:
            logger.error("[YouTube] API 搜索异常: %s", e)
            return await self._search_without_key(query, max_results)

        results = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid_id = item.get("id", {}).get("videoId", "")
            if not vid_id:
                continue

            title = snippet.get("title", "")
            description = snippet.get("description", "")[:300]
            channel = snippet.get("channelTitle", "")
            published = snippet.get("publishedAt", "")[:10]
            thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url", "")

            results.append(
                SearchResult(
                    title=title,
                    content=f"[视频] {description or title} | 频道: {channel}",
                    url=f"https://www.youtube.com/watch?v={vid_id}",
                    source_id=self.source_id,
                    score=0.72,
                    modality="video",
                    timestamp=published,
                    language=_detect_lang(title + description),
                    metadata={
                        "video_id": vid_id,
                        "channel": channel,
                        "thumbnail": thumb,
                        "embed_url": f"https://www.youtube.com/embed/{vid_id}",
                    },
                )
            )

        return results

    # ─── 无 API Key（RSS + scraping 降级）─────────────────────────────
    async def _search_without_key(
        self, query: str, max_results: int
    ) -> list[SearchResult]:
        """
        无 API Key 方案：
        1. 尝试 YouTube 搜索页面（轻量解析）
        2. 失败则返回空（不 crash）
        """
        try:
            # YouTube 搜索页面（不需要 key）
            # 通过解析初始数据 JSON 获取结果
            html = await self._http.get_text(
                _YOUTUBE_SEARCH_URL,
                params={"search_query": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )

        except Exception as e:
            logger.error("[YouTube] 无 key 搜索异常: %s", e)
            return []

        results = []
        try:
            # 从 HTML 里提取 videoId + title（YouTube 会在 HTML 中内嵌数据）
            # 提取视频 ID
            vid_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}', html)
            channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"\}', html)
            descs = re.findall(
                r'"descriptionSnippet":\{"runs":\[\{"text":"([^"]+)"\}', html
            )

            # 去重 vid_id（HTML 里会重复）
            seen_ids = []
            for vid in vid_ids:
                if vid not in seen_ids:
                    seen_ids.append(vid)

            for i, vid_id in enumerate(seen_ids[:max_results]):
                title = titles[i] if i < len(titles) else f"YouTube 视频 {i + 1}"
                channel = channels[i] if i < len(channels) else ""
                desc = descs[i] if i < len(descs) else ""

                results.append(
                    SearchResult(
                        title=title,
                        content=f"[视频] {desc or title} | 频道: {channel}",
                        url=f"https://www.youtube.com/watch?v={vid_id}",
                        source_id=self.source_id,
                        score=0.60,  # 无 key 方案可信度稍低
                        modality="video",
                        language=_detect_lang(title),
                        metadata={
                            "video_id": vid_id,
                            "channel": channel,
                            "thumbnail": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                            "embed_url": f"https://www.youtube.com/embed/{vid_id}",
                            "no_api_key": True,
                        },
                    )
                )

        except Exception as e:
            logger.error("[YouTube] HTML 解析异常: %s", e)

        return results


def _is_chinese(text: str) -> bool:
    cn = sum(1 for c in text[:100] if "\u4e00" <= c <= "\u9fff")
    return cn > len(text[:100]) * 0.15


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
