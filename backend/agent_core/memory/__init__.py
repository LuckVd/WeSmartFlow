"""对话记忆。

框架提供协议 + 三种开箱策略 + 一种持久化会话记忆，业务侧只选策略不写实现：

- :class:`FullMemory`     默认，保留全部（向后兼容）
- :class:`WindowMemory`   滑动窗口，适合长对话且不需要早期信息
- :class:`SummaryMemory`  滚动摘要，适合长对话且需要保留早期结论
- :class:`SessionMemory`  跨 run 连续：store 持久化 + 锚点/轨迹/摘要压缩合一
                          （``SessionStore`` 协议由业务实现）

注意：本包只管**对话上下文压缩**。长期记忆（用户画像、知识图谱）属于
业务领域，应通过 ``ContextProvider`` 注入 system prompt，不要混入此处。
"""

from .base import (
    BaseMemory,
    Message,
    estimate_tokens,
    is_pair_complete,
    safe_cut,
)
from .session_memory import SessionMemory
from .store import SessionStore
from .strategies import FullMemory, SummaryMemory, WindowMemory

__all__ = [
    "BaseMemory",
    "Message",
    "FullMemory",
    "WindowMemory",
    "SummaryMemory",
    "SessionMemory",
    "SessionStore",
    "safe_cut",
    "is_pair_complete",
    "estimate_tokens",
]
