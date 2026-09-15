#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图像生成工具工厂（薄适配层）。

历史版本在此处直接读配置并构造 ``QwenImageGenTool``；现在配置读取、
后端选择、额度拦截与记账全部收敛到 :func:`services.image_factory.get_image_gen`
（与 LLM 的 ``get_llm`` 同构），本函数只负责把工厂产出的客户端
包装成 Agent 工具。

业务代码应直接调本函数或 ``services.image_factory.get_image_gen``，
不得绕过工厂自行构造图像生成后端客户端。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_image_gen_tool(user_id: str):
    """构建图像生成工具实例（内部走 services/image_factory）。

    Args:
        user_id: 当前用户 ID，用于读取个性化设置与额度归属。

    Returns:
        已挂治理 hook 的 :class:`agent_core.tool.image_gen.ImageGenTool`。
    """
    from agent_core.tool.image_gen import ImageGenTool
    from services.image_factory import get_image_gen

    client = get_image_gen(user_id, scene="media")
    # 工具名带后端标识（qwen_image_generate / openai_image_generate），
    # 兼容历史 prompt 中对工具名的引用
    return ImageGenTool(client, name=f"{client.backend}_image_generate")


__all__ = ["build_image_gen_tool"]
