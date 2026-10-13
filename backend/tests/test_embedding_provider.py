"""Regression tests for the KG embedding Provider Gateway boundary.

These tests deliberately use a fake OpenAI-compatible client: they verify timeout
policy, safe no-retry behaviour, response validation and ledger attribution without
making a network request or requiring a configured KG credential.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kg.embedder import OpenAICompatEmbedder  # noqa: E402
from services.provider_gateway import ProviderGateway, ProviderMetrics  # noqa: E402


class _EmbeddingEndpoint:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses):
        self.embeddings = _EmbeddingEndpoint(responses)


def _response(*vectors, usage=None, indexes=None):
    indexes = list(range(len(vectors))) if indexes is None else indexes
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=vector)
            for index, vector in zip(indexes, vectors)
        ],
        usage=usage,
    )


class EmbeddingProviderTests(unittest.TestCase):
    def setUp(self):
        self.metrics = ProviderMetrics()
        self.gateway = ProviderGateway(metrics=self.metrics, sleep=lambda _delay: None)

    def make_embedder(self, responses, *, dim=2):
        self.client = _FakeClient(responses)
        return OpenAICompatEmbedder(
            api_key="secret-is-never-observed",
            base_url="https://user:secret@example.test/v1?api_key=not-for-logs",
            model="text-embedding-v4",
            dim=dim,
            batch_size=2,
            client=self.client,
            gateway=self.gateway,
        )

    def test_profile_is_secret_free_and_embedding_never_retries_ambiguous_timeout(self):
        embedder = self.make_embedder([ConnectionError("upstream timeout")])
        profile = embedder.provider_profile
        self.assertEqual(profile.category, "embedding")
        self.assertEqual(profile.id, "openai-compatible-embedding")
        self.assertEqual(profile.retry.timeout_seconds, 30)
        self.assertFalse(profile.retry.retry_safe)
        self.assertNotIn("secret", str(profile.public_dict()))

        with self.assertRaises(ConnectionError):
            embedder.embed_one("linear algebra")
        self.assertEqual(len(self.client.embeddings.calls), 1)
        event = self.metrics.snapshot_for(category="embedding")["recent"][-1]
        self.assertEqual(event["operation"], "embeddings.create")
        self.assertEqual(event["outcome"], "error")
        self.assertTrue(event["retryable"])

    def test_orders_provider_indexes_and_records_system_embedding_usage(self):
        response = _response(
            [0.2, 0.3],
            [0.4, 0.5],
            indexes=[1, 0],
            usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 7}),
        )
        embedder = self.make_embedder([response])

        with patch("services.usage_meter.record_usage") as record_usage:
            vectors = embedder.embed_many(["first", "second"])

        self.assertEqual(vectors, [[0.4, 0.5], [0.2, 0.3]])
        record_usage.assert_called_once_with(
            "__system__",
            category="embedding",
            scene="kg",
            model="text-embedding-v4",
            provider="openai-compatible-embedding",
            usage={"prompt_tokens": 7},
            is_system=True,
            counts_quota=False,
        )
        event = self.metrics.snapshot_for(category="embedding")["recent"][-1]
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["attempts"], 1)

    def test_missing_usage_is_estimated_and_wrong_dimension_is_rejected_at_boundary(
        self,
    ):
        embedder = self.make_embedder([_response([1.0])], dim=2)
        with patch("services.usage_meter.record_usage") as record_usage:
            with self.assertRaisesRegex(RuntimeError, "dimension 1; expected 2"):
                embedder.embed_one("a short input")

        # The provider response was received and can be billed even though its
        # vector cannot be stored, so its cost is still a system expense.
        usage = record_usage.call_args.kwargs["usage"]
        self.assertTrue(usage["estimated"])
        self.assertGreater(usage["prompt_tokens"], 0)
        event = self.metrics.snapshot_for(category="embedding")["recent"][-1]
        self.assertEqual(event["outcome"], "error")
        self.assertEqual(event["error_type"], "RuntimeError")

    def test_empty_inputs_are_not_sent_or_metered(self):
        embedder = self.make_embedder([])
        with patch("services.usage_meter.record_usage") as record_usage:
            self.assertEqual(embedder.embed_one(""), [])
            self.assertEqual(embedder.embed_many(["", ""]), [[], []])
        self.assertEqual(self.client.embeddings.calls, [])
        record_usage.assert_not_called()

    def test_invalid_direct_constructor_values_are_rejected_before_client_use(self):
        with self.assertRaisesRegex(ValueError, "dimension"):
            OpenAICompatEmbedder("key", "", "model", 0, client=object())
        with self.assertRaisesRegex(ValueError, "batch_size"):
            OpenAICompatEmbedder("key", "", "model", 2, 101, client=object())


if __name__ == "__main__":
    unittest.main()
