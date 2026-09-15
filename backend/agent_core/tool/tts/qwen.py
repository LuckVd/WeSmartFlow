"""DashScope qwen3-tts-instruct-flash 语音合成（纯 HTTP，零额外依赖）。

逻辑迁移自 ``agent_core.tool.qwen_tts``。
"""

from __future__ import annotations

import json
import time
import urllib.request
import wave
from pathlib import Path

from .base import BaseTTS, TTSResult

QWEN_TTS_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/"
    "multimodal-generation/generation"
)
QWEN_TTS_MODEL = "qwen3-tts-instruct-flash"

DEFAULT_VOICE = "Cherry"
DEFAULT_INSTRUCT = "亲切自然、循循善诱的教师讲解，语速适中，清晰沉稳"


class QwenTTS(BaseTTS):
    """qwen3-tts-instruct-flash 客户端，适合单人讲解旁白。"""

    backend = "qwen3-tts"
    model = QWEN_TTS_MODEL

    def __init__(self, api_key: str, timeout: int = 90):
        self.api_key = api_key
        self.timeout = timeout

    def synthesize(
        self, text: str, output_path: str, voice: str = "", instruct: str = ""
    ) -> TTSResult:
        text = (text or "").strip()
        if not text:
            return TTSResult(text=text, backend=self.backend, error="文本为空")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            return TTSResult(
                text=text, backend=self.backend, error="DASHSCOPE_API_KEY 未配置"
            )

        payload = json.dumps(
            {
                "model": QWEN_TTS_MODEL,
                "input": {
                    "text": text,
                    "voice": voice or DEFAULT_VOICE,
                    "instructions": instruct or DEFAULT_INSTRUCT,
                },
                "parameters": {"optimize_instructions": True},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            QWEN_TTS_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            url = (data.get("output") or {}).get("audio", {}).get("url")
            if not url:
                raise RuntimeError(
                    f"dashscope 无音频返回: {json.dumps(data, ensure_ascii=False)[:300]}"
                )
            callback = getattr(self, "on_generated", None)
            if callback:
                callback(
                    TTSResult(
                        text=text,
                        backend=self.backend,
                        model=self.model,
                        success=True,
                        billed_characters=(data.get("usage") or {}).get(
                            "characters", len(text)
                        ),
                    )
                )
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                audio = r.read()
            out_path.write_bytes(audio)

            duration = 0.0
            try:
                with wave.open(str(out_path), "rb") as wf:
                    duration = wf.getnframes() / wf.getframerate()
            except Exception:  # pylint: disable=broad-except
                pass
            _ = time.time() - t0  # elapsed 仅作日志用途
            return TTSResult(
                text=text,
                path=str(out_path),
                duration=round(duration, 2),
                backend=self.backend,
                success=True,
                model=self.model,
                billed_characters=(data.get("usage") or {}).get(
                    "characters", len(text)
                ),
            )
        except Exception as e:  # pylint: disable=broad-except
            return TTSResult(text=text, backend=self.backend, error=str(e)[:200])
