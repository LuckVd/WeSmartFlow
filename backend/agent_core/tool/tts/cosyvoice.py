"""CosyVoice 语音合成客户端（dashscope cosyvoice-v1 / v2）。

逻辑迁移自 ``court/tts.py`` 的合成部分——角色音色映射、情感指令、
内存缓存属 court 业务，仍留在 court 层；本客户端只负责纯调用。

v2 支持 instruction 情感参数（默认 v1）。输出为 mp3 字节流，
落盘到 ``output_path``。
"""

from __future__ import annotations

import os
from threading import Lock
from pathlib import Path

from .base import BaseTTS, TTSResult


_SDK_KEY_LOCK = Lock()


class CosyVoiceTTS(BaseTTS):
    """CosyVoice 客户端，输出 mp3。"""

    backend = "cosyvoice"

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model or os.environ.get("TTS_MODEL", "cosyvoice-v1")

    def synthesize(
        self, text: str, output_path: str, voice: str = "", instruct: str = ""
    ) -> TTSResult:
        text = (text or "").strip()
        if not text:
            return TTSResult(text=text, backend=self.backend, error="文本为空")

        if not self.api_key:
            return TTSResult(text=text, backend=self.backend, error="no api key")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # dashscope SDK 在实例初始化时读取全局 key
            from dashscope.audio.tts_v2 import SpeechSynthesizer

            kwargs = {
                "model": self.model,
                "voice": voice or "longyue",
                "headers": {"Authorization": f"Bearer {self.api_key}"},
            }
            if self.model.startswith("cosyvoice-v2") and instruct:
                kwargs["instruction"] = instruct
            # SDK snapshots its global key in __init__; restore immediately.
            import dashscope

            with _SDK_KEY_LOCK:
                previous_key = dashscope.api_key
                try:
                    dashscope.api_key = self.api_key
                    synth = SpeechSynthesizer(**kwargs)
                finally:
                    dashscope.api_key = previous_key
            audio = synth.call(text)
            if not audio:
                return TTSResult(text=text, backend=self.backend, error="empty audio")
            usage = ((synth.last_response or {}).get("payload") or {}).get(
                "usage"
            ) or {}
            billed_characters = usage.get("characters", len(text))
            callback = getattr(self, "on_generated", None)
            if callback:
                callback(
                    TTSResult(
                        text=text,
                        backend=self.backend,
                        model=self.model,
                        success=True,
                        billed_characters=billed_characters,
                    )
                )
            out_path.write_bytes(audio)
            return TTSResult(
                text=text,
                path=str(out_path),
                backend=self.backend,
                success=True,
                model=self.model,
                billed_characters=billed_characters,
            )
        except Exception as e:  # pylint: disable=broad-except
            return TTSResult(text=text, backend=self.backend, error=str(e)[:120])
