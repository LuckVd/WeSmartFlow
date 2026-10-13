"""
KG 嵌入服务

设计要点：
- 单一抽象 `Embedder`，通过环境变量决定具体实现
- `NullEmbedder` 占位：未配置 KG_EMBEDDING_API_KEY 时使用，向量通道关闭
- `OpenAICompatEmbedder`：兼容 OpenAI / 阿里百炼 / 任何 OpenAI 风格 embeddings 接口
- Provider Gateway 管理超时、无凭据观测和调用边界；embedding 绝不做通用重试，
  因为超时后的上游计费状态无法可靠判断

环境变量：
  KG_EMBEDDING_API_KEY    必需，留空则关闭向量通道
  KG_EMBEDDING_BASE_URL   兼容接口的 base url（如百炼 https://dashscope.aliyuncs.com/compatible-mode/v1）
  KG_EMBEDDING_MODEL      模型名（默认 text-embedding-v4）
  KG_EMBEDDING_DIM        向量维度（默认 1024）
  KG_EMBEDDING_BATCH      单次请求最多条数（默认 10，迁就百炼上限）
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Any, Protocol

from services.provider_gateway import ProviderGateway, get_provider_gateway

from .config import (
    KG_EMBEDDING_API_KEY,
    KG_EMBEDDING_BASE_URL,
    KG_EMBEDDING_BATCH,
    KG_EMBEDDING_DIM,
    KG_EMBEDDING_MODEL,
    KG_EMBEDDING_SEND_DIMENSIONS,
)

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """嵌入器协议。"""

    dim: int
    model: str

    def embed_one(self, text: str) -> list[float]: ...

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbedder:
    """占位实现：所有方法返回空向量；vector_store 检测到 dim==0 后关闭向量通道。"""

    dim: int = 0
    model: str = ""

    def embed_one(self, text: str) -> list[float]:
        return []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class OpenAICompatEmbedder:
    """OpenAI-compatible embedding client behind the Provider Gateway.

    KG embedding uses a platform-level credential and is always charged to the
    system ledger.  It must not inherit a request user's quota or personal-key
    setting: the same vector can be shared by many users and background indexing
    has no request owner.  The provider profile carries no key and is therefore
    safe to attach to diagnostics.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dim: int,
        batch_size: int = 10,
        *,
        send_dimensions: bool = False,
        client: Any | None = None,
        gateway: ProviderGateway | None = None,
    ) -> None:
        if not isinstance(dim, int) or not 1 <= dim <= 32_768:
            raise ValueError(
                "embedding dimension must be an integer between 1 and 32768"
            )
        if not isinstance(batch_size, int) or not 1 <= batch_size <= 100:
            raise ValueError(
                "embedding batch_size must be an integer between 1 and 100"
            )
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self.send_dimensions = bool(send_dimensions)
        self._gateway = gateway or get_provider_gateway()
        self.provider_profile = self._gateway.resolve(
            category="embedding",
            backend="openai-compatible",
            model=model,
            endpoint=base_url,
        )

        if client is None:
            # Delay import so a deployment with KG disabled does not require the
            # optional SDK at import time.  Embedding requests are intentionally
            # non-retried: an upstream timeout can still represent a billable call.
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url=base_url or None,
                timeout=self.provider_profile.retry.timeout_seconds,
                max_retries=0,
            )
        self._client = client

    def _record_usage(self, response: Any, inp: str | list[str]) -> None:
        """Record a successful upstream response as a system embedding expense.

        A few OpenAI-compatible services omit usage from an otherwise successful
        embedding response.  Record a conservative input-only estimate in that
        case instead of silently treating the provider call as free.
        """
        from services.usage_meter import record_usage

        raw_usage = getattr(response, "usage", None)
        if hasattr(raw_usage, "model_dump"):
            usage = raw_usage.model_dump()
        elif isinstance(raw_usage, dict):
            usage = dict(raw_usage)
        else:
            usage = {}

        if not any(key in usage for key in ("prompt_tokens", "input_tokens")):
            from agent_core.memory.base import estimate_tokens

            texts = [inp] if isinstance(inp, str) else inp
            usage = {
                "prompt_tokens": estimate_tokens(
                    [{"role": "user", "content": text} for text in texts]
                ),
                "completion_tokens": 0,
                "estimated": True,
            }

        record_usage(
            "__system__",
            category="embedding",
            scene="kg",
            model=self.model,
            provider=self.provider_profile.id,
            usage=usage,
            is_system=True,
            counts_quota=False,
        )

    def _extract_vectors(self, response: Any, expected_count: int) -> list[list[float]]:
        """Validate and order provider output before it reaches sqlite-vec.

        A wrong dimension, missing item or non-finite number otherwise appears much
        later as a storage failure.  Fail at the provider boundary with no request
        body in the error so the gateway records one safe, actionable failure.
        """
        data = getattr(response, "data", None)
        if not isinstance(data, (list, tuple)) or len(data) != expected_count:
            actual = len(data) if isinstance(data, (list, tuple)) else 0
            raise RuntimeError(
                f"embedding provider returned {actual} vectors; expected {expected_count}"
            )

        vectors: list[list[float] | None] = [None] * expected_count
        for fallback_index, item in enumerate(data):
            index = getattr(item, "index", fallback_index)
            if not isinstance(index, int) or not 0 <= index < expected_count:
                raise RuntimeError(
                    "embedding provider returned an invalid vector index"
                )
            if vectors[index] is not None:
                raise RuntimeError(
                    "embedding provider returned duplicate vector indexes"
                )
            raw_vector = getattr(item, "embedding", None)
            if not isinstance(raw_vector, (list, tuple)) or len(raw_vector) != self.dim:
                actual_dim = (
                    len(raw_vector) if isinstance(raw_vector, (list, tuple)) else 0
                )
                raise RuntimeError(
                    f"embedding provider returned dimension {actual_dim}; expected {self.dim}"
                )
            try:
                vector = [float(value) for value in raw_vector]
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    "embedding provider returned non-numeric vector values"
                ) from exc
            if not all(math.isfinite(value) for value in vector):
                raise RuntimeError(
                    "embedding provider returned non-finite vector values"
                )
            vectors[index] = vector

        if any(vector is None for vector in vectors):
            raise RuntimeError("embedding provider omitted one or more vector indexes")
        return [vector for vector in vectors if vector is not None]

    def _call(self, inp: str | list[str]) -> list[list[float]]:
        expected_count = 1 if isinstance(inp, str) else len(inp)

        def _invoke() -> list[list[float]]:
            params: dict[str, Any] = {"model": self.model, "input": inp}
            if self.send_dimensions:
                params["dimensions"] = self.dim
            response = self._client.embeddings.create(**params)
            # The response may still be billable when its vector payload is bad,
            # so persist its usage before schema validation raises.
            self._record_usage(response, inp)
            return self._extract_vectors(response, expected_count)

        return self._gateway.call_sync(
            self.provider_profile,
            "embeddings.create",
            _invoke,
            scene="kg",
        )

    def embed_one(self, text: str) -> list[float]:
        if not text:
            return []
        out = self._call(text)
        return out[0] if out else []

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result: list[list[float]] = []
        # 跳过空串但占位返回 []，方便上游对齐 index
        cleaned: list[tuple[int, str]] = [(i, t) for i, t in enumerate(texts) if t]
        out_map: dict[int, list[float]] = {}
        for batch_start in range(0, len(cleaned), self.batch_size):
            batch = cleaned[batch_start : batch_start + self.batch_size]
            inputs = [t for _, t in batch]
            vecs = self._call(inputs)
            for (idx, _), vec in zip(batch, vecs):
                out_map[idx] = vec
        for i in range(len(texts)):
            result.append(out_map.get(i, []))
        return result


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """根据 config 返回单例 Embedder。"""
    if not KG_EMBEDDING_API_KEY:
        logger.info("KG embedder: KG_EMBEDDING_API_KEY 未配置，向量通道关闭")
        return NullEmbedder()

    try:
        emb = OpenAICompatEmbedder(
            api_key=KG_EMBEDDING_API_KEY,
            base_url=KG_EMBEDDING_BASE_URL,
            model=KG_EMBEDDING_MODEL,
            dim=KG_EMBEDDING_DIM,
            batch_size=KG_EMBEDDING_BATCH,
            send_dimensions=KG_EMBEDDING_SEND_DIMENSIONS,
        )
        logger.info(
            "KG embedder: 已启用 OpenAI 兼容客户端 model=%s dim=%d",
            KG_EMBEDDING_MODEL,
            KG_EMBEDDING_DIM,
        )
        return emb
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("KG embedder: 初始化失败，回退为 NullEmbedder：%s", exc)
        return NullEmbedder()
