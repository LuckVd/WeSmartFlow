"""arXiv 搜索源 — 学术论文预印本（免费）"""

from __future__ import annotations

import asyncio
import logging

from .base_source import BaseSource
from ..models import SearchResult

logger = logging.getLogger(__name__)


class ArxivSource(BaseSource):
    source_id = "arxiv"
    display_name = "arXiv"
    description = "arXiv 学术论文搜索（免费），适合前沿研究和技术概念"
    modalities = ["text"]
    languages = ["en"]

    def is_available(self) -> bool:
        try:
            import arxiv  # noqa: F401

            return True
        except ImportError:
            return False

    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        try:
            import arxiv
        except ImportError:
            logger.warning("[arXiv] arxiv 库未安装")
            return []

        try:

            def _do_search():
                search = arxiv.Search(
                    query=query,
                    max_results=max_results,
                    sort_by=arxiv.SortCriterion.Relevance,
                )
                # arxiv 2.x API: 用 Client().results(search)
                # arxiv 1.x API: 用 search.results()
                try:
                    client = arxiv.Client()
                    return list(client.results(search))
                except (AttributeError, TypeError):
                    # fallback 旧版 API
                    return list(search.results())

            papers = await asyncio.to_thread(_do_search)

        except Exception as e:
            logger.error("[arXiv] 搜索异常: %s", e)
            return []

        results = []
        for paper in papers:
            authors = ", ".join(a.name for a in paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " et al."

            published = paper.published.strftime("%Y-%m-%d") if paper.published else ""

            results.append(
                SearchResult(
                    title=paper.title,
                    content=paper.summary[:500],
                    url=paper.entry_id,
                    source_id=self.source_id,
                    score=0.75,  # arXiv 不提供相关度分，学术源默认较高
                    timestamp=published,
                    language="en",
                    metadata={
                        "authors": authors,
                        "categories": [c for c in (paper.categories or [])[:3]],
                        "pdf_url": paper.pdf_url,
                    },
                )
            )

        return results
