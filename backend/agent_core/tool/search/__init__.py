"""搜索客户端抽象：与 BaseLLM 同构的基础调用层。

实现类只负责「一次搜索」的纯调用（框架层不认识业务）；
额度拦截与用量记账由业务层工厂通过 hookwrapper 挂在
:meth:`BaseSearchClient.search` 外层（见 services/search_factory.py）。
"""

from .base import BaseSearchClient, SearchError, SearchResult
from .tavily import TavilySearchClient

__all__ = [
    "BaseSearchClient",
    "SearchError",
    "SearchResult",
    "TavilySearchClient",
]
