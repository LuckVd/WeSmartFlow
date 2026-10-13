"""macOS say TTS 客户端。

直接调用系统 ``say`` 命令合成 WAV，无需任何服务与依赖。
逻辑迁移自 ``agent_core.tool.tts_say``。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from .base import BaseTTS, TTSResult


class MacSayTTS(BaseTTS):
    """macOS 系统 say 命令客户端：say → AIFF → afconvert → WAV (PCM 16bit)。"""

    backend = "macos-say"

    def __init__(self, voice: str = "Tingting", rate: int = 180):
        self.voice = voice
        self.rate = rate

    def is_available(self) -> bool:
        """当前系统是否可执行 say 命令（仅 macOS 且已安装）。"""
        import shutil

        return shutil.which("say") is not None

    def synthesize(
        self, text: str, output_path: str, voice: str = "", instruct: str = ""
    ) -> TTSResult:
        # instruct 对 say 无意义，忽略
        text = (text or "").strip()
        if not text:
            return TTSResult(text=text, backend=self.backend, error="文本为空")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp_aiff:
            aiff_path = tmp_aiff.name

        try:
            subprocess.run(
                [
                    "say",
                    "-v",
                    voice or self.voice,
                    "-r",
                    str(self.rate),
                    "-o",
                    aiff_path,
                    text,
                ],
                check=True,
                timeout=120,
                capture_output=True,
            )
            try:
                subprocess.run(
                    [
                        "afconvert",
                        "-f",
                        "WAVE",
                        "-d",
                        "LEI16@24000",
                        aiff_path,
                        str(out_path),
                    ],
                    check=True,
                    timeout=30,
                    capture_output=True,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                # ``afconvert`` occasionally aborts after creating a tiny,
                # truncated WAV.  ffmpeg produces the same PCM contract and
                # lets a background course repair complete reliably.
                if not shutil.which("ffmpeg"):
                    raise exc
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        aiff_path,
                        "-ac",
                        "1",
                        "-ar",
                        "24000",
                        "-c:a",
                        "pcm_s16le",
                        str(out_path),
                    ],
                    check=True,
                    timeout=30,
                    capture_output=True,
                )

            duration = 0.0
            try:
                with wave.open(str(out_path), "rb") as wf:
                    duration = wf.getnframes() / wf.getframerate()
            except Exception:  # pylint: disable=broad-except
                pass

            _ = time.time()
            return TTSResult(
                text=text,
                path=str(out_path),
                duration=round(duration, 2),
                backend=self.backend,
                success=True,
            )
        except subprocess.CalledProcessError as e:
            return TTSResult(
                text=text, backend=self.backend, error=f"say 命令执行失败: {e}"
            )
        except subprocess.TimeoutExpired:
            return TTSResult(text=text, backend=self.backend, error="say 命令执行超时")
        except Exception as e:  # pylint: disable=broad-except
            return TTSResult(text=text, backend=self.backend, error=str(e))
        finally:
            if os.path.exists(aiff_path):
                os.unlink(aiff_path)
