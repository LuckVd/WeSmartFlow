"""Regression tests for non-billable HTTP integration policy.

These tests use ``httpx.MockTransport`` only. They prove that HTTP behaviour
cannot silently regress into unsafe retries, unbounded fan-out, or SmartSearch
web-fetch access to private addresses.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.http import (  # noqa: E402
    IntegrationHttpClient,
    IntegrationHttpError,
    IntegrationPolicy,
    UnsafeIntegrationUrl,
    validate_public_http_url,
)
from services.smart_search.sources.anysearch_source import AnySearchSource  # noqa: E402
from services.smart_search.sources.flickr_source import FlickrSource  # noqa: E402
from services.smart_search.sources.web_fetch_source import WebFetchSource  # noqa: E402
from services.smart_search.sources.wikimedia_source import WikimediaSource  # noqa: E402
from services.smart_search.sources.youtube_source import YouTubeSource  # noqa: E402


async def _no_sleep(_delay: float) -> None:
    return None


class IntegrationHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_only_safe_get_and_observes_final_attempt_count(self):
        calls: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.method)
            return httpx.Response(503 if len(calls) == 1 else 200, json={"ok": True})

        client = IntegrationHttpClient(
            IntegrationPolicy(name="public-source", max_retries=1, retry_safe=True),
            transport=httpx.MockTransport(handler),
            sleep=_no_sleep,
        )
        self.assertEqual(
            await client.get_json("https://example.test/search"), {"ok": True}
        )
        self.assertEqual(calls, ["GET", "GET"])

    async def test_post_is_never_retried_even_when_policy_allows_get_retry(self):
        calls: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.method)
            return httpx.Response(503, json={"error": "unavailable"})

        client = IntegrationHttpClient(
            IntegrationPolicy(name="post-search", max_retries=3, retry_safe=True),
            transport=httpx.MockTransport(handler),
            sleep=_no_sleep,
        )
        with self.assertRaises(IntegrationHttpError) as raised:
            await client.post_json("https://example.test/search", json={"q": "test"})
        self.assertEqual(calls, ["POST"])
        self.assertEqual(raised.exception.attempts, 1)
        self.assertTrue(raised.exception.retryable)

    async def test_concurrency_is_bounded_for_one_adapter_instance(self):
        active = 0
        peak = 0

        async def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200, json={"ok": True})

        client = IntegrationHttpClient(
            IntegrationPolicy(name="bounded", max_concurrency=2),
            transport=httpx.MockTransport(handler),
        )
        await asyncio.gather(
            *(client.get_json(f"https://example.test/{index}") for index in range(7))
        )
        self.assertEqual(peak, 2)

    async def test_url_validator_rejects_private_literal_and_mixed_dns_answers(self):
        with self.assertRaises(UnsafeIntegrationUrl):
            await validate_public_http_url("http://127.0.0.1/private")
        with self.assertRaises(UnsafeIntegrationUrl):
            await validate_public_http_url("http://localhost/private")

        async def mixed_dns(_host: str, _port: int) -> list[str]:
            return ["93.184.216.34", "127.0.0.1"]

        with self.assertRaises(UnsafeIntegrationUrl):
            await validate_public_http_url(
                "https://example.test/path", resolver=mixed_dns
            )

    async def test_url_validator_accepts_public_dns_answer(self):
        async def public_dns(_host: str, _port: int) -> list[str]:
            return ["93.184.216.34"]

        valid = await validate_public_http_url(
            "https://example.test/path?secret=value", resolver=public_dns
        )
        self.assertEqual(valid, "https://example.test/path?secret=value")


class SmartSearchSourceAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_search_sources_preserve_result_shapes_through_adapter(self):
        class FakeHttp:
            def __init__(self):
                self.calls: list[tuple[str, dict]] = []

            async def get_json(self, _url, **kwargs):
                self.calls.append(("json", kwargs))
                params = kwargs["params"]
                if params.get("list") == "search":
                    return {"query": {"search": [{"title": "File:Diagram.svg"}]}}
                if params.get("prop") == "imageinfo|revisions":
                    return {
                        "query": {
                            "pages": {
                                "1": {
                                    "title": "File:Diagram.svg",
                                    "imageinfo": [
                                        {
                                            "url": "https://cdn.example.test/full.svg",
                                            "thumburl": "https://cdn.example.test/thumb.png",
                                            "descriptionurl": "https://commons.example.test/file",
                                            "extmetadata": {
                                                "ImageDescription": {
                                                    "value": "<b>图示</b>"
                                                },
                                                "LicenseShortName": {"value": "CC BY"},
                                            },
                                        }
                                    ],
                                }
                            }
                        }
                    }
                return {
                    "items": [
                        {
                            "id": {"videoId": "abcdefghijk"},
                            "snippet": {
                                "title": "讲解视频",
                                "description": "内容",
                                "channelTitle": "频道",
                                "publishedAt": "2026-09-23T00:00:00Z",
                                "thumbnails": {
                                    "medium": {"url": "https://img.example.test/a.jpg"}
                                },
                            },
                        }
                    ]
                }

            async def get_text(self, _url, **kwargs):
                self.calls.append(("text", kwargs))
                return """<?xml version='1.0'?><rss xmlns:media='http://search.yahoo.com/mrss/'><channel><item><title>Image</title><description>&lt;b&gt;说明&lt;/b&gt;</description><link>https://flickr.example.test/page</link><media:content url='https://flickr.example.test/image.jpg'/></item></channel></rss>"""

        http = FakeHttp()
        wikimedia = await WikimediaSource(http_client=http).search("图", max_results=1)
        youtube = await YouTubeSource(api_key="key", http_client=http).search(
            "视频", max_results=1
        )
        flickr = await FlickrSource(http_client=http).search("图", max_results=1)

        self.assertEqual(
            wikimedia[0].metadata["thumb_url"], "https://cdn.example.test/thumb.png"
        )
        self.assertEqual(wikimedia[0].metadata["license"], "CC BY")
        self.assertEqual(youtube[0].metadata["video_id"], "abcdefghijk")
        self.assertTrue(youtube[0].url.endswith("abcdefghijk"))
        self.assertEqual(
            flickr[0].metadata["image_url"], "https://flickr.example.test/image.jpg"
        )
        self.assertEqual(
            [kind for kind, _ in http.calls], ["json", "json", "json", "text"]
        )

    async def test_anysearch_keeps_post_request_and_records_only_successful_call(self):
        observed: list[dict] = []

        class FakeHttp:
            async def post_json(self, url, **kwargs):
                observed.append({"url": url, **kwargs})
                return {
                    "results": [
                        {
                            "title": "Result",
                            "content": "内容",
                            "url": "https://example.test/result",
                        }
                    ]
                }

        source = AnySearchSource(
            api_key="test-key", user_id="__system__", http_client=FakeHttp()
        )
        with patch("services.usage_meter.record_usage") as record_usage:
            results = await source.search("测试", max_results=2, language="zh")
        self.assertEqual(len(results), 1)
        self.assertEqual(observed[0]["url"], source.API_URL)
        self.assertEqual(observed[0]["json"]["query"], "测试")
        self.assertEqual(observed[0]["json"]["language"], "zh")
        record_usage.assert_called_once()

    async def test_web_fetch_validates_initial_url_before_http_call(self):
        class NoNetworkHttp:
            async def request(self, *_args, **_kwargs):
                raise AssertionError("private target must not be requested")

        source = WebFetchSource(http_client=NoNetworkHttp())
        result = await source._fetch_one("http://127.0.0.1/admin")
        self.assertIsNone(result)

    async def test_web_fetch_rejects_private_redirect_before_following_it(self):
        calls: list[str] = []

        class RedirectHttp:
            async def request(self, _method: str, url: str, **_kwargs):
                calls.append(url)
                return httpx.Response(
                    302,
                    headers={"location": "http://127.0.0.1/admin"},
                    request=httpx.Request("GET", url),
                )

        source = WebFetchSource(http_client=RedirectHttp())

        async def public_dns(_host: str, _port: int) -> list[str]:
            return ["93.184.216.34"]

        async def guarded_url(url: str) -> str:
            return await validate_public_http_url(url, resolver=public_dns)

        with patch(
            "services.smart_search.sources.web_fetch_source.validate_public_http_url",
            side_effect=guarded_url,
        ):
            result = await source._fetch_one("https://example.test/start")
        self.assertIsNone(result)
        self.assertEqual(calls, ["https://example.test/start"])


if __name__ == "__main__":
    unittest.main()
