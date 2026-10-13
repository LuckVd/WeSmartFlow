"""
沉浸式学习（AI主导学习）路由

提供：
  POST /api/immersive/generate            — SSE 流式生成课件（核心接口）
  POST /api/immersive/resume              — 断点续传（恢复生成）
  GET  /api/immersive/exercises/:sid/:cid  — 获取结构化习题数据
  POST /api/immersive/quiz-result          — 上报答题结果
  POST /api/immersive/complete             — 用户确认完成学习
  GET  /api/immersive/courses             — 列出已生成的课程
  GET  /api/immersive/suggestions         — 个性化推荐云朵

文件读取统一走 ``/api/documents/{doc_id}/raw|asset/{sub}`` 接口，
本路由不再提供静态文件服务。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import Field

from api.contracts import ApiRequest, ApiResponse, standard_error_responses
from api.streaming import encode_sse_event, event_stream_headers

from services.immersive import (
    immersive_generate,
    immersive_resume,
    get_exercises_for_chapter,
    complete_immersive_session,
)
from services.immersive.persistence import create_session, update_workspace
from services.immersive.job_manager import manager as immersive_jobs
from services.immersive.sse import sse_event
from repositories import SessionRepository
from config import COURSES_DIR
from dependencies import get_current_user
from services.credit_quota import CreditsExceeded
from services.content_guard import get_content_guard
from utils.validators import SessionIdField, SessionIdPath, sanitize_uuid
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/immersive", tags=["immersive"])

_GENERATE_LOCKS: dict[str, asyncio.Lock] = {}


def _normalize_topic_for_lock(topic: str) -> str:
    return re.sub(r"\s+", "", (topic or "").strip().lower())


def _generate_lock_for(user_id: str, topic: str) -> asyncio.Lock:
    key = f"{user_id}:{_normalize_topic_for_lock(topic)}"
    lock = _GENERATE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _GENERATE_LOCKS[key] = lock
    return lock


# ── 请求模型 ─────────────────────────────────────────────────────


class GenerateRequest(ApiRequest):
    topic: str = Field(min_length=1, max_length=200, description="要学习的主题")
    user_profile: str = Field(default="", max_length=8_000)
    enable_audio: bool = False
    enable_exercises: bool = True


class JobRequest(ApiRequest):
    session_id: SessionIdField


class JobControlResponse(ApiResponse):
    ok: bool
    session_id: str
    mode: Literal["background", "cancelled"]


class ResumeRequest(ApiRequest):
    session_id: SessionIdField


class QuizAnswerItem(ApiRequest):
    question: str = Field(default="", max_length=8_000)
    user_answer: str = Field(default="", max_length=2_000)
    correct_answer: str = Field(default="", max_length=2_000)
    correct: bool = False
    difficulty: str = Field(default="", max_length=32)


class QuizResultRequest(ApiRequest):
    session_id: SessionIdField
    chapter_id: int = Field(ge=1, le=200)
    chapter_title: str = Field(default="", max_length=500)
    results: list[QuizAnswerItem] = Field(default_factory=list, max_length=100)


class QuizResultResponse(ApiResponse):
    status: Literal["ok", "partial"]
    message: str = ""
    accuracy: float | None = None
    mastery_level: str | None = None
    details: dict[str, dict[str, float]] = Field(default_factory=dict)
    learning_map_evidence: list[dict[str, Any]] = Field(default_factory=list)


class CompleteRequest(ApiRequest):
    session_id: SessionIdField
    feedback: str = Field(default="", max_length=4_000)


class CourseSummary(ApiResponse):
    slug: str
    topic: str
    overview: str = ""
    total_chapters: int = Field(ge=0)
    completed_chapters: int = Field(ge=0)
    # Legacy clients currently receive this server path.  Keep it in the
    # contract until the next API version can replace it with a course ID.
    path: str = ""


class CourseListResponse(ApiResponse):
    courses: list[CourseSummary] = Field(default_factory=list)


class SuggestionsResponse(ApiResponse):
    suggestions: list[dict] = Field(default_factory=list)
    source: str = "default"


# ── SSE 生成接口 ─────────────────────────────────────────────────


@router.post(
    "/generate",
    operation_id="start_immersive_generation",
    responses=standard_error_responses(400, 401, 422, 429, 503),
)
async def generate_immersive(
    req: GenerateRequest, request: Request, user_id: str = Depends(get_current_user)
):
    """SSE 流式生成沉浸式课件。"""
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="topic 不能为空")

    # ── 内容安全审核（输入） ──
    guard = get_content_guard()
    if guard.enabled:
        guard_result = await guard.check_input(req.topic.strip())
        if not guard_result.is_safe:
            guard.log_violation(user_id, req.topic, guard_result)
            raise HTTPException(
                status_code=400,
                detail=guard_result.reason,
            )

    topic = req.topic.strip()
    reused_session = False
    lock = _generate_lock_for(user_id, topic)
    async with lock:
        repo = SessionRepository()
        reusable = repo.find_active_immersive_by_topic(user_id, topic)
        if reusable:
            session_id = reusable.id
            reused_session = True
            logger.info(
                "复用同 topic 沉浸式生成会话: user=%s topic=%s session=%s running=%s",
                safe_log(user_id),
                safe_log(topic),
                safe_log(session_id),
                immersive_jobs.is_running(session_id),
            )
            if not immersive_jobs.is_running(session_id):
                update_workspace(session_id, workspace={"generation_status": "running"})
                immersive_jobs.start(
                    session_id,
                    user_id,
                    immersive_resume(session_id=session_id, user_id=user_id),
                )
        else:
            session_id = create_session(topic, user_id=user_id)
            update_workspace(
                session_id,
                workspace={
                    "generation_status": "running",
                    "topic": topic,
                    "enable_audio": req.enable_audio,
                    "enable_exercises": req.enable_exercises,
                },
            )
            immersive_jobs.start(
                session_id,
                user_id,
                immersive_generate(
                    topic=topic,
                    user_profile=req.user_profile or "",
                    user_id=user_id,
                    enable_audio=req.enable_audio,
                    enable_exercises=req.enable_exercises,
                    session_id=session_id,
                ),
            )

    async def event_stream():
        try:
            if reused_session:
                yield sse_event(
                    "session_reused",
                    session_id=session_id,
                    topic=topic,
                    message=f"已接回正在生成的课程「{topic}」",
                )
            async for event in immersive_jobs.subscribe(session_id):
                if await request.is_disconnected():
                    # A lost browser is treated as “continue in background”.
                    # The explicit stop endpoint is the only destructive path.
                    immersive_jobs.detach(session_id)
                    logger.info(
                        "客户端断开，沉浸式任务转入后台: %s", safe_log(session_id)
                    )
                    break
                yield event
        except CreditsExceeded as e:
            yield encode_sse_event(
                "error",
                message=str(e),
                code="credits_exceeded",
                quota=e.quota,
                used=e.used,
            )
        finally:
            # Disconnects are background-detach by default.  An explicit cancel
            # request has already cancelled the job and is therefore a no-op.
            immersive_jobs.detach(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=event_stream_headers(),
    )


@router.post(
    "/jobs/detach",
    operation_id="detach_immersive_job",
    response_model=JobControlResponse,
    responses=standard_error_responses(401, 404, 422),
)
async def detach_immersive_job(
    body: JobRequest, user_id: str = Depends(get_current_user)
):
    session_id = sanitize_uuid(body.session_id, field_name="session_id")
    session = SessionRepository().get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(404, "课程不存在")
    detached = immersive_jobs.detach(session_id)
    return {"ok": detached, "session_id": session_id, "mode": "background"}


@router.post(
    "/jobs/cancel",
    operation_id="cancel_immersive_job",
    response_model=JobControlResponse,
    responses=standard_error_responses(401, 404, 409, 422),
)
async def cancel_immersive_job(
    body: JobRequest, user_id: str = Depends(get_current_user)
):
    session_id = sanitize_uuid(body.session_id, field_name="session_id")
    session = SessionRepository().get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(404, "课程不存在")
    cancelled = immersive_jobs.cancel(session_id)
    # Persist immediately as well as from the task's CancelledError handler.
    # This also makes cancellation useful after a process restart, when the
    # in-memory job is no longer present but the session is still resumable.
    current = SessionRepository().read_workspace(session_id)
    if (
        current.get("stage") not in {"ready", "completed"}
        and session.status != "completed"
    ):
        update_workspace(
            session_id,
            stage="cancelled",
            next_actions=[
                {"type": "resume_generation", "label": "继续生成"},
                {"type": "start_learning", "label": "先学习已生成内容"},
            ],
            workspace={"generation_status": "cancelled"},
        )
    return {"ok": cancelled, "session_id": session_id, "mode": "cancelled"}


# ── 断点续传 ───────────────────────────────────────────────────


@router.post(
    "/resume",
    operation_id="resume_immersive_generation",
    responses=standard_error_responses(400, 401, 404, 422, 429, 503),
)
async def resume_immersive(
    req: ResumeRequest, request: Request, user_id: str = Depends(get_current_user)
):
    """SSE 流式恢复生成（断点续传）。

    从中断处继续生成尚未完成的章节，复用已有大纲和 course_dir。
    """
    if not req.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id 不能为空")

    # ── 入口显式净化（SAST sanitizer）──
    session_id = sanitize_uuid(req.session_id.strip(), field_name="session_id")
    session = SessionRepository().get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(404, "课程不存在")

    async def event_stream():
        try:
            update_workspace(session_id, workspace={"generation_status": "running"})
            immersive_jobs.start(
                session_id,
                user_id,
                immersive_resume(session_id=session_id, user_id=user_id),
            )
            async for event in immersive_jobs.subscribe(session_id):
                if await request.is_disconnected():
                    immersive_jobs.detach(session_id)
                    logger.info(
                        "客户端断开，恢复任务转入后台: %s", safe_log(session_id)
                    )
                    break
                yield event
        except CreditsExceeded as e:
            yield encode_sse_event(
                "error",
                message=str(e),
                code="credits_exceeded",
                quota=e.quota,
                used=e.used,
            )
        finally:
            immersive_jobs.detach(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=event_stream_headers(),
    )


# ── 习题 API ──────────────────────────────────────────────────


@router.get(
    "/exercises/{session_id}/{chapter_id}",
    operation_id="get_immersive_chapter_exercises",
    responses=standard_error_responses(401, 404, 422),
)
async def get_exercises(
    session_id: SessionIdPath,
    chapter_id: int,
    limit: int = 0,
    user_id: str = Depends(get_current_user),
):
    """获取指定会话某章节的结构化习题数据。

    返回已解析的 JSON 题目列表，前端无需自行解析 Markdown。
    ?limit=N 可限制返回题目数量（默认 0 = 全部）。
    """
    # ── 入口显式净化（SAST sanitizer）──
    # 通过 uuid.UUID 解析 + str 重格式化，将外部输入替换为可信字符串，
    # 切断污点（taint）传播链，所有下游调用使用净化后的值。
    session_id = sanitize_uuid(session_id, field_name="session_id")

    try:
        result = get_exercises_for_chapter(
            session_id=session_id,
            chapter_id=chapter_id,
            user_id=user_id,
            limit=limit,
        )
        return result
    except ValueError as e:
        # 不向前端暴露异常详情；详细原因仅记到服务端日志
        logger.warning(
            "获取习题失败 user=%s session=%s chapter=%s: %s",
            safe_log(user_id),
            safe_log(session_id),
            safe_log(chapter_id),
            e,
        )
        raise HTTPException(status_code=404, detail="习题不存在或不可访问")


# ── 习题作答结果上报 ──────────────────────────────────────────


@router.post(
    "/quiz-result",
    operation_id="submit_immersive_quiz_result",
    response_model=QuizResultResponse,
    responses=standard_error_responses(401, 404, 422),
)
async def submit_quiz_result(
    req: QuizResultRequest,
    user_id: str = Depends(get_current_user),
):
    """前端习题完成后批量上报答题结果，用于更新用户画像中的知识点掌握度。"""
    from services.immersive.profile_updater import update_profile_from_quiz

    if not req.results:
        return QuizResultResponse(status="ok", message="无答题数据")

    # ── 入口显式净化（SAST sanitizer）──
    session_id = sanitize_uuid(req.session_id, field_name="session_id")

    try:
        result = await update_profile_from_quiz(
            user_id=user_id,
            session_id=session_id,
            chapter_id=req.chapter_id,
            chapter_title=req.chapter_title,
            results=[r.model_dump() for r in req.results],
        )
        return QuizResultResponse(**result)
    except Exception:
        # 不向前端暴露异常详情；详细堆栈仅记到服务端日志
        logger.exception(
            "习题结果上报处理失败 user=%s session=%s chapter=%s",
            safe_log(user_id),
            safe_log(session_id),
            safe_log(req.chapter_id),
        )
        return QuizResultResponse(status="partial", message="处理失败，请稍后重试")


# ── 用户确认完成 ──────────────────────────────────────────────


@router.post(
    "/complete",
    operation_id="complete_immersive_session",
    responses=standard_error_responses(400, 401, 404, 409, 422),
)
async def complete_session(
    req: CompleteRequest,
    user_id: str = Depends(get_current_user),
):
    """用户主动确认完成学习会话。

    生成流程结束后 session 仍为 active，只有用户确认后才标记 completed。
    """
    # ── 入口显式净化（SAST sanitizer）──
    session_id = sanitize_uuid(req.session_id, field_name="session_id")

    try:
        result = complete_immersive_session(
            session_id=session_id,
            user_id=user_id,
            feedback=req.feedback or "",
        )
        return result
    except ValueError as e:
        # 不向前端暴露异常详情；详细原因仅记到服务端日志
        logger.warning(
            "确认完成会话失败 user=%s session=%s: %s",
            safe_log(user_id),
            safe_log(session_id),
            e,
        )
        raise HTTPException(status_code=400, detail="请求参数不合法或会话状态异常")


# ── 课程列表 ─────────────────────────────────────────────────────


@router.get(
    "/courses",
    operation_id="list_immersive_courses",
    response_model=CourseListResponse,
    responses=standard_error_responses(401),
)
async def list_courses(
    user_id: str = Depends(get_current_user),
):
    """列出当前用户已生成的沉浸式课程。

    目录结构：COURSES_DIR/{topic_slug}_{session_id}/...
    过滤策略：从 sessions 表反查该 user 的 session_id 集合，
    匹配 course_slug 末尾的完整 session_id。
    """
    courses_dir = COURSES_DIR
    if not courses_dir.exists():
        return CourseListResponse()

    from database import get_db

    user_sids: set[str] = set()
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM sessions WHERE user_id = ?", (user_id,))
        for row in cur.fetchall():
            sid = row["id"]
            if sid:
                user_sids.add(sid)

    courses = []
    for d in sorted(courses_dir.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        if "_" not in name:
            continue
        sid_suffix = name.rsplit("_", 1)[-1]
        if sid_suffix not in user_sids:
            continue

        outline_file = d / "outline.json"
        outline = None
        if outline_file.exists():
            try:
                outline = json.loads(outline_file.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-except
                pass

        chapter_dirs = sorted(
            [c for c in d.iterdir() if c.is_dir() and c.name.startswith("chapter_")]
        )
        chapters_with_pdf = sum(
            1
            for c in chapter_dirs
            if any(f.suffix == ".pdf" for f in c.iterdir() if f.is_file())
        )

        courses.append(
            CourseSummary(
                slug=d.name,
                topic=outline.get("topic", d.name) if outline else d.name,
                overview=outline.get("overview", "") if outline else "",
                total_chapters=len(outline.get("chapters", []))
                if outline
                else len(chapter_dirs),
                completed_chapters=chapters_with_pdf,
                path=str(d),
            )
        )

    return CourseListResponse(courses=courses)


# ── 个性化推荐云朵 ─────────────────────────────────────────────────


@router.get(
    "/suggestions",
    operation_id="get_immersive_suggestions",
    response_model=SuggestionsResponse,
    responses=standard_error_responses(401, 429, 503),
)
async def get_suggestions(
    user_id: str = Depends(get_current_user),
):
    """根据用户画像和学习历史，调用 LLM 生成个性化推荐主题云朵。"""
    from services.immersive.suggestions import generate_suggestions

    try:
        result = await generate_suggestions(user_id)
        return SuggestionsResponse(**result)
    except Exception as e:
        logger.warning("生成个性化推荐失败: %s", e)
        return SuggestionsResponse()
