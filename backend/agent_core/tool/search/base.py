"""搜索客户端抽象基类。

与 ``agent_core.llm.base.BaseLLM`` 同构：本模块定义「一次搜索」的
最小契约，实现类（tavily / bing / serp ...）各自封装后端 SDK，
治理逻辑（额度拦截、记账）一律不写在这里——由
``services/search_factory`` 用 :func:`agent_core.hooks.hookwrapper`
挂在实例方法外层。

为什么失败要抛异常而不是返回错误字段
------------------------------------
hookwrapper 的语义是「fn 抛出则 post 不触发」——失败不产生计费
副作用。因此客户端契约约定：**失败抛 :class:`SearchError`**，
成功返回 :class:`SearchResult`。错误字符串的转换由上层工具壳完成。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class SearchError(Exception):
    """搜索调用失败（未配置 Key、依赖缺失、接口异常等）。"""


@dataclass
class SearchResult:
    """一次搜索的结构化结果。

    Attributes:
        query:   原始查询词。
        answer:  AI 综合摘要（后端支持时），可为 None。
        results: 结果条目列表 ``[{title, url, content, score}, ...]``。
    """

    query: str = ""
    answer: Optional[str] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    api_credits: float = 1

    @property
    def ok(self) -> bool:
        """是否有可用内容（摘要或至少一条结果）。"""
        return bool(self.answer or self.results)


class BaseSearchClient(ABC):
    """搜索客户端抽象基类。

    实现类构造时接收后端配置（api_key 等），保持无状态、可复用；
    user 级别的治理状态由工厂在实例方法外层注入，不落在实例上。
    """

    #: 后端标识（tavily / bing / ...），用于日志与计价归因
    backend: str = "search"

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
    ) -> SearchResult:
        """执行一次搜索。

        Args:
            query:          搜索关键词或问题。
            max_results:    返回结果条数上限。
            search_depth:   搜索深度（basic / advanced，后端支持时生效）。
            include_answer: 是否请求 AI 综合摘要。

        Returns:
            结构化搜索结果。

        Raises:
            SearchError: 任何失败（未配置 Key、依赖缺失、接口异常）。
        """
