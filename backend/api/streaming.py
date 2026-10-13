"""Backwards-compatible SSE envelopes shared by streaming APIs.

Old consumers can keep reading top-level ``type`` and business fields. New
consumers receive ordered/replayable metadata in the same payload and standard
SSE ``id`` / ``event`` lines.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from api.request_context import get_request_id

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_RESERVED_FIELDS = {
    "type",
    "event_id",
    "sequence",
    "job_id",
    "request_id",
    "occurred_at",
    "data",
}


def build_stream_event(
    event_type: str,
    /,
    *,
    event_id: str | None = None,
    sequence: int | None = None,
    job_id: str = "",
    request_id: str | None = None,
    occurred_at: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build a legacy-compatible event payload with modern metadata."""

    _validate_token("event type", event_type)
    event_id = event_id or f"evt_{uuid4().hex}"
    _validate_token("event id", event_id)
    if job_id:
        _validate_token("job id", job_id)
    if sequence is not None and int(sequence) < 0:
        raise ValueError("sequence 不能为负数")

    # ``data`` already has semantic meaning in existing course events (outline
    # content, chapter payloads). Preserve it. New events without data expose
    # their non-reserved fields inside a predictable `data` object as well.
    legacy_fields = {k: v for k, v in fields.items() if k not in _RESERVED_FIELDS}
    payload: dict[str, Any] = {
        "type": event_type,
        "event_id": event_id,
        "request_id": request_id if request_id is not None else get_request_id(),
        "occurred_at": occurred_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **fields,
    }
    if sequence is not None:
        payload["sequence"] = int(sequence)
    if job_id:
        payload["job_id"] = job_id
    if "data" not in payload:
        payload["data"] = legacy_fields
    return payload


def encode_sse_event(event_type: str, /, **fields: Any) -> str:
    """Encode an event as a single RFC-compatible SSE frame.

    ``event_type`` is positional-only so business payloads may carry their own
    ``event_type`` field (e.g. immersive ``agent_event`` = start/think/...)
    without colliding with this parameter.
    """

    payload = build_stream_event(event_type, **fields)
    # Use a neutral wire event name so old parsers that only inspect data lines
    # retain exactly their current dispatch behavior.
    return (
        f"id: {payload['event_id']}\n"
        "event: message\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def extract_sse_payload(frame: str) -> dict[str, Any] | None:
    """Read the JSON payload from either a legacy or modern single SSE frame."""

    for line in str(frame or "").splitlines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    return None


class SSEEventEmitter:
    """Assign monotonic sequence numbers and reject accidental duplicate IDs."""

    def __init__(self, *, job_id: str = "", next_sequence: int = 1) -> None:
        self.job_id = job_id
        self._next_sequence = max(0, next_sequence)
        self._event_ids: set[str] = set()

    def emit(self, event_type: str, /, **fields: Any) -> str:
        event_id = fields.pop("event_id", None) or f"evt_{uuid4().hex}"
        if event_id in self._event_ids:
            raise ValueError("同一 SSE 流不能重复 event_id")
        self._event_ids.add(event_id)
        sequence = fields.pop("sequence", self._next_sequence)
        self._next_sequence = int(sequence) + 1
        return encode_sse_event(
            event_type,
            event_id=event_id,
            sequence=sequence,
            job_id=fields.pop("job_id", self.job_id),
            **fields,
        )


def event_stream_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def _validate_token(label: str, value: str) -> None:
    if not _SAFE_TOKEN.fullmatch(str(value or "")):
        raise ValueError(f"{label} 包含非法 SSE 控制字符")
