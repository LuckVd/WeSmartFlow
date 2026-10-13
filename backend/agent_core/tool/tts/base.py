"""TTS 客户端抽象基类。

与 ``agent_core.llm.base.BaseLLM`` 同构：实现类（qwen3-tts / mac say /
cosyvoice）各自封装后端，治理逻辑（额度拦截、记账）由
``services/tts_factory`` 挂在实例方法外层，不写在这里。

契约：``synthesize`` 失败**不抛异常**，返回 ``success=False`` 的
:class:`TTSResult`——批量讲解稿生成是逐条容错的流程，单条失败不该
中断整批。供应商已生成成功时通过 on_generated 回调报告用量，
即使本地保存失败，已产生的成本仍由工厂记录。

``synthesize_batch`` 的默认实现逐条调用 ``self.synthesize``：
工厂包装的是实例的 ``synthesize``（setattr 到实例上），批量循环
自然逐条触发治理 hook——这也是为什么批量不单独挂 hook。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """单条语音合成结果。"""

    text: str = ""
    path: str = ""
    duration: float = 0.0
    backend: str = ""
    success: bool = False
    error: str = ""
    model: str = ""
    billed_characters: int = 0


def _norm_filename(filename: str, idx: int) -> str:
    """归一化批量条目的文件名：空则按序号生成，强制 .wav 后缀。"""
    name = (filename or "").strip() or f"frame_{idx + 1:03d}.wav"
    if not name.endswith(".wav"):
        name += ".wav"
    return name


class BaseTTS(ABC):
    """TTS 客户端抽象基类。"""

    #: 后端标识（qwen3-tts / macos-say / cosyvoice ...）
    backend: str = "tts"

    @abstractmethod
    def synthesize(
        self, text: str, output_path: str, voice: str = "", instruct: str = ""
    ) -> TTSResult:
        """单条文本合成语音并落盘。

        Args:
            text:        待合成文本（空文本返回失败结果）。
            output_path: 输出音频文件路径（wav/mp3 由后端决定）。
            voice:       音色（空串用后端默认值）。
            instruct:    风格 / 情感指令（后端支持时生效）。

        Returns:
            合成结果；失败时 ``success=False`` 且带 ``error``，不抛异常。
        """

    def synthesize_batch(
        self,
        items: List[Dict[str, str]],
        output_dir: str,
        voice: str = "",
        instruct: str = "",
        max_concurrency: int = 1,
    ) -> Dict[str, Any]:
        """批量合成：逐条调用 :meth:`synthesize`（每条独立触发治理 hook）。

        ``max_concurrency`` keeps the historical sequential default.  Callers
        that create many independent page narrations can opt into a small,
        bounded pool; output ordering, per-item accounting hooks and failure
        isolation remain identical to the sequential path.

        返回结构与历史 ``qwen_tts.synthesize_batch`` / ``say_batch_synthesize``
        完全一致::

            {
                "voice", "backend", "total", "success_count",
                "total_seconds", "output_dir", "results": [...]
            }
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        results: List[Dict[str, Any] | None] = [None] * len(items or [])
        total_t0 = time.time()

        def synthesize_one(idx: int, item: Dict[str, str]) -> Dict[str, Any]:
            text = (item.get("text") or "").strip()
            filename = _norm_filename(item.get("filename", ""), idx)
            if not text:
                return {
                    "index": idx,
                    "filename": filename,
                    "path": "",
                    "duration_seconds": 0,
                    "success": False,
                    "error": "文本为空",
                }
            try:
                result = self.synthesize(
                    text, str(out_dir / filename), voice=voice, instruct=instruct
                )
            except Exception as exc:  # defensive: a backend should return failure
                logger.exception(
                    "[%s %d/%d] 合成异常", self.backend, idx + 1, len(items)
                )
                return {
                    "index": idx,
                    "filename": filename,
                    "path": "",
                    "duration_seconds": 0,
                    "success": False,
                    "error": str(exc),
                }
            logger.info(
                "[%s %d/%d] %s %d字 -> %.1fs",
                self.backend,
                idx + 1,
                len(items),
                "✓" if result.success else "✗",
                len(text),
                result.duration,
            )
            return {
                "index": idx,
                "filename": filename,
                "path": result.path,
                "duration_seconds": result.duration,
                "success": result.success,
                "error": result.error,
            }

        parallelism = max(1, min(int(max_concurrency or 1), len(items or []) or 1))
        if parallelism == 1:
            for idx, item in enumerate(items or []):
                results[idx] = synthesize_one(idx, item)
        else:
            with ThreadPoolExecutor(max_workers=parallelism) as executor:
                futures = {
                    executor.submit(synthesize_one, idx, item): idx
                    for idx, item in enumerate(items or [])
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    results[idx] = future.result()

        total_elapsed = time.time() - total_t0
        ordered_results = [r for r in results if r is not None]
        success_count = sum(1 for r in ordered_results if r["success"])
        return {
            "voice": voice,
            "backend": self.backend,
            "total": len(items or []),
            "success_count": success_count,
            "total_seconds": round(total_elapsed, 2),
            "output_dir": str(out_dir),
            "results": ordered_results,
        }
