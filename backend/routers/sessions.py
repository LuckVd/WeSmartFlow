"""
会话路由（含 SSE 流式聊天）
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.streaming import encode_sse_event, event_stream_headers
from models.session import SessionCreate, ChatMessage, SessionSchema, SessionDetail
from services import TutorService
from agent_core.agent.events import (
    AgentThinkChunkEvent,
    AgentThinkEvent,
    AgentToolCallChunkEvent,
    AgentToolCallEvent,
    AgentToolRunEvent,
    AgentToolResultEvent,
    AgentFinalEvent,
    DomainEvent,
    extract_event_text,
)
from agents.events import (
    KIND_FILE_CREATED,
    KIND_MASTERY_UPDATED,
    KIND_NODE_CREATED,
)
from dependencies import get_current_user
from services.credit_quota import CreditsExceeded
from services.content_guard import get_content_guard
from utils.validators import SessionIdPath

logger = logging.getLogger(__name__)


def _sse(payload: dict) -> str:
    """Emit the shared SSE envelope while preserving legacy top-level fields."""
    event_type = str(payload.get("type") or "progress")
    return encode_sse_event(
        event_type, **{k: v for k, v in payload.items() if k != "type"}
    )


def _serialize_run_content(content) -> str:
    """将 AgentToolRunEvent.content 序列化为前端可解析的字符串。

    - str：直接返回
    - AgentThinkChunkEvent / AgentThinkEvent：序列化为 {type, delta/content} JSON
    - AgentToolCallEvent / AgentToolResultEvent：序列化为 {type, tool, result} JSON
    - 其他事件：返回空字符串
    """
    if isinstance(content, str):
        return content
    if isinstance(content, AgentThinkChunkEvent):
        return json.dumps(
            {"type": "think_chunk", "delta": content.delta}, ensure_ascii=False
        )
    if isinstance(content, AgentThinkEvent):
        return json.dumps(
            {"type": "thinking", "content": content.content}, ensure_ascii=False
        )
    if isinstance(content, AgentToolCallEvent):
        return json.dumps(
            {"type": "tool_call", "tool": content.tool_name}, ensure_ascii=False
        )
    if isinstance(content, AgentToolResultEvent):
        result_text = extract_event_text(content.result)
        return json.dumps(
            {
                "type": "tool_result",
                "tool": content.tool_name,
                "result": result_text[:120],
            },
            ensure_ascii=False,
        )
    return ""


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSchema])
def list_sessions(user_id: str = Depends(get_current_user)):
    from services.immersive.job_manager import manager as immersive_jobs

    sessions = TutorService().list_sessions(user_id)
    # 状态仍为 running/background 但进程内已没有对应任务（如服务重启），
    # 对外按"已中断"展示，避免历史页永远显示"后台处理中"。仅读时覆盖，不落盘。
    for s in sessions:
        ws = s.workspace or {}
        if ws.get("generation_status") in {
            "running",
            "background",
        } and not immersive_jobs.is_running(s.id):
            s.workspace = {**ws, "generation_status": "interrupted"}
    return sessions


@router.post("", response_model=SessionSchema, status_code=201)
def create_session(data: SessionCreate, user_id: str = Depends(get_current_user)):
    return TutorService().create_session(user_id, data)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: SessionIdPath, user_id: str = Depends(get_current_user)):
    detail = TutorService().get_session_detail(user_id, session_id)
    if not detail:
        raise HTTPException(404, "会话不存在")
    return detail


@router.post("/{session_id}/chat/stream")
async def chat_stream(
    request: Request,
    session_id: SessionIdPath,
    body: ChatMessage,
    user_id: str = Depends(get_current_user),
):
    """
    SSE 流式聊天接口。

    每条 SSE 消息格式：data: <JSON>\\n\\n
    JSON 通过 type 字段区分事件类型：

    - think_chunk   — LLM 思考文本分片（流式）  { type, delta, step }
    - thinking      — LLM 本轮思考汇总          { type, content, step }
    - tool_call_chunk — tool_call 参数分片      { type, index, id, tool, args_delta, step }
    - tool_call     — 工具调用完整信息          { type, id, tool, args, step }
    - tool_run      — 工具执行过程事件          { type, id, tool, content, step }
    - tool_result   — 工具最终结果              { type, id, tool, args, result, step }
    - text_reply    — 最终回复完整文本          { type, text }
    - done          — 回复完成                  { type, mastery_changes }
    - file_created  — 文件生成                  { type, file_id }
    - node_created  — 节点创建                  { type, node_id, title }
    - mastery_updated — 掌握度更新              { type, node_id, delta }
    - error         — 错误                      { type, message }
    """
    # ── 内容安全审核（输入） ──
    guard = get_content_guard()
    if guard.enabled:
        guard_result = await guard.check_input(body.content)
        if not guard_result.is_safe:
            guard.log_violation(user_id, body.content, guard_result)

            async def blocked_stream():
                yield _sse(
                    {
                        "type": "error",
                        "message": guard_result.reason,
                        "code": "content_blocked",
                    }
                )

            return StreamingResponse(
                blocked_stream(),
                media_type="text/event-stream",
                headers=event_stream_headers(),
            )

    service = TutorService()

    async def event_stream():
        """直接迭代 Agent 事件流，序列化为 SSE 格式输出。"""
        mastery_changes: dict[str, float] = {}
        try:
            async for event in service.stream_chat(user_id, session_id, body.content):
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.info("客户端断开，停止生成")
                    break

                if isinstance(event, AgentThinkChunkEvent):
                    data = {
                        "type": "think_chunk",
                        "delta": event.delta,
                        "step": event.step,
                    }
                    yield _sse(data)
                elif isinstance(event, AgentToolCallChunkEvent):
                    data = {
                        "type": "tool_call_chunk",
                        "index": event.index,
                        "id": event.id,
                        "tool": event.tool_name,
                        "args_delta": event.arguments_delta,
                        "step": event.step,
                    }
                    yield _sse(data)
                elif isinstance(event, AgentToolRunEvent):
                    serialized = _serialize_run_content(event.content)
                    if not serialized:
                        continue  # 跳过无意义的空事件（如业务事件）
                    data = {
                        "type": "tool_run",
                        "id": event.id,
                        "tool": event.tool_name,
                        "content": serialized,
                        "step": event.step,
                    }
                    yield _sse(data)
                elif (
                    isinstance(event, DomainEvent)
                    and event.kind == KIND_MASTERY_UPDATED
                ):
                    node_id = event.payload.get("node_id", "")
                    delta = event.payload.get("delta", 0.0)
                    mastery_changes[node_id] = mastery_changes.get(node_id, 0.0) + delta
                    data = {
                        "type": "mastery_updated",
                        "node_id": node_id,
                        "delta": delta,
                    }
                    yield _sse(data)
                elif isinstance(event, AgentFinalEvent):
                    # ── 内容安全审核（输出净化） ──
                    final_text = guard.sanitize_output(event.content)
                    yield _sse({"type": "text_reply", "text": final_text})
                    yield _sse({"type": "done", "mastery_changes": mastery_changes})
                elif isinstance(event, AgentThinkEvent):
                    data = {
                        "type": "thinking",
                        "content": event.content,
                        "step": event.step,
                    }
                    yield _sse(data)
                elif isinstance(event, AgentToolCallEvent):
                    data = {
                        "type": "tool_call",
                        "id": event.id,
                        "tool": event.tool_name,
                        "args": event.arguments,
                        "step": event.step,
                    }
                    yield _sse(data)
                elif isinstance(event, AgentToolResultEvent):
                    data = {
                        "type": "tool_result",
                        "id": event.id,
                        "tool": event.tool_name,
                        "args": event.arguments,
                        "result": extract_event_text(event.result),
                        "step": event.step,
                    }
                    yield _sse(data)
                elif isinstance(event, DomainEvent) and event.kind == KIND_FILE_CREATED:
                    data = {
                        "type": "file_created",
                        "file_id": event.payload.get("file_id", ""),
                        "title": event.payload.get("title", ""),
                        "file_type": event.payload.get("file_type", ""),
                    }
                    yield _sse(data)
                elif isinstance(event, DomainEvent) and event.kind == KIND_NODE_CREATED:
                    data = {
                        "type": "node_created",
                        "node_id": event.payload.get("node_id", ""),
                        "title": event.payload.get("title", ""),
                    }
                    yield _sse(data)
        except asyncio.CancelledError:
            pass  # 客户端断开，静默退出
        except CreditsExceeded as e:
            yield _sse(
                {
                    "type": "error",
                    "message": str(e),
                    "code": "credits_exceeded",
                    "quota": e.quota,
                    "used": e.used,
                }
            )
        except ValueError:
            yield _sse(
                {
                    "type": "error",
                    "message": "请求无法处理，请检查输入后重试。",
                    "code": "invalid_request",
                }
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception("聊天流处理失败")
            yield _sse(
                {
                    "type": "error",
                    "message": "服务暂时不可用，请稍后重试。",
                    "code": "internal_error",
                    "retryable": True,
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=event_stream_headers(),
    )


class DurationUpdate(BaseModel):
    minutes: int


@router.patch("/{session_id}/duration")
def update_duration(
    session_id: SessionIdPath,
    body: DurationUpdate,
    user_id: str = Depends(get_current_user),
):
    """记录本次会话的学习时长（前端离开页面时调用）"""
    try:
        TutorService().record_duration(user_id, session_id, body.minutes)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))
