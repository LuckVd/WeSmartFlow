"""Reusable in-memory async job manager.

This manager is deliberately transport-agnostic: it owns lifecycle, replay and
cancellation, while HTTP/SSE routers decide how a job is created and exposed.
Persisted business state remains the source of truth after process restart.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable, Optional
from uuid import uuid4

from api.request_context import get_request_id


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    BACKGROUND = "background"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_DONE = object()
JobEvent = dict[str, Any]
JobRunner = AsyncGenerator[JobEvent, None]
OnStateChange = Callable[["JobSnapshot"], Awaitable[None] | None]


@dataclass(frozen=True)
class JobSnapshot:
    id: str
    owner_id: str
    kind: str
    resource_id: str = ""
    status: JobStatus = JobStatus.QUEUED
    created_at: str = ""
    updated_at: str = ""
    last_sequence: int = 0
    error_code: str = ""
    error_message: str = ""


@dataclass
class _Job:
    snapshot: JobSnapshot
    task: Optional[asyncio.Task] = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    replay: deque[JobEvent] = field(default_factory=lambda: deque(maxlen=300))
    on_state_change: OnStateChange | None = None


class AsyncJobManager:
    """Run owned jobs, replay ordered events and support safe cancellation."""

    def __init__(self, *, max_replay: int = 300) -> None:
        self._jobs: dict[str, _Job] = {}
        self._max_replay = max_replay

    def get(self, job_id: str) -> Optional[JobSnapshot]:
        job = self._jobs.get(job_id)
        return job.snapshot if job else None

    def find_active(
        self, *, owner_id: str, kind: str, resource_id: str
    ) -> Optional[JobSnapshot]:
        for job in self._jobs.values():
            state = job.snapshot
            if (
                state.owner_id == owner_id
                and state.kind == kind
                and state.resource_id == resource_id
                and state.status
                in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.BACKGROUND}
            ):
                return state
        return None

    def start(
        self,
        *,
        owner_id: str,
        kind: str,
        runner: JobRunner,
        resource_id: str = "",
        job_id: Optional[str] = None,
        on_state_change: OnStateChange | None = None,
    ) -> JobSnapshot:
        existing = self._jobs.get(job_id or "")
        if existing and existing.task and not existing.task.done():
            return existing.snapshot
        now = _now()
        snapshot = JobSnapshot(
            id=job_id or f"job_{uuid4().hex}",
            owner_id=owner_id,
            kind=kind,
            resource_id=resource_id,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        job = _Job(
            snapshot=snapshot,
            replay=deque(maxlen=self._max_replay),
            on_state_change=on_state_change,
        )
        self._jobs[snapshot.id] = job
        job.task = asyncio.create_task(self._run(job, runner), name=snapshot.id)
        return snapshot

    async def _run(self, job: _Job, runner: JobRunner) -> None:
        await self._set_status(job, JobStatus.RUNNING)
        try:
            async for event in runner:
                await self.publish(job.snapshot.id, event)
            if job.snapshot.status != JobStatus.CANCELLED:
                await self._set_status(job, JobStatus.SUCCEEDED)
        except asyncio.CancelledError:
            await self._set_status(job, JobStatus.CANCELLED)
            raise
        except Exception as exc:  # pylint: disable=broad-except
            await self.publish(
                job.snapshot.id,
                {
                    "type": "error",
                    "code": "job_failed",
                    "message": "任务未能完成，请稍后重试。",
                },
            )
            await self._set_status(
                job,
                JobStatus.FAILED,
                error_code="job_failed",
                error_message=str(exc),
            )
        finally:
            for queue in list(job.subscribers):
                queue.put_nowait(_DONE)
            job.subscribers.clear()

    async def publish(self, job_id: str, event: JobEvent) -> JobEvent:
        job = self._jobs[job_id]
        sequence = job.snapshot.last_sequence + 1
        payload = {
            **event,
            "job_id": job_id,
            "sequence": sequence,
            "event_id": event.get("event_id") or f"evt_{uuid4().hex}",
            "occurred_at": event.get("occurred_at") or _now(),
            "request_id": event.get("request_id") or get_request_id(),
        }
        job.replay.append(payload)
        job.snapshot = _replace(job.snapshot, last_sequence=sequence)
        for queue in list(job.subscribers):
            queue.put_nowait(payload)
        return payload

    async def subscribe(
        self, job_id: str, *, after_sequence: int = 0
    ) -> AsyncGenerator[JobEvent, None]:
        job = self._jobs.get(job_id)
        if not job:
            return
        queue: asyncio.Queue = asyncio.Queue()
        for event in job.replay:
            if int(event.get("sequence", 0)) > after_sequence:
                queue.put_nowait(event)
        if job.snapshot.status in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            queue.put_nowait(_DONE)
        job.subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is _DONE:
                    return
                yield event
        finally:
            job.subscribers.discard(queue)

    async def detach(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or not job.task or job.task.done():
            return False
        await self._set_status(job, JobStatus.BACKGROUND)
        return True

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or not job.task or job.task.done():
            return False
        job.task.cancel()
        return True

    async def _set_status(
        self,
        job: _Job,
        status: JobStatus,
        *,
        error_code: str = "",
        error_message: str = "",
    ) -> None:
        job.snapshot = _replace(
            job.snapshot,
            status=status,
            error_code=error_code or job.snapshot.error_code,
            error_message=error_message or job.snapshot.error_message,
        )
        if job.on_state_change:
            result = job.on_state_change(job.snapshot)
            if result is not None:
                await result


def _replace(snapshot: JobSnapshot, **changes: Any) -> JobSnapshot:
    return JobSnapshot(**{**snapshot.__dict__, **changes, "updated_at": _now()})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
