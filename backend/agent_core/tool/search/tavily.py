"""Tavily 搜索客户端（tavily-python SDK 封装）。

逻辑迁移自 ``agent_core.tool.web.TavilySearch``——工具壳只保留
参数 schema 与输出格式化，实际调用走本客户端。
"""

from __future__ import annotations

from typing import Any

from .base import BaseSearchClient, SearchError, SearchResult


class TavilySearchClient(BaseSearchClient):
    """Tavily AI 搜索客户端，返回经 AI 提炼的结构化结果。"""

    backend = "tavily"

    def __init__(self, api_key: str = ""):
        """
        Args:
            api_key: Tavily API Key；为空时 :meth:`search` 抛 :class:`SearchError`。
        """
        self.api_key = api_key

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
    ) -> SearchResult:
        if not self.api_key:
            raise SearchError(
                "未配置 TAVILY_API_KEY，请在设置页面填写或在 .env 文件中添加 TAVILY_API_KEY=tvly-xxxxx"
            )
        try:
            from tavily import TavilyClient
        except ImportError as exc:  # pylint: disable=broad-except
            raise SearchError(
                "未安装 tavily-python 库，请运行 pip install tavily-python"
            ) from exc

        try:
            client = TavilyClient(api_key=self.api_key)
            response: dict[str, Any] = client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_answer=include_answer,
            )
        except SearchError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise SearchError(f"搜索异常: {exc}") from exc

        return SearchResult(
            query=query,
            answer=response.get("answer"),
            results=list(response.get("results", [])),
            api_credits=(response.get("usage") or {}).get(
                "credits", 2 if search_depth == "advanced" else 1
            ),
        )
