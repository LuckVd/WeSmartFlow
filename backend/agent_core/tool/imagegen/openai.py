"""OpenAI 兼容图像生成客户端（/v1/images/generations）。

逻辑迁移自 ``agent_core.tool.openai_image_gen.OpenAIImageGenTool``——
工具壳只保留参数 schema 与输出格式化，实际调用走本客户端。
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from .base import BaseImageGen, ImageGenError, save_image

try:
    import requests
except ImportError:  # pylint: disable=unused-import
    requests = None  # type: ignore[assignment]


class OpenAIImageGen(BaseImageGen):
    """调用兼容 OpenAI Images API 的图像生成服务生成图片。"""

    backend = "openai"
    default_size = "1920x1080"

    def __init__(
        self,
        api_key: str = "any",
        base_url: str = "http://localhost:8080/v1",
        model: Optional[str] = None,
        steps: Optional[int] = None,
        guidance_scale: Optional[float] = None,
    ):
        """
        Args:
            api_key:        API Key，服务不校验时传任意字符串即可。
            base_url:       服务根地址。
            model:          模型名称，为 None 时由服务端决定。
            steps:          推理步数（1~150），为 None 时由服务端决定。
            guidance_scale: CFG 引导系数，为 None 时由服务端决定。
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.steps = steps
        self.guidance_scale = guidance_scale

    def generate(
        self,
        prompt: str,
        output_dir: str,
        size: str = "",
        negative_prompt: Optional[str] = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> str:
        if requests is None:
            raise ImageGenError("未安装 requests 库，请先安装 requests>=2.31.0")

        size = size or self.default_size
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",
            "n": 1,
        }
        if self.model:
            payload["model"] = self.model
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if self.steps is not None:
            payload["steps"] = self.steps
        if self.guidance_scale is not None:
            payload["guidance_scale"] = self.guidance_scale

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"图片生成请求失败: {exc}") from exc

        if response.status_code != 200:
            try:
                detail = response.json().get("detail", response.text[:500])
            except Exception:  # pylint: disable=broad-except
                detail = response.text[:500]
            raise ImageGenError(
                f"图片生成接口返回异常: HTTP {response.status_code} / {detail}"
            )

        try:
            resp_json = response.json()
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"响应解析失败: {exc}") from exc

        data_list = resp_json.get("data") or []
        if not data_list:
            raise ImageGenError("图片生成接口未返回可用图像数据")

        callback = getattr(self, "on_generated", None)
        if callback:
            callback()

        item = data_list[0]
        b64_json = item.get("b64_json")
        url = item.get("url")

        # 优先使用 b64_json，否则下载 url
        if b64_json:
            try:
                image_bytes = base64.b64decode(b64_json)
            except Exception as exc:  # pylint: disable=broad-except
                raise ImageGenError(f"图片 base64 解码失败: {exc}") from exc
        elif url:
            try:
                img_resp = requests.get(url, timeout=timeout)
                img_resp.raise_for_status()
                image_bytes = img_resp.content
            except Exception as exc:  # pylint: disable=broad-except
                raise ImageGenError(f"下载生成图片失败: {exc}") from exc
        else:
            raise ImageGenError("响应中既无 b64_json 也无 url")

        try:
            return save_image(
                image_bytes,
                output_dir,
                {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "size": size,
                    "steps": self.steps,
                    "guidance_scale": self.guidance_scale,
                    "model": self.model,
                    "base_url": self.base_url,
                },
            )
        except ImageGenError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"图片落盘失败: {exc}") from exc
