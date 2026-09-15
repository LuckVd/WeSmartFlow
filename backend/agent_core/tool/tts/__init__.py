"""TTS 客户端抽象：与 BaseLLM 同构的基础调用层。

实现类只负责「一段文本 → 一个音频文件」的纯调用（框架层不认识业务）；
额度拦截与用量记账由业务层工厂通过 hookwrapper 挂在
:meth:`BaseTTS.synthesize` 外层（见 services/tts_factory.py）。
"""

from .base import BaseTTS, TTSResult
from .cosyvoice import CosyVoiceTTS
from .fallback import FallbackTTS
from .mac_say import MacSayTTS
from .qwen import QwenTTS

__all__ = [
    "BaseTTS",
    "CosyVoiceTTS",
    "FallbackTTS",
    "MacSayTTS",
    "QwenTTS",
    "TTSResult",
]
