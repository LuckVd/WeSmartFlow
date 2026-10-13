"""OpenAI 兼容语音合成（``POST {base_url}/audio/speech``，纯 HTTP，零额外依赖）。

适用于任何实现了 OpenAI ``/audio/speech`` 协议的服务（官方或自建中转）。
固定请求 wav 输出，与批量讲解流程的 ``.wav`` 落盘约定一致。

计费字符数优先读取响应头 ``X-Billed-Characters``（供应商按自身口径计算，
例如汉字按 2 字符计），缺失时回退为文本长度。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import wave
from pathlib import Path

from .base import BaseTTS, TTSResult

BILLED_CHARACTERS_HEADER = "X-Billed-Characters"


def _billed_characters(headers, text: str) -> int:
    raw = headers.get(BILLED_CHARACTERS_HEADER) if headers is not None else None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return len(text)
    return value if value > 0 else len(text)


def _error_message(exc: urllib.error.HTTPError) -> str:
    """只提取 OpenAI 风格错误的 message，避免把整段响应写进结果。"""
    try:
        body = json.loads(exc.read().decode("utf-8", "replace"))
        message = (body.get("error") or {}).get("message") or ""
    except Exception:  # pylint: disable=broad-except
        message = ""
    return f"HTTP {exc.code}" + (f": {message}" if message else "")


class OpenAICompatTTS(BaseTTS):
    """OpenAI ``/audio/speech`` 兼容客户端。"""

    backend = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        voice: str = "",
        speed: float | None = None,
        timeout: int = 300,
    ):
        self.api_key = api_key
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = model
        self.default_voice = voice
        self.speed = speed
        self.timeout = timeout

    def synthesize(
        self, text: str, output_path: str, voice: str = "", instruct: str = ""
    ) -> TTSResult:
        # instruct 为 qwen 专有的风格指令，OpenAI 协议无对应字段，忽略。
        text = (text or "").strip()
        if not text:
            return TTSResult(text=text, backend=self.backend, error="文本为空")
        if not (self.api_key and self.base_url and self.model):
            return TTSResult(
                text=text,
                backend=self.backend,
                error="TTS_API_KEY/TTS_BASE_URL/TTS_MODEL 未配置完整",
            )

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        body: dict = {"model": self.model, "input": text, "response_format": "wav"}
        chosen_voice = voice or self.default_voice
        if chosen_voice:
            body["voice"] = chosen_voice
        if self.speed is not None:
            body["speed"] = self.speed

        req = urllib.request.Request(
            self.base_url + "/audio/speech",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                audio = resp.read()
                billed = _billed_characters(resp.headers, text)
        except urllib.error.HTTPError as exc:
            return TTSResult(text=text, backend=self.backend, error=_error_message(exc))
        except Exception as exc:  # pylint: disable=broad-except
            return TTSResult(
                text=text,
                backend=self.backend,
                error=f"{type(exc).__name__}: {exc}"[:200],
            )
        if not audio:
            return TTSResult(text=text, backend=self.backend, error="服务未返回音频")

        # 供应商已生成成功：先报告用量，再落盘（落盘失败也不漏记成本）
        callback = getattr(self, "on_generated", None)
        if callback:
            callback(
                TTSResult(
                    text=text,
                    backend=self.backend,
                    model=self.model,
                    success=True,
                    billed_characters=billed,
                )
            )
        try:
            out_path.write_bytes(audio)
        except Exception as exc:  # pylint: disable=broad-except
            return TTSResult(
                text=text, backend=self.backend, error=f"保存音频失败: {exc}"[:200]
            )

        duration = 0.0
        try:
            with wave.open(str(out_path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
        except Exception:  # pylint: disable=broad-except
            pass
        return TTSResult(
            text=text,
            path=str(out_path),
            duration=round(duration, 2),
            backend=self.backend,
            success=True,
            model=self.model,
            billed_characters=billed,
        )
