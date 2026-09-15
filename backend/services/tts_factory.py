"""TTS 客户端工厂：装配额度拦截 + 记账 hook（与 llm_factory 同构）。

调用方（沉浸式课程、知识卡片、court demo）一律通过 :func:`get_tts`
获取客户端实例——用量治理的单一收口。

后端选择（``backend`` 参数）：
  - ``"auto"``（默认）：qwen3-tts → macOS say → None（三级优先级），
    单条失败自动回退（见 agent_core/tool/tts/fallback.py）；
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
from agent_core.tool.tts.qwen import QwenTTS

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
    if isinstance(client, (QwenTTS, CosyVoiceTTS)):
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

    if backend == "cosyvoice":
        if not key:
            return None
        client: BaseTTS = CosyVoiceTTS(api_key=key)
    elif key:
        primary = _attach_hooks(
            QwenTTS(api_key=key),
            user_id=user_id,
            scene=scene,
            with_quota=with_quota,
            is_system=is_system,
        )
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
