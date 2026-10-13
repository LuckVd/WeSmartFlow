"""Provider gateway for configuration, capability discovery and call observability.

The gateway deliberately sits *above* provider SDKs and the existing factories:
provider implementations keep their protocol-specific code, while factories resolve a
stable provider profile and instrument their public call boundary.  This gives new
providers one place to declare their capabilities and operational policy without
mixing keys, retries or metrics into business services.

It is intentionally conservative about retries.  A failed image or speech generation
may already have been accepted and billed by the upstream provider, so the gateway
never blindly repeats those calls.  Retrieval calls may retry transient transport
failures, and the OpenAI-compatible LLM client retains its existing, provider-aware
retry implementation.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
import functools
import logging
import os
import random
import re
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from typing import Any, AsyncGenerator, Callable, Deque, Mapping, Optional

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_PROVIDER_NAME = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider implementation can do.

    Capabilities describe an adapter, not a particular user configuration.  They can
    be used later by a provider selection UI or by routing policy without probing an
    upstream API during a user request.
    """

    streaming: bool = False
    tool_calls: bool = False
    user_managed_credentials: bool = True
    supports_cancellation: bool = False
    idempotent_requests: bool = False


@dataclass(frozen=True)
class RetryPolicy:
    """Timeout and retry policy attached to one provider profile."""

    timeout_seconds: float
    max_retries: int = 0
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    retry_safe: bool = False

    def delay_for(self, retry_number: int) -> float:
        """Return an exponential-backoff delay with bounded jitter."""

        raw = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(0, retry_number - 1)),
        )
        return raw * random.uniform(0.8, 1.2)


@dataclass(frozen=True)
class ProviderDefinition:
    """Static registration data for a concrete provider adapter."""

    id: str
    category: str
    capabilities: ProviderCapabilities
    default_timeout_seconds: float
    default_max_retries: int = 0
    default_base_delay_seconds: float = 0.5
    default_max_delay_seconds: float = 4.0
    retry_safe: bool = False
    # Existing implementation already owns retries.  The gateway observes it but
    # must not wrap it in a second generic retry loop.
    native_retry: bool = False


@dataclass(frozen=True)
class ProviderProfile:
    """Resolved, secret-free configuration for one external provider call path."""

    id: str
    category: str
    model: str
    endpoint: str
    capabilities: ProviderCapabilities
    retry: RetryPolicy
    native_retry: bool = False

    def public_dict(self) -> dict[str, Any]:
        """Return safe diagnostic data; credentials are never part of a profile."""

        return {
            "id": self.id,
            "category": self.category,
            "model": self.model,
            "endpoint": self.endpoint,
            "capabilities": asdict(self.capabilities),
            "retry": asdict(self.retry),
            "native_retry": self.native_retry,
        }


@dataclass(frozen=True)
class ProviderCallEvent:
    """A bounded, safe observation record for one logical provider call."""

    provider: str
    category: str
    operation: str
    scene: str
    request_id: str
    model: str
    outcome: str
    duration_ms: int
    attempts: int
    retryable: bool = False
    error_type: str = ""

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderMetrics:
    """In-process operational counters with a bounded recent-call buffer.

    It is an intentionally small first implementation.  Metrics do not become a
    dependency of the generation path: logging is always attempted, and failures in
    a metrics consumer cannot affect a provider call.  A future OpenTelemetry or
    Prometheus exporter can consume ``snapshot`` without changing factory APIs.
    """

    def __init__(self, recent_limit: int = 500):
        self._lock = threading.Lock()
        self._counts: Counter[tuple[str, str, str, str]] = Counter()
        self._attempts: Counter[tuple[str, str, str]] = Counter()
        self._recent: Deque[ProviderCallEvent] = deque(maxlen=recent_limit)

    def record(self, event: ProviderCallEvent) -> None:
        key = (event.category, event.provider, event.operation, event.outcome)
        compact = (event.category, event.provider, event.operation)
        with self._lock:
            self._counts[key] += 1
            self._attempts[compact] += max(1, event.attempts)
            self._recent.append(event)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = [
                {
                    "category": category,
                    "provider": provider,
                    "operation": operation,
                    "outcome": outcome,
                    "calls": calls,
                    "attempts": self._attempts[(category, provider, operation)],
                }
                for (category, provider, operation, outcome), calls in sorted(
                    self._counts.items()
                )
            ]
            recent = [event.public_dict() for event in self._recent]
        return {"counters": counters, "recent": recent}

    def snapshot_for(self, *, category: str | None = None) -> dict[str, Any]:
        """Return a filtered, secret-free diagnostic snapshot."""

        snapshot = self.snapshot()
        if not category:
            return snapshot
        normalized = (category or "").strip().lower()
        return {
            "counters": [
                item for item in snapshot["counters"] if item["category"] == normalized
            ],
            "recent": [
                item for item in snapshot["recent"] if item["category"] == normalized
            ],
        }

    def reset(self) -> None:
        """Clear in-memory observations. Intended for isolated tests only."""

        with self._lock:
            self._counts.clear()
            self._attempts.clear()
            self._recent.clear()


# Keys use the existing factory-facing backend names.  A category is included so
# ``openai`` image and the OpenAI-compatible LLM adapter can evolve independently.
_REGISTRY: dict[tuple[str, str], ProviderDefinition] = {
    (
        "llm",
        "openai-compatible",
    ): ProviderDefinition(
        id="openai-compatible",
        category="llm",
        capabilities=ProviderCapabilities(streaming=True, tool_calls=True),
        default_timeout_seconds=300,
        default_max_retries=3,
        default_base_delay_seconds=1.0,
        default_max_delay_seconds=8.0,
        retry_safe=True,
        native_retry=True,
    ),
    (
        "embedding",
        "openai-compatible",
    ): ProviderDefinition(
        # Embedding is semantically read-only, but an ambiguous timeout may still
        # have been accepted and billed upstream.  Do not repeat it generically
        # unless a future adapter provides a provider-specific idempotency key.
        id="openai-compatible-embedding",
        category="embedding",
        capabilities=ProviderCapabilities(
            # KG vectors are shared platform assets.  The current adapter only
            # reads KG_EMBEDDING_* deployment config; it must not be presented as
            # a per-user credential capability by a future provider settings UI.
            user_managed_credentials=False,
            idempotent_requests=True,
        ),
        default_timeout_seconds=30,
    ),
    (
        "image",
        "qwen",
    ): ProviderDefinition(
        id="qwen-image",
        category="image",
        capabilities=ProviderCapabilities(),
        default_timeout_seconds=300,
    ),
    (
        "image",
        "openai",
    ): ProviderDefinition(
        id="openai-image",
        category="image",
        capabilities=ProviderCapabilities(),
        # Relay endpoints may wrap async upstream tasks (submit + poll) inside a
        # single request; measured generations take 25-51s, so 60s was too tight.
        default_timeout_seconds=300,
    ),
    (
        "search",
        "tavily",
    ): ProviderDefinition(
        id="tavily",
        category="search",
        capabilities=ProviderCapabilities(idempotent_requests=True),
        default_timeout_seconds=15,
        default_max_retries=1,
        default_base_delay_seconds=0.5,
        default_max_delay_seconds=2.0,
        retry_safe=True,
    ),
    (
        "audio",
        "qwen3-tts",
    ): ProviderDefinition(
        id="qwen3-tts",
        category="audio",
        capabilities=ProviderCapabilities(),
        default_timeout_seconds=90,
    ),
    (
        "audio",
        "openai-compatible",
    ): ProviderDefinition(
        # Long text may be synthesized asynchronously behind the endpoint, so the
        # default timeout is generous.  No generic retries: a lost response may
        # already have been billed upstream.
        id="openai-compatible-tts",
        category="audio",
        capabilities=ProviderCapabilities(),
        default_timeout_seconds=300,
    ),
    (
        "audio",
        "cosyvoice",
    ): ProviderDefinition(
        id="cosyvoice",
        category="audio",
        capabilities=ProviderCapabilities(),
        default_timeout_seconds=90,
    ),
    (
        "audio",
        "macos-say",
    ): ProviderDefinition(
        id="macos-say",
        category="audio",
        capabilities=ProviderCapabilities(
            user_managed_credentials=False,
            idempotent_requests=True,
            supports_cancellation=True,
        ),
        default_timeout_seconds=60,
    ),
}


def _clean_name(value: str) -> str:
    return _PROVIDER_NAME.sub("_", (value or "").lower()).strip("_")


def _provider_env(definition: ProviderDefinition, suffix: str, default: str) -> str:
    """Read a provider-specific policy setting with a global fallback.

    Example for qwen image: ``PROVIDER_QWEN_IMAGE_TIMEOUT_SECONDS``;
    global fallback: ``PROVIDER_DEFAULT_TIMEOUT_SECONDS``.  Legacy LLM settings
    remain honored so deployment configuration does not need a flag day migration.
    """

    prefix = f"PROVIDER_{_clean_name(definition.id).upper()}_{suffix}"
    global_name = f"PROVIDER_DEFAULT_{suffix}"
    if prefix in os.environ:
        return os.environ[prefix]
    if definition.id == "openai-compatible":
        legacy = {
            "TIMEOUT_SECONDS": "LLM_TIMEOUT",
            "MAX_RETRIES": "LLM_MAX_RETRIES",
            "RETRY_BASE_DELAY_SECONDS": "LLM_RETRY_BASE_DELAY",
            "RETRY_MAX_DELAY_SECONDS": "LLM_RETRY_MAX_DELAY",
        }.get(suffix)
        if legacy and legacy in os.environ:
            return os.environ[legacy]
    return os.getenv(global_name, default)


class ProviderGateway:
    """Registry, policy resolver and instrumenter for external provider calls."""

    def __init__(
        self,
        registry: Optional[Mapping[tuple[str, str], ProviderDefinition]] = None,
        metrics: Optional[ProviderMetrics] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._registry = dict(registry or _REGISTRY)
        self.metrics = metrics or ProviderMetrics()
        self._sleep = sleep

    def available(self, category: str | None = None) -> list[ProviderDefinition]:
        """List registered adapters, optionally limited to one billable category."""

        values = self._registry.values()
        if category:
            values = (item for item in values if item.category == category)
        return sorted(values, key=lambda item: item.id)

    def resolve(
        self,
        *,
        category: str,
        backend: str,
        model: str = "",
        endpoint: str = "",
    ) -> ProviderProfile:
        """Resolve a safe profile from registry defaults and environment overrides."""

        key = ((category or "").strip().lower(), (backend or "").strip().lower())
        definition = self._registry.get(key)
        if definition is None:
            # Unknown adapters remain observable while opt-in configuration is added.
            # They get no automatic retry because their idempotency is unknown.
            definition = ProviderDefinition(
                id=_clean_name(backend) or "unknown-provider",
                category=key[0] or "unknown",
                capabilities=ProviderCapabilities(),
                default_timeout_seconds=30,
            )

        timeout = _float_from_raw(
            _provider_env(
                definition,
                "TIMEOUT_SECONDS",
                str(definition.default_timeout_seconds),
            ),
            definition.default_timeout_seconds,
        )
        max_retries = _int_from_raw(
            _provider_env(
                definition, "MAX_RETRIES", str(definition.default_max_retries)
            ),
            definition.default_max_retries,
        )
        base_delay = _float_from_raw(
            _provider_env(
                definition,
                "RETRY_BASE_DELAY_SECONDS",
                str(definition.default_base_delay_seconds),
            ),
            definition.default_base_delay_seconds,
        )
        max_delay = _float_from_raw(
            _provider_env(
                definition,
                "RETRY_MAX_DELAY_SECONDS",
                str(definition.default_max_delay_seconds),
            ),
            definition.default_max_delay_seconds,
        )
        retry = RetryPolicy(
            timeout_seconds=timeout,
            max_retries=max_retries,
            base_delay_seconds=base_delay,
            max_delay_seconds=max(base_delay, max_delay),
            retry_safe=definition.retry_safe,
        )
        return ProviderProfile(
            id=definition.id,
            category=definition.category,
            model=(model or "")[:120],
            endpoint=_safe_endpoint(endpoint),
            capabilities=definition.capabilities,
            retry=retry,
            native_retry=definition.native_retry,
        )

    def instrument_sync(
        self,
        profile: ProviderProfile,
        operation: str,
        fn: Callable[..., Any],
        *,
        scene: str = "unknown",
        success: Callable[[Any], bool] | None = None,
        attempts: Callable[[Any], int] | None = None,
        retry: bool | None = None,
    ) -> Callable[..., Any]:
        """Wrap a synchronous client call with safe metrics and retry policy."""

        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return self.call_sync(
                profile,
                operation,
                lambda: fn(*args, **kwargs),
                scene=scene,
                success=success,
                attempts=attempts,
                retry=retry,
            )

        return wrapped

    def call_sync(
        self,
        profile: ProviderProfile,
        operation: str,
        invoke: Callable[[], Any],
        *,
        scene: str = "unknown",
        success: Callable[[Any], bool] | None = None,
        attempts: Callable[[Any], int] | None = None,
        retry: bool | None = None,
    ) -> Any:
        """Invoke a synchronous provider operation and record one logical event."""

        started = time.monotonic()
        attempts_made = 0
        # A caller may opt out of a safe retry, but cannot opt into a retry for
        # a non-idempotent provider.  Image/TTS calls can have been accepted
        # and charged even when their response times out.
        allow_retry = (
            profile.retry.retry_safe and not profile.native_retry and retry is not False
        )
        while True:
            attempts_made += 1
            try:
                result = invoke()
                ok = success(result) if success else True
                final_attempts = _result_attempts(result, attempts, attempts_made)
                self._record(
                    profile,
                    operation,
                    scene,
                    "success" if ok else "error",
                    started,
                    final_attempts,
                    error_type="provider_response_error" if not ok else "",
                )
                return result
            except Exception as exc:  # pylint: disable=broad-except
                retryable = self.is_retryable_exception(exc)
                if (
                    allow_retry
                    and retryable
                    and attempts_made <= profile.retry.max_retries
                ):
                    delay = profile.retry.delay_for(attempts_made)
                    logger.info(
                        "provider_call_retry provider=%s category=%s operation=%s "
                        "attempt=%d delay_ms=%d error_type=%s",
                        profile.id,
                        profile.category,
                        operation,
                        attempts_made,
                        round(delay * 1000),
                        type(exc).__name__,
                    )
                    self._sleep(delay)
                    continue
                self._record(
                    profile,
                    operation,
                    scene,
                    "error",
                    started,
                    attempts_made,
                    retryable=retryable,
                    error_type=type(exc).__name__,
                )
                raise

    def instrument_async(
        self,
        profile: ProviderProfile,
        operation: str,
        fn: Callable[..., Any],
        *,
        scene: str = "unknown",
        success: Callable[[Any], bool] | None = None,
        attempts: Callable[[Any], int] | None = None,
    ) -> Callable[..., Any]:
        """Instrument an async provider call. Native provider retry remains native."""

        @functools.wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                ok = success(result) if success else True
                self._record(
                    profile,
                    operation,
                    scene,
                    "success" if ok else "error",
                    started,
                    _result_attempts(result, attempts, 1),
                    error_type="provider_response_error" if not ok else "",
                )
                return result
            except Exception as exc:  # pylint: disable=broad-except
                self._record(
                    profile,
                    operation,
                    scene,
                    "error",
                    started,
                    1,
                    retryable=self.is_retryable_exception(exc),
                    error_type=type(exc).__name__,
                )
                raise

        return wrapped

    def instrument_async_stream(
        self,
        profile: ProviderProfile,
        operation: str,
        fn: Callable[..., AsyncGenerator[Any, None]],
        *,
        scene: str = "unknown",
        success: Callable[[Any], bool] | None = None,
        attempts: Callable[[Any], int] | None = None,
    ) -> Callable[..., AsyncGenerator[Any, None]]:
        """Instrument a streaming call without buffering or changing its events."""

        @functools.wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
            started = time.monotonic()
            last: Any = _MISSING
            completed = False
            try:
                async for event in fn(*args, **kwargs):
                    last = event
                    yield event
                completed = True
            except Exception as exc:  # pylint: disable=broad-except
                self._record(
                    profile,
                    operation,
                    scene,
                    "error",
                    started,
                    1,
                    retryable=self.is_retryable_exception(exc),
                    error_type=type(exc).__name__,
                )
                raise
            finally:
                if completed:
                    ok = last is not _MISSING and (success(last) if success else True)
                    self._record(
                        profile,
                        operation,
                        scene,
                        "success" if ok else "error",
                        started,
                        _result_attempts(last, attempts, 1),
                        error_type="provider_response_error" if not ok else "",
                    )
                elif last is not _MISSING:
                    # A client disconnect is meaningful but not a provider failure.
                    self._record(
                        profile,
                        operation,
                        scene,
                        "cancelled",
                        started,
                        1,
                    )

        return wrapped

    @staticmethod
    def is_retryable_exception(exc: Exception) -> bool:
        """Classify transport and transient upstream failures without SDK coupling."""

        status = getattr(exc, "status_code", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status in _RETRYABLE_HTTP_STATUSES
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        return any(
            marker in name or marker in message
            for marker in (
                "timeout",
                "connection",
                "temporarily unavailable",
                "rate limit",
                "too many requests",
            )
        )

    def _record(
        self,
        profile: ProviderProfile,
        operation: str,
        scene: str,
        outcome: str,
        started: float,
        attempts: int,
        *,
        retryable: bool = False,
        error_type: str = "",
    ) -> None:
        try:
            # Import lazily: provider calls are also valid from command-line jobs
            # which do not import FastAPI's request-context machinery.
            try:
                from api.request_context import get_request_id

                request_id = get_request_id() or "-"
            except Exception:  # pragma: no cover - defensive import boundary
                request_id = "-"
            event = ProviderCallEvent(
                provider=profile.id,
                category=profile.category,
                operation=operation,
                scene=(scene or "unknown")[:80],
                request_id=request_id,
                model=profile.model,
                outcome=outcome,
                duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                attempts=max(1, int(attempts)),
                retryable=retryable,
                error_type=error_type[:80],
            )
            self.metrics.record(event)
            logger.info(
                "provider_call provider=%s category=%s operation=%s scene=%s "
                "outcome=%s duration_ms=%d attempts=%d retryable=%s "
                "error_type=%s request_id=%s",
                event.provider,
                event.category,
                event.operation,
                event.scene,
                event.outcome,
                event.duration_ms,
                event.attempts,
                event.retryable,
                event.error_type or "-",
                event.request_id,
            )
        except Exception:  # pylint: disable=broad-except
            # Observability must remain an isolated side effect.
            logger.warning("Provider 调用观测写入失败", exc_info=True)

    def record_observation(
        self,
        profile: ProviderProfile,
        operation: str,
        *,
        scene: str = "unknown",
        outcome: str = "success",
        started: float | None = None,
        attempts: int = 1,
        retryable: bool = False,
        error_type: str = "",
    ) -> None:
        """Record an adapter-owned external call without exposing metric internals.

        Most callers should use :meth:`call_sync` or one of the instrumentation
        wrappers.  HTTP integration adapters own their own request/retry loop, so
        they use this narrow public seam to report the final logical call.  The
        method intentionally accepts a resolved, secret-free profile only.
        """

        self._record(
            profile,
            operation,
            scene,
            outcome,
            started if started is not None else time.monotonic(),
            attempts,
            retryable=retryable,
            error_type=error_type,
        )


def _float_from_raw(value: str, default: float) -> float:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _int_from_raw(value: str, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _safe_endpoint(value: str) -> str:
    """Keep endpoint diagnostics useful while ensuring no credentials leak to logs."""

    raw = (value or "").strip()
    if not raw:
        return ""
    # Query strings commonly contain signed URLs / tokens, so never expose them.
    # Userinfo can carry basic-auth credentials and must be stripped as well.
    try:
        parsed = urlsplit(raw)
        if parsed.scheme and parsed.hostname:
            host = parsed.hostname
            try:
                port = parsed.port
            except ValueError:
                port = None
            if port:
                host = f"{host}:{port}"
            return urlunsplit((parsed.scheme, host, parsed.path, "", ""))[:300]
    except ValueError:
        pass
    return raw.split("?", 1)[0].rsplit("@", 1)[-1][:300]


def _result_attempts(
    result: Any,
    extractor: Callable[[Any], int] | None,
    fallback: int,
) -> int:
    try:
        value = extractor(result) if extractor else fallback
        return max(1, int(value))
    except Exception:  # pylint: disable=broad-except
        return max(1, fallback)


_MISSING = object()

# Shared application gateway.  It contains no user state or provider secrets.
provider_gateway = ProviderGateway()


def get_provider_gateway() -> ProviderGateway:
    """Return the process-wide provider gateway used by the compatibility factories."""

    return provider_gateway


__all__ = [
    "ProviderCapabilities",
    "ProviderCallEvent",
    "ProviderDefinition",
    "ProviderGateway",
    "ProviderMetrics",
    "ProviderProfile",
    "RetryPolicy",
    "get_provider_gateway",
    "provider_gateway",
]
