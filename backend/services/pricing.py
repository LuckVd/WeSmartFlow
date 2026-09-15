"""
credits 计价：把 token 用量与第三方调用折算成统一的虚拟货币。

为什么需要 credits
------------------
按「调用次数」计费时，一次 200 token 与一次 200k token 记为同一次，
成本失真可达三个数量级；推理模型的思考 token 更是完全不可见
（实测单次出题曾产生 11175 个 thinking token，计数只 +1）。

credits 口径
------------
**1 credit = 1 元 / 1,000,000**，即 100 万 credits = 1 元人民币。

选这个锚点是为了可解释：credits 数值与「百万 token 单价」同量级，
运营看板上换算成钱只需除以 100 万，也便于对用户展示。

计价要点
--------
1. 输入/输出分别计价——输出通常是输入的 2~4 倍单价
2. 命中提示缓存的 token 单独计价，单价常低一个数量级，
   不区分会显著高估成本
3. 思考 token 已包含在 completion_tokens 内，无需重复计算，
   但会单独记录用于评估 reasoning_effort 的优化收益
4. 日期后缀按已知型号匹配，未知模型用明确的估算默认价，
   此结果为估算，不能作为供应商账单
"""

from __future__ import annotations

import logging
import math
import os
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# credits 与人民币的换算：1 元 = 1_000_000 credits
CREDITS_PER_YUAN = 1_000_000

# ── 模型定价（元 / 百万 token）────────────────────────────────
# in         输入（缓存未命中）
# in_cached  输入（命中提示缓存）
# out        输出
#
# 数值按各家公开价目表填写；调价时只需改这里。
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "text-embedding-v4": {"in": 0.5, "in_cached": 0.5, "out": 0},
    # DeepSeek
    "deepseek-chat": {"in": 2.0, "in_cached": 0.2, "out": 8.0},
    "deepseek-reasoner": {"in": 4.0, "in_cached": 0.4, "out": 16.0},
    "deepseek-v4-flash": {"in": 3.0, "in_cached": 0.1, "out": 9.0},
    "deepseek-v4-pro": {"in": 9.0, "in_cached": 0.3, "out": 27.0},
    # OpenAI
    "gpt-4o": {"in": 18.0, "in_cached": 9.0, "out": 72.0},
    "gpt-4o-mini": {"in": 1.1, "in_cached": 0.55, "out": 4.3},
    "o1-preview": {"in": 108.0, "in_cached": 54.0, "out": 432.0},
    "o3-mini": {"in": 8.0, "in_cached": 4.0, "out": 32.0},
    # 通义千问
    "qwen-plus": {"in": 0.8, "in_cached": 0.2, "out": 2.0},
    "qwen-max": {"in": 2.4, "in_cached": 0.6, "out": 9.6},
    "qwen-turbo": {"in": 0.3, "in_cached": 0.1, "out": 0.6},
}

# 未知模型的保守默认价：取中档偏高，宁可高估也不漏记
DEFAULT_PRICING: Dict[str, float] = {"in": 4.0, "in_cached": 1.0, "out": 16.0}

# 原价快照：2026-09-06；美元采用可配置的记账汇率，不声称是实时汇率。
# https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
# https://help.aliyun.com/zh/model-studio/model-pricing
# https://docs.tavily.com/documentation/api-credits
PRICING_VERSION = "2026-09-06"
USD_CNY = float(os.getenv("PRICING_USD_CNY", "7.2"))
OPENAI_USD = {
    "gpt-4o": (2.5, 1.25, 10),
    "gpt-4o-mini": (0.15, 0.075, 0.6),
    "o1-preview": (15, 7.5, 60),
    "o3-mini": (1.1, 0.55, 4.4),
}
IMAGE_CNY = {
    "qwen-image-2.0-pro": 0.5,
    "qwen-image-2.0": 0.2,
    "qwen-image-max": 0.5,
    "qwen-image-plus": 0.2,
    "qwen-image": 0.25,
}
AUDIO_CNY_PER_CHAR = {
    "qwen3-tts-instruct-flash": 0.00008,
    "qwen3-tts-flash": 0.00008,
    "cosyvoice-v1": 0.0002,
    "cosyvoice-v2": 0.0002,
    "cosyvoice-v3-plus": 0.0002,
    "cosyvoice-v3-flash": 0.0001,
    "tts-1-hd": Decimal("30") * Decimal(str(USD_CNY)) / 1_000_000,
    "tts-1": Decimal("15") * Decimal(str(USD_CNY)) / 1_000_000,
}


def _override(key: str):
    """部署可按实际供应商合同覆盖：LLM 为三项单价，其他为元/单位。"""
    return json.loads(os.getenv("PRICING_OVERRIDES_JSON", "{}")).get(key)


def _match(name: str, table: dict):
    for prefix in sorted(table, key=len, reverse=True):
        if name == prefix or name.startswith(prefix + "-"):
            return table[prefix]
    return None


def resolve_pricing(
    model: str, *, at: Optional[datetime] = None, usage=None
) -> Dict[str, float]:
    name = (model or "").strip().lower()
    custom = _override("llm:" + name)
    if custom is not None:
        return custom
    if name.startswith(("deepseek-v4-flash", "deepseek-v4-pro")):
        base = MODEL_PRICING[
            "deepseek-v4-flash"
            if name.startswith("deepseek-v4-flash")
            else "deepseek-v4-pro"
        ]
        dt = (at or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Shanghai"))
        peak = dt.weekday() < 5 and (9 <= dt.hour < 12 or 14 <= dt.hour < 18)
        return {key: value * (1 if peak else 0.5) for key, value in base.items()}
    if name == "qwen-plus" or name.startswith("qwen-plus-"):
        u = normalize_usage(usage)
        thinking = (
            bool((usage or {}).get("thinking_enabled")) or u["reasoning_tokens"] > 0
        )
        tier = (
            0
            if u["prompt_tokens"] <= 128000
            else 1
            if u["prompt_tokens"] <= 256000
            else 2
        )
        # Older snapshots predate tiered pricing.
        if name in {
            "qwen-plus-2025-07-14",
            "qwen-plus-2025-04-28",
            "qwen-plus-2025-01-25",
            "qwen-plus-2025-01-12",
            "qwen-plus-2024-12-20",
        }:
            tier = 0
        inp = (0.8, 2.4, 4.8)[tier]
        return {
            "in": inp,
            "in_cached": inp,
            "out": ((8, 24, 64) if thinking else (2, 20, 48))[tier],
        }
    usd = _match(name, OPENAI_USD)
    if usd is not None:
        return dict(
            zip(
                ("in", "in_cached", "out"),
                (Decimal(str(v)) * Decimal(str(USD_CNY)) for v in usd),
            )
        )
    price = _match(name, MODEL_PRICING)
    if price is not None:
        return price
    logger.warning("未知模型 %r 使用估算价；请配置 PRICING_OVERRIDES_JSON", model)
    return DEFAULT_PRICING


def normalize_usage(usage: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """把各家风格不一的 usage 字段归一化为统一结构。

    兼容的字段别名：
      - 缓存命中：prompt_cache_hit_tokens（DeepSeek）、
        cached_tokens / prompt_tokens_details.cached_tokens（OpenAI）
      - 思考 token：reasoning_tokens、
        completion_tokens_details.reasoning_tokens

    Returns:
        ``{"prompt_tokens", "completion_tokens", "reasoning_tokens",
        "cached_tokens"}``，缺失或非法值一律归零。
    """

    def _int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    u = usage or {}
    prompt = _int(u.get("prompt_tokens", u.get("input_tokens")))
    completion = _int(u.get("completion_tokens", u.get("output_tokens")))

    cached = _int(u.get("prompt_cache_hit_tokens")) or _int(u.get("cached_tokens"))
    if not cached:
        details = u.get("prompt_tokens_details") or {}
        if isinstance(details, dict):
            cached = _int(details.get("cached_tokens"))

    reasoning = _int(u.get("reasoning_tokens"))
    if not reasoning:
        details = u.get("completion_tokens_details") or {}
        if isinstance(details, dict):
            reasoning = _int(details.get("reasoning_tokens"))

    # 缓存命中量不可能超过总输入量（防脏数据把计费算负）
    cached = min(cached, prompt)
    # 思考 token 已包含在 completion 内
    reasoning = min(reasoning, completion)

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "cached_tokens": cached,
    }


def calc_llm_credits(
    model: str, usage: Optional[Dict[str, Any]], *, at: Optional[datetime] = None
) -> int:
    """按模型定价把 token 用量折算成 credits。

    思考 token 不额外计费——它已计入 completion_tokens。

    Returns:
        向上取整的 credits；无 token 时返回 0。
    """
    u = normalize_usage(usage)
    fresh_in = u["prompt_tokens"] - u["cached_tokens"]
    if fresh_in <= 0 and u["cached_tokens"] <= 0 and u["completion_tokens"] <= 0:
        return 0

    p = resolve_pricing(model, at=at, usage=usage)
    # 单价单位是「元/百万 token」，而 1 元 = 1e6 credits，
    # 故 credits = tokens × 单价，无需再做量级换算。
    total = sum(
        Decimal(tokens) * Decimal(str(p[key]))
        for tokens, key in (
            (max(0, fresh_in), "in"),
            (u["cached_tokens"], "in_cached"),
            (u["completion_tokens"], "out"),
        )
    )
    if not total.is_finite() or total < 0:
        raise ValueError("无效的模型单价")
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def calc_unit_credits(
    category: str,
    units: float = 1,
    *,
    model: str = "",
    provider: str = "",
    region: str = "beijing",
) -> int:
    """按张/计费字符/API credit 计价；零单位为零，本地语音为零。"""
    count = max(0, float(units))
    if not count or provider in {"macos-say", "browser"}:
        return 0
    name = (model or "").lower()
    price = _override(f"{category}:{name or provider}")
    if price is None and category == "image":
        price = _match(name, IMAGE_CNY)
        if price is not None and region == "singapore":
            price = (
                0.03
                if name.startswith("qwen-image-plus")
                else 0.075
                if price == 0.5
                else 0.035
            ) * USD_CNY
    elif price is None and category == "audio":
        price = _match(name, AUDIO_CNY_PER_CHAR)
    elif price is None and category == "search" and provider == "tavily":
        price = Decimal(os.getenv("TAVILY_USD_PER_CREDIT", "0.008")) * Decimal(
            str(USD_CNY)
        )
    if price is None and category == "search" and provider == "anysearch":
        price = 0.0  # 官方 Free 计划；商业合同必须配置 override。
    if price is None:
        raise ValueError(
            f"未配置 {category}/{name or provider} 单价，请设置 PRICING_OVERRIDES_JSON"
        )
    if not math.isfinite(float(price)) or float(price) < 0:
        raise ValueError("单价不能为负数")
    return int(
        (
            Decimal(str(price)) * Decimal(str(count)) * CREDITS_PER_YUAN
        ).to_integral_value(rounding=ROUND_CEILING)
    )


def credits_to_yuan(credits: int) -> float:
    """credits 换算成人民币元，供看板展示。"""
    return round((credits or 0) / CREDITS_PER_YUAN, 6)


def ensure_usage(usage, messages, content="", tool_calls=None):
    """Retain provider usage; mark a conservative estimate when usage is absent.

    This is not a supplier invoice: hidden reasoning cannot be reconstructed.
    """
    u = dict(usage or {})
    if any(k in u for k in ("prompt_tokens", "input_tokens")) and any(
        k in u for k in ("completion_tokens", "output_tokens")
    ):
        return u
    from agent_core.memory.base import estimate_tokens

    prompt = estimate_tokens(messages)
    completion = estimate_tokens(
        [{"role": "assistant", "content": str(content or "") + str(tool_calls or "")}]
    )
    total = int(u.get("total_tokens", 0) or 0)
    if total > 0:
        completion = max(completion, total - prompt)
    logger.warning("Provider omitted token breakdown; recording estimated usage")
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "estimated": True,
    }
