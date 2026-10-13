"""Offline safety tests for OAuth, GitHub rewards and Mini Program HTTP adapters."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.request_context import _REQUEST_ID  # noqa: E402
from integrations.github import (  # noqa: E402
    GitHubAuthorizationRejected,
    GitHubClient,
    GitHubProtocolError,
)
from integrations.http import (  # noqa: E402
    IntegrationHttpError,
    IntegrationPolicy,
    SyncIntegrationHttpClient,
    redact_url,
)
from integrations.wechat import (  # noqa: E402
    WeChatAuthorizationRejected,
    WeChatMiniProgramClient,
    WeChatProtocolError,
)
from services.provider_gateway import ProviderGateway, ProviderMetrics  # noqa: E402


class RecordingSyncTransport(httpx.BaseTransport):
    """A deterministic in-memory transport that captures no real network data."""

    def __init__(self, statuses: list[int], body: object | None = None):
        self.statuses = list(statuses)
        self.body = body if body is not None else {}
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self.statuses.pop(0)
        return httpx.Response(status, json=self.body, request=request)


class AuthIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.token = _REQUEST_ID.set("req_auth_integration_20260923")
        self.metrics = ProviderMetrics()
        self.gateway = ProviderGateway(metrics=self.metrics, sleep=lambda _delay: None)
        self.gateway_patch = patch(
            "integrations.http.get_provider_gateway", return_value=self.gateway
        )
        self.gateway_patch.start()

    def tearDown(self):
        self.gateway_patch.stop()
        _REQUEST_ID.reset(self.token)

    def sync_client(
        self, policy: IntegrationPolicy, transport: httpx.BaseTransport
    ) -> SyncIntegrationHttpClient:
        return SyncIntegrationHttpClient(
            policy, transport=transport, sleep=lambda _delay: None
        )

    def test_post_and_single_use_get_never_retry_even_with_retry_enabled(self):
        policy = IntegrationPolicy(
            name="oauth-code", timeout_seconds=1, max_retries=3, retry_safe=True
        )
        post_transport = RecordingSyncTransport([503, 204])
        client = self.sync_client(policy, post_transport)
        with self.assertRaises(IntegrationHttpError) as post_error:
            client.post_json("https://example.test/token", json={"code": "private"})
        self.assertEqual(post_error.exception.attempts, 1)
        self.assertEqual(len(post_transport.requests), 1)

        # A temporary code exchanged with GET must choose a no-retry policy.
        one_time = self.sync_client(
            IntegrationPolicy(
                name="wechat-mini-program",
                timeout_seconds=1,
                max_retries=0,
                retry_safe=False,
            ),
            RecordingSyncTransport([503, 200]),
        )
        with self.assertRaises(IntegrationHttpError) as get_error:
            one_time.get_json(
                "https://example.test/jscode2session", params={"js_code": "private"}
            )
        self.assertEqual(get_error.exception.attempts, 1)

    def test_safe_read_retries_once_and_metrics_are_request_correlated(self):
        transport = RecordingSyncTransport([503, 204])
        client = self.sync_client(
            IntegrationPolicy(
                name="github-star-verification",
                timeout_seconds=1,
                max_retries=1,
                retry_safe=True,
            ),
            transport,
        )
        response = client.request(
            "GET", "https://api.github.com/user/starred/acme/repo"
        )
        self.assertEqual(response.status_code, 204)
        response.close()
        self.assertEqual(len(transport.requests), 2)
        event = self.metrics.snapshot()["recent"][-1]
        self.assertEqual(event["category"], "integration")
        self.assertEqual(event["provider"], "github_star_verification")
        self.assertEqual(event["request_id"], "req_auth_integration_20260923")
        self.assertEqual(event["attempts"], 2)

    def test_adapter_diagnostics_do_not_leak_query_credentials_or_payloads(self):
        transport = RecordingSyncTransport([500])
        client = self.sync_client(
            IntegrationPolicy(name="github-oauth", timeout_seconds=1), transport
        )
        secret = "super-secret-token"
        with self.assertRaises(IntegrationHttpError) as error:
            client.post_json(
                f"https://user:{secret}@example.test/token?code={secret}",
                json={"client_secret": secret, "code": secret},
            )
        self.assertNotIn(secret, str(error.exception))
        event = self.metrics.snapshot()["recent"][-1]
        self.assertNotIn(secret, json.dumps(event))
        self.assertEqual(
            redact_url(f"https://u:{secret}@example.test/p?q={secret}"),
            "https://example.test/p",
        )

    def test_github_oauth_adapter_validates_payloads_and_never_exposes_provider_error(
        self,
    ):
        token_transport = RecordingSyncTransport(
            [200],
            {"error": "bad_verification_code", "error_description": "secret detail"},
        )
        github = GitHubClient(
            oauth_http=self.sync_client(
                IntegrationPolicy(name="github-oauth", timeout_seconds=1),
                token_transport,
            )
        )
        with self.assertRaises(GitHubAuthorizationRejected) as error:
            github.exchange_code(
                client_id="client", client_secret="secret", code="code"
            )
        self.assertNotIn("secret detail", str(error.exception))
        self.assertEqual(len(token_transport.requests), 1)

        profile_transport = RecordingSyncTransport([200], {"id": 1, "login": ""})
        github = GitHubClient(
            api_http=self.sync_client(
                IntegrationPolicy(name="github-api", timeout_seconds=1),
                profile_transport,
            )
        )
        with self.assertRaises(GitHubProtocolError):
            github.current_user("private-token")

    def test_github_profile_get_remains_single_attempt_while_star_check_can_retry(self):
        profile_transport = RecordingSyncTransport(
            [503, 200], {"id": 1, "login": "alice"}
        )
        github = GitHubClient(
            api_http=self.sync_client(
                IntegrationPolicy(
                    name="github-api",
                    timeout_seconds=1,
                    max_retries=3,
                    retry_safe=False,
                ),
                profile_transport,
            )
        )
        with self.assertRaises(IntegrationHttpError) as error:
            github.current_user("private-token")
        self.assertEqual(error.exception.attempts, 1)
        self.assertEqual(len(profile_transport.requests), 1)

    def test_github_star_404_is_a_normal_false_result(self):
        star_transport = RecordingSyncTransport([404])
        github = GitHubClient(
            star_http=self.sync_client(
                IntegrationPolicy(
                    name="github-star-verification",
                    timeout_seconds=1,
                    max_retries=1,
                    retry_safe=True,
                ),
                star_transport,
            )
        )
        self.assertFalse(github.has_starred("private-token", "Tencent/WeSmartFlow"))
        self.assertEqual(len(star_transport.requests), 1)

    def test_wechat_adapter_accepts_only_clean_openid_and_safe_errors(self):
        success = RecordingSyncTransport([200], {"openid": "openid-123"})
        client = WeChatMiniProgramClient(
            self.sync_client(
                IntegrationPolicy(name="wechat-mini-program", timeout_seconds=1),
                success,
            )
        )
        self.assertEqual(
            client.exchange_code(app_id="app", app_secret="secret", code="one-time"),
            "openid-123",
        )

        rejected = RecordingSyncTransport(
            [200], {"errcode": 40029, "errmsg": "secret detail"}
        )
        client = WeChatMiniProgramClient(
            self.sync_client(
                IntegrationPolicy(name="wechat-mini-program", timeout_seconds=1),
                rejected,
            )
        )
        with self.assertRaises(WeChatAuthorizationRejected) as error:
            client.exchange_code(app_id="app", app_secret="secret", code="one-time")
        self.assertNotIn("secret detail", str(error.exception))

        malformed = RecordingSyncTransport([200], {"openid": ""})
        client = WeChatMiniProgramClient(
            self.sync_client(
                IntegrationPolicy(name="wechat-mini-program", timeout_seconds=1),
                malformed,
            )
        )
        with self.assertRaises(WeChatProtocolError):
            client.exchange_code(app_id="app", app_secret="secret", code="one-time")

    def test_async_adapter_uses_public_observation_seam(self):
        # The async adapter shares the metric contract and must not depend on the
        # ProviderGateway private `_record` implementation.
        self.assertNotIn("._record(", Path("backend/integrations/http.py").read_text())
        self.assertIn(
            "record_observation(", Path("backend/integrations/http.py").read_text()
        )

    def test_sync_adapter_limits_concurrent_short_lived_instances(self):
        active = 0
        peak = 0
        guard = threading.Lock()

        class SlowTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                nonlocal active, peak
                with guard:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.02)
                with guard:
                    active -= 1
                return httpx.Response(204, request=request)

        policy = IntegrationPolicy(
            name="sync-concurrency-test", timeout_seconds=1, max_concurrency=2
        )

        def invoke() -> None:
            response = self.sync_client(policy, SlowTransport()).request(
                "GET", "https://example.test/read"
            )
            response.close()

        threads = [threading.Thread(target=invoke) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(peak, 2)

    def test_auth_callback_contract_rejects_oversized_or_unsafe_one_time_credentials(
        self,
    ):
        from api.errors import install_api_foundation
        from routers.auth import router

        app = FastAPI()
        install_api_foundation(app)
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        invalid = client.post(
            "/api/auth/github/callback",
            json={"state": "not valid", "code": "x" * 513},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertEqual(invalid.json()["code"], "validation_error")
        self.assertEqual(invalid.json()["request_id"], invalid.headers["x-request-id"])
        self.assertEqual(
            client.get("/openapi.json").json()["paths"]["/api/auth/github/callback"][
                "post"
            ]["operationId"],
            "complete_github_oauth_callback",
        )


if __name__ == "__main__":
    unittest.main()
