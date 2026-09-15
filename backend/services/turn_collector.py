"""对话轮次副作用收集与持久化。

一轮对话中，工具会产生多种副作用：创建知识节点、生成卡片、生成测验、
更新掌握度。本模块负责：

1. **收集**：作为工具 ``on_result_hook`` 累积这些副作用
2. **产出事件**：返回 :class:`DomainEvent` 供框架并入事件流（有序）
3. **持久化**：轮次结束时把 assistant 消息与关联产物写库

改造前这些逻辑埋在 ``TutorService`` 里，且 hook 只能把事件塞进旁路
``asyncio.Queue`` 再手工 flush——事件顺序取决于 flush 时机而非实际发生顺序。
现在 hook 直接返回事件，顺序由框架保证。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.events import file_created, mastery_updated, node_created
from models.session import MessageArtifacts, MessageSchema, SessionFile

logger = logging.getLogger(__name__)

#: 生成文件类卡片的工具名
_CARD_TOOLS = ("generate_html_card", "generate_interactive_viz")


class TurnCollector:
    """收集一轮对话中工具产生的副作用。

    用作工具的 ``on_result_hook``：框架每次工具执行完成后调用
    :meth:`on_tool_result`，本类累积状态并返回业务事件。

    Attributes:
        mastery_changes: ``{node_id: 累计 delta}``
        created_node_ids: 本轮新建的知识节点 ID
        created_quiz_ids: 本轮新建的测验 ID
        ordered_files:   按工具调用序号排列的产物插槽（含 None 空洞）
    """

    def __init__(self) -> None:
        self.mastery_changes: Dict[str, float] = {}
        self.created_node_ids: List[str] = []
        self.created_quiz_ids: List[str] = []
        self.ordered_files: List[Optional[Dict[str, Any]]] = []

    # ------------------------------------------------------------------
    # Hook 入口
    # ------------------------------------------------------------------

    def on_tool_result(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: Any,
        index: int = 0,
    ) -> Optional[Any]:
        """工具结果 hook。

        Args:
            tool_name: 工具名。
            params:    调用参数。
            result:    工具返回值。
            index:     该次调用的**全局序号**，用于产物保序。

        Returns:
            :class:`DomainEvent` 或 None（无副作用时）。
        """
        logger.debug("[Turn] 工具 %s 完成 index=%d", tool_name, index)

        if tool_name in _CARD_TOOLS:
            return self._on_card(tool_name, params, result, index)
        if tool_name == "create_node":
            return self._on_node(result)
        if tool_name == "create_quiz":
            return self._on_quiz(params, result, index)
        if tool_name == "update_mastery":
            return self._on_mastery(params, result)
        return None

    # 允许直接把实例当回调传递
    __call__ = on_tool_result

    # ------------------------------------------------------------------
    # 各类副作用
    # ------------------------------------------------------------------

    def _on_card(
        self, tool_name: str, params: Dict[str, Any], result: Any, index: int
    ) -> Optional[Any]:
        """HTML 卡片 / 交互可视化生成完毕。"""
        if not isinstance(result, str) or result.startswith("Error"):
            return None

        try:
            if tool_name == "generate_html_card":
                # 返回 JSON {file_id, script}
                file_id = json.loads(result).get("file_id", "")
                file_type = "html_card"
            else:
                # generate_interactive_viz 返回纯 viz_id
                file_id = result.strip()
                file_type = "viz"
        except (json.JSONDecodeError, AttributeError):
            logger.warning("[Turn] %s 返回值解析失败", tool_name)
            return None

        if not file_id:
            return None

        title = params.get("title", "")
        self._put_file(index, file_id, title, file_type)
        return file_created(
            file_id=file_id, title=title, file_type=file_type, index=index
        )

    def _on_node(self, result: Any) -> Optional[Any]:
        """知识节点创建完毕。"""
        data = self._as_dict(result, "create_node")
        if not data or not data.get("created"):
            return None
        node_id = data.get("node_id", "")
        if not node_id:
            return None
        self.created_node_ids.append(node_id)
        return node_created(node_id=node_id, title=data.get("title", ""))

    def _on_quiz(
        self, params: Dict[str, Any], result: Any, index: int
    ) -> Optional[Any]:
        """测验创建完毕。

        测验也占用 ordered_files 插槽，以保证与卡片的相对展示顺序。
        """
        data = self._as_dict(result, "create_quiz")
        if not data or "quiz_id" not in data:
            return None

        quiz_id = data["quiz_id"]
        self.created_quiz_ids.append(quiz_id)

        question = params.get("question", "")
        title = (question[:20] + "…") if len(question) > 20 else (question or "练习题")

        self._put_file(index, quiz_id, title, "quiz")
        return file_created(file_id=quiz_id, title=title, file_type="quiz", index=index)

    def _on_mastery(self, params: Dict[str, Any], result: Any) -> Optional[Any]:
        """掌握度更新。"""
        node_id = params.get("node_id")
        delta = params.get("delta", 0.0)
        if not node_id:
            return None
        if isinstance(result, str) and result.startswith("Error"):
            return None

        self.mastery_changes[node_id] = self.mastery_changes.get(node_id, 0.0) + delta
        return mastery_updated(node_id=node_id, delta=delta)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _put_file(self, index: int, file_id: str, title: str, file_type: str) -> None:
        """把产物写入指定序号的插槽（不足则补 None 占位）。"""
        while len(self.ordered_files) <= index:
            self.ordered_files.append(None)
        self.ordered_files[index] = {
            "file_id": file_id,
            "title": title,
            "file_type": file_type,
        }

    @staticmethod
    def _as_dict(result: Any, tool_name: str) -> Optional[Dict[str, Any]]:
        """把工具返回值规整为字典。"""
        if isinstance(result, dict):
            return result
        if not isinstance(result, str):
            return None
        try:
            data = json.loads(result)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            logger.warning("[Turn] %s 返回值非合法 JSON", tool_name)
            return None

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    @property
    def files(self) -> List[Dict[str, Any]]:
        """按序号排列的产物列表（已剔除空洞）。"""
        return [f for f in self.ordered_files if f is not None]

    @property
    def file_ids(self) -> List[str]:
        """按序号排列的产物 ID 列表。"""
        return [f["file_id"] for f in self.files]

    @property
    def node_refs(self) -> List[str]:
        """掌握度有变化的**已有**节点（排除本轮新建的）。"""
        return list(set(self.mastery_changes) - set(self.created_node_ids))

    @property
    def all_node_ids(self) -> List[str]:
        """本轮涉及的全部节点 ID。"""
        return list(set(self.created_node_ids) | set(self.mastery_changes))

    def to_artifacts(self) -> MessageArtifacts:
        """构造 assistant 消息的产物清单。"""
        return MessageArtifacts(
            files=self.file_ids,
            new_nodes=list(self.created_node_ids),
            node_refs=self.node_refs,
            mastery_delta=dict(self.mastery_changes),
            quiz_ids=list(self.created_quiz_ids),
        )

    def build_assistant_message(
        self, content: str, message_id: Optional[str] = None
    ) -> MessageSchema:
        """构造带产物清单的 assistant 消息。"""
        return MessageSchema(
            id=message_id or str(uuid.uuid4()),
            role="assistant",
            content=content,
            created_at=datetime.now(timezone.utc),
            artifacts=self.to_artifacts(),
        )

    def session_files(self, message_id: str) -> List[SessionFile]:
        """构造会话文件记录（关联到指定 assistant 消息）。"""
        return [
            SessionFile(
                file_id=f["file_id"],
                file_type=f["file_type"],
                title=f.get("title", ""),
                from_message_id=message_id,
                created_at=datetime.now(timezone.utc),
            )
            for f in self.files
        ]

    def __repr__(self) -> str:
        return (
            f"<TurnCollector nodes={len(self.created_node_ids)} "
            f"files={len(self.files)} quizzes={len(self.created_quiz_ids)} "
            f"mastery={len(self.mastery_changes)}>"
        )


__all__ = ["TurnCollector"]
