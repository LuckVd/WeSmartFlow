"""Versioned generic asynchronous-job API.

The initial public resource exposes read/stream/cancel operations for jobs
created by migrated producers. Creation remains domain-specific, e.g. an
immersive course endpoint can return a ``job_id`` while preserving its legacy
SSE response for older clients.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from api.contracts import ApiResponse, standard_error_responses
from api.streaming import encode_sse_event, event_stream_headers
from dependencies import get_current_user
from services.jobs import AsyncJobManager, JobSnapshot, JobStatus

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs-v1"])
manager = AsyncJobManager()


class JobResponse(ApiResponse):
    id: str
    kind: str
    resource_id: str = ""
    status: JobStatus
    created_at: str
    updated_at: str
    last_sequence: int = Field(ge=0)
    error_code: str = ""


class JobCancelledResponse(ApiResponse):
    id: str
    status: JobStatus
    cancelled: bool


def _as_response(snapshot: JobSnapshot) -> JobResponse:
    return JobResponse(
        id=snapshot.id,
        kind=snapshot.kind,
        resource_id=snapshot.resource_id,
        status=snapshot.status,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        last_sequence=snapshot.last_sequence,
        error_code=snapshot.error_code,
    )


def _owned_job(job_id: str, user_id: str) -> JobSnapshot:
    snapshot = manager.get(job_id)
    if not snapshot or snapshot.owner_id != user_id:
        raise HTTPException(404, "任务不存在")
    return snapshot


@router.get(
    "/{job_id}",
    operation_id="get_job_v1",
    response_model=JobResponse,
    responses=standard_error_responses(401, 404),
)
async def get_job(job_id: str, user_id: str = Depends(get_current_user)):
    return _as_response(_owned_job(job_id, user_id))


@router.post(
    "/{job_id}/cancel",
    operation_id="cancel_job_v1",
    response_model=JobCancelledResponse,
    responses=standard_error_responses(401, 404),
)
async def cancel_job(job_id: str, user_id: str = Depends(get_current_user)):
    snapshot = _owned_job(job_id, user_id)
    cancelled = await manager.cancel(job_id)
    if cancelled:
        # Make the command response deterministic even before the task gets a
        # scheduling slice and observes CancelledError.
        await asyncio.sleep(0)
    latest = manager.get(job_id) or snapshot
    return JobCancelledResponse(id=job_id, status=latest.status, cancelled=cancelled)


@router.get(
    "/{job_id}/events",
    operation_id="stream_job_events_v1",
    responses=standard_error_responses(401, 404, 422),
)
async def stream_job_events(
    job_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
):
    _owned_job(job_id, user_id)

    async def event_stream():
        async for event in manager.subscribe(job_id, after_sequence=after_sequence):
            if await request.is_disconnected():
                break
            legacy_type = str(event.get("type") or "progress")
            data = {
                k: v
                for k, v in event.items()
                if k
                not in {
                    "type",
                    "sequence",
                    "job_id",
                    "event_id",
                    "request_id",
                    "occurred_at",
                }
            }
            yield encode_sse_event(
                legacy_type,
                job_id=job_id,
                sequence=event.get("sequence"),
                event_id=event.get("event_id"),
                request_id=event.get("request_id"),
                occurred_at=event.get("occurred_at"),
                **data,
            )

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=event_stream_headers()
    )


# ── Legacy immersive session adapter ─────────────────────────────────────
# Existing `/api/immersive/*` endpoints keep their session_id-centric API.
# These v1 routes expose the same in-process job through the generic lifecycle
# contract while persistence remains in the immersive workspace/session store.


@router.get(
    "/immersive/{session_id}",
    operation_id="get_immersive_job_v1",
    response_model=JobResponse,
    responses=standard_error_responses(401, 404),
)
async def get_immersive_job(session_id: str, user_id: str = Depends(get_current_user)):
    from repositories import SessionRepository
    from services.immersive.job_manager import manager as immersive_jobs

    session = SessionRepository().get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(404, "课程不存在")
    snapshot = immersive_jobs.snapshot(session_id)
    workspace = SessionRepository().read_workspace(session_id)
    status = (snapshot or {}).get("status") or workspace.get("workspace", {}).get(
        "generation_status", ""
    )
    if not status:
        status = (
            "succeeded"
            if workspace.get("stage") in {"ready", "completed"}
            else "failed"
        )
    # Legacy workspace calls a successful generation "completed", while the
    # generic Job API uses the stable terminal status "succeeded".
    if status == "completed":
        status = "succeeded"
    return JobResponse(
        id=f"immersive:{session_id}",
        kind="immersive-generation",
        resource_id=session_id,
        status=JobStatus(status)
        if status in JobStatus._value2member_map_
        else JobStatus.FAILED,
        created_at=str(session.created_at),
        updated_at=str(session.created_at),
        last_sequence=int((snapshot or {}).get("last_sequence", 0)),
        error_code=str((snapshot or {}).get("error_code", "")),
    )


@router.get(
    "/immersive/{session_id}/events",
    operation_id="stream_immersive_job_events_v1",
    responses=standard_error_responses(401, 404, 422),
)
async def stream_immersive_job_events(
    session_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
):
    from repositories import SessionRepository
    from services.immersive.job_manager import manager as immersive_jobs
    from api.streaming import extract_sse_payload

    session = SessionRepository().get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(404, "课程不存在")

    async def event_stream():
        async for frame in immersive_jobs.subscribe(
            session_id, after_sequence=after_sequence
        ):
            if await request.is_disconnected():
                break
            payload = extract_sse_payload(frame)
            if payload is None:
                continue
            event_type = str(payload.pop("type", "progress"))
            yield encode_sse_event(event_type, **payload)

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=event_stream_headers()
    )


@router.post(
    "/immersive/{session_id}/cancel",
    operation_id="cancel_immersive_job_v1",
    response_model=JobCancelledResponse,
    responses=standard_error_responses(401, 404),
)
async def cancel_immersive_job_v1(
    session_id: str, user_id: str = Depends(get_current_user)
):
    from repositories import SessionRepository
    from services.immersive.job_manager import manager as immersive_jobs

    session = SessionRepository().get_by_id(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(404, "课程不存在")
    cancelled = immersive_jobs.cancel(session_id)
    if not cancelled:
        workspace = SessionRepository().read_workspace(session_id)
        terminal = workspace.get("stage") in {"ready", "completed", "cancelled"}
        return JobCancelledResponse(
            id=f"immersive:{session_id}",
            status=JobStatus.SUCCEEDED if terminal else JobStatus.FAILED,
            cancelled=False,
        )
    if cancelled:
        await asyncio.sleep(0)
    return JobCancelledResponse(
        id=f"immersive:{session_id}",
        status=JobStatus.CANCELLED if cancelled else JobStatus.FAILED,
        cancelled=cancelled,
    )
