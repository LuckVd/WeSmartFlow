"""Global HTTP error normalization for the public API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .contracts import ProblemDetails
from .request_context import RequestContextMiddleware, get_request_id

logger = logging.getLogger(__name__)

_STATUS_DEFAULTS: dict[int, tuple[str, str, bool]] = {
    400: ("invalid_request", "请求无效", False),
    401: ("authentication_required", "需要登录", False),
    403: ("permission_denied", "没有权限", False),
    404: ("resource_not_found", "资源不存在", False),
    409: ("resource_conflict", "资源状态冲突", False),
    413: ("payload_too_large", "请求内容过大", False),
    422: ("validation_error", "请求参数不合法", False),
    429: ("rate_limited", "请求过于频繁或额度不足", True),
    500: ("internal_error", "服务暂时不可用", True),
    502: ("upstream_invalid_response", "上游服务响应异常", True),
    503: ("upstream_unavailable", "上游服务暂时不可用", True),
    504: ("upstream_timeout", "上游服务响应超时", True),
}


@dataclass
class DomainError(Exception):
    """Expected business failure that should cross the HTTP boundary safely."""

    status_code: int
    code: str
    detail: str
    title: str = "请求未完成"
    retryable: bool = False
    extensions: dict[str, Any] = field(default_factory=dict)


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    retryable: bool = False,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = get_request_id() or "unknown"
    payload = ProblemDetails(
        type=f"https://api.wesmartflow.local/problems/{code}",
        code=code,
        title=title,
        status=status,
        detail=detail,
        request_id=request_id,
        retryable=retryable,
        extensions=extensions or {},
    )
    return JSONResponse(
        status_code=status,
        content=payload.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def _safe_http_detail(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def install_api_foundation(app: FastAPI) -> None:
    """Install request correlation and normalized errors exactly once per app."""

    if getattr(app.state, "api_foundation_installed", False):
        return
    app.state.api_foundation_installed = True
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError):
        return problem_response(
            status=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            retryable=exc.retryable,
            extensions=exc.extensions,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        safe_errors = [
            {
                "location": [str(part) for part in error.get("loc", [])],
                "code": str(error.get("type", "invalid")),
                "message": str(error.get("msg", "参数不合法")),
            }
            for error in exc.errors()
        ]
        return problem_response(
            status=422,
            code="validation_error",
            title="请求参数不合法",
            detail="请检查请求字段后重试。",
            extensions={"errors": safe_errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException):
        code, title, retryable = _STATUS_DEFAULTS.get(
            exc.status_code,
            ("http_error", "请求失败", False),
        )
        return problem_response(
            status=exc.status_code,
            code=code,
            title=title,
            detail=_safe_http_detail(exc.detail, title),
            retryable=retryable,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception(
            "未处理 API 异常 method=%s path=%s request=%s",
            request.method,
            request.url.path,
            get_request_id() or "-",
        )
        return problem_response(
            status=500,
            code="internal_error",
            title="服务暂时不可用",
            detail="服务处理请求时出现问题，请稍后重试。",
            retryable=True,
        )
