"""TTS 组合实现：主后端单条失败时用备用后端重试该条。

与历史 ``qwen_tts.synthesize_batch`` 三级优先级（qwen3-tts →
macOS say → 不生成）的差异：旧实现是「整批全部失败才回退」，
本实现逐条回退；工厂分别包装各后端，供应商已生成的音频即使下载
失败仍记录成本，本地备用语音单独按零成本记录。
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import BaseTTS, TTSResult

logger = logging.getLogger(__name__)


class FallbackTTS(BaseTTS):
    """组合 TTS：``primary`` 失败的条目用 ``fallback`` 重试。"""

    def __init__(self, primary: BaseTTS, fallback: Optional[BaseTTS] = None):
        self._primary = primary
        self._fallback = fallback
        # 对外展示主后端
        self.backend = primary.backend

    def synthesize(
        self, text: str, output_path: str, voice: str = "", instruct: str = ""
    ) -> TTSResult:
        r = self._primary.synthesize(text, output_path, voice=voice, instruct=instruct)
        if r.success or self._fallback is None:
            return r
        logger.warning(
            "TTS %s 单条失败（%s），回退 %s",
            self._primary.backend,
            (r.error or "")[:80],
            self._fallback.backend,
        )
        r2 = self._fallback.synthesize(
            text, output_path, voice=voice, instruct=instruct
        )
        return r2
