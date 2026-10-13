"""Detached immersive generation jobs.

The HTTP connection is only a progress subscription.  A job keeps consuming
the existing immersive generator after the browser leaves, while subscribers
can disconnect and later rely on the persisted workspace/resume audit.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncGenerator

from services.immersive.persistence import update_workspace
from services.immersive.sse import sse_event
from api.streaming import encode_sse_event, extract_sse_payload


_DONE = object()
_MAX_REPLAY = 300


@dataclass
class _Job:
    session_id: str
    user_id: str
    task: asyncio.Task | None = None
    detached: bool = False
    done: bool = False
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    replay: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_REPLAY))
    next_sequence: int = 1
    status: str = "queued"
    error_code: str = ""


class ImmersiveJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}

    def start(self, session_id: str, user_id: str, generator) -> None:
        old = self._jobs.get(session_id)
        if old and old.task and not old.task.done():
            return
        job = _Job(session_id=session_id, user_id=user_id)
        self._jobs[session_id] = job
        job.task = asyncio.create_task(
            self._run(job, generator), name=f"immersive-{session_id}"
        )

    async def _run(self, job: _Job, generator) -> None:
        job.status = "running"
        try:
            async for event in generator:
                event = self._enrich_event(job, event)
                job.replay.append(event)
                for queue in list(job.subscribers):
                    queue.put_nowait(event)
            # A detached job can finish after the browser has gone away. Keep
            # the persisted status in sync so the history page does not keep
            # showing a stale "后台处理中" badge.
            current = update_workspace(job.session_id)
            if current.get("stage") not in {"failed", "cancelled"}:
                update_workspace(
                    job.session_id,
                    workspace={"generation_status": "completed"},
                )
            if job.status != "cancelled":
                job.status = "succeeded"
        except asyncio.CancelledError:
            job.status = "cancelled"
            update_workspace(
                job.session_id,
                stage="cancelled",
                next_actions=[
                    {"type": "resume_generation", "label": "继续生成"},
                    {"type": "start_learning", "label": "先学习已生成内容"},
                ],
                workspace={"generation_status": "cancelled"},
            )
            raise
        except Exception as exc:  # pylint: disable=broad-except
            job.status = "failed"
            job.error_code = "job_failed"
            update_workspace(
                job.session_id,
                stage="failed",
                next_actions=[
                    {"type": "resume_generation", "label": "继续生成"},
                    {"type": "start_learning", "label": "先学习已生成内容"},
                ],
                workspace={"generation_status": "failed", "last_error": str(exc)},
            )
            error_event = sse_event(
                "error", session_id=job.session_id, message=str(exc)
            )
            error_event = self._enrich_event(job, error_event)
            job.replay.append(error_event)
            for queue in list(job.subscribers):
                queue.put_nowait(error_event)
        finally:
            job.done = True
            for queue in list(job.subscribers):
                queue.put_nowait(_DONE)
            job.subscribers.clear()

    @staticmethod
    def _enrich_event(job: _Job, event: str) -> str:
        """Add replay metadata to producer SSE without breaking old payloads."""

        payload = extract_sse_payload(event)
        if payload is None:
            # Preserve arbitrary strings for the existing manager abstraction
            # and callers that use it without SSE transport.
            return event
        event_type = str(payload.pop("type", "progress"))
        payload.pop("sequence", None)
        payload["job_id"] = payload.get("job_id") or job.session_id
        payload["sequence"] = job.next_sequence
        job.next_sequence += 1
        return encode_sse_event(event_type, **payload)

    async def subscribe(
        self, session_id: str, *, after_sequence: int = 0
    ) -> AsyncGenerator[str, None]:
        job = self._jobs.get(session_id)
        if not job:
            return
        queue: asyncio.Queue = asyncio.Queue()
        for event in job.replay:
            payload = extract_sse_payload(event) or {}
            # Keep supporting the manager's original arbitrary-string tests and
            # callers. SSE frames use sequence filtering; non-SSE payloads have
            # no replay cursor and are therefore replayed in full.
            if not payload or int(payload.get("sequence", 0)) > after_sequence:
                queue.put_nowait(event)
        if job.done:
            queue.put_nowait(_DONE)
        job.subscribers.add(queue)
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    return
                yield item
        finally:
            job.subscribers.discard(queue)

    def detach(self, session_id: str) -> bool:
        job = self._jobs.get(session_id)
        if not job or not job.task or job.task.done():
            return False
        job.detached = True
        job.status = "background"
        update_workspace(
            session_id,
            workspace={"generation_status": "background"},
        )
        return True

    def cancel(self, session_id: str) -> bool:
        job = self._jobs.get(session_id)
        if not job or not job.task or job.task.done():
            return False
        job.task.cancel()
        return True

    def is_running(self, session_id: str) -> bool:
        job = self._jobs.get(session_id)
        return bool(job and job.task and not job.task.done())

    def is_detached(self, session_id: str) -> bool:
        job = self._jobs.get(session_id)
        return bool(job and job.detached)

    def snapshot(self, session_id: str) -> dict | None:
        """Return the safe in-memory lifecycle state for a session job."""

        job = self._jobs.get(session_id)
        if not job:
            return None
        return {
            "session_id": job.session_id,
            "user_id": job.user_id,
            "status": job.status,
            "detached": job.detached,
            "done": job.done,
            "last_sequence": max(0, job.next_sequence - 1),
            "error_code": job.error_code,
        }


manager = ImmersiveJobManager()

__all__ = ["ImmersiveJobManager", "manager"]
