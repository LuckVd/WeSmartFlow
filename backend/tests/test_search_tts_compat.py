"""Tavily 兼容搜索地址与 OpenAI 兼容 TTS 的离线回归测试。"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _wav_bytes(frames: int = 2400, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_TTS_ENV = ("TTS_API_KEY", "TTS_BASE_URL", "TTS_MODEL", "TTS_VOICE", "TTS_SPEED")


class TavilyCompatibleSearchTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                "TAVILY_API_KEY": "platform-test-key",
                "TAVILY_BASE_URL": "https://relay.example.test/v1/",
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def _client(self, user_key: str):
        from services import search_factory

        with (
            patch("database.get_setting", return_value=user_key),
            patch.object(search_factory, "_attach_hooks", side_effect=lambda c, **_: c),
        ):
            return search_factory.get_search_client("alice")

    def test_platform_key_uses_configured_base_url(self):
        client = self._client("")
        self.assertEqual(client.api_key, "platform-test-key")
        self.assertEqual(client.base_url, "https://relay.example.test/v1")

    def test_user_key_never_goes_to_platform_base_url(self):
        client = self._client("user-test-key")
        self.assertEqual(client.api_key, "user-test-key")
        self.assertEqual(client.base_url, "")

    def test_sdk_posts_to_compatible_search_path_with_bearer(self):
        import requests
        from agent_core.tool.search.tavily import TavilySearchClient

        seen = {}

        def fake_post(session, url, data=None, timeout=None, **_kw):
            seen["url"] = url
            seen["auth"] = session.headers.get("Authorization")
            seen["body"] = json.loads(data)
            resp = MagicMock(status_code=200)
            resp.json.return_value = {
                "query": "q",
                "answer": None,
                "results": [
                    {"title": "t", "url": "https://a", "content": "c", "score": 1.0}
                ],
                "usage": {"credits": 1},
            }
            return resp

        with patch.object(requests.Session, "post", fake_post):
            result = TavilySearchClient(
                "platform-test-key", base_url="https://relay.example.test/v1"
            ).search("q", max_results=3)
        self.assertEqual(seen["url"], "https://relay.example.test/v1/search")
        self.assertEqual(seen["auth"], "Bearer platform-test-key")
        self.assertEqual(seen["body"]["query"], "q")
        self.assertEqual(seen["body"]["max_results"], 3)
        self.assertEqual(result.results[0]["url"], "https://a")
        self.assertEqual(result.api_credits, 1)

    def test_default_base_url_is_official(self):
        from agent_core.tool.search.tavily import TavilySearchClient

        fake = MagicMock()
        fake.search.return_value = {"results": []}
        with patch("tavily.TavilyClient", return_value=fake) as ctor:
            TavilySearchClient("k").search("q")
        self.assertIsNone(ctor.call_args.kwargs["api_base_url"])


class OpenAICompatTTSClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def make(self, **kw):
        from agent_core.tool.tts.openai_compat import OpenAICompatTTS

        params = dict(
            api_key="tts-test-key",
            base_url="https://relay.example.test/v1/",
            model="minimax-speech-turbo",
            voice="presenter_female",
        )
        params.update(kw)
        return OpenAICompatTTS(**params)

    def test_request_contract_billing_header_and_duration(self):
        seen = {}
        order = []

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data)
            return _FakeResponse(_wav_bytes(), {"X-Billed-Characters": "14"})

        tts = self.make(speed=1.2)
        out = Path(self.tmp.name) / "a.wav"
        tts.on_generated = lambda r: order.append(
            ("billed", r.billed_characters, out.exists())
        )
        with patch("urllib.request.urlopen", fake_urlopen):
            result = tts.synthesize("你好世界", str(out), instruct="ignored")

        self.assertTrue(result.success, result.error)
        self.assertEqual(seen["url"], "https://relay.example.test/v1/audio/speech")
        self.assertEqual(seen["auth"], "Bearer tts-test-key")
        self.assertEqual(
            seen["body"],
            {
                "model": "minimax-speech-turbo",
                "input": "你好世界",
                "response_format": "wav",
                "voice": "presenter_female",
                "speed": 1.2,
            },
        )
        self.assertEqual(result.billed_characters, 14)
        self.assertAlmostEqual(result.duration, 0.1, places=2)
        # 用量在落盘之前报告
        self.assertEqual(order, [("billed", 14, False)])

    def test_caller_voice_overrides_default_and_missing_header_uses_length(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["body"] = json.loads(req.data)
            return _FakeResponse(_wav_bytes(), {})

        with patch("urllib.request.urlopen", fake_urlopen):
            result = self.make().synthesize(
                "hello", str(Path(self.tmp.name) / "b.wav"), voice="audiobook_female_1"
            )
        self.assertEqual(seen["body"]["voice"], "audiobook_female_1")
        self.assertNotIn("speed", seen["body"])
        self.assertEqual(result.billed_characters, 5)

    def test_http_error_returns_failure_without_billing(self):
        billed = []

        def fake_urlopen(req, timeout=None):
            body = json.dumps({"error": {"message": "bad voice", "type": "x"}}).encode()
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(body))

        tts = self.make()
        tts.on_generated = billed.append
        with patch("urllib.request.urlopen", fake_urlopen):
            result = tts.synthesize("hello", str(Path(self.tmp.name) / "c.wav"))
        self.assertFalse(result.success)
        self.assertEqual(result.error, "HTTP 400: bad voice")
        self.assertEqual(billed, [])

    def test_empty_text_and_incomplete_config_fail_fast(self):
        with patch("urllib.request.urlopen") as urlopen:
            self.assertFalse(self.make().synthesize("  ", "x.wav").success)
            self.assertFalse(self.make(model="").synthesize("hi", "x.wav").success)
        urlopen.assert_not_called()


class TTSFactorySelectionTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in _TTS_ENV + ("DASHSCOPE_API_KEY",):
            os.environ.pop(name, None)

    def _get(self, user_key: str = "", **env):
        from services import tts_factory

        os.environ.update(env)
        with (
            patch.object(tts_factory, "_dotenv_value", return_value=""),
            patch.object(tts_factory, "_user_tts_key", return_value=user_key),
            patch("database.get_setting", return_value=user_key),
            patch.object(tts_factory, "_attach_hooks", side_effect=lambda c, **_: c),
            patch.object(tts_factory.shutil, "which", return_value=None),
        ):
            return tts_factory.get_tts("alice")

    def _compat_env(self):
        return {
            "TTS_API_KEY": "tts-test-key",
            "TTS_BASE_URL": "https://relay.example.test/v1",
            "TTS_MODEL": "minimax-speech-turbo",
            "TTS_VOICE": "presenter_female",
            "TTS_SPEED": "1.1",
        }

    def test_platform_compat_tts_is_primary(self):
        from agent_core.tool.tts.openai_compat import OpenAICompatTTS

        tts = self._get(**self._compat_env(), DASHSCOPE_API_KEY="dash-test-key")
        primary = tts._primary
        self.assertIsInstance(primary, OpenAICompatTTS)
        self.assertEqual(primary.model, "minimax-speech-turbo")
        self.assertEqual(primary.default_voice, "presenter_female")
        self.assertEqual(primary.speed, 1.1)
        self.assertEqual(primary.timeout, 300)

    def test_user_dashscope_key_still_wins(self):
        from agent_core.tool.tts.qwen import QwenTTS

        tts = self._get("user-dash-key", **self._compat_env())
        self.assertIsInstance(tts._primary, QwenTTS)
        self.assertEqual(tts._primary.api_key, "user-dash-key")

    def test_partial_config_skips_tts_instead_of_switching_provider(self):
        tts = self._get(TTS_API_KEY="tts-test-key", DASHSCOPE_API_KEY="dash-test-key")
        self.assertIsNone(tts)

    def test_unset_compat_keeps_dashscope(self):
        from agent_core.tool.tts.qwen import QwenTTS

        tts = self._get(DASHSCOPE_API_KEY="dash-test-key")
        self.assertIsInstance(tts._primary, QwenTTS)

    def test_minimax_models_are_priced(self):
        from services.pricing import calc_unit_credits

        turbo = calc_unit_credits("audio", 1_000_000, model="minimax-speech-turbo")
        hd = calc_unit_credits("audio", 1_000_000, model="minimax-speech-hd")
        self.assertGreater(turbo, 0)
        self.assertGreater(hd, turbo)


if __name__ == "__main__":
    unittest.main()
