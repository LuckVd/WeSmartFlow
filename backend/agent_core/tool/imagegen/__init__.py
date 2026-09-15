"""图像生成客户端抽象：与 BaseLLM 同构的基础调用层。

实现类只负责「一次文生图」的纯调用（框架层不认识业务）；
额度拦截与用量记账由业务层工厂通过 hookwrapper 挂在
:meth:`BaseImageGen.generate` 外层（见 services/image_factory.py）。
"""

from .base import BaseImageGen, ImageGenError, save_image
from .openai import OpenAIImageGen
from .qwen import QwenImageGen

__all__ = [
    "BaseImageGen",
    "ImageGenError",
    "OpenAIImageGen",
    "QwenImageGen",
    "save_image",
]
