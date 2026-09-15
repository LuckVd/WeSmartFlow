#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图像生成工具：BaseImageGen 客户端的 Agent 工具壳。

替代历史的 QwenImageGenTool / OpenAIImageGenTool——后端调用逻辑已
迁至 :mod:`agent_core.tool.imagegen`，本类只负责参数 schema 与输出格式化。
治理 hook（额度拦截 + 记账）挂在工厂注入的 client 上
（见 services/image_factory.py），注册到 ToolRegistry 时**无需**再绑
before_call。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agent_core.tool.imagegen.base import BaseImageGen, ImageGenError

from .base import BaseTool

logger = logging.getLogger(__name__)


class ImageGenTool(BaseTool):
    """调用图像生成服务（工厂注入的 client）生成图片并落盘到指定目录。"""

    name = "image_generate"
    description = (
        "调用图像生成服务，根据文本提示词生成高质量图片并保存到指定目录。"
        "支持指定图像尺寸、负向提示词等参数。"
        "调用成功后返回图片的本地绝对路径。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图像描述提示词，支持中英文，详细描述画面内容。",
            },
            "output_dir": {
                "type": "string",
                "description": "图片输出目录路径，图片将保存到该目录下。",
            },
            "size": {
                "type": "string",
                "description": (
                    "图像尺寸。qwen 后端格式 W*H（如 1024*1024、1280*720），"
                    "openai 后端格式 WxH（如 1920x1080）。默认由后端决定。"
                ),
            },
            "negative_prompt": {
                "type": "string",
                "description": (
                    "负向提示词，描述不希望出现的内容，"
                    "如：低分辨率，低画质，肢体畸形，手指畸形。"
                ),
            },
            "prompt_extend": {
                "type": "boolean",
                "description": "是否开启提示词自动扩写（qwen 后端），默认 true。",
            },
            "watermark": {
                "type": "boolean",
                "description": "是否在图片上添加水印（qwen 后端），默认 false。",
            },
            "timeout": {
                "type": "integer",
                "description": "请求超时时间（秒），默认 300。",
            },
        },
        "required": ["prompt", "output_dir"],
    }

    def __init__(self, client: BaseImageGen, name: Optional[str] = None):
        """
        Args:
            client: 工厂产出的客户端实例（已带治理 hook）。
            name:   工具名，默认 ``image_generate``；为兼容历史 prompt
                    可传 ``qwen_image_generate`` 等。
        """
        self._client = client
        if name:
            self.name = name
        super().__init__()

    def run(
        self,
        prompt: str = "",
        output_dir: str = "",
        size: str = "",
        negative_prompt: Optional[str] = None,
        prompt_extend: bool = True,
        watermark: bool = False,
        timeout: int = 300,
        **kwargs: Any,
    ) -> str:
        """执行图片生成。顶层 try-except 确保任何异常都不向上冒泡。"""
        try:
            path = self._client.generate(
                prompt=prompt,
                output_dir=output_dir,
                size=size,
                negative_prompt=negative_prompt,
                timeout=timeout,
                prompt_extend=prompt_extend,
                watermark=watermark,
            )
            return f"图片生成成功，路径：{path}"
        except ImageGenError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("图片生成未预期异常（已安全跳过）: %s", exc, exc_info=True)
            return f"Error: 图片生成遇到未预期错误，已跳过（不影响后续流程）: {exc}"


__all__ = ["ImageGenTool"]
