"""CosyVoice 语音合成（court demo 专用）。

角色音色映射、情感指令、内存缓存属 court 业务，留在本模块；
实际合成调用走 :func:`services.tts_factory.get_tts`（backend="cosyvoice"），
额度拦截与记账挂在工厂产出的客户端上（demo 以系统任务记账）。

失败时前端回退浏览器 TTS。
"""

import base64
import hashlib
import logging
import os
import tempfile
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

    # 缓存命中不调用供应商；新合成记在当前登录用户下。
    from services.credit_quota import CreditsExceeded
    from services.tts_factory import get_tts
    from services.external_usage import current_usage

    tts = get_tts(
        current_usage().user_id,
        backend="cosyvoice",
        scene="court",
    )
    if tts is None:
        return {"ok": False, "error": "no api key"}

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        r = tts.synthesize(text, tmp_path, voice=voice, instruct=instruction)
        if not r.success:
            return {"ok": False, "error": (r.error or "synth failed")[:120]}
        b64 = base64.b64encode(Path(tmp_path).read_bytes()).decode("ascii")
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
    except CreditsExceeded:
        raise
    except Exception as e:  # pylint: disable=broad-except
        logger.warning("TTS 合成失败: %s", e)
        return {"ok": False, "error": str(e)[:120]}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
