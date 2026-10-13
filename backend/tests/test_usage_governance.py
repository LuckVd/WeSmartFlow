"""Offline integration tests: real SQLite ledger and quota, mocked paid providers."""

import asyncio
import importlib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import pricing, usage_meter, credit_quota, llm_factory
from services.external_usage import (
    usage_scope,
    current_usage,
    UsageThread,
    before_raw,
    record_raw,
)
from agent_core.llm import LLMResponse
from agent_core.llm.base import StreamFinishEvent
from migrate_credits import _DDL, migrate
from services.credit_wallet import SCHEMA, debit, balance


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "usage.db"
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_DDL + SCHEMA)
        self.conn.executescript(
            "CREATE TABLE users(id TEXT PRIMARY KEY, github_id TEXT); INSERT INTO users VALUES ('alice',NULL);"
        )

        @contextmanager
        def db():
            with self.conn:
                yield self.conn

        self.patches = [
            patch.object(usage_meter, "get_db", db),
            patch("database.get_db", db),
            patch.object(credit_quota, "get_setting", return_value=""),
            patch.object(credit_quota, "CREDITS_ENFORCEMENT_ENABLED", True),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.conn.close()
        self.tmp.cleanup()

    def exhaust(self, user_id):
        available = balance(user_id)
        with self.conn:
            debit(self.conn, user_id, available, "test-exhaust")

    def test_deepseek_peak_cache_and_reasoning(self):
        usage = {
            "prompt_tokens": 1000,
            "prompt_cache_hit_tokens": 200,
            "completion_tokens": 100,
            "completion_tokens_details": {"reasoning_tokens": 80},
        }
        peak = datetime(2026, 9, 7, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
        quiet = peak.replace(hour=12)
        # 网关价目：$0.285714 / $0.0058 / $1.142858 每百万 token，按 7.2 折算
        self.assertEqual(
            pricing.calc_llm_credits("deepseek-v4-flash", usage, at=peak), 2477
        )
        self.assertEqual(
            pricing.calc_llm_credits("deepseek-v4-flash", usage, at=quiet), 1239
        )
        # 周末与工作日同一峰谷规则
        saturday_peak = datetime(2026, 9, 12, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
        saturday_quiet = saturday_peak.replace(hour=20)
        self.assertEqual(
            pricing.calc_llm_credits("deepseek-v4-flash", usage, at=saturday_peak),
            2477,
        )
        self.assertEqual(
            pricing.calc_llm_credits("deepseek-v4-flash", usage, at=saturday_quiet),
            1239,
        )

    def test_llm_uses_provider_cost_usd_else_token_estimate(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 100}
        peak = datetime(2026, 9, 7, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
        estimated = pricing.calc_llm_credits("deepseek-v4-flash", usage, at=peak)
        # 供应商给出真实成本时直接采用（$0.001 × 7.2 = 7200 credits）
        self.assertEqual(
            pricing.calc_llm_credits(
                "deepseek-v4-flash", {**usage, "cost_usd": 0.001}, at=peak
            ),
            7200,
        )
        # 缺失 / 非法 / 非正数 → 退回 token 估算
        for bad in (None, 0, -0.5, "x", float("nan")):
            self.assertEqual(
                pricing.calc_llm_credits(
                    "deepseek-v4-flash", {**usage, "cost_usd": bad}, at=peak
                ),
                estimated,
            )

    def test_extract_usage_keeps_gateway_cost_usd(self):
        from types import SimpleNamespace

        from agent_core.llm.openai_llm import _extract_usage

        raw = SimpleNamespace(
            prompt_tokens=10, completion_tokens=5, total_tokens=15, cost_usd=1.5e-05
        )
        self.assertEqual(_extract_usage(raw)["cost_usd"], 1.5e-05)
        raw.cost_usd = 0
        self.assertNotIn("cost_usd", _extract_usage(raw))
        raw.cost_usd = True
        self.assertNotIn("cost_usd", _extract_usage(raw))

    def test_usd_to_credits_and_tavily_price(self):
        self.assertEqual(pricing.usd_to_credits(0.018395), 132444)
        for bad in (None, 0, -1, "x", float("nan")):
            self.assertIsNone(pricing.usd_to_credits(bad))
        # 网关 Tavily 兼容搜索按 $0.0003/credit 计费
        self.assertEqual(
            pricing.calc_unit_credits("search", 1000, provider="tavily"), 2160000
        )

    def test_media_units_and_overrides(self):
        self.assertEqual(
            pricing.calc_unit_credits("image", 1, model="qwen-image-2.0"), 200000
        )
        self.assertEqual(
            pricing.calc_unit_credits("audio", 1000, model="qwen3-tts-instruct-flash"),
            80000,
        )
        self.assertEqual(
            pricing.calc_unit_credits("audio", 1000, model="cosyvoice-v1"), 200000
        )
        self.assertEqual(
            pricing.calc_unit_credits("search", 2, provider="tavily"), 4320
        )
        self.assertEqual(
            pricing.calc_unit_credits("search", 1, provider="anysearch"), 0
        )
        self.assertEqual(
            pricing.calc_unit_credits("audio", 100, provider="macos-say"), 0
        )
        self.assertEqual(pricing.calc_unit_credits("audio", 0, model="unknown"), 0)
        with self.assertRaises(ValueError):
            pricing.calc_unit_credits("image", 1, model="unknown")
        with patch.dict(
            "os.environ", {"PRICING_OVERRIDES_JSON": '{"image:private-model":0.15}'}
        ):
            self.assertEqual(
                pricing.calc_unit_credits("image", 2, model="private-model"), 300000
            )

    def test_qwen_tiers(self):
        p = pricing.resolve_pricing(
            "qwen-plus",
            usage={
                "prompt_tokens": 128001,
                "completion_tokens": 100,
                "reasoning_tokens": 10,
            },
        )
        self.assertEqual(p["in"], 2.4)
        self.assertEqual(p["out"], 24)

    def test_missing_usage_marked(self):
        result = pricing.ensure_usage(
            None, [{"role": "user", "content": "你好"}], "你好"
        )
        self.assertTrue(result["estimated"])
        self.assertGreater(pricing.calc_llm_credits("qwen-plus", result), 0)
        actual = {"prompt_tokens": 10, "completion_tokens": 5}
        self.assertEqual(pricing.ensure_usage(actual, [], ""), actual)

    def test_ledger_attribution_and_quota(self):
        usage_meter.record_usage(
            "alice", category="image", model="qwen-image-2.0", counts_quota=True
        )
        usage_meter.record_usage(
            "alice", category="image", model="qwen-image-2.0-pro", counts_quota=False
        )
        usage_meter.record_usage(
            "alice", category="image", model="qwen-image-2.0-pro", is_system=True
        )
        overview = usage_meter.get_usage_overview("alice")
        self.assertEqual(overview["credits"], 200000)
        self.assertEqual(sum(r["credits"] for r in overview["by_category"]), 200000)
        self.assertEqual(len(usage_meter.list_usage_events("alice")), 3)
        self.assertEqual(usage_meter.get_platform_overview()["credits"], 700000)
        self.exhaust("alice")
        with self.assertRaises(credit_quota.CreditsExceeded):
            credit_quota.assert_available("alice", platform_key=True)
        credit_quota.assert_available("alice", platform_key=False)

    def test_system_embedding_is_token_priced_but_never_debits_a_user_wallet(self):
        credits = usage_meter.record_usage(
            "__system__",
            category="embedding",
            scene="kg",
            model="text-embedding-v4",
            usage={"prompt_tokens": 1000, "completion_tokens": 0},
            provider="openai-compatible-embedding",
            is_system=True,
            counts_quota=False,
        )
        self.assertEqual(credits, 500)
        event = self.conn.execute(
            "SELECT category, is_system, prompt_tokens, credits FROM usage_events"
        ).fetchone()
        self.assertEqual(
            dict(event),
            {
                "category": "embedding",
                "is_system": 1,
                "prompt_tokens": 1000,
                "credits": 500,
            },
        )
        details = self.conn.execute(
            "SELECT provider, counts_quota FROM usage_details"
        ).fetchone()
        self.assertEqual(
            dict(details),
            {
                "provider": "openai-compatible-embedding",
                "counts_quota": 0,
            },
        )
        self.assertEqual(usage_meter.get_period_credits("__system__"), 0)

    def test_raw_platform_calls_cannot_use_personal_key_exemption(self):
        self.exhaust("alice")
        with usage_scope("alice", "live-science"):
            with patch.object(credit_quota, "get_setting", return_value="personal-key"):
                record_raw("image", model="qwen-image-2.0")
                with self.assertRaises(credit_quota.CreditsExceeded):
                    before_raw("llm")
        self.assertEqual(usage_meter.get_period_credits("alice"), 200000)

    def test_nested_threads_keep_owner_and_reset(self):
        result = []

        def parent():
            child = UsageThread(target=lambda: result.append(current_usage().user_id))
            child.start()
            child.join()

        with usage_scope("alice", "court"):
            t = UsageThread(target=parent)
            t.start()
            t.join()
        self.assertEqual(result, ["alice"])
        with self.assertRaises(RuntimeError):
            current_usage()

    def test_llm_three_paths_record_once_each_and_reject_before_call(self):
        class Fake:
            model_name = "qwen-plus"
            calls = 0

            def think(self, messages):
                self.calls += 1
                return LLMResponse(
                    "ok", usage={"prompt_tokens": 10, "completion_tokens": 5}
                )

            async def async_think(self, messages):
                self.calls += 1
                return LLMResponse(
                    "ok", usage={"prompt_tokens": 10, "completion_tokens": 5}
                )

            async def stream_think(self, messages):
                self.calls += 1
                yield StreamFinishEvent(
                    LLMResponse(
                        "ok", usage={"prompt_tokens": 10, "completion_tokens": 5}
                    )
                )

        f = llm_factory._attach_hooks(
            Fake(), user_id="alice", scene="chat", with_quota=True, is_system=False
        )
        f.think([])
        asyncio.run(f.async_think([]))

        async def stream():
            async for _ in f.stream_think([]):
                pass

        asyncio.run(stream())
        self.assertEqual(len(usage_meter.list_usage_events("alice")), 3)
        self.assertEqual(f.calls, 3)
        self.exhaust("alice")
        with self.assertRaises(credit_quota.CreditsExceeded):
            f.think([])
        self.assertEqual(f.calls, 3)

    def test_search_depth_and_system(self):
        from agent_core.tool.search.tavily import TavilySearchClient
        from services.search_factory import _attach_hooks

        fake = MagicMock()
        fake.search.return_value = {"results": []}
        with patch("tavily.TavilyClient", return_value=fake):
            c = _attach_hooks(
                TavilySearchClient("test"),
                user_id="alice",
                scene="search",
                with_quota=True,
            )
            c.search("q", search_depth="advanced")
            s = _attach_hooks(
                TavilySearchClient("test"),
                user_id="__system__",
                scene="system",
                with_quota=True,
            )
            s.search("q")
        self.assertEqual(usage_meter.get_period_credits("alice"), 4320)
        self.assertEqual(usage_meter.get_period_credits("__system__"), 0)
        self.assertEqual(usage_meter.list_usage_events("__system__")[0]["is_system"], 1)

    def test_tts_characters_and_local(self):
        from services.tts_factory import _attach_hooks
        from agent_core.tool.tts.base import TTSResult

        class Fake:
            backend = "qwen3-tts"
            model = "qwen3-tts-instruct-flash"

            def synthesize(self, *args, **kwargs):
                return TTSResult(
                    text="abc",
                    backend=self.backend,
                    model=self.model,
                    success=True,
                    billed_characters=10,
                )

        c = _attach_hooks(Fake(), user_id="alice", scene="media", with_quota=True)
        c.synthesize("abc", "unused")
        self.assertEqual(usage_meter.get_period_credits("alice"), 800)

    def test_demo_auth_and_math_metering(self):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        from dependencies import create_access_token
        from routers.examples import router
        from routers.court import router as court

        app = FastAPI()
        app.include_router(router)
        app.include_router(court)

        @app.exception_handler(credit_quota.CreditsExceeded)
        async def exceeded(request, exc):
            return JSONResponse(status_code=429, content={"detail": str(exc)})

        client = TestClient(app)
        for route in app.routes:
            if route.path.startswith("/api/") and "POST" in (
                getattr(route, "methods", None) or set()
            ):
                self.assertIn(
                    client.post(route.path, json={}).status_code, (401, 403), route.path
                )

        class Fake:
            model_name = "qwen-plus"

            async def async_think(self, messages):
                return LLMResponse(
                    "three", usage={"prompt_tokens": 10, "completion_tokens": 5}
                )

        # Use actual factory hook on a mock of the provider class, so billing and auth are both exercised.
        with (
            patch("services.llm_factory.OpenAILLM") as cls,
            patch("services.llm_factory._get_cfg", return_value=""),
            patch.dict(
                "os.environ",
                {
                    "LLM_API_KEY": "test",
                    "LLM_BASE_URL": "https://invalid.test",
                    "LLM_MODEL": "qwen-plus",
                },
            ),
        ):
            f = Fake()
            f.think = lambda messages: None

            async def stream(messages):
                if False:
                    yield None

            f.stream_think = stream
            cls.return_value = f
            headers = {"Authorization": "Bearer " + create_access_token("alice")}
            payload = {"messages": [{"role": "user", "content": "count"}]}
            response = client.post(
                "/api/demo/dive-into-math-garden/llm", headers=headers, json=payload
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["text"], "three")
            self.assertGreater(usage_meter.get_period_credits("alice"), 0)
            self.exhaust("alice")
            response = client.post(
                "/api/demo/dive-into-math-garden/llm", headers=headers, json=payload
            )
            self.assertEqual(response.status_code, 429, response.text)

    def test_generated_image_is_billed_even_when_download_fails(self):
        from services.image_factory import _attach_hooks
        from agent_core.tool.imagegen.qwen import QwenImageGen
        from agent_core.tool.imagegen.base import ImageGenError

        response = MagicMock(status_code=200)
        response.json.return_value = {
            "output": {
                "choices": [
                    {"message": {"content": [{"image": "https://invalid.test/image"}]}}
                ]
            }
        }
        client = _attach_hooks(
            QwenImageGen("test", model="qwen-image-2.0"),
            user_id="alice",
            scene="media",
            with_quota=True,
        )
        with (
            patch.object(
                importlib.import_module("agent_core.tool.imagegen.qwen").requests,
                "post",
                return_value=response,
            ),
            patch.object(
                importlib.import_module("agent_core.tool.imagegen.qwen").requests,
                "get",
                side_effect=RuntimeError("download failed"),
            ),
        ):
            with self.assertRaises(ImageGenError):
                client.generate("image", self.tmp.name)
        self.assertEqual(usage_meter.get_period_credits("alice"), 200000)
        self.assertEqual(len(usage_meter.list_usage_events("alice")), 1)

    def test_qwen_tts_billed_before_download_and_failure_not_free(self):
        import json
        from services.tts_factory import _attach_hooks
        from agent_core.tool.tts.qwen import QwenTTS

        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "output": {"audio": {"url": "https://invalid.test/audio"}},
                "usage": {"characters": 12},
            }
        ).encode()
        client = _attach_hooks(
            QwenTTS("test"), user_id="alice", scene="media", with_quota=True
        )
        with patch.object(
            importlib.import_module("agent_core.tool.tts.qwen").urllib.request,
            "urlopen",
            side_effect=[response, RuntimeError("download failed")],
        ):
            result = client.synthesize("hello", str(Path(self.tmp.name) / "a.wav"))
        self.assertFalse(result.success)
        self.assertEqual(usage_meter.get_period_credits("alice"), 960)
        self.assertEqual(len(usage_meter.list_usage_events("alice")), 1)

    def test_cosyvoice_uses_instance_key_and_restores_global(self):
        import dashscope
        from agent_core.tool.tts.cosyvoice import CosyVoiceTTS
        from dashscope.audio.tts_v2 import SpeechSynthesizer

        seen = []

        def fake_call(instance, text):
            seen.append(instance.apikey)
            return b"fake-audio"

        with (
            patch.object(dashscope, "api_key", "original"),
            patch.object(SpeechSynthesizer, "call", fake_call),
        ):
            result = CosyVoiceTTS("personal").synthesize(
                "hello", str(Path(self.tmp.name) / "a.mp3")
            )
            self.assertTrue(result.success, result.error)
            self.assertEqual(seen, ["personal"])
            self.assertEqual(dashscope.api_key, "original")

    def test_migration_idempotent(self):
        self.assertEqual(migrate(self.path), 0)
        self.assertEqual(migrate(self.path), 0)

    def test_upgrade_early_detail_schema(self):
        self.conn.execute("ALTER TABLE usage_details DROP COLUMN estimated")
        self.conn.commit()
        self.assertEqual(migrate(self.path), 0)
        self.assertIn(
            "estimated",
            {r[1] for r in self.conn.execute("PRAGMA table_info(usage_details)")},
        )
        self.assertEqual(migrate(self.path), 0)


if __name__ == "__main__":
    unittest.main()
