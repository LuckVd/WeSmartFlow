"""
SmartSearchTool: 暴露给 Agent 的统一检索工具

替代原有的 TavilySearch，内部自动路由 + 多源并行 + 筛选。
Agent 只需调这一个工具，复杂性完全封装。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from agent_core.tool.base import BaseTool

logger = logging.getLogger(__name__)


class SmartSearchTool(BaseTool):
    """
    多源智能搜索工具 — 替代单一的 tavily_search。

    内部流程：
    1. Router 分析 query → 决定调哪些源 + 生成各源定制 query
    2. 并行调用 Tavily + AnySearch + DuckDuckGo + arXiv（按需）
    3. 结果筛选：来源可信度评分 → 去重 → 多源交叉验证
    4. 排序后返回 top-8（带可信度标注 + 来源引用）
    """

    name = "smart_search"
    description = (
        "多源智能搜索：自动路由到最佳搜索源（网页/学术/代码/社区），"
        "并行检索后自动去重、验证、排序。"
        "比单一搜索覆盖面更广、结果更准确，适合需要综合信息的场景。\n"
        "直接传入自然语言 query 即可，无需手动选择搜索引擎。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问题（自然语言）",
            },
            "num_results": {
                "type": "integer",
                "description": "期望返回的结果数量，默认 8",
            },
        },
        "required": ["query"],
    }

    def __init__(
        self,
        tavily_client=None,
        tavily_key: Optional[str] = None,
        anysearch_key: Optional[str] = None,
        llm_func=None,
        user_id: str = "",
    ):
        """
        Args:
            tavily_client: 工厂产出的 BaseSearchClient（已挂额度拦截 +
                           记账 hook，见 services/search_factory）。
            tavily_key:    未注入 client 时的回退 Key（兼容脚本用法）。
            anysearch_key: AnySearch API Key
            llm_func:      异步 LLM 函数，用于复杂路由决策
        """
        self._user_id = user_id
        self._tavily_client = tavily_client
        self._tavily_key = tavily_key or os.getenv("TAVILY_API_KEY", "")
        self._anysearch_key = anysearch_key or os.getenv("ANYSEARCH_API_KEY", "")
        self._llm_func = llm_func
        self._service = None  # 懒加载
        super().__init__()

    def _get_service(self):
        """懒加载 SmartSearchService（避免 import 时就初始化）"""
        if self._service is None:
            from .service import SmartSearchService

            self._service = SmartSearchService(
                user_id=self._user_id,
                tavily_client=self._tavily_client,
                tavily_key=self._tavily_key,
                anysearch_key=self._anysearch_key,
                llm_func=self._llm_func,
            )
        return self._service

    def run(self, query: str, num_results: int = 8, **kwargs: Any) -> str:
        """同步执行（会 block，在 Agent 框架中会被 to_thread 包装）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已在 async 上下文中（Agent 框架常见情况）
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run, self._async_search(query, num_results)
                    ).result(timeout=30)
            else:
                result = asyncio.run(self._async_search(query, num_results))
            return result
        except Exception as e:
            logger.error("[SmartSearchTool] 执行异常: %s", e)
            return f"搜索失败: {e}"

    async def async_run(self, query: str, num_results: int = 8, **kwargs: Any) -> str:
        """异步执行（推荐，Agent 框架会优先调这个）"""
        return await self._async_search(query, num_results)

    async def _async_search(self, query: str, num_results: int) -> str:
        """核心执行逻辑"""
        service = self._get_service()
        result = await service.search(query, top_k=num_results)

        # 返回精简文本给 Agent（控制 token 消耗）
        return result.to_agent_text()
