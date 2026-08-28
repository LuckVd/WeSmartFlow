"""
Flickr 图片搜索源

无需 API Key！使用 Flickr 公开搜索接口（不需要注册）。
返回图片标题、描述、缩略图 URL、原图 URL。

Flickr 上有大量 CC 许可的教育用图。
"""

from __future__ import annotations

import logging

from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)

# Flickr 公开搜索 API（无需 Key）
_FLICKR_SEARCH_URL = "https://www.flickr.com/services/feeds/photos_public.gne"


class FlickrSource(BaseSource):
    source_id = "flickr"
    display_name = "Flickr Images"
    description = (
        "Flickr 图片搜索（无需 API Key），返回公开图片及描述，适合查找示意图/原理图"
    )
    modalities = ["image"]
    languages = ["zh", "en"]

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
        使用 Flickr 公开 RSS feeds 搜索图片，不需要 API Key。
        返回图片标题 + 描述 + 直链 URL，Agent 可直接引用。
        """
        try:
            import httpx
            from xml.etree import ElementTree as ET

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _FLICKR_SEARCH_URL,
                    params={
                        "format": "rss_200",
                        "tags": query.replace(" ", ","),
                        "lang": "zh-us",
                    },
                )
                resp.raise_for_status()
                xml_text = resp.text

        except Exception as e:
            logger.error("[Flickr] 搜索异常: %s", e)
            return []

        results = []
        try:
            root = ET.fromstring(xml_text)
            ns = {
                "media": "http://search.yahoo.com/mrss/",
                "dc": "http://purl.org/dc/elements/1.1/",
            }
            channel = root.find("channel")
            if channel is None:
                return []

            for item in channel.findall("item")[:max_results]:
                title = (item.findtext("title") or "").strip()
                description_raw = item.findtext("description") or ""
                link = item.findtext("link") or ""

                # 提取图片 URL（media:content 或 enclosure）
                media_content = item.find("media:content", ns)
                image_url = ""
                if media_content is not None:
                    image_url = media_content.get("url", "")
                if not image_url:
                    enclosure = item.find("enclosure")
                    if enclosure is not None:
                        image_url = enclosure.get("url", "")

                # 提取纯文字描述（去掉 HTML img 标签）
                import re

                description = re.sub(r"<[^>]+>", "", description_raw).strip()
                description = description[:300] if description else title

                if not title and not image_url:
                    continue

                results.append(
                    SearchResult(
                        title=title or "图片",
                        content=f"[图片] {description}",
                        url=image_url or link,
                        source_id=self.source_id,
                        score=0.65,
                        modality="image",
                        language=_detect_lang(title + description),
                        metadata={
                            "image_url": image_url,
                            "page_url": link,
                            "type": "photo",
                        },
                    )
                )

        except Exception as e:
            logger.error("[Flickr] XML 解析异常: %s", e)

        return results


def _detect_lang(text: str) -> str:
    if not text:
        return "unknown"
    cn = sum(1 for c in text[:200] if "\u4e00" <= c <= "\u9fff")
    return "zh" if cn > len(text[:200]) * 0.1 else "en"
