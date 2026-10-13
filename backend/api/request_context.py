"""Per-request correlation context shared by HTTP handlers and logs."""

from __future__ import annotations

import contextvars
import logging
import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID = contextvars.ContextVar("wesmartflow_request_id", default="")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


def get_request_id() -> str:
    """Return the request ID for the current async context, if available."""

    return _REQUEST_ID.get()


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def normalize_request_id(value: str | None) -> str:
    """Accept a bounded caller-supplied ID or create a safe server ID."""

    candidate = (value or "").strip()
    return candidate if _REQUEST_ID_PATTERN.fullmatch(candidate) else _new_request_id()


class RequestContextMiddleware:
    """Attach and expose a request ID without buffering streams or uploads."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        request_id = normalize_request_id(
            headers.get(b"x-request-id", b"").decode("latin-1")
        )
        token = _REQUEST_ID.set(request_id)
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                response_headers = list(message.get("headers") or [])
                if not any(
                    key.lower() == b"x-request-id" for key, _ in response_headers
                ):
                    response_headers.append(
                        (b"x-request-id", request_id.encode("ascii"))
                    )
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # FastAPI's outer ServerErrorMiddleware emits an unhandled 500
            # after this middleware has unwound.  Add the correlation header
            # here so that even that last-resort response remains traceable.
            if not response_started:
                logging.getLogger(__name__).exception(
                    "未处理 API 异常 request_id=%s", request_id
                )
                # Import lazily to avoid the contracts -> errors -> context
                # import cycle during application start-up.
                from .errors import problem_response

                response = problem_response(
                    status=500,
                    code="internal_error",
                    title="服务暂时不可用",
                    detail="服务处理请求时出现问题，请稍后重试。",
                    retryable=True,
                )
                await response(scope, receive, send_with_request_id)
                return
            raise
        finally:
            _REQUEST_ID.reset(token)


class RequestContextLogFilter(logging.Filter):
    """Make ``request_id`` available to every standard logging formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True
