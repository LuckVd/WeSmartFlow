"""会话记忆的持久化后端协议。

框架（``agent_core.memory``）定义协议、业务侧实现——这是框架不反向
import 业务模块（如 ``database.py``）的依赖倒置边界。

协议覆盖三类原语（各自独立读写，压缩策略不在此处）：

1. **详细历史消息**：按索引区间读取（``from_index``/``to_index``），
   消息的全量顺序由实现方保证单调追加；
2. **压缩摘要**：文本 + 覆盖游标（``summarized_until``，即「摘要已
   覆盖到第几条消息」）成对读写；
3. **刷新**（可选）：实现方若缓存了快照（如构造时预载的 detail），
   应支持丢弃缓存、下次读取时重新加载——供 ``SessionMemory.flush``
   在运行结束后看到最新落库的消息。
"""

from __future__ import annotations

from typing import List, Optional, Protocol, Tuple, runtime_checkable

from .base import Message


@runtime_checkable
class SessionStore(Protocol):
    """会话记忆持久化协议（业务实现，框架消费）。"""

    def load_message_count(self) -> int:
        """持久化的消息总数（用于计算摘要覆盖窗口）。"""
        ...

    def load_messages(
        self, from_index: int = 0, to_index: Optional[int] = None
    ) -> List[Message]:
        """按索引区间读取消息（``[from_index, to_index)``）。

        支持返回实现方原生形态（Pydantic 模型或 dict），由
        :func:`agent_core.memory.base.normalize_history` 统一规整。
        """
        ...

    def load_summary(self) -> Tuple[str, int]:
        """读取压缩摘要，返回 ``(summary_text, summarized_until)``。

        无摘要时返回 ``("", 0)``。
        """
        ...

    def save_summary(self, text: str, summarized_until: int) -> None:
        """持久化摘要并推进覆盖游标（两者成对写入）。"""
        ...


__all__ = ["SessionStore"]
