"""TTS 客户端工厂：装配额度拦截 + 记账 hook（与 llm_factory 同构）。

调用方（沉浸式课程、知识卡片、court demo）一律通过 :func:`get_tts`
获取客户端实例——用量治理的单一收口。

后端选择（``backend`` 参数）：
  - ``"auto"``（默认）：用户自配 DashScope Key → 平台 OpenAI 兼容 TTS
    （TTS_*）→ 平台 DashScope qwen3-tts → macOS say → None，
    单条失败回退 macOS say（见 agent_core/tool/tts/fallback.py）；
  - ``"cosyvoice"``：court demo 专用音色通道。

计价：audio 按供应商计费字符数计量（见 services/pricing.py）。
供应商生成成功即记账，即使随后的下载或落盘失败；本地 say 成本为零。
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from agent_core.hooks import hookwrapper, observe
from agent_core.tool.tts.base import BaseTTS
from agent_core.tool.tts.cosyvoice import CosyVoiceTTS
from agent_core.tool.tts.fallback import FallbackTTS
from agent_core.tool.tts.mac_say import MacSayTTS
from agent_core.tool.tts.openai_compat import OpenAICompatTTS
from agent_core.tool.tts.qwen import QwenTTS
from services.provider_gateway import get_provider_gateway

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _dotenv_value(name: str) -> str:
    """从项目根 .env 直接读取变量（环境变量未设置时的兜底）。"""
    try:
        from dotenv import dotenv_values

        val = (dotenv_values(_PROJECT_ROOT / ".env") or {}).get(name)
        return (val or "").strip()
    except Exception:  # pylint: disable=broad-except
        return ""


def _dashscope_key(user_id: str) -> str:
    """读取 DashScope API Key。

    优先级：用户设置 tts_api_key → 环境变量 DASHSCOPE_API_KEY →
    .env DASHSCOPE_API_KEY → .env IMG_API_KEY（court 历史配置兼容，
    该项目的 DashScope 系 key 一度统一写在 IMG_API_KEY）。
    """
    try:
        from database import get_setting

        key = (get_setting(user_id, "tts_api_key") or "").strip()
        if key:
            return key
    except Exception:  # pylint: disable=broad-except
        pass
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if key:
        return key
    key = _dotenv_value("DASHSCOPE_API_KEY")
    if key:
        return key
    return _dotenv_value("IMG_API_KEY")


def _user_tts_key(user_id: str) -> str:
    try:
        from database import get_setting

        return (get_setting(user_id, "tts_api_key") or "").strip()
    except Exception:  # pylint: disable=broad-except
        return ""


def _openai_compat_settings() -> Optional[dict]:
    """读取平台 OpenAI 兼容 TTS 配置（TTS_API_KEY / TTS_BASE_URL / TTS_MODEL）。

    三项全部留空表示未启用；只配了一部分时报错，避免静默回退到其他供应商。
    """
    names = ("TTS_API_KEY", "TTS_BASE_URL", "TTS_MODEL")
    values = [os.environ.get(n, "").strip() or _dotenv_value(n) for n in names]
    if not any(values):
        return None
    if not all(values):
        raise RuntimeError(
            "TTS 配置不完整。请同时设置 TTS_API_KEY, TTS_BASE_URL 和 TTS_MODEL。"
        )
    speed_raw = os.environ.get("TTS_SPEED", "").strip() or _dotenv_value("TTS_SPEED")
    try:
        speed = float(speed_raw) if speed_raw else None
    except ValueError:
        speed = None
    return {
        "api_key": values[0],
        "base_url": values[1],
        "model": values[2],
        "voice": os.environ.get("TTS_VOICE", "").strip() or _dotenv_value("TTS_VOICE"),
        "speed": speed,
    }


def _attach_hooks(
    client: BaseTTS,
    *,
    user_id: str,
    scene: str,
    with_quota: bool,
    is_system: bool = False,
) -> BaseTTS:
    """在 ``client.synthesize`` 外层装配额度拦截与记账 hook。

    只包装单条 ``synthesize``；``synthesize_batch`` 的基类默认实现
    循环调用 ``self.synthesize``，批量场景自然逐条触发 hook。
    """

    from services.credit_quota import is_using_platform_key
    from services.pricing import calc_unit_credits

    platform_key = is_using_platform_key(user_id, "audio")

    # Speech generation can be accepted and billed upstream before the response
    # body reaches us, so its provider definitions intentionally disable generic
    # retries.  We still get one traceable event for each primary/fallback call.
    gateway = get_provider_gateway()
    profile = gateway.resolve(
        category="audio",
        backend=client.backend,
        model=getattr(client, "model", ""),
    )
    client.synthesize = gateway.instrument_sync(  # type: ignore[method-assign]
        profile,
        "speech.synthesize",
        client.synthesize,
        scene=scene,
        success=lambda result: bool(getattr(result, "success", False)),
    )
    client.provider_profile = profile  # type: ignore[attr-defined]

    def _pre(*_args, **_kwargs):
        from services.credit_quota import assert_available

        if client.backend == "macos-say":
            return
        calc_unit_credits(
            "audio", 1, model=getattr(client, "model", ""), provider=client.backend
        )
        assert_available(user_id, "audio", platform_key=platform_key)

    def _post(result):
        from services.usage_meter import record_usage

        # 失败条目不记账（BaseTTS 契约：失败不抛异常，靠 success 判定）
        if not getattr(result, "success", False):
            return
        units = result.billed_characters or len(result.text or "")
        record_usage(
            user_id,
            category="audio",
            scene=scene,
            units=units,
            model=result.model or getattr(client, "model", ""),
            provider=result.backend,
            counts_quota=platform_key and result.backend != "macos-say",
            is_system=is_system,
        )

    pre = observe(_pre) if with_quota else None
    if isinstance(client, (QwenTTS, CosyVoiceTTS, OpenAICompatTTS)):
        client.on_generated = _post
        post = None
    else:
        post = observe(_post)
    client.synthesize = hookwrapper(client.synthesize, pre=pre, post=post)  # type: ignore[method-assign]
    return client


def get_tts(
    user_id: str,
    *,
    backend: str = "auto",
    with_quota: bool = True,
    scene: str = "media",
    is_system: bool = False,
) -> Optional[BaseTTS]:
    """构造 TTS 客户端并挂治理 hook。

    Args:
        user_id:    用户 ID，用于读配置与额度归属。
        backend:    ``"auto"``（三级优先级）或 ``"cosyvoice"``。
        with_quota: 是否启用事前拦截（默认 True）；系统级调用传 False。
        scene:      用量归因场景（immersive / court / media ...）。
        is_system:  系统任务记账标记（仍记账但不计入用户额度汇总）。

    Returns:
        客户端实例；无任何可用后端（无 key 且非 macOS）时返回 None，
        调用方应跳过语音生成。
    """
    key = _dashscope_key(user_id)
    say_available = shutil.which("say") is not None

    def _with_say_fallback(primary: BaseTTS) -> BaseTTS:
        fallback = (
            _attach_hooks(
                MacSayTTS(),
                user_id=user_id,
                scene=scene,
                with_quota=False,
                is_system=is_system,
            )
            if say_available
            else None
        )
        return FallbackTTS(primary, fallback)

    compat = None
    if backend != "cosyvoice" and not _user_tts_key(user_id):
        try:
            compat = _openai_compat_settings()
        except RuntimeError:
            # 配置错误不静默切换到其他供应商；跳过语音并留下明确日志
            logger.error("TTS_* 配置不完整，已跳过语音生成", exc_info=True)
            return None

    if backend == "cosyvoice":
        if not key:
            return None
        client: BaseTTS = CosyVoiceTTS(api_key=key)
    elif compat:
        # 平台 OpenAI 兼容 TTS；用户自配的 DashScope Key 仍优先走 qwen
        compat_profile = get_provider_gateway().resolve(
            category="audio",
            backend="openai-compatible",
            model=compat["model"],
            endpoint=compat["base_url"],
        )
        primary = _attach_hooks(
            OpenAICompatTTS(
                **compat, timeout=int(compat_profile.retry.timeout_seconds)
            ),
            user_id=user_id,
            scene=scene,
            with_quota=with_quota,
            is_system=is_system,
        )
        return _with_say_fallback(primary)
    elif key:
        qwen_profile = get_provider_gateway().resolve(
            category="audio", backend="qwen3-tts", model="qwen3-tts-instruct-flash"
        )
        primary = _attach_hooks(
            QwenTTS(api_key=key, timeout=int(qwen_profile.retry.timeout_seconds)),
            user_id=user_id,
            scene=scene,
            with_quota=with_quota,
            is_system=is_system,
        )
        return _with_say_fallback(primary)
    elif say_available:
        client = MacSayTTS()
    else:
        return None

    return _attach_hooks(
        client,
        user_id=user_id,
        scene=scene,
        with_quota=with_quota,
        is_system=is_system,
    )


__all__ = ["get_tts"]
