"""Regression tests for bounded parallel narration synthesis."""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.tool.tts.base import BaseTTS, TTSResult


class FakeTTS(BaseTTS):
    backend = "fake"

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def synthesize(self, text, output_path, voice="", instruct=""):
        time.sleep(0.04)
        with self.lock:
            self.calls.append(text)
        return TTSResult(
            text=text,
            path=output_path,
            duration=0.04,
            backend=self.backend,
            success=True,
        )


class BatchSynthesisTests(unittest.TestCase):
    def test_parallel_batch_preserves_input_order_and_reduces_wall_time(self):
        items = [
            {"text": value, "filename": f"{index}.wav"}
            for index, value in enumerate("abcd")
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tts = FakeTTS()
            started = time.perf_counter()
            result = tts.synthesize_batch(items, tmp, max_concurrency=2)
            elapsed = time.perf_counter() - started
        self.assertEqual([item["index"] for item in result["results"]], [0, 1, 2, 3])
        self.assertEqual(
            [item["filename"] for item in result["results"]],
            ["0.wav", "1.wav", "2.wav", "3.wav"],
        )
        self.assertEqual(result["success_count"], 4)
        self.assertLess(elapsed, 0.14)

    def test_empty_item_stays_a_ordered_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = FakeTTS().synthesize_batch(
                [{"text": "ok"}, {"text": ""}], tmp, max_concurrency=3
            )
        self.assertTrue(result["results"][0]["success"])
        self.assertFalse(result["results"][1]["success"])
        self.assertEqual(result["results"][1]["error"], "文本为空")


if __name__ == "__main__":
    unittest.main()
