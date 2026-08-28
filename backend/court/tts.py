"""CosyVoice 语音合成（dashscope cosyvoice-v1 / v2）。

角色 → 音色映射；v2 支持 instruction 情感参数（默认 v1，当前 key 仅有 v1 权限）。
设置 .env TTS_MODEL=cosyvoice-v2 + 开通 v2 权限即启用情感语音。
内存缓存；失败时前端回退浏览器 TTS。
"""

import base64
import hashlib
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_TTS_CACHE: Dict[str, Dict[str, Any]] = {}
_TTS_LOCK = threading.Lock()

VOICE_MAP = {
    "xz": "longcheng",  # 唐玄宗 · 沉稳男声
    "cx": "longshu",  # 陈玄礼 · 浑厚男声
    "gl": "longyuan",  # 高力士 · 偏细
    "td": "longshuo",  # 太子   · 少年男声
    "n": "longyue",  # 旁白   · 播音女声
    "libai": "longfei",  # 李白   · 阳刚
}

# 角色 → instruction（cosyvoice-v2 用自然语言描述情感/风格）
INSTRUCTION_MAP = {
    "n": "声音平稳、客观，如新闻播报",
    "xz": "声音低沉、威严，带着帝王之气",
    "cx": "语气愤怒、急切，带有逼迫感",
    "gl": "语气机警、委婉，略带狡黠",
    "td": "声音悲伤、不甘，带着委屈",
    "libai": "声音豪放、恣意，带着醉意和狂放",
}


def _api_key() -> str:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("IMG_API_KEY") and "=" in line:
                return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


def synthesize(text: str, voice_key: str = "n") -> Dict[str, Any]:
    """同步合成语音，返回 {ok, audio_url(data:audio/mp3;base64,...)}。"""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "empty text"}
    voice = VOICE_MAP.get(voice_key, "longyue")
    model = os.environ.get("TTS_MODEL", "cosyvoice-v1")
    instruction = (
        INSTRUCTION_MAP.get(voice_key, "声音自然")
        if model.startswith("cosyvoice-v2")
        else ""
    )
    key = hashlib.md5(f"{model}:{voice}:{instruction}:{text}".encode()).hexdigest()
    with _TTS_LOCK:
        if key in _TTS_CACHE:
            return _TTS_CACHE[key]
    api_key = _api_key()
    if not api_key:
        return {"ok": False, "error": "no api key"}
    try:
        os.environ["DASHSCOPE_API_KEY"] = api_key
        from dashscope.audio.tts_v2 import SpeechSynthesizer

        kwargs: Dict[str, Any] = {"model": model, "voice": voice}
        if model.startswith("cosyvoice-v2"):
            kwargs["instruction"] = instruction
        synth = SpeechSynthesizer(**kwargs)
        audio = synth.call(text)
        if not audio:
            return {"ok": False, "error": "empty audio"}
        b64 = base64.b64encode(audio).decode("ascii")
        result = {
            "ok": True,
            "audio_url": f"data:audio/mp3;base64,{b64}",
            "voice": voice,
        }
        with _TTS_LOCK:
            if len(_TTS_CACHE) > 150:
                _TTS_CACHE.clear()
            _TTS_CACHE[key] = result
        return result
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("TTS 合成失败: %s", e)
        return {"ok": False, "error": str(e)[:120]}
