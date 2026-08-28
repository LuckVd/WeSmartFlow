#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DashScope qwen3-tts-instruct-flash 语音合成（纯 HTTP，零额外依赖）。

与知识之境（examples/live_science）使用同一条 TTS 通道。提供与
`agent_core.tool.tts_say.say_batch_synthesize` 完全一致的批量返回结构，
并封装三级优先级：

  1. qwen3-tts-instruct-flash —— 有 DASHSCOPE_API_KEY 时优先；
  2. macOS `say`               —— 无 key 时回退；
  3. 两者都不可用             —— 不生成（返回全失败 results）。

音色默认 Cherry + 教师讲解语气指令，适合沉浸式课程与知识卡片的单人讲解旁白。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

QWEN_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_TTS_MODEL = "qwen3-tts-instruct-flash"

DEFAULT_VOICE = "Cherry"
DEFAULT_INSTRUCT = "亲切自然、循循善诱的教师讲解，语速适中，清晰沉稳"

_ENV_NAME = "DASHSCOPE_API_KEY"


def get_dashscope_api_key() -> str:
    """读取 DASHSCOPE_API_KEY：环境变量 → config 触发 load_dotenv → 直接读 .env。"""
    key = os.environ.get(_ENV_NAME, "").strip()
    if key:
        return key
    try:
        import config  # noqa: F401  # 触发 load_dotenv，把 .env 注入 os.environ

        key = os.environ.get(_ENV_NAME, "").strip()
        if key:
            return key
    except Exception:  # pylint: disable=broad-except
        pass
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(_ENV_NAME) and "=" in line:
                return line.partition("=")[2].strip().strip('"').strip("'")
    return ""


def qwen_tts_available() -> bool:
    return bool(get_dashscope_api_key())


def _norm_filename(filename: str, idx: int) -> str:
    name = (filename or "").strip() or f"frame_{idx + 1:03d}.wav"
    if not name.endswith(".wav"):
        name += ".wav"
    return name


def _qwen_tts_to_wav(
    text: str,
    output_path: str,
    voice: str,
    instruct: str,
    timeout: int = 90,
) -> Dict[str, Any]:
    """单条文本 → qwen3-tts-instruct-flash → 落盘 WAV。返回 {success,path,error,...}。"""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    key = get_dashscope_api_key()
    if not key:
        return {
            "success": False,
            "path": "",
            "duration_seconds": 0,
            "elapsed_seconds": 0,
            "error": "DASHSCOPE_API_KEY 未配置",
        }
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
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        url = (data.get("output") or {}).get("audio", {}).get("url")
        if not url:
            raise RuntimeError(
                f"dashscope 无音频返回: {json.dumps(data, ensure_ascii=False)[:300]}"
            )
        with urllib.request.urlopen(url, timeout=timeout) as r:
            audio = r.read()
        out_path.write_bytes(audio)
        elapsed = time.time() - t0
        duration = 0.0
        try:
            with wave.open(str(out_path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
        except Exception:  # pylint: disable=broad-except
            pass
        return {
            "success": True,
            "path": str(out_path),
            "duration_seconds": round(duration, 2),
            "elapsed_seconds": round(elapsed, 2),
            "error": "",
        }
    except Exception as e:  # pylint: disable=broad-except
        return {
            "success": False,
            "path": "",
            "duration_seconds": 0,
            "elapsed_seconds": 0,
            "error": str(e)[:200],
        }


def qwen_tts_batch_synthesize(
    items: List[Dict[str, str]],
    output_dir: str,
    voice: str = "",
    instruct: str = "",
) -> Dict[str, Any]:
    """批量 qwen3-tts 合成，返回结构与 say_batch_synthesize 一致。"""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    total_t0 = time.time()
    for idx, item in enumerate(items):
        text = (item.get("text") or "").strip()
        filename = _norm_filename(item.get("filename", ""), idx)
        if not text:
            results.append(
                {
                    "index": idx,
                    "filename": filename,
                    "path": "",
                    "duration_seconds": 0,
                    "success": False,
                    "error": "文本为空",
                }
            )
            continue
        out_path = out_dir / filename
        r = _qwen_tts_to_wav(text, str(out_path), voice, instruct)
        logger.info(
            "[qwen-tts %d/%d] %s %d字 -> %.1fs",
            idx + 1,
            len(items),
            "✓" if r["success"] else "✗",
            len(text),
            r.get("duration_seconds", 0),
        )
        results.append(
            {
                "index": idx,
                "filename": filename,
                "path": r.get("path", ""),
                "duration_seconds": r.get("duration_seconds", 0),
                "success": r.get("success", False),
                "error": r.get("error", ""),
            }
        )
    total_elapsed = time.time() - total_t0
    success_count = sum(1 for r in results if r["success"])
    return {
        "voice": voice or DEFAULT_VOICE,
        "backend": "qwen3-tts",
        "total": len(items),
        "success_count": success_count,
        "total_seconds": round(total_elapsed, 2),
        "output_dir": str(out_dir),
        "results": results,
    }


def synthesize_batch(
    items: List[Dict[str, str]],
    output_dir: str,
    voice: str = "",
    instruct: str = "",
) -> Dict[str, Any]:
    """三级优先级统一入口：qwen3-tts → macOS say → 不生成。"""
    items = items or []
    if qwen_tts_available():
        res = qwen_tts_batch_synthesize(items, output_dir, voice, instruct)
        if res["success_count"] > 0 or not items:
            return res
        logger.warning("qwen3-tts 全部失败（%d 条），回退 macOS say", len(items))

    if shutil.which("say"):
        from agent_core.tool.tts_say import say_batch_synthesize

        res = say_batch_synthesize(
            items=items, output_dir=output_dir, voice="Tingting", rate=180
        )
        res["backend"] = "macos-say"
        return res

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = [
        {
            "index": i,
            "filename": _norm_filename(item.get("filename", ""), i),
            "path": "",
            "duration_seconds": 0,
            "success": False,
            "error": "无可用 TTS 通道（无 DASHSCOPE_API_KEY 且无 macOS say）",
        }
        for i, item in enumerate(items)
    ]
    logger.warning("无可用 TTS 通道，跳过语音生成（%d 条）", len(items))
    return {
        "voice": voice or DEFAULT_VOICE,
        "backend": "none",
        "total": len(items),
        "success_count": 0,
        "total_seconds": 0,
        "output_dir": str(out_dir),
        "results": results,
    }


__all__ = [
    "qwen_tts_available",
    "get_dashscope_api_key",
    "qwen_tts_batch_synthesize",
    "synthesize_batch",
    "DEFAULT_VOICE",
    "DEFAULT_INSTRUCT",
]
