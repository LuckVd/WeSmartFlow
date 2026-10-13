"""Shared safe HTTP adapter for non-billable third-party integrations.

Provider Gateway owns paid AI providers. This adapter owns OAuth, public data
fetching and similar HTTP APIs: bounded requests, safe retry only for idempotent
operations, redacted diagnostics, and correlation-aware observations.

``IntegrationHttpClient`` is intentionally a small facade rather than another
HTTP framework. It gives source adapters one auditable place for timeout,
concurrency, retry and metrics policy while keeping each integration's request
and response schema close to its own adapter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
import ipaddress
import logging
import random
import socket
import threading
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from api.request_context import get_request_id
from services.provider_gateway import get_provider_gateway

logger = logging.getLogger(__name__)
_RETRYABLE = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class IntegrationPolicy:
    """Operational policy for one non-billable HTTP integration.

    ``retry_safe`` is deliberately insufficient on its own: retries are limited
    to GET, HEAD and OPTIONS. A provider that exposes a search action as POST
    therefore cannot be retried accidentally.
    """

    name: str
    timeout_seconds: float = 15.0
    max_retries: int = 0
    retry_safe: bool = False
    follow_redirects: bool = False
    max_redirects: int = 3
    max_concurrency: int = 8
    trust_env: bool = False

    def __post_init__(self) -> None:
        if not (self.name or "").strip():
            raise ValueError("integration policy requires a name")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least one")


class IntegrationHttpError(RuntimeError):
    """A secret-free, source-safe HTTP integration failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        attempts: int = 1,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.attempts = max(1, int(attempts))


class UnsafeIntegrationUrl(ValueError):
    """A URL is structurally invalid or would target a non-public address."""


async def validate_public_http_url(
    url: str,
    *,
    resolver: Callable[[str, int], Awaitable[Collection[str]]] | None = None,
) -> str:
    """Validate that an HTTP(S) URL resolves only to public addresses.

    The structural checks stop scheme confusion, userinfo tricks and literal
    loopback/private addresses. DNS is then resolved once for every initial URL
    and redirect target; a mixed public/private answer is rejected rather than
    accepting the public answer and leaving an SSRF bypass path. Callers still
    must validate every redirect because a safe initial host can redirect.

    The returned URL preserves the original path and query for the request but
    is never itself logged by this module.
    """

    raw = (url or "").strip()
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise UnsafeIntegrationUrl("only http and https URLs are allowed")
        if not parsed.hostname:
            raise UnsafeIntegrationUrl("URL must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeIntegrationUrl("URL userinfo is not allowed")
        # Accessing port validates numeric syntax and range in urllib.
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except (TypeError, ValueError) as exc:
        raise UnsafeIntegrationUrl("invalid URL") from exc

    host = parsed.hostname.rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise UnsafeIntegrationUrl("non-public URL host is not allowed")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeIntegrationUrl("non-public URL host is not allowed")
        return raw

    addresses = await (resolver or _resolve_addresses)(host, port)
    normalized: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for value in addresses:
        try:
            normalized.add(ipaddress.ip_address(value))
        except ValueError as exc:
            raise UnsafeIntegrationUrl(
                "URL host resolved to an invalid address"
            ) from exc
    if not normalized or any(not address.is_global for address in normalized):
        raise UnsafeIntegrationUrl("URL host resolved to a non-public address")
    return raw


async def _resolve_addresses(host: str, port: int) -> Collection[str]:
    """Resolve all address answers so mixed DNS cannot bypass URL validation."""

    try:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except (OSError, socket.gaierror) as exc:
        raise UnsafeIntegrationUrl("URL host could not be resolved") from exc
    return tuple(record[4][0] for record in records if record[4])


class IntegrationHttpClient:
    """Async HTTP facade with bounded work and redacted observability.

    The optional injected client/transport are testing seams. Production source
    adapters use the default client, which is closed after each logical request;
    this avoids leaking loop-bound resources from short-lived command-line jobs.
    An injected client remains owned by its caller and is never closed here.
    """

    def __init__(
        self,
        policy: IntegrationPolicy,
        client: httpx.AsyncClient | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if client is not None and transport is not None:
            raise ValueError("provide either client or transport, not both")
        if client is not None:
            # An injected shared client may carry its own transport/proxy policy.
            # Adapters that use it must have reviewed it at construction time.
            logger.debug(
                "integration_http uses caller-owned client name=%s", policy.name
            )
        self.policy = policy
        self._client = client
        self._transport = transport
        self._sleep = sleep
        # The client object is shared by one source instance, so this protects a
        # provider from fan-out across concurrent searches without globally
        # coupling unrelated integrations.
        self._semaphore = asyncio.Semaphore(policy.max_concurrency)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        content: bytes | str | None = None,
        accepted_statuses: Collection[int] | None = None,
    ) -> httpx.Response:
        """Execute one bounded request and return an already-buffered response.

        URLs, headers and bodies are intentionally never included in error text
        or metrics: they can contain user queries, access tokens, or signed URLs.
        """

        method = method.upper()
        accepted = frozenset(accepted_statuses or ())
        if any(status < 100 or status > 599 for status in accepted):
            raise ValueError("accepted_statuses must contain HTTP status codes")
        safe_retry = self.policy.retry_safe and method in _IDEMPOTENT_METHODS
        attempts = 0
        started = time.monotonic()

        async with self._semaphore:
            owns_client = self._client is None
            client = self._client or httpx.AsyncClient(
                timeout=httpx.Timeout(self.policy.timeout_seconds),
                follow_redirects=self.policy.follow_redirects,
                max_redirects=self.policy.max_redirects,
                transport=self._transport,
                # External integration traffic must not silently inherit proxy
                # variables. A reviewed proxy can be supplied as an injected
                # client by its owning integration.
                trust_env=self.policy.trust_env,
            )
            try:
                while True:
                    attempts += 1
                    try:
                        response = await client.request(
                            method,
                            url,
                            headers=headers,
                            params=params,
                            json=json,
                            content=content,
                            # A caller-supplied client must not weaken the
                            # integration policy's deadline.
                            timeout=self.policy.timeout_seconds,
                        )
                        if (
                            response.status_code in _RETRYABLE
                            and safe_retry
                            and attempts <= self.policy.max_retries
                        ):
                            await response.aclose()
                            await self._sleep(self._delay(attempts))
                            continue
                        if (
                            response.status_code >= 400
                            and response.status_code not in accepted
                        ):
                            await response.aclose()
                            error = IntegrationHttpError(
                                f"{self.policy.name} returned HTTP {response.status_code}",
                                status_code=response.status_code,
                                retryable=response.status_code in _RETRYABLE,
                                attempts=attempts,
                            )
                            self._observe(
                                "error",
                                started,
                                attempts,
                                f"HTTP{response.status_code}",
                                retryable=error.retryable,
                            )
                            raise error
                        self._observe("success", started, attempts)
                        return response
                    except IntegrationHttpError:
                        raise
                    except httpx.RequestError as exc:
                        retryable = isinstance(
                            exc, (httpx.TimeoutException, httpx.NetworkError)
                        )
                        if (
                            safe_retry
                            and retryable
                            and attempts <= self.policy.max_retries
                        ):
                            await self._sleep(self._delay(attempts))
                            continue
                        self._observe(
                            "error",
                            started,
                            attempts,
                            type(exc).__name__,
                            retryable=retryable,
                        )
                        raise IntegrationHttpError(
                            f"{self.policy.name} request failed",
                            retryable=retryable,
                            attempts=attempts,
                        ) from exc
            finally:
                if owns_client:
                    await client.aclose()

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET a JSON document through the shared policy boundary."""

        response = await self.request("GET", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationHttpError(
                f"{self.policy.name} returned invalid JSON"
            ) from exc
        finally:
            await response.aclose()

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        """POST once and parse JSON; POST is never automatically retried."""

        response = await self.request("POST", url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationHttpError(
                f"{self.policy.name} returned invalid JSON"
            ) from exc
        finally:
            await response.aclose()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        """GET a text document through the shared policy boundary."""

        response = await self.request("GET", url, **kwargs)
        try:
            return response.text
        finally:
            await response.aclose()

    def _delay(self, attempt: int) -> float:
        return min(4.0, 0.4 * (2 ** (attempt - 1))) * random.uniform(0.8, 1.2)

    def _observe(
        self,
        outcome: str,
        started: float,
        attempts: int,
        error_type: str = "",
        *,
        retryable: bool = False,
    ) -> None:
        # Reuse the ProviderGateway event shape without treating public content
        # or OAuth traffic as a billable model/provider call.
        gateway = get_provider_gateway()
        profile = gateway.resolve(
            category="integration", backend=self.policy.name, endpoint=""
        )
        gateway.record_observation(
            profile,
            "http.request",
            scene="integration",
            outcome=outcome,
            started=started,
            attempts=attempts,
            retryable=retryable,
            error_type=error_type,
        )
        logger.info(
            "integration_http name=%s outcome=%s attempts=%s retryable=%s request_id=%s",
            self.policy.name,
            outcome,
            attempts,
            retryable,
            get_request_id() or "-",
        )


class SyncIntegrationHttpClient:
    """Synchronous counterpart for existing synchronous application routes.

    It deliberately does not bridge into the async adapter with ``asyncio.run``:
    FastAPI dispatches normal functions in a worker thread, and this small
    companion avoids loop ownership and shutdown problems while enforcing the
    same policy.  It owns a client only for the duration of one logical request;
    injected clients are caller-owned test seams.
    """

    _shared_limit_lock = threading.Lock()
    _shared_limits: dict[tuple[str, int], threading.BoundedSemaphore] = {}

    def __init__(
        self,
        policy: IntegrationPolicy,
        client: httpx.Client | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if client is not None and transport is not None:
            raise ValueError("provide either client or transport, not both")
        self.policy = policy
        self._client = client
        self._transport = transport
        self._sleep = sleep

    @classmethod
    def _shared_semaphore(cls, policy: IntegrationPolicy) -> threading.BoundedSemaphore:
        """Return a process-wide limiter for short-lived synchronous adapters.

        OAuth routes build an adapter per request, so a per-instance semaphore
        would not constrain concurrent FastAPI worker threads.  The key includes
        the declared limit so a deliberate policy change cannot silently reuse a
        stale capacity.  This holds only during I/O, never during response parsing.
        """

        key = (policy.name.strip().lower(), policy.max_concurrency)
        with cls._shared_limit_lock:
            limiter = cls._shared_limits.get(key)
            if limiter is None:
                limiter = threading.BoundedSemaphore(policy.max_concurrency)
                cls._shared_limits[key] = limiter
            return limiter

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        content: bytes | str | None = None,
        accepted_statuses: Collection[int] | None = None,
    ) -> httpx.Response:
        """Execute a bounded synchronous integration request.

        Just like the async adapter, no token, authorization header, body,
        query string or remote response body reaches an exception or metric.
        """

        method = method.upper()
        accepted = frozenset(accepted_statuses or ())
        if any(status < 100 or status > 599 for status in accepted):
            raise ValueError("accepted_statuses must contain HTTP status codes")
        safe_retry = self.policy.retry_safe and method in _IDEMPOTENT_METHODS
        attempts = 0
        started = time.monotonic()
        owns_client = self._client is None
        try:
            with self._shared_semaphore(self.policy):
                # Build short-lived clients *after* entering the process-wide
                # limiter. Otherwise a request burst can open arbitrarily many
                # sockets while waiting for its allowed upstream slot.
                client = self._client or httpx.Client(
                    timeout=httpx.Timeout(self.policy.timeout_seconds),
                    follow_redirects=self.policy.follow_redirects,
                    max_redirects=self.policy.max_redirects,
                    transport=self._transport,
                    # Do not inherit an unreviewed proxy configuration for
                    # credentials exchanged by OAuth and mini-program login.
                    trust_env=self.policy.trust_env,
                )
                while True:
                    attempts += 1
                    try:
                        response = client.request(
                            method,
                            url,
                            headers=headers,
                            params=params,
                            json=json,
                            content=content,
                            timeout=self.policy.timeout_seconds,
                        )
                        if (
                            response.status_code in _RETRYABLE
                            and safe_retry
                            and attempts <= self.policy.max_retries
                        ):
                            response.close()
                            self._sleep(self._delay(attempts))
                            continue
                        if (
                            response.status_code >= 400
                            and response.status_code not in accepted
                        ):
                            response.close()
                            error = IntegrationHttpError(
                                f"{self.policy.name} returned HTTP {response.status_code}",
                                status_code=response.status_code,
                                retryable=response.status_code in _RETRYABLE,
                                attempts=attempts,
                            )
                            self._observe(
                                "error",
                                started,
                                attempts,
                                f"HTTP{response.status_code}",
                                retryable=error.retryable,
                            )
                            raise error
                        self._observe("success", started, attempts)
                        return response
                    except IntegrationHttpError:
                        raise
                    except httpx.RequestError as exc:
                        retryable = isinstance(
                            exc, (httpx.TimeoutException, httpx.NetworkError)
                        )
                        if (
                            safe_retry
                            and retryable
                            and attempts <= self.policy.max_retries
                        ):
                            self._sleep(self._delay(attempts))
                            continue
                        self._observe(
                            "error",
                            started,
                            attempts,
                            type(exc).__name__,
                            retryable=retryable,
                        )
                        raise IntegrationHttpError(
                            f"{self.policy.name} request failed",
                            retryable=retryable,
                            attempts=attempts,
                        ) from exc
        finally:
            if owns_client and "client" in locals():
                client.close()

    def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET a JSON document through the integration boundary."""

        response = self.request("GET", url, **kwargs)
        try:
            return self._decode_json(response)
        finally:
            response.close()

    def post_json(self, url: str, **kwargs: Any) -> Any:
        """POST once and parse JSON; POST never retries implicitly."""

        response = self.request("POST", url, **kwargs)
        try:
            return self._decode_json(response)
        finally:
            response.close()

    def _decode_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise IntegrationHttpError(
                f"{self.policy.name} returned invalid JSON"
            ) from exc

    def _delay(self, attempt: int) -> float:
        return min(4.0, 0.4 * (2 ** (attempt - 1))) * random.uniform(0.8, 1.2)

    def _observe(
        self,
        outcome: str,
        started: float,
        attempts: int,
        error_type: str = "",
        *,
        retryable: bool = False,
    ) -> None:
        gateway = get_provider_gateway()
        profile = gateway.resolve(
            category="integration", backend=self.policy.name, endpoint=""
        )
        gateway.record_observation(
            profile,
            "http.request",
            scene="integration",
            outcome=outcome,
            started=started,
            attempts=attempts,
            retryable=retryable,
            error_type=error_type,
        )
        logger.info(
            "integration_http name=%s outcome=%s attempts=%s retryable=%s request_id=%s",
            self.policy.name,
            outcome,
            attempts,
            retryable,
            get_request_id() or "-",
        )


def redact_url(value: str) -> str:
    """Remove query, fragment and userinfo before diagnostics or logs."""

    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        # Defensive fallback: diagnostics must never throw while trying to strip
        # a malformed URL, and must never retain query/fragment/userinfo data.
        return str(value or "").split("?", 1)[0].split("#", 1)[0].rsplit("@", 1)[-1]
