"""``SessionStore`` 协议的 SQLite 实现（包装 SessionRepository）。

框架层 ``agent_core.memory.SessionMemory`` 通过协议消费本类；持久化
位置与字段名（``workspace.history_summary`` / ``workspace.summarized_until``）
沿用历史滚动摘要的存储布局，已有会话数据无需迁移。

顺序契约（重要）
----------------
``SessionMemory`` 在构造时立即加载历史并固化快照。为避免本轮用户
消息同时出现在「历史段」和「锚点」，快照必须代表**本轮开始前**的
状态——调用方先构造 memory、本轮消息在运行结束后再落库，契约即
天然满足（tutor 当前做法：user/assistant 成对延迟落库）。

``SessionMemory`` 为懒压缩：render 撞窗/预算紧张时才调
``save_summary``（写摘要 + 推进绝对游标）。运行中本轮消息不落库，
DB 不会变化，游标推进始终指向已持久化的消息。
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from agent_core.memory.base import Message, normalize_history

logger = logging.getLogger(__name__)


class SQLiteSessionStore:
    """以 ``sessions`` / ``messages`` / ``workspace`` 为后端的会话存储。"""

    def __init__(self, session_repo, session_id: str):
        """
        Args:
            session_repo: ``SessionRepository`` 实例。
            session_id:   会话 ID。
        """
        self._repo = session_repo
        self._session_id = session_id
        self._detail = None  # 懒加载缓存；refresh() 后下次读取重新查库

    # ── 内部 ─────────────────────────────────────────────

    def _load_detail(self):
        if self._detail is None:
            self._detail = self._repo.get_detail(self._session_id)
        return self._detail

    def refresh(self) -> None:
        """丢弃缓存快照，下次读取时重新加载（供 flush 看到新落库消息）。"""
        self._detail = None

    # ── SessionStore 协议 ───────────────────────────────

    def load_message_count(self) -> int:
        detail = self._load_detail()
        if not detail or not detail.messages:
            return 0
        return len(detail.messages)

    def load_messages(
        self, from_index: int = 0, to_index: Optional[int] = None
    ) -> List[Message]:
        detail = self._load_detail()
        if not detail or not detail.messages:
            return []
        raw = detail.messages[from_index:to_index]
        return normalize_history(raw)

    def load_summary(self) -> Tuple[str, int]:
        detail = self._load_detail()
        workspace = (detail.workspace or {}) if detail else {}
        try:
            until = int(workspace.get("summarized_until") or 0)
        except (TypeError, ValueError):
            until = 0
        text = (workspace.get("history_summary") or "").strip()
        return text, until

    def save_summary(self, text: str, summarized_until: int) -> None:
        self._repo.update_workspace(
            self._session_id,
            workspace={
                "history_summary": text,
                "summarized_until": summarized_until,
            },
        )
        self.refresh()  # 缓存失效

    def __repr__(self) -> str:
        return f"<SQLiteSessionStore session={self._session_id}>"


__all__ = ["SQLiteSessionStore"]
