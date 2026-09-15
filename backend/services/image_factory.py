"""图像生成客户端工厂：装配额度拦截 + 记账 hook（与 llm_factory 同构）。

调用方（Agent 工具、测试接口）一律通过 :func:`get_image_gen` 获取
客户端实例——用量治理的单一收口。

后端选择：``IMG_PROVIDER`` 环境变量（``qwen`` / ``openai``，默认
``qwen``，与历史 ``build_image_gen_tool`` 行为一致）。配置读取优先
用户设置（img_api_key / img_base_url / img_model），回退环境变量。
"""

from __future__ import annotations

import logging
import os

from agent_core.hooks import hookwrapper, observe
from agent_core.tool.imagegen.base import BaseImageGen
from agent_core.tool.imagegen.openai import OpenAIImageGen
from agent_core.tool.imagegen.qwen import QwenImageGen

logger = logging.getLogger(__name__)

# 与历史 agents/tools/image_gen_factory.py 的默认值保持一致
_DEFAULT_API_KEY = "any"
_DEFAULT_BASE_URL = "http://localhost:8080/v1"


def _read_config(user_id: str) -> dict:
    """读取图像生成配置：用户设置优先，回退环境变量与内置默认值。"""
    try:
        from database import get_setting

        return {
            "api_key": get_setting(user_id, "img_api_key")
            or os.getenv("IMG_API_KEY", _DEFAULT_API_KEY),
            "base_url": get_setting(user_id, "img_base_url")
            or os.getenv("IMG_BASE_URL", _DEFAULT_BASE_URL),
            "model": get_setting(user_id, "img_model")
            or os.getenv("IMG_MODEL")
            or None,
        }
    except Exception:  # pylint: disable=broad-except
        logger.warning("图像生成配置读取失败（使用默认值）", exc_info=True)
        return {
            "api_key": os.getenv("IMG_API_KEY", _DEFAULT_API_KEY),
            "base_url": os.getenv("IMG_BASE_URL", _DEFAULT_BASE_URL),
            "model": os.getenv("IMG_MODEL") or None,
        }


def _attach_hooks(
    client: BaseImageGen,
    *,
    user_id: str,
    scene: str,
    with_quota: bool,
) -> BaseImageGen:
    """在 ``client.generate`` 外层装配额度拦截与记账 hook。"""

    from services.credit_quota import is_using_platform_key
    from services.pricing import calc_unit_credits

    platform_key = is_using_platform_key(user_id, "image")
    model = getattr(client, "model", "") or ""
    region = "singapore" if "-intl." in getattr(client, "base_url", "") else "beijing"

    def _pre(*_args, **_kwargs):
        from services.credit_quota import assert_available

        calc_unit_credits(
            "image", 1, model=model, provider=client.backend, region=region
        )
        assert_available(user_id, "image", platform_key=platform_key)

    def _post(_result):
        from services.usage_meter import record_usage

        record_usage(
            user_id,
            category="image",
            scene=scene,
            units=1,
            model=model,
            provider=client.backend,
            region=region,
            counts_quota=platform_key,
        )

    pre = observe(_pre) if with_quota else None
    client.on_generated = lambda: _post(None)
    client.generate = hookwrapper(client.generate, pre=pre)  # type: ignore[method-assign]
    return client


def get_image_gen(
    user_id: str,
    *,
    with_quota: bool = True,
    scene: str = "media",
) -> BaseImageGen:
    """构造图像生成客户端并挂治理 hook。

    Args:
        user_id:    用户 ID，用于读配置与额度归属。
        with_quota: 是否启用事前拦截（默认 True）；系统级调用传 False。
        scene:      用量归因场景（见 usage_meter.VALID_SCENES）。
    """
    cfg = _read_config(user_id)
    provider = os.getenv("IMG_PROVIDER", "qwen").strip().lower()

    if provider == "openai":
        client: BaseImageGen = OpenAIImageGen(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
        )
    else:
        client = QwenImageGen(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"] or "qwen-image-2.0-pro",
        )
    return _attach_hooks(client, user_id=user_id, scene=scene, with_quota=with_quota)


__all__ = ["get_image_gen"]
