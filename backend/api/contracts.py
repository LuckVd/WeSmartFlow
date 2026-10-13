"""Stable HTTP API contracts shared by routers.

New endpoints should use these models instead of defining permissive Pydantic
models in individual routers.  Existing endpoints can migrate incrementally so
that public ``/api`` behavior remains backwards compatible.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base contract with strict input parsing and predictable JSON output."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class ApiRequest(ApiModel):
    """Base class for request bodies exposed by the HTTP API."""


class ApiResponse(ApiModel):
    """Base class for explicit successful API responses."""


class SuccessResponse(ApiResponse):
    """Minimal acknowledgement response for commands without a resource body."""

    ok: Literal[True] = True


class ProviderMetricsResponse(ApiResponse):
    """Secret-free, process-local external-provider health counters."""

    counters: list[dict[str, Any]] = Field(default_factory=list)
    recent: list[dict[str, Any]] = Field(default_factory=list)


class ProblemDetails(ApiResponse):
    """Stable, machine-readable error envelope.

    ``detail`` is safe to show to users.  Provider stack traces and secrets must
    stay in server logs; clients can use ``request_id`` when reporting an issue.
    """

    type: str = "about:blank"
    code: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    request_id: str
    retryable: bool = False
    extensions: dict[str, Any] = Field(default_factory=dict)


ERROR_RESPONSE_DESCRIPTIONS = {
    400: "请求不符合业务规则",
    401: "认证失败或登录已过期",
    403: "没有执行该操作的权限",
    404: "请求的资源不存在",
    409: "资源状态冲突",
    422: "请求参数校验失败",
    429: "请求频率或额度超限",
    500: "服务内部错误",
    502: "上游服务响应无效",
    503: "服务或上游供应商暂不可用",
}


def standard_error_responses(*status_codes: int) -> dict[int, dict[str, Any]]:
    """Return FastAPI OpenAPI response declarations for standard errors."""

    return {
        code: {
            "model": ProblemDetails,
            "description": ERROR_RESPONSE_DESCRIPTIONS.get(code, "请求失败"),
        }
        for code in status_codes
    }
