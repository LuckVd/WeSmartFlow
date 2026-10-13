"""API contract and transport foundations for WeSmartFlow."""

from .contracts import ApiRequest, ApiResponse, ProblemDetails
from .errors import DomainError, install_api_foundation, problem_response
from .request_context import get_request_id

__all__ = [
    "ApiRequest",
    "ApiResponse",
    "ProblemDetails",
    "DomainError",
    "get_request_id",
    "install_api_foundation",
    "problem_response",
]
