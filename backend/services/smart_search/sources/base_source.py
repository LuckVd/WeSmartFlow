"""搜索源基类"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import SearchResult


class BaseSource(ABC):
    """所有搜索源 adapter 的统一基类。"""

    # 子类必须设置
    source_id: str = ""
    display_name: str = ""
    description: str = ""
    # 支持的模态和语言
    modalities: list[str] = ["text"]
    languages: list[str] = ["zh", "en"]

    @abstractmethod
    async def search(
        self, query: str, max_results: int = 5, **kwargs
    ) -> list[SearchResult]:
        """
        执行搜索，返回统一格式的 SearchResult 列表。

        每个子类要做到：
        1. 调 API / 本地查询
        2. 异常处理（不抛到外面，返回空列表或带 error 的结果）
        3. 返回格式统一

        Args:
            query: 搜索关键词（已由 Router 针对该源定制化）
            max_results: 最大返回条数
            **kwargs: 源特有参数

        Returns:
            list[SearchResult]
        """
        ...

    def is_available(self) -> bool:
        """检查该源是否可用（有 API key / 网络通 等）"""
        return True

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.source_id}>"
