"""通义千问图像生成客户端（DashScope multimodal-generation API）。

逻辑迁移自 ``agent_core.tool.qwen_image_gen.QwenImageGenTool``——
工具壳只保留参数 schema 与输出格式化，实际调用走本客户端。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BaseImageGen, ImageGenError, save_image

try:
    import requests
except ImportError:  # pylint: disable=unused-import
    requests = None  # type: ignore[assignment]


class QwenImageGen(BaseImageGen):
    """调用阿里云 DashScope qwen-image 系列接口生成图片。"""

    backend = "qwen"
    default_size = "1024*1024"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        model: str = "qwen-image-2.0-pro",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(
        self,
        prompt: str,
        output_dir: str,
        size: str = "",
        negative_prompt: Optional[str] = None,
        timeout: int = 300,
        prompt_extend: bool = True,
        watermark: bool = False,
        **kwargs: Any,
    ) -> str:
        if requests is None:
            raise ImageGenError("未安装 requests 库，请先安装 requests>=2.31.0")
        if not self.api_key:
            raise ImageGenError("未提供 DashScope API Key，请在构造时传入 api_key。")

        size = size or self.default_size
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
            "parameters": {
                "size": size,
                "prompt_extend": prompt_extend,
                "watermark": watermark,
            },
        }
        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                self.base_url, json=payload, headers=headers, timeout=timeout
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"图片生成请求失败: {exc}") from exc

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:  # pylint: disable=broad-except
                detail = response.text[:500]
            raise ImageGenError(
                f"图片生成接口返回异常: HTTP {response.status_code} / {detail}"
            )

        try:
            resp_json = response.json()
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"响应解析失败: {exc}") from exc

        # DashScope 响应结构：output.choices[0].message.content[0].image
        try:
            content = resp_json["output"]["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ImageGenError(f"响应结构不符合预期: {str(resp_json)[:300]}") from exc

        image_url: Optional[str] = None
        for item in content:
            if isinstance(item, dict):
                image_url = item.get("image")
                if image_url:
                    break
        if not image_url:
            raise ImageGenError(f"响应中未找到图片 URL: {str(resp_json)[:300]}")

        callback = getattr(self, "on_generated", None)
        if callback:
            callback()

        try:
            img_resp = requests.get(image_url, timeout=timeout)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"下载生成图片失败: {exc}") from exc

        try:
            return save_image(
                image_bytes,
                output_dir,
                {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "size": size,
                    "prompt_extend": prompt_extend,
                    "watermark": watermark,
                    "model": self.model,
                    "base_url": self.base_url,
                },
            )
        except ImageGenError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise ImageGenError(f"图片落盘失败: {exc}") from exc
