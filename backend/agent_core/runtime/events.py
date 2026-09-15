"""业务语义事件。

框架**不定义**任何具体业务事件（如"卡片已生成""掌握度更新"），只提供
一个不透明的信封 :class:`DomainEvent`：``kind`` 标识语义、``payload``
携带数据。框架负责在正确的位置把它并入事件流，不解释其内容。

这样 ``agent_core`` 可以整体复用到任何领域（客服、代码、教育），
业务侧在自己的 ``agents/events.py`` 里定义 ``kind`` 常量和强类型包装。

业务侧典型用法::

    KIND_FILE_CREATED = "file_created"

    def file_created(file_id: str, title: str = "") -> DomainEvent:
        return DomainEvent(KIND_FILE_CREATED, {"file_id": file_id, "title": title})

    # 在工具 hook 里
    ctx.emit(file_created(fid, title))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DomainEvent:
    """业务语义事件信封。

    Attributes:
        kind:    业务事件类型标识，由业务侧自行约定（框架不校验）。
        payload: 事件数据，需可 JSON 序列化以便直接推送前端。
        source:  产生该事件的工具名或节点名，便于排查（框架自动填充）。
    """

    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "payload": dict(self.payload), "source": self.source}

    def __repr__(self) -> str:
        return f"<DomainEvent {self.kind} payload_keys={list(self.payload)}>"


__all__ = ["DomainEvent"]
