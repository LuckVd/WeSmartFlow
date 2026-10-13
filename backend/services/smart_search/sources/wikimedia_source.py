"""
Wikimedia Commons 图片搜索源

完全免费，无需注册任何账号。
Wikimedia Commons 是维基百科的媒体库，有数千万张开放授权的教育图片：
- 学术示意图（细胞图、物理定律图、数学图形）
- 历史图片
- 地图
- 科学插图
- 所有图片均为 CC 协议，可自由使用

API 文档：https://commons.wikimedia.org/w/api.php
"""

from __future__ import annotations

import logging
from typing import Any

from integrations import IntegrationHttpClient, IntegrationPolicy
from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)

_WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


class WikimediaSource(BaseSource):
    source_id = "wikimedia"
    display_name = "Wikimedia Commons"
    description = "维基共享资源图片搜索（免费，无需注册），返回 CC 协议的教育/学术图片"
    modalities = ["image"]
    languages = ["zh", "en"]

    def __init__(self, http_client: Any = None):
        self._http = http_client or IntegrationHttpClient(
            IntegrationPolicy(
                name="wikimedia",
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
        """
        调用 Wikimedia Commons API 搜索图片。
        返回图片标题 + 描述 + 图片直链 URL。
        """
        try:
            # Step 1: 搜索文件
            search_data = await self._http.get_json(
                _WIKIMEDIA_API,
                params={
                    "action": "query",
                    "format": "json",
                    "list": "search",
                    "srsearch": f"{query} filetype:bitmap|drawing",
                    "srnamespace": "6",  # File namespace
                    "srlimit": max_results,
                    "srprop": "snippet|titlesnippet",
                },
            )

        except Exception as e:
            logger.error("[Wikimedia] 搜索异常: %s", e)
            return []

        pages = search_data.get("query", {}).get("search", [])
        if not pages:
            return []

        # Step 2: 批量获取图片 URL
        titles = [p["title"] for p in pages]
        results = []
        try:
            img_data = await self._http.get_json(
                _WIKIMEDIA_API,
                params={
                    "action": "query",
                    "format": "json",
                    "titles": "|".join(titles),
                    "prop": "imageinfo|revisions",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 800,  # 请求缩略图宽度 800px
                    "rvprop": "content",
                },
            )

        except Exception as e:
            logger.error("[Wikimedia] 图片信息获取异常: %s", e)
            return []

        import re

        for page_id, page_info in img_data.get("query", {}).get("pages", {}).items():
            title = page_info.get("title", "").replace("File:", "")
            imageinfos = page_info.get("imageinfo", [])
            if not imageinfos:
                continue

            ii = imageinfos[0]
            thumb_url = ii.get("thumburl") or ii.get("url", "")
            full_url = ii.get("url", "")
            page_url = ii.get("descriptionurl", "")

            # 从扩展元数据提取描述
            extmeta = ii.get("extmetadata", {})
            description = (
                extmeta.get("ImageDescription", {}).get("value", "")
                or extmeta.get("ObjectName", {}).get("value", "")
                or title
            )
            # 去掉 HTML 标签
            description = re.sub(r"<[^>]+>", "", description).strip()[:300]

            if not thumb_url and not full_url:
                continue

            results.append(
                SearchResult(
                    title=title,
                    content=f"[图片] {description}",
                    url=thumb_url or full_url,
                    source_id=self.source_id,
                    score=0.75,  # Wikimedia 是权威教育图片库
                    modality="image",
                    language=_detect_lang(title + description),
                    metadata={
                        "thumb_url": thumb_url,
                        "full_url": full_url,
                        "page_url": page_url,
                        "license": extmeta.get("LicenseShortName", {}).get(
                            "value", "CC"
                        ),
                    },
                )
            )

        return results[:max_results]


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
