"""Unit tests for the phase-three provider gateway.

The tests contain no real network calls.  They protect two operational guarantees:
read-only providers may retry a transient failure, while potentially billable media
creation is never repeated implicitly.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.provider_gateway import (  # noqa: E402
    ProviderCapabilities,
    ProviderDefinition,
    ProviderGateway,
    ProviderMetrics,
)


class ProviderGatewayTests(unittest.TestCase):
    def setUp(self):
        self.metrics = ProviderMetrics()
        self.gateway = ProviderGateway(metrics=self.metrics, sleep=lambda _delay: None)

    def test_registry_resolves_capabilities_and_never_exposes_query_credentials(self):
        with patch.dict(
            os.environ,
            {
                "PROVIDER_QWEN_IMAGE_TIMEOUT_SECONDS": "123",
                "PROVIDER_QWEN_IMAGE_MAX_RETRIES": "4",
            },
            clear=False,
        ):
            profile = self.gateway.resolve(
                category="image",
                backend="qwen",
                model="qwen-image-2.0-pro",
                endpoint="https://user:secret@example.test/v1?api_key=top-secret",
            )
        self.assertEqual(profile.id, "qwen-image")
        self.assertEqual(profile.retry.timeout_seconds, 123)
        # Image generation is deliberately non-idempotent even if somebody set a
        # retry count in deployment configuration.
        self.assertFalse(profile.retry.retry_safe)
        public = profile.public_dict()
        self.assertNotIn("top-secret", str(public))
        self.assertNotIn("secret@", public["endpoint"])
        self.assertFalse(public["capabilities"]["streaming"])

    def test_metrics_can_be_filtered_for_an_admin_diagnostic_endpoint(self):
        image = self.gateway.resolve(category="image", backend="qwen")
        search = self.gateway.resolve(category="search", backend="tavily")
        self.gateway.call_sync(image, "images.generate", lambda: "/tmp/a.png")
        self.gateway.call_sync(search, "search.query", lambda: {"ok": True})
        filtered = self.metrics.snapshot_for(category="image")
        self.assertEqual(len(filtered["recent"]), 1)
        self.assertEqual(filtered["recent"][0]["provider"], "qwen-image")

    def test_factory_instrumentation_keeps_quota_rejection_out_of_provider_metrics(
        self,
    ):
        """The factory order must never mistake a local pre-hook for outage."""

        from agent_core.llm import LLMResponse
        from services import llm_factory

        class FakeLLM:
            model_name = "qwen-plus"

            def think(self, _messages):
                return LLMResponse("ok")

            async def async_think(self, _messages):
                return LLMResponse("ok")

            async def stream_think(self, _messages):
                if False:
                    yield None

        profile = self.gateway.resolve(
            category="llm", backend="openai-compatible", model="qwen-plus"
        )
        original = llm_factory.get_provider_gateway
        try:
            llm_factory.get_provider_gateway = lambda: self.gateway
            llm = llm_factory._attach_provider_gateway(
                FakeLLM(), profile=profile, scene="chat"
            )
            # Simulate the existing factory order: gateway wraps raw provider,
            # then quota is the outer hook and rejects before raw invocation.
            from agent_core.hooks import hookwrapper, observe

            def reject(*_args, **_kwargs):
                raise RuntimeError("quota rejected locally")

            llm.think = hookwrapper(llm.think, pre=observe(reject))
            with self.assertRaisesRegex(RuntimeError, "quota rejected"):
                llm.think([])
        finally:
            llm_factory.get_provider_gateway = original
        self.assertEqual(self.metrics.snapshot()["recent"], [])

    def test_read_only_search_retries_one_transient_transport_failure(self):
        profile = self.gateway.resolve(category="search", backend="tavily")
        attempts = 0

        def invoke():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("temporary connection failure")
            return {"ok": True}

        result = self.gateway.call_sync(
            profile,
            "search.query",
            invoke,
            scene="search",
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(attempts, 2)
        counter = self.metrics.snapshot()["counters"]
        self.assertEqual(counter[0]["outcome"], "success")
        self.assertEqual(counter[0]["attempts"], 2)

    def test_media_generation_is_never_retried_without_explicit_provider_guarantee(
        self,
    ):
        profile = self.gateway.resolve(category="image", backend="qwen")
        attempts = 0

        def invoke():
            nonlocal attempts
            attempts += 1
            raise ConnectionError("timeout while waiting for image")

        with self.assertRaises(ConnectionError):
            self.gateway.call_sync(profile, "images.generate", invoke, scene="media")
        self.assertEqual(attempts, 1)
        event = self.metrics.snapshot()["recent"][-1]
        self.assertEqual(event["outcome"], "error")
        self.assertTrue(event["retryable"])

    def test_caller_cannot_force_retry_for_non_idempotent_media(self):
        profile = self.gateway.resolve(category="image", backend="qwen")
        attempts = 0

        def invoke():
            nonlocal attempts
            attempts += 1
            raise ConnectionError("upstream timed out")

        with self.assertRaises(ConnectionError):
            self.gateway.call_sync(
                profile,
                "images.generate",
                invoke,
                scene="media",
                retry=True,
            )
        self.assertEqual(attempts, 1)

    def test_unknown_adapter_is_observable_but_has_no_implicit_retry(self):
        profile = self.gateway.resolve(category="search", backend="new-provider")
        self.assertEqual(profile.id, "new_provider")
        self.assertFalse(profile.retry.retry_safe)
        self.assertEqual(profile.retry.max_retries, 0)

    def test_embedding_profile_has_a_bounded_timeout_without_automatic_retry(self):
        profile = self.gateway.resolve(
            category="embedding",
            backend="openai-compatible",
            model="text-embedding-v4",
        )
        self.assertEqual(profile.id, "openai-compatible-embedding")
        self.assertEqual(profile.category, "embedding")
        self.assertEqual(profile.retry.timeout_seconds, 30)
        self.assertFalse(profile.retry.retry_safe)
        self.assertTrue(profile.capabilities.idempotent_requests)
        self.assertFalse(profile.capabilities.user_managed_credentials)

    def test_custom_registry_supports_future_provider_addition_without_factory_changes(
        self,
    ):
        definition = ProviderDefinition(
            id="acme-search",
            category="search",
            capabilities=ProviderCapabilities(idempotent_requests=True),
            default_timeout_seconds=7,
            default_max_retries=2,
            retry_safe=True,
        )
        gateway = ProviderGateway(
            registry={("search", "acme"): definition},
            metrics=ProviderMetrics(),
        )
        profile = gateway.resolve(category="search", backend="acme", model="acme-v1")
        self.assertEqual(profile.id, "acme-search")
        self.assertEqual(profile.retry.timeout_seconds, 7)
        self.assertEqual(profile.retry.max_retries, 2)
        self.assertTrue(profile.capabilities.idempotent_requests)


class ImageUrlFallbackTests(unittest.TestCase):
    """中转站图片接口改为返回 url 时，客户端负责下载落盘。"""

    def _client(self):
        from agent_core.tool.imagegen.openai import OpenAIImageGen

        return OpenAIImageGen(
            api_key="relay-test-key",
            base_url="https://relay.example.test/v1",
            model="seedream-5.0-lite",
        )

    def test_url_response_is_downloaded_and_saved(self):
        import tempfile

        order = []
        seen = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            seen["url"] = url
            seen["auth"] = headers["Authorization"]
            seen["body"] = json
            seen["on_generated_before_post"] = bool(order)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"data": [{"url": "https://cdn.example.test/a.png"}]},
                text="",
            )

        def fake_get(url, timeout=None):
            order.append("download")
            return SimpleNamespace(
                status_code=200, raise_for_status=lambda: None, content=b"PNGDATA"
            )

        with tempfile.TemporaryDirectory() as tmp:
            client = self._client()
            client.on_generated = lambda: order.append("billed")
            with patch("requests.post", fake_post), patch("requests.get", fake_get):
                path = client.generate("一只猫", tmp, size="1024x1024")
            self.assertTrue(path.endswith(".png"))
            self.assertEqual(Path(path).read_bytes(), b"PNGDATA")
        self.assertEqual(order, ["billed", "download"])  # 计费先于下载
        self.assertEqual(
            seen["url"], "https://relay.example.test/v1/images/generations"
        )
        self.assertEqual(seen["auth"], "Bearer relay-test-key")
        self.assertEqual(seen["body"]["model"], "seedream-5.0-lite")
        self.assertFalse(seen["on_generated_before_post"])

    def test_usage_cost_usd_is_reported_to_billing_callback(self):
        import tempfile

        calls = []

        def post_with(usage):
            def fake_post(url, json=None, headers=None, timeout=None):
                body = {"data": [{"url": "https://cdn.example.test/a.png"}]}
                if usage is not None:
                    body["usage"] = usage
                return SimpleNamespace(status_code=200, json=lambda: body, text="")

            return fake_post

        get = SimpleNamespace(
            status_code=200, raise_for_status=lambda: None, content=b"PNG"
        )
        for usage, expected in (
            ({"cost_usd": 0.018395, "output_tokens": 601}, [{"cost_usd": 0.018395}]),
            ({"output_tokens": 601}, [{}]),
            (None, [{}]),
        ):
            calls.clear()
            with tempfile.TemporaryDirectory() as tmp:
                client = self._client()
                client.on_generated = lambda **kw: calls.append(kw)
                with (
                    patch("requests.post", post_with(usage)),
                    patch("requests.get", return_value=get),
                ):
                    client.generate("猫", tmp, size="1024x1024")
            self.assertEqual(calls, expected)

    def test_factory_bills_actual_cost_usd_else_estimate(self):
        from services import image_factory
        from services.pricing import calc_unit_credits

        recorded = []

        class FakeClient:
            backend = "openai"
            model = "gpt-image-2"
            base_url = "https://relay.example.test/v1"

            def generate(self, *a, **k):
                return "/tmp/x.png"

        with (
            patch("services.credit_quota.is_using_platform_key", return_value=True),
            patch(
                "services.usage_meter.record_usage",
                side_effect=lambda *a, **k: recorded.append(k),
            ),
        ):
            client = image_factory._attach_hooks(
                FakeClient(), user_id="u", scene="media", with_quota=False
            )
            client.on_generated(cost_usd=0.018395)
            client.on_generated()
        self.assertEqual(recorded[0]["credits"], 132444)  # 实际成本 ×7.2
        self.assertIsNone(recorded[1]["credits"])  # 无成本 → 交给估价
        self.assertEqual(calc_unit_credits("image", 1, model="gpt-image-2"), 130000)

    def test_b64_response_still_supported(self):
        import base64
        import tempfile

        payload = {"data": [{"b64_json": base64.b64encode(b"B64DATA").decode()}]}
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch(
                    "requests.post",
                    return_value=SimpleNamespace(
                        status_code=200, json=lambda: payload, text=""
                    ),
                ),
                patch("requests.get") as get,
            ):
                path = self._client().generate("cat", tmp)
                get.assert_not_called()
                self.assertEqual(Path(path).read_bytes(), b"B64DATA")

    def test_relay_error_raises_image_gen_error(self):
        import tempfile
        from agent_core.tool.imagegen.openai import ImageGenError

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "requests.post",
                return_value=SimpleNamespace(
                    status_code=403,
                    json=lambda: {"error": {"message": "模型未开放"}},
                    text="",
                ),
            ):
                with self.assertRaisesRegex(ImageGenError, "403"):
                    self._client().generate("cat", tmp)

    def test_seedream_models_are_priced_per_image(self):
        from services.pricing import calc_unit_credits, credits_to_yuan

        for model, yuan in (
            ("seedream-5.0-lite", 0.22),
            ("seedream-4.5", 0.25),
            ("seedream-4.0", 0.2),
            ("seedream-5-0-pro", 0.3),
            ("gpt-image-2", 0.13),
        ):
            with self.subTest(model=model):
                self.assertAlmostEqual(
                    credits_to_yuan(calc_unit_credits("image", 1, model=model)),
                    yuan,
                    places=4,
                )

    def test_gpt_image_sizes_snap_to_supported_set(self):
        from agent_core.tool.imagegen.openai import OpenAIImageGen

        cases = {
            "1920x1080": "1536x1024",  # 16:9 课程插图 → 最近横版档
            "1080x1920": "1024x1536",
            "1024x1024": "1024x1024",
            "1536x1024": "1536x1024",
            "2k": "1024x1024",  # 无法解析 → 方形兜底
            "": "1024x1024",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                snapped, adjusted = OpenAIImageGen._snap_gpt_image_size(raw)
                self.assertEqual(snapped, expected)
                self.assertEqual(adjusted, snapped != raw)

    def test_gpt_image_request_snaps_size_and_records_requested(self):
        import json
        import tempfile
        from agent_core.tool.imagegen.openai import OpenAIImageGen

        seen = {}
        with tempfile.TemporaryDirectory() as tmp:

            def fake_post(url, json=None, headers=None, timeout=None):
                seen["body"] = json
                return SimpleNamespace(
                    status_code=200,
                    json=lambda: {"data": [{"url": "https://cdn.example.test/a.png"}]},
                    text="",
                )

            with (
                patch("requests.post", fake_post),
                patch(
                    "requests.get",
                    return_value=SimpleNamespace(
                        status_code=200, raise_for_status=lambda: None, content=b"PNG"
                    ),
                ),
            ):
                path = OpenAIImageGen(
                    api_key="relay-test-key",
                    base_url="https://relay.example.test/v1",
                    model="gpt-image-2",
                ).generate("cat", tmp, size="1920x1080")
                self.assertEqual(seen["body"]["size"], "1536x1024")
                self.assertNotIn("response_format", seen["body"])
                meta = json.loads(Path(path).with_suffix(".meta.json").read_text())
                self.assertEqual(meta["size"], "1536x1024")
                self.assertEqual(meta["requested_size"], "1920x1080")

    def test_non_gpt_image_models_keep_raw_size(self):
        import tempfile
        from agent_core.tool.imagegen.openai import OpenAIImageGen

        seen = {}
        with tempfile.TemporaryDirectory() as tmp:

            def fake_post(url, json=None, headers=None, timeout=None):
                seen["body"] = json
                return SimpleNamespace(
                    status_code=200,
                    json=lambda: {"data": [{"url": "https://cdn.example.test/a.png"}]},
                    text="",
                )

            with (
                patch("requests.post", fake_post),
                patch(
                    "requests.get",
                    return_value=SimpleNamespace(
                        status_code=200, raise_for_status=lambda: None, content=b"P"
                    ),
                ),
            ):
                OpenAIImageGen(
                    api_key="k",
                    base_url="https://relay.example.test/v1",
                    model="seedream-5.0-lite",
                ).generate("cat", tmp, size="1024x1024")
                self.assertEqual(seen["body"]["size"], "1024x1024")
                self.assertEqual(seen["body"].get("response_format"), "b64_json")

    def test_openai_image_timeout_allows_async_relay(self):
        from services.provider_gateway import get_provider_gateway

        profile = get_provider_gateway().resolve(
            category="image", backend="openai", model="seedream-5.0-lite"
        )
        self.assertEqual(profile.retry.timeout_seconds, 300)


if __name__ == "__main__":
    unittest.main()
