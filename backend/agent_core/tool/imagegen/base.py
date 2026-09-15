"""图像生成客户端抽象基类。

与 ``agent_core.llm.base.BaseLLM`` 同构：实现类（qwen / openai 兼容 …）
各自封装后端 API，治理逻辑（额度拦截、记账）由
``services/image_factory`` 挂在实例方法外层，不写在这里。

契约：成功返回图片绝对路径（str），失败抛 :class:`ImageGenError`
。实现类可通过 on_generated 回调报告供应商生成成功，下载/落盘
失败仍可能有供应商成本；工厂负责装配该回调。
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional


class ImageGenError(Exception):
    """图像生成失败（未配置 Key、接口异常、落盘失败等）。"""


def save_image(image_bytes: bytes, output_dir: str, meta: Dict[str, Any]) -> str:
    """把生成图片落盘到指定目录，返回绝对路径。

    文件名由内容 SHA256 前 16 位决定（幂等、防重复）；同一目录下
    相同内容不会重复写盘。同时写 ``<hash>.meta.json`` 记录生成参数，
    便于事后审计与归因。
    """
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
    image_path = out_dir / f"{image_hash}.png"

    if not image_path.exists():
        image_path.write_bytes(image_bytes)
        meta_path = image_path.with_suffix(".meta.json")
        meta_path.write_text(
            json.dumps(
                {
                    "image_hash": image_hash,
                    "image_path": str(image_path),
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                    **meta,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return str(image_path)


class BaseImageGen(ABC):
    """图像生成客户端抽象基类。"""

    #: 后端标识（qwen / openai ...），用于日志与计价归因
    backend: str = "imagegen"
    #: 该后端的默认尺寸（格式随后端而异：qwen 为 W*H，openai 为 WxH）
    default_size: str = "1024*1024"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_dir: str,
        size: str = "",
        negative_prompt: Optional[str] = None,
        timeout: int = 300,
        **kwargs: Any,
    ) -> str:
        """生成一张图片并落盘。

        Args:
            prompt:          图像描述提示词。
            output_dir:      输出目录（不存在会自动创建）。
            size:            图像尺寸，为空用 ``default_size``。
            negative_prompt: 负向提示词（后端支持时生效）。
            timeout:         请求超时（秒）。
            **kwargs:        后端特有参数（prompt_extend / watermark 等），
                             不识别的后端应忽略。

        Returns:
            图片绝对路径。

        Raises:
            ImageGenError: 任何失败。
        """
