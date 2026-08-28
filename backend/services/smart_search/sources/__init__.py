"""
搜索源 Adapters — 文本 / 图片 / 视频 全模态

每个 adapter 实现统一接口：
  async def search(query: str, max_results: int = 5) -> list[SearchResult]

模态分类：
  ▸ 文本：TavilySource / AnySearchSource / ArxivSource / WebFetchSource
  ▸ 图片：FlickrSource / WikimediaSource
  ▸ 视频：YouTubeSource
"""

from .base_source import BaseSource
from .tavily_source import TavilySource
from .anysearch_source import AnySearchSource
from .arxiv_source import ArxivSource
from .web_fetch_source import WebFetchSource
from .flickr_source import FlickrSource
from .wikimedia_source import WikimediaSource
from .youtube_source import YouTubeSource

__all__ = [
    "BaseSource",
    # 文本
    "TavilySource",
    "AnySearchSource",
    "ArxivSource",
    "WebFetchSource",
    # 图片
    "FlickrSource",
    "WikimediaSource",
    # 视频
    "YouTubeSource",
]
