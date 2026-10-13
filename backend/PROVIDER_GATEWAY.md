# Provider Gateway

`services.provider_gateway` is the operational boundary for third-party AI calls.
It deliberately complements rather than replaces the existing LLM, image, search and
TTS factories.

## Boundary and responsibilities

| Layer | Owns |
| --- | --- |
| Business service | User intent and domain workflow |
| Factory | User-vs-platform credentials, quota precheck, usage ledger |
| Provider Gateway | Provider identity, declared capabilities, timeout/retry policy and safe call observations |
| Provider client | SDK/protocol request and response conversion |

A resolved `ProviderProfile` is safe to expose to internal diagnostics: it has a
provider ID, model, endpoint without query/userinfo, capabilities and retry policy.
It never contains an API key.

## Registry conventions

Provider definitions are keyed by `(category, backend)` and currently cover:

- `llm/openai-compatible`
- `embedding/openai-compatible`
- `image/qwen`, `image/openai`
- `search/tavily`
- `audio/qwen3-tts`, `audio/cosyvoice`, `audio/macos-say`

A new adapter is added by registering a `ProviderDefinition`, then having its factory
resolve and instrument the public client method. Unknown providers stay observable but
have no automatic retry until their idempotency is explicitly declared.

## Policy configuration

The supported deployment settings are scoped per provider and fall back to a global
default:

```dotenv
PROVIDER_QWEN_IMAGE_TIMEOUT_SECONDS=300
PROVIDER_TAVILY_MAX_RETRIES=1
PROVIDER_OPENAI_COMPATIBLE_EMBEDDING_TIMEOUT_SECONDS=30
PROVIDER_DEFAULT_TIMEOUT_SECONDS=30
```

The OpenAI-compatible LLM profile also honours the existing `LLM_TIMEOUT`,
`LLM_MAX_RETRIES`, `LLM_RETRY_BASE_DELAY` and `LLM_RETRY_MAX_DELAY` values, so existing
deployments do not require an immediate environment migration.

Only idempotent, read-only calls are retried by the generic gateway. Tavily search is
currently in that class. Image and speech generation intentionally have no generic
retry because a timeout can occur after upstream acceptance and charging. The LLM
client continues to own its existing provider-aware retry loop; the gateway reports
its attempt count instead of adding a second retry loop.

Embedding uses the same OpenAI-compatible SDK boundary, but is tracked as an
independent `embedding` category. Its platform credential and ledger entries belong to
the system KG workflow (`scene=kg`), never to the active request user. Although the
operation has no mutation semantics, an ambiguous timeout can follow upstream billing;
it therefore has no generic automatic retry. A scheduled reindex can make a deliberate
retry after diagnosis.

## Observability

Every instrumented logical call produces a safe in-memory event with `provider`,
`category`, `operation`, `scene`, `request_id`, `model`, outcome, duration, attempts,
and a failure class. Events use a bounded buffer and counters so instrumentation cannot
grow memory unboundedly. Existing application logs include the same `request_id`.

Administrators can inspect the current-process snapshot via:

```text
GET /api/usage/providers/metrics?category=llm
```

This endpoint requires an admin token. It is intended for incident diagnosis; process
restarts clear it. A Prometheus/OpenTelemetry exporter can consume
`ProviderMetrics.snapshot()` later without changing factory or client APIs.

The same endpoint accepts `category=integration` for OAuth and other non-billable
external HTTP calls. Integration observations have the same request ID, provider name,
outcome, duration, attempt count and safe error type as AI provider observations. They
never include request URLs, query strings, credentials, headers, request bodies, or
upstream response bodies.

## Integration HTTP adapter

`integrations.http` is the boundary for third-party HTTP APIs that are not AI provider
SDKs. It has both async and synchronous clients, so existing synchronous FastAPI routes
do not need unsafe nested event-loop execution. Each adapter declares an
`IntegrationPolicy` with a timeout, concurrency cap, redirect policy, environment-proxy
policy, and retry safety.

- The generic adapter retries only `GET`, `HEAD`, and `OPTIONS`, and only when the
  adapter explicitly declares `retry_safe=True`.
- OAuth token exchange and temporary login-code exchange use `max_retries=0` even when
  a remote API happens to expose them through a GET URL. This prevents reuse of a code
  after a timeout where the provider may have already accepted it.
- GitHub Star verification is a read-only check and may retry one transient failure.
  A GitHub 404 remains a normal “not starred” product result, not an infrastructure
  failure.
- The GitHub and WeChat adapters keep their fixed HTTPS endpoints, bearer headers,
  secrets, temporary codes and provider payloads inside the adapter. Router errors use
  only stable, user-safe messages. Redirects and proxy environment inheritance are
  disabled by default.

## Remaining direct HTTP clients

The factory-backed paid paths now enter the gateway: LLM, image generation, Tavily,
TTS, and KG embedding. Smart Search, GitHub OAuth/rewards, and WeChat Mini Program
login now enter the Integration HTTP Adapter.

Only these specialized paths remain:

1. `court/forge.py` and `court/service.py`: one-time image creation and signed-media
   download need a court media adapter with observability and URL allowlists. Image
   creation must remain non-retrying to avoid duplicate charges.
2. `channels/protocol.py`: it already has a shared async client for authenticated long
   polling. Add only observability after a cancellation/reconnect audit; retries could
   duplicate outbound bot messages.
3. `agent_core/tool/web.py`: validate public targets before its generic fetch path is
   enabled for new product workflows. Its proxy compatibility needs a separate audit.

The image/TTS provider clients still contain protocol HTTP internally, but their public
calls already pass through their factories and Provider Gateway. They are not ungoverned
application-level integrations.

No business code should instantiate a new paid-provider SDK or read a provider secret.
It should request the relevant factory client instead.
