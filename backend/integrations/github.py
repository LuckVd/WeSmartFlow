"""GitHub OAuth and Star-verification adapter.

The routes deliberately know nothing about GitHub URLs, bearer headers or HTTP
status variants.  This adapter keeps those details at a single, non-billable
integration boundary and ensures an OAuth code or token is never retried or
included in a diagnostic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from .http import (
    IntegrationHttpError,
    IntegrationPolicy,
    SyncIntegrationHttpClient,
)

_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_API = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_USER_AGENT = "WeSmartFlow/1.0"


class GitHubAuthorizationRejected(IntegrationHttpError):
    """GitHub rejected a user authorization code without exposing its payload."""


class GitHubProtocolError(IntegrationHttpError):
    """GitHub returned a syntactically valid but unusable response."""


class GitHubClient:
    """Synchronous GitHub OAuth client with operation-specific retry policy."""

    def __init__(
        self,
        *,
        oauth_http: SyncIntegrationHttpClient | None = None,
        api_http: SyncIntegrationHttpClient | None = None,
        star_http: SyncIntegrationHttpClient | None = None,
    ) -> None:
        # An OAuth authorization code is single-use.  Retrying after a timeout
        # can turn a successful exchange into a confusing "used code" failure.
        self._oauth_http = oauth_http or SyncIntegrationHttpClient(
            IntegrationPolicy(
                name="github-oauth",
                timeout_seconds=15,
                max_retries=0,
                retry_safe=False,
                follow_redirects=False,
                max_concurrency=4,
            )
        )
        # Profile/email requests carry a bearer token.  They are read-only but
        # deliberately not retried automatically until GitHub token semantics
        # and rate-limit behaviour are explicitly configured for this path.
        self._api_http = api_http or SyncIntegrationHttpClient(
            IntegrationPolicy(
                name="github-api",
                timeout_seconds=10,
                max_retries=0,
                retry_safe=False,
                follow_redirects=False,
                max_concurrency=8,
            )
        )
        # The Star endpoint is a pure read used only to decide whether a credit
        # grant may proceed.  A one-time transient retry is safe here.
        self._star_http = star_http or SyncIntegrationHttpClient(
            IntegrationPolicy(
                name="github-star-verification",
                timeout_seconds=10,
                max_retries=1,
                retry_safe=True,
                follow_redirects=False,
                max_concurrency=8,
            )
        )

    def exchange_code(self, *, client_id: str, client_secret: str, code: str) -> str:
        """Exchange a single-use authorization code exactly once."""

        payload = self._oauth_http.post_json(
            _OAUTH_TOKEN_URL,
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            },
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        )
        data = _mapping(payload, "github-oauth")
        token = data.get("access_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        # GitHub's `error_description` can contain provider-specific detail.
        # Keep it on neither API nor application logs.
        if data.get("error"):
            raise GitHubAuthorizationRejected(
                "GitHub authorization was rejected", retryable=False
            )
        raise GitHubProtocolError("github-oauth returned no access token")

    def current_user(self, access_token: str) -> dict[str, Any]:
        """Return the minimal profile fields needed by account binding."""

        data = _mapping(
            self._api_http.get_json(
                f"{_GITHUB_API}/user", headers=self._headers(access_token)
            ),
            "github-api",
        )
        github_id = data.get("id")
        login = data.get("login")
        if github_id in (None, "") or not isinstance(login, str) or not login.strip():
            raise GitHubProtocolError("github-api returned an incomplete user")
        return {
            "id": str(github_id),
            "login": login.strip()[:256],
            "name": _optional_text(data.get("name"), limit=256),
            "email": _optional_text(data.get("email"), limit=320),
            "avatar_url": _optional_text(data.get("avatar_url"), limit=2048),
        }

    def verified_email(self, access_token: str) -> str | None:
        """Choose the primary verified email, then another verified address."""

        payload = self._api_http.get_json(
            f"{_GITHUB_API}/user/emails", headers=self._headers(access_token)
        )
        if not isinstance(payload, list):
            raise GitHubProtocolError("github-api returned invalid email data")
        verified: list[str] = []
        for item in payload:
            if not isinstance(item, Mapping) or not item.get("verified"):
                continue
            email = _optional_text(item.get("email"), limit=320)
            if not email:
                continue
            if item.get("primary"):
                return email
            verified.append(email)
        return verified[0] if verified else None

    def has_starred(self, access_token: str, repository: str) -> bool:
        """Check Star state; 404 is an expected false result, never an error."""

        owner, name = _repository_parts(repository)
        response = self._star_http.request(
            "GET",
            f"{_GITHUB_API}/user/starred/{quote(owner, safe='')}/{quote(name, safe='')}",
            headers=self._headers(access_token),
            accepted_statuses={404},
        )
        try:
            if response.status_code == 404:
                return False
            if response.status_code == 204:
                return True
            raise GitHubProtocolError(
                "github-star-verification returned an unexpected response",
                status_code=response.status_code,
            )
        finally:
            response.close()

    @staticmethod
    def _headers(access_token: str) -> dict[str, str]:
        if not isinstance(access_token, str) or not access_token.strip():
            raise GitHubProtocolError("missing GitHub access token")
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": _ACCEPT,
            "User-Agent": _USER_AGENT,
        }


def get_github_client() -> GitHubClient:
    """Build a stateless GitHub adapter for the current synchronous request."""

    return GitHubClient()


def _mapping(value: Any, source: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GitHubProtocolError(f"{source} returned invalid JSON data")
    return value


def _optional_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped[:limit] if stripped else None


def _repository_parts(repository: str) -> tuple[str, str]:
    parts = (repository or "").strip().split("/")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise GitHubProtocolError("invalid GitHub repository configuration")
    return parts[0].strip(), parts[1].strip()


__all__ = [
    "GitHubAuthorizationRejected",
    "GitHubClient",
    "GitHubProtocolError",
    "get_github_client",
]
