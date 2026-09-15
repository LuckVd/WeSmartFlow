"""业务语义事件定义。

框架（``agent_core``）只认识不透明的 :class:`DomainEvent` 信封，不解释其内容。
本模块定义本产品的具体业务事件语义——这样"掌握度""卡片类型"这类教育领域
概念不会污染框架的事件协议。

用法（工具 hook 中）::

    def _hook(self, tool_name, params, result, index):
        return file_created(file_id=fid, title=t, file_type="html", index=index)

消费侧（Service / Router）::

    if isinstance(ev, DomainEvent) and ev.kind == KIND_FILE_CREATED:
        file_id = ev.payload["file_id"]
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agent_core.runtime.events import DomainEvent

# ----------------------------------------------------------------------
# 事件 kind 常量
# ----------------------------------------------------------------------

#: 文件（HTML 卡片 / 可视化 / 测验）生成完毕
KIND_FILE_CREATED = "file_created"

#: 知识节点被创建
KIND_NODE_CREATED = "node_created"

#: 节点掌握度发生变化
KIND_MASTERY_UPDATED = "mastery_updated"

#: 测验被创建
KIND_QUIZ_CREATED = "quiz_created"

#: 课程生成流水线阶段推进
KIND_COURSE_STAGE = "course_stage"


# ----------------------------------------------------------------------
# 构造器
# ----------------------------------------------------------------------


def file_created(
    file_id: str,
    title: str = "",
    file_type: str = "",
    index: int = 0,
    **extra: Any,
) -> DomainEvent:
    """构造"文件已生成"事件。

    Args:
        file_id:   文件相对路径或标识。
        title:     文件标题（如卡片标题）。
        file_type: 文件类型：``html`` / ``quiz`` / ``viz``。
        index:     该文件对应的工具调用全局序号，用于前端保序展示。
    """
    return DomainEvent(
        KIND_FILE_CREATED,
        {
            "file_id": file_id,
            "title": title,
            "file_type": file_type,
            "index": index,
            **extra,
        },
    )


def node_created(node_id: str, title: str = "", **extra: Any) -> DomainEvent:
    """构造"知识节点已创建"事件。"""
    return DomainEvent(KIND_NODE_CREATED, {"node_id": node_id, "title": title, **extra})


def mastery_updated(node_id: str, delta: float, **extra: Any) -> DomainEvent:
    """构造"掌握度变化"事件。

    Args:
        node_id: 节点 ID。
        delta:   本次变化量（可正可负）。
    """
    return DomainEvent(
        KIND_MASTERY_UPDATED, {"node_id": node_id, "delta": delta, **extra}
    )


def quiz_created(quiz_id: str, node_id: str = "", **extra: Any) -> DomainEvent:
    """构造"测验已创建"事件。"""
    return DomainEvent(
        KIND_QUIZ_CREATED, {"quiz_id": quiz_id, "node_id": node_id, **extra}
    )


def course_stage(
    stage: str, pct: int = 0, message: str = "", **extra: Any
) -> DomainEvent:
    """构造"课程生成阶段推进"事件。

    Args:
        stage:   阶段标识，如 ``outline`` / ``research`` / ``tex``。
        pct:     进度百分比 0-100。
        message: 展示给用户的说明文本。
    """
    return DomainEvent(
        KIND_COURSE_STAGE,
        {"stage": stage, "pct": pct, "message": message, **extra},
    )


# ----------------------------------------------------------------------
# 消费辅助
# ----------------------------------------------------------------------


def payload_of(event: Any, kind: str) -> Optional[Dict[str, Any]]:
    """若 event 是指定 kind 的 DomainEvent，返回其 payload，否则 None。

    便于消费侧写扁平的分支::

        if (p := payload_of(ev, KIND_FILE_CREATED)):
            handle_file(p["file_id"])
    """
    if isinstance(event, DomainEvent) and event.kind == kind:
        return event.payload
    return None


__all__ = [
    "KIND_COURSE_STAGE",
    "KIND_FILE_CREATED",
    "KIND_MASTERY_UPDATED",
    "KIND_NODE_CREATED",
    "KIND_QUIZ_CREATED",
    "course_stage",
    "file_created",
    "mastery_updated",
    "node_created",
    "payload_of",
    "quiz_created",
]
