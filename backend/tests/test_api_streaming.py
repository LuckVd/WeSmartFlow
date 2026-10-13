"""Unit tests for the backwards-compatible SSE envelope."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.streaming import SSEEventEmitter, build_stream_event, encode_sse_event


def _payload_from_frame(frame: str) -> dict:
    lines = frame.rstrip().splitlines()
    data_line = next(line for line in lines if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


class SSEEnvelopeTests(unittest.TestCase):
    def test_legacy_top_level_fields_remain_readable(self):
        frame = encode_sse_event(
            "progress",
            event_id="evt_progress_1",
            sequence=7,
            job_id="job_course_1",
            request_id="req_web_20260922",
            stage="render_pdf",
            pct=65,
            message="正在排版 PDF",
        )
        payload = _payload_from_frame(frame)

        # This is the payload shape existing parsers consume.
        self.assertEqual(payload["type"], "progress")
        self.assertEqual(payload["stage"], "render_pdf")
        self.assertEqual(payload["pct"], 65)
        self.assertEqual(payload["message"], "正在排版 PDF")

        # New consumers have lifecycle and replay metadata plus one payload.
        self.assertEqual(payload["event_id"], "evt_progress_1")
        self.assertEqual(payload["sequence"], 7)
        self.assertEqual(payload["job_id"], "job_course_1")
        self.assertEqual(payload["request_id"], "req_web_20260922")
        self.assertEqual(
            payload["data"],
            {"stage": "render_pdf", "pct": 65, "message": "正在排版 PDF"},
        )
        self.assertTrue(payload["occurred_at"].endswith("Z"))
        self.assertTrue(frame.startswith("id: evt_progress_1\nevent: message\n"))

    def test_existing_data_field_is_not_nested_or_changed(self):
        outline = {"title": "哲学导论", "chapters": [{"id": 1}]}
        payload = build_stream_event(
            "outline",
            event_id="evt_outline_1",
            data=outline,
        )

        self.assertEqual(payload["type"], "outline")
        self.assertEqual(payload["data"], outline)
        self.assertNotIn("payload", payload)

    def test_emitter_assigns_monotonic_sequences_and_unique_ids(self):
        emitter = SSEEventEmitter(job_id="job_card_1", next_sequence=12)
        first = _payload_from_frame(emitter.emit("progress", message="开始生成"))
        second = _payload_from_frame(emitter.emit("done"))

        self.assertEqual([first["sequence"], second["sequence"]], [12, 13])
        self.assertEqual(first["job_id"], "job_card_1")
        self.assertNotEqual(first["event_id"], second["event_id"])
        with self.assertRaises(ValueError):
            emitter.emit("progress", event_id=first["event_id"])

    def test_rejects_unsafe_sse_header_tokens(self):
        with self.assertRaises(ValueError):
            encode_sse_event("progress\nretry: 1")
        with self.assertRaises(ValueError):
            encode_sse_event("progress", event_id="evt\nmalicious")

    def test_immersive_producer_keeps_legacy_data_frame_during_migration(self):
        """The direct immersive service producer remains unchanged for now."""

        from services.immersive.sse import sse_event as immersive_sse_event

        frame = immersive_sse_event("progress", stage="tex", pct=42)
        payload = _payload_from_frame(frame)
        self.assertEqual(payload, {"type": "progress", "stage": "tex", "pct": 42})

    def test_business_field_named_event_type_does_not_collide(self):
        """沉浸式 agent_event 的业务字段就叫 event_type（start/think/...）。

        回归：encode_sse_event 的首个形参也叫 event_type，经 job_manager 重编码
        ``encode_sse_event(type, **payload)`` 时曾抛
        "got multiple values for argument 'event_type'"，导致课程生成一启动就失败。
        """

        frame = encode_sse_event(
            "agent_event",
            agent_type="planner",
            event_type="start",
            content="规划大纲",
            step=0,
        )
        payload = _payload_from_frame(frame)
        self.assertEqual(payload["type"], "agent_event")  # 信封类型不被覆盖
        self.assertEqual(payload["event_type"], "start")  # 前端读取的业务字段保留
        self.assertEqual(payload["agent_type"], "planner")
        self.assertEqual(payload["data"]["event_type"], "start")

        emitted = SSEEventEmitter(job_id="job_1").emit(
            "agent_event", event_type="think"
        )
        self.assertEqual(_payload_from_frame(emitted)["event_type"], "think")

    def test_job_manager_enrich_keeps_agent_event_fields(self):
        """detached job 的重编码路径：producer 帧 -> _enrich_event -> 带序号的帧。"""

        from services.immersive.job_manager import _Job, ImmersiveJobManager
        from services.immersive.sse import sse_event as immersive_sse_event

        job = _Job(session_id="sess_1", user_id="user_1")
        producer = immersive_sse_event(
            "agent_event",
            agent_type="planner",
            event_type="tool_call",
            content="调用工具",
            step=2,
        )
        enriched = _payload_from_frame(ImmersiveJobManager._enrich_event(job, producer))

        self.assertEqual(enriched["type"], "agent_event")
        self.assertEqual(enriched["event_type"], "tool_call")
        self.assertEqual(enriched["step"], 2)
        self.assertEqual(enriched["job_id"], "sess_1")
        self.assertEqual(enriched["sequence"], 1)


if __name__ == "__main__":
    unittest.main()


class RouterSSESafetyTests(unittest.TestCase):
    def test_chat_router_does_not_emit_raw_exception_text(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "routers" / "sessions.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('f"服务器内部错误：{e}"', source)
        self.assertIn('code": "internal_error"', source)
        self.assertIn("event_stream_headers()", source)

    def test_other_streaming_routes_use_shared_envelope(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "routers"
        for name in ("llm.py", "cards.py", "immersive.py"):
            source = (root / name).read_text(encoding="utf-8")
            self.assertIn("encode_sse_event", source, name)
            self.assertIn("event_stream_headers", source, name)
