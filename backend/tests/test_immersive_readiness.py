"""Regression tests for the early-learning state used by immersive courses."""

from __future__ import annotations

from pathlib import Path
import asyncio
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.session import SessionDetail
from services.immersive import node_extractor, service, suggestions
from services.immersive.layout import CourseLayout
from services.immersive.tts import parse_speaker_notes_response


class ChapterReadinessTests(unittest.TestCase):
    def test_speaker_notes_parser_accepts_wrapped_object_and_fills_missing_pages(self):
        raw = """
        下面是讲解稿：
        ```json
        {"notes": [
          {"page": 1, "script": "第一页先从同余的直觉出发。"},
          {"page": 3, "script": "第三页重点看欧几里得算法为什么会终止。"}
        ]}
        ```
        """
        tex = r"""
        \begin{frame}\frametitle{同余入门}\end{frame}
        \begin{frame}\frametitle{整除与余数}\end{frame}
        \begin{frame}\frametitle{欧几里得算法}\end{frame}
        """

        notes = parse_speaker_notes_response(raw, 3, tex)

        self.assertEqual(len(notes), 3)
        self.assertIn("同余", notes[0])
        self.assertIn("整除与余数", notes[1])
        self.assertIn("欧几里得", notes[2])

    def test_node_extractor_falls_back_to_knowledge_points_on_empty_llm(self):
        class EmptyLLM:
            def think(self, *_args, **_kwargs):
                return SimpleNamespace(content="")

        class FakeNodeRepo:
            def __init__(self):
                self.created = []

            def find_by_title(self, _user_id, _title):
                return None

            def create(self, _user_id, data, initial_mastery=0.1):
                self.created.append((data, initial_mastery))
                return SimpleNamespace(id=f"node-{len(self.created)}")

            def get_by_id(self, _node_id):
                return None

        repo = FakeNodeRepo()
        with patch.object(node_extractor, "NodeRepository", return_value=repo):
            nodes = node_extractor.extract_and_persist_nodes(
                session_id="session-1",
                topic="数学竞赛数论专题",
                chapters=[
                    {
                        "title": "同余与整除",
                        "knowledge_points": ["同余", "欧几里得算法"],
                    }
                ],
                llm=EmptyLLM(),
                user_id="user-1",
            )

        self.assertEqual([node["title"] for node in nodes], ["同余", "欧几里得算法"])
        self.assertTrue(all(item[0].content.key_points for item in repo.created))

    def test_session_detail_accepts_learning_ready_canvas_block_status(self):
        detail = SessionDetail(
            id="session-1",
            user_id="user-1",
            title="[AI课程]苹果公司的前世今生",
            topic="苹果公司的前世今生",
            status="active",
            node_ids_covered=[],
            files=[],
            message_count=0,
            duration_minutes=0,
            created_at="2026-09-20T19:30:00+08:00",
            ended_at=None,
            canvas_blocks=[
                {
                    "id": "chapter_2_status",
                    "type": "chapter_status",
                    "title": "第2章 Mac 时代",
                    "status": "learning_ready",
                    "chapter_id": 2,
                    "data": {"stage": "learning_ready"},
                }
            ],
            messages=[],
        )

        self.assertEqual(detail.canvas_blocks[0].status, "learning_ready")

    def test_tex_prompt_keeps_original_outline_successor_during_partial_resume(self):
        chapters = [
            {"chapter_id": 3, "title": "认识论"},
            {"chapter_id": 4, "title": "形而上学", "knowledge_points": ["存在"]},
            {"chapter_id": 5, "title": "伦理学"},
        ]
        prompt = service._build_tex_prompt(
            topic="哲学导论",
            chapters=chapters,
            index=1,
            research_path=Path("/tmp/chapter_04/research.json"),
            tex_path=Path("/tmp/chapter_04/chapter_04.tex"),
            images_dir=Path("/tmp/chapter_04/images"),
        )

        self.assertIn("上一章：第3章「认识论」", prompt)
        self.assertIn("下一章：第5章「伦理学」", prompt)
        self.assertIn("不得改写其章节号或主题", prompt)

    def test_navigation_validator_rejects_wrong_successor_and_accepts_expected_one(
        self,
    ):
        chapters = [
            {"chapter_id": 3, "title": "认识论"},
            {"chapter_id": 4, "title": "形而上学"},
            {"chapter_id": 5, "title": "伦理学"},
        ]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_04.tex"
            tex_path.write_text("下一章：认识论——我们如何知道？", encoding="utf-8")
            error = service.validate_chapter_navigation(tex_path, chapters, 1)
            self.assertIn("第5章「伦理学」", error or "")

            tex_path.write_text(
                "下一章：第5章 伦理学——我们应当如何生活", encoding="utf-8"
            )
            self.assertIsNone(
                service.validate_chapter_navigation(tex_path, chapters, 1)
            )

    def test_navigation_validator_allows_generic_next_cue_without_exact_label(self):
        chapters = [
            {"chapter_id": 1, "title": "透视"},
            {"chapter_id": 2, "title": "齐次坐标"},
        ]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_01.tex"
            tex_path.write_text(
                "下一章我们继续把直觉变成可计算的代数语言。", encoding="utf-8"
            )
            self.assertIsNone(
                service.validate_chapter_navigation(tex_path, chapters, 0)
            )

    def test_navigation_validator_rejects_backward_chapter_target(self):
        chapters = [
            {"chapter_id": 1, "title": "透视"},
            {"chapter_id": 2, "title": "齐次坐标"},
            {"chapter_id": 3, "title": "交比"},
            {"chapter_id": 4, "title": "对偶原理"},
        ]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_03.tex"
            tex_path.write_text(
                "下一章：第2章「齐次坐标」——回到坐标计算。", encoding="utf-8"
            )
            error = service.validate_chapter_navigation(tex_path, chapters, 2)
            self.assertIn("第2章「齐次坐标」", error or "")
            self.assertIn("第4章「对偶原理」", error or "")

    def test_navigation_validator_accepts_beamer_next_chapter_block_title(self):
        chapters = [
            {"chapter_id": 1, "title": "透视"},
            {"chapter_id": 2, "title": "齐次坐标"},
        ]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_01.tex"
            tex_path.write_text(
                """
\\begin{frame}{小结}
  \\begin{block}{下一章}
    我们将进入\\alert{第2章「齐次坐标」}，把无穷远点也纳入计算。
  \\end{block}
\\end{frame}
""",
                encoding="utf-8",
            )
            self.assertIsNone(
                service.validate_chapter_navigation(tex_path, chapters, 0)
            )

    def test_navigation_validator_rejects_wrong_successor_inside_beamer_block(self):
        chapters = [
            {"chapter_id": 1, "title": "透视"},
            {"chapter_id": 2, "title": "齐次坐标"},
            {"chapter_id": 3, "title": "交比"},
        ]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_01.tex"
            tex_path.write_text(
                """
\\begin{frame}{小结}
  \\begin{block}{下一章}
    接下来直接进入第3章「交比」。
  \\end{block}
\\end{frame}
""",
                encoding="utf-8",
            )
            error = service.validate_chapter_navigation(tex_path, chapters, 0)
            self.assertIn("第2章「齐次坐标」", error or "")

    def test_navigation_validator_accepts_beamer_frame_next_chapter_title(self):
        chapters = [
            {"chapter_id": 1, "title": "透视"},
            {"chapter_id": 2, "title": "齐次坐标"},
        ]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_01.tex"
            tex_path.write_text(
                """
\\begin{frame}{下一章}
  第2章「齐次坐标」：把几何问题转成代数计算。
\\end{frame}
""",
                encoding="utf-8",
            )
            self.assertIsNone(
                service.validate_chapter_navigation(tex_path, chapters, 0)
            )

    def test_navigation_validator_rejects_next_chapter_cue_in_final_chapter(self):
        chapters = [{"chapter_id": 1, "title": "结语"}]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            tex_path = Path(directory) / "chapter_01.tex"
            tex_path.write_text("下一章：继续探究", encoding="utf-8")
            error = service.validate_chapter_navigation(tex_path, chapters, 0)
        self.assertIn("最后一章不应出现", error or "")

    def test_chapter_artifact_status_does_not_require_research_after_valid_pdf(self):
        chapters = [{"chapter_id": 1, "title": "透视"}]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            course = CourseLayout(Path(directory) / "course")
            course.ensure_dirs(chapter_ids=[1])
            chapter_dir = course.chapter_dir(1)
            course.tex_file(1).write_text("%" + "x" * 80, encoding="utf-8")
            course.pdf_file(1).write_bytes(b"%PDF-1.7\n" + b"x" * 80)
            course.exercises_file(1).write_text("题目" * 40, encoding="utf-8")
            (chapter_dir / "chapter_01_overview.md").write_text(
                "预习" * 40, encoding="utf-8"
            )

            with patch.object(service, "_chapter_pdf_error", return_value=None):
                status = service._chapter_artifact_status(
                    course,
                    chapters[0],
                    0,
                    chapters=chapters,
                    enable_audio=False,
                    enable_exercises=True,
                )

            self.assertTrue(status["ready"])
            self.assertTrue(status["checks"]["pdf"])
            self.assertFalse(status["checks"]["research"])
            self.assertIn("research", status["optional_missing"])
            self.assertNotIn("research", status["missing"])

    def test_resume_audit_registers_ready_pdf_without_existing_doc_id(self):
        chapters = [{"chapter_id": 1, "title": "透视"}]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            course = CourseLayout(Path(directory) / "course")
            course.ensure_dirs(chapter_ids=[1])
            chapter_dir = course.chapter_dir(1)
            course.tex_file(1).write_text("%" + "x" * 80, encoding="utf-8")
            course.pdf_file(1).write_bytes(b"%PDF-1.7\n" + b"x" * 80)
            course.exercises_file(1).write_text("题目" * 40, encoding="utf-8")
            (chapter_dir / "chapter_01_overview.md").write_text(
                "预习" * 40, encoding="utf-8"
            )

            with (
                patch.object(service, "_chapter_pdf_error", return_value=None),
                patch.object(service, "register_chapter_pdf", return_value="pdf-doc"),
                patch.object(
                    service, "register_chapter_exercises", return_value="ex-doc"
                ),
                patch.object(service, "append_session_file"),
            ):
                audited, pending, generated = service._audit_resume_chapters(
                    "session",
                    course,
                    chapters,
                    [{"chapter_id": 1, "title": "透视", "status": "ready"}],
                    topic="射影几何",
                    user_id="user",
                    enable_audio=False,
                    enable_exercises=True,
                )

        self.assertEqual(pending, set())
        self.assertEqual(generated, 1)
        self.assertEqual(audited[0]["pdf_doc_id"], "pdf-doc")
        self.assertEqual(audited[0]["exercises_doc_id"], "ex-doc")
        self.assertIn("pdf_ch1", audited[0]["block_ids"])
        self.assertIn("quiz_ch1_bank", audited[0]["block_ids"])

    def test_resume_audit_registers_ready_audio_without_existing_doc_id(self):
        chapters = [{"chapter_id": 1, "title": "透视"}]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            course = CourseLayout(Path(directory) / "course")
            course.ensure_dirs(chapter_ids=[1])
            chapter_dir = course.chapter_dir(1)
            course.tex_file(1).write_text(
                "\\begin{frame}A"
                + "x" * 80
                + "\\end{frame}\\begin{frame}B"
                + "y" * 80
                + "\\end{frame}",
                encoding="utf-8",
            )
            course.pdf_file(1).write_bytes(b"%PDF-1.7\n" + b"x" * 80)
            course.exercises_file(1).write_text("题目" * 40, encoding="utf-8")
            (chapter_dir / "chapter_01_overview.md").write_text(
                "预习" * 40, encoding="utf-8"
            )
            (chapter_dir / "speaker_notes.json").write_text(
                '["第一页讲解", "第二页讲解"]', encoding="utf-8"
            )
            audio_dir = chapter_dir / "audio"
            audio_dir.mkdir()
            (audio_dir / "frame_001.wav").write_bytes(b"RIFF" + b"x" * 80)
            (audio_dir / "frame_002.wav").write_bytes(b"RIFF" + b"x" * 80)

            with (
                patch.object(service, "_chapter_pdf_error", return_value=None),
                patch.object(service, "register_chapter_pdf", return_value="pdf-doc"),
                patch.object(
                    service, "register_chapter_exercises", return_value="ex-doc"
                ),
                patch.object(
                    service, "register_chapter_notes", return_value="notes-doc"
                ),
                patch.object(
                    service, "register_chapter_audio", return_value="audio-doc"
                ) as audio_register,
                patch.object(service, "append_session_file"),
            ):
                audited, pending, generated = service._audit_resume_chapters(
                    "session",
                    course,
                    chapters,
                    [{"chapter_id": 1, "title": "透视", "status": "ready"}],
                    topic="射影几何",
                    user_id="user",
                    enable_audio=True,
                    enable_exercises=True,
                )

        self.assertEqual(pending, set())
        self.assertEqual(generated, 1)
        self.assertEqual(audited[0]["audio_doc_id"], "audio-doc")
        self.assertEqual(audited[0]["notes_doc_id"], "notes-doc")
        self.assertEqual(len(audited[0]["audio_files"]), 2)
        self.assertTrue(
            audited[0]["audio_files"][0]["url"].startswith(
                "/api/documents/audio-doc/asset/"
            )
        )
        audio_register.assert_called_once()

    def test_backfill_chapter_block_audio_metadata(self):
        with (
            patch.object(
                service,
                "read_workspace",
                return_value={
                    "canvas_blocks": [
                        {
                            "id": "pdf_ch1",
                            "type": "pdf",
                            "data": {
                                "doc_id": "pdf-doc",
                                "audio_files": [
                                    {"filename": "frame_001.wav", "success": True}
                                ],
                            },
                        }
                    ]
                },
            ),
            patch.object(service, "upsert_canvas_block") as upsert,
        ):
            changed = service._backfill_chapter_block_doc_ids(
                "session",
                [
                    {
                        "chapter_id": 1,
                        "audio_doc_id": "audio-doc",
                        "audio_files": [{"filename": "frame_001.wav", "success": True}],
                    }
                ],
            )

        self.assertEqual(changed, 1)
        data = upsert.call_args.args[1]["data"]
        self.assertEqual(data["audio_doc_id"], "audio-doc")
        self.assertEqual(
            data["audio_files"][0]["url"],
            "/api/documents/audio-doc/asset/frame_001.wav",
        )

    def test_audio_enabled_ready_chapter_without_audio_doc_still_needs_followup(self):
        self.assertTrue(
            service._chapter_requires_followup(
                {
                    "chapter_id": 1,
                    "status": "ready",
                    "audio_enabled": True,
                    "audio_files": [{"filename": "frame_001.wav", "success": True}],
                    "audio_doc_id": "",
                }
            )
        )
        self.assertFalse(
            service._chapter_requires_followup(
                {
                    "chapter_id": 1,
                    "status": "ready",
                    "audio_enabled": True,
                    "audio_files": [{"filename": "frame_001.wav", "success": True}],
                    "audio_doc_id": "audio-doc",
                }
            )
        )

    def test_tex_writer_retry_runs_fresh_attempt_after_pdf_validation_error(self):
        from tempfile import TemporaryDirectory

        async def fake_stream(*args, **kwargs):
            yield "data: fake\n\n"

        async def run_case():
            emitted = []

            async def emit(event: str) -> None:
                emitted.append(event)

            with TemporaryDirectory() as directory:
                course = CourseLayout(Path(directory) / "course")
                course.ensure_dirs(chapter_ids=[1])
                chapters = [{"chapter_id": 1, "title": "透视", "knowledge_points": []}]
                with (
                    patch.object(service, "_pdf_is_ready", return_value=False),
                    patch.object(
                        service, "_chapter_pdf_error", side_effect=["PDF 缺图", None]
                    ),
                    patch.object(
                        service,
                        "_build_agent_by_name",
                        side_effect=[object(), object()],
                    ) as build_agent,
                    patch.object(
                        service, "stream_agent_events", side_effect=fake_stream
                    ),
                ):
                    result = await service._run_tex_writer_with_retry(
                        topic="射影几何",
                        chapters=chapters,
                        index=0,
                        course=course,
                        layout=object(),
                        user_id="user",
                        emit=emit,
                        max_attempts=2,
                    )

            return result, emitted, build_agent.call_count

        result, emitted, call_count = asyncio.run(run_case())
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(call_count, 2)
        self.assertTrue(any("自动重试第 1 章 PDF" in event for event in emitted))

    def test_tex_prefetch_skips_already_ready_chapters(self):
        from tempfile import TemporaryDirectory

        async def run_case():
            with TemporaryDirectory() as directory:
                course = CourseLayout(Path(directory) / "course")
                course.ensure_dirs(chapter_ids=[1, 2])
                chapters = [
                    {"chapter_id": 1, "title": "已完成"},
                    {"chapter_id": 2, "title": "待生成"},
                ]
                calls = []
                publish_calls = []

                async def fake_retry(**kwargs):
                    calls.append(kwargs["index"])
                    await kwargs["emit"]("data: fake\n\n")
                    return {"ok": True, "attempts": 1, "error": ""}

                async def fake_publish(index, ch_info):
                    publish_calls.append((index, ch_info.get("chapter_id")))
                    return [
                        service.sse_event("workspace_update", block={"id": "pdf_ch2"})
                    ]

                def fake_ready(pdf_path, *args, **kwargs):
                    return pdf_path.name == "chapter_01.pdf"

                with (
                    patch.object(service, "_pdf_is_ready", side_effect=fake_ready),
                    patch.object(
                        service, "_run_tex_writer_with_retry", side_effect=fake_retry
                    ),
                ):
                    events = [
                        event
                        async for event in service._stream_parallel_tex_prefetch(
                            topic="射影几何",
                            chapters=chapters,
                            chapter_items=list(enumerate(chapters)),
                            course=course,
                            layout=object(),
                            user_id="user",
                            max_concurrency=3,
                            publish_ready=fake_publish,
                        )
                    ]
            return calls, publish_calls, events

        calls, publish_calls, events = asyncio.run(run_case())
        self.assertEqual(calls, [1])
        self.assertEqual(publish_calls, [(1, 2)])
        self.assertTrue(any("第 2 章 PDF" in event for event in events))
        self.assertTrue(any("pdf_ch2" in event for event in events))
        self.assertFalse(any("第 1 章 PDF" in event for event in events))

    def test_tex_prefetch_uses_rolling_concurrency_window(self):
        from tempfile import TemporaryDirectory

        async def run_case():
            with TemporaryDirectory() as directory:
                course = CourseLayout(Path(directory) / "course")
                course.ensure_dirs(chapter_ids=[1, 2, 3, 4])
                chapters = [
                    {"chapter_id": 1, "title": "第一章"},
                    {"chapter_id": 2, "title": "第二章"},
                    {"chapter_id": 3, "title": "第三章"},
                    {"chapter_id": 4, "title": "第四章"},
                ]
                calls = []
                active = 0
                max_active = 0

                async def fake_retry(**kwargs):
                    nonlocal active, max_active
                    calls.append(kwargs["index"])
                    active += 1
                    max_active = max(max_active, active)
                    await asyncio.sleep(0.001)
                    active -= 1
                    return {"ok": True, "attempts": 1, "error": ""}

                with (
                    patch.object(service, "_pdf_is_ready", return_value=False),
                    patch.object(
                        service, "_run_tex_writer_with_retry", side_effect=fake_retry
                    ),
                ):
                    events = [
                        event
                        async for event in service._stream_parallel_tex_prefetch(
                            topic="射影几何",
                            chapters=chapters,
                            chapter_items=list(enumerate(chapters)),
                            course=course,
                            layout=object(),
                            user_id="user",
                            max_concurrency=3,
                            publish_ready=None,
                        )
                    ]
            return calls, max_active, events

        calls, max_active, events = asyncio.run(run_case())
        self.assertEqual(set(calls), {0, 1, 2, 3})
        self.assertLessEqual(max_active, 3)
        self.assertTrue(any("第 4 章 PDF" in event for event in events))

    def test_tex_prefetch_limit_is_per_immersive_request(self):
        from tempfile import TemporaryDirectory

        async def run_case():
            active = 0
            max_active = 0

            async def fake_retry(**kwargs):
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.01)
                active -= 1
                return {"ok": True, "attempts": 1, "error": ""}

            async def consume_one(prefix):
                with TemporaryDirectory() as directory:
                    course = CourseLayout(Path(directory) / prefix)
                    course.ensure_dirs(chapter_ids=[1, 2, 3])
                    chapters = [
                        {"chapter_id": 1, "title": f"{prefix}-1"},
                        {"chapter_id": 2, "title": f"{prefix}-2"},
                        {"chapter_id": 3, "title": f"{prefix}-3"},
                    ]
                    return [
                        event
                        async for event in service._stream_parallel_tex_prefetch(
                            topic=prefix,
                            chapters=chapters,
                            chapter_items=list(enumerate(chapters)),
                            course=course,
                            layout=object(),
                            user_id=prefix,
                            max_concurrency=3,
                        )
                    ]

            with (
                patch.object(service, "_pdf_is_ready", return_value=False),
                patch.object(
                    service, "_run_tex_writer_with_retry", side_effect=fake_retry
                ),
            ):
                await asyncio.gather(consume_one("user-a"), consume_one("user-b"))
            return max_active

        max_active = asyncio.run(run_case())
        self.assertGreater(max_active, 3)
        self.assertLessEqual(max_active, 6)

    def test_enrichment_uses_request_local_rolling_concurrency_window(self):
        from tempfile import TemporaryDirectory

        async def run_case():
            with TemporaryDirectory() as directory:
                course = CourseLayout(Path(directory) / "course")
                course.ensure_dirs(chapter_ids=[1, 2, 3, 4])
                chapters = [
                    {"chapter_id": 1, "title": "第一章", "knowledge_points": []},
                    {"chapter_id": 2, "title": "第二章", "knowledge_points": []},
                    {"chapter_id": 3, "title": "第三章", "knowledge_points": []},
                    {"chapter_id": 4, "title": "第四章", "knowledge_points": []},
                ]
                for ch in chapters:
                    ch_id = ch["chapter_id"]
                    course.tex_file(ch_id).write_text(
                        "\\begin{frame}x\\end{frame}", encoding="utf-8"
                    )
                    course.pdf_file(ch_id).write_bytes(b"%PDF-1.7\n" + b"x" * 80)

                workspace = {
                    "workspace": {
                        "chapters": [
                            {
                                "chapter_id": ch["chapter_id"],
                                "title": ch["title"],
                                "status": "learning_ready",
                            }
                            for ch in chapters
                        ]
                    },
                    "canvas_blocks": [],
                }
                published = {
                    ch["chapter_id"]: {
                        "chapter_id": ch["chapter_id"],
                        "title": ch["title"],
                        "pdf_block": {
                            "id": f"pdf_ch{ch['chapter_id']}",
                            "type": "pdf",
                            "status": "ready",
                            "chapter_id": ch["chapter_id"],
                            "data": {},
                        },
                        "status_block": {
                            "id": f"chapter_{ch['chapter_id']}_status",
                            "type": "chapter_status",
                            "status": "learning_ready",
                            "chapter_id": ch["chapter_id"],
                            "data": {},
                        },
                        "pdf_doc_id": f"pdf-{ch['chapter_id']}",
                        "pdf_rel": f"chapter_{ch['chapter_id']:02d}.pdf",
                        "pdf_revision": "rev",
                        "num_frames": 1,
                    }
                    for ch in chapters
                }
                active = 0
                max_active = 0
                starts = []
                finishes = []
                started_first_three = asyncio.Event()
                release_slow = asyncio.Event()
                fourth_started = asyncio.Event()

                def fake_read_workspace(_session_id):
                    return workspace

                def fake_update_workspace(_session_id, **patch):
                    nested = patch.get("workspace") or {}
                    if nested:
                        workspace["workspace"] = {
                            **workspace.get("workspace", {}),
                            **nested,
                        }
                    for key, value in patch.items():
                        if key != "workspace" and value is not None:
                            workspace[key] = value
                    return workspace

                def fake_upsert(_session_id, block, **_kwargs):
                    blocks = workspace.setdefault("canvas_blocks", [])
                    for idx, item in enumerate(blocks):
                        if item.get("id") == block.get("id"):
                            blocks[idx] = {**item, **block}
                            break
                    else:
                        blocks.append(block)
                    return workspace

                async def fake_stream(_agent, prompt, *_args, **_kwargs):
                    nonlocal active, max_active
                    match = service.re.search(r"第 (\d+) 章", prompt)
                    ch_id = int(match.group(1))
                    starts.append(ch_id)
                    active += 1
                    max_active = max(max_active, active)
                    if len(starts) == 3:
                        started_first_three.set()
                    if ch_id == 4:
                        fourth_started.set()
                    if ch_id in {1, 3}:
                        await release_slow.wait()
                    else:
                        await asyncio.sleep(0.01)
                    course.exercises_file(ch_id).write_text(
                        "题目" * 40, encoding="utf-8"
                    )
                    active -= 1
                    finishes.append(ch_id)
                    yield service.sse_event(
                        "agent_event", agent_type="exercises", chapter_id=ch_id
                    )

                async def consume():
                    return [
                        event
                        async for event in service._stream_parallel_chapter_enrichment(
                            session_id="session",
                            topic="射影几何",
                            chapters=chapters,
                            chapter_items=list(enumerate(chapters)),
                            course=course,
                            layout=object(),
                            user_id="user",
                            enable_audio=False,
                            enable_exercises=True,
                            tts_llm=None,
                            total_ch=4,
                            pct_per_chapter=10,
                            published_pdf_by_chapter=published,
                            state_write_lock=asyncio.Lock(),
                            max_concurrency=3,
                        )
                    ]

                with (
                    patch.object(
                        service, "read_workspace", side_effect=fake_read_workspace
                    ),
                    patch.object(
                        service, "update_workspace", side_effect=fake_update_workspace
                    ),
                    patch.object(
                        service, "upsert_canvas_block", side_effect=fake_upsert
                    ),
                    patch.object(service, "append_session_file"),
                    patch.object(
                        service,
                        "register_chapter_exercises",
                        side_effect=lambda **kw: f"ex-{kw['chapter_id']}",
                    ),
                    patch.object(
                        service,
                        "_build_agent_by_name",
                        side_effect=lambda *args: object(),
                    ),
                    patch.object(
                        service, "stream_agent_events", side_effect=fake_stream
                    ),
                    patch.object(service, "archive_immersive_chapter"),
                    patch.object(service, "pack_chapter_bundle", return_value=None),
                    patch.object(service, "extract_and_persist_nodes", return_value=[]),
                    patch.object(service, "get_llm", return_value=object()),
                ):
                    consumer = asyncio.create_task(consume())
                    await asyncio.wait_for(started_first_three.wait(), timeout=1)
                    self.assertEqual(set(starts[:3]), {1, 2, 3})
                    self.assertLessEqual(max_active, 3)
                    await asyncio.wait_for(fourth_started.wait(), timeout=1)
                    self.assertIn(2, finishes)
                    self.assertNotIn(1, finishes)
                    self.assertNotIn(3, finishes)
                    self.assertLessEqual(max_active, 3)
                    release_slow.set()
                    events = await asyncio.wait_for(consumer, timeout=1)
            return starts, finishes, max_active, events, published

        starts, finishes, max_active, events, published = asyncio.run(run_case())
        self.assertEqual(set(starts[:3]), {1, 2, 3})
        self.assertEqual(starts[3], 4)
        self.assertEqual(set(finishes), {1, 2, 3, 4})
        self.assertLessEqual(max_active, 3)
        self.assertEqual(len(published["__chapter_results__"]), 4)
        self.assertTrue(any('"type": "chapter_done"' in event for event in events))

    def test_generation_progress_tracks_enrichment_phases(self):
        from repositories.session_repo import summarize_generation_progress

        def ch(cid, **extra):
            return {"chapter_id": cid, "status": "learning_ready", **extra}

        base = {"planned_chapters": 3, "enable_exercises": True, "enable_audio": True}

        # PDF 未齐 -> pdf 阶段
        p = summarize_generation_progress(
            {**base, "chapters": [ch(1), ch(2), {"chapter_id": 3, "status": "pending"}]}
        )
        self.assertEqual(p["phase"], "pdf")
        self.assertEqual(p["pdf"]["done"], 2)

        # PDF 齐、习题/语音未完 -> enrichment；失败也算终态
        steps_running = {"exercises": "running", "audio": "running", "kg": "pending"}
        steps_done = {"exercises": "done", "audio": "failed", "kg": "pending"}
        p = summarize_generation_progress(
            {
                **base,
                "chapters": [
                    ch(1, enrich_steps=steps_done),
                    ch(2, enrich_steps=steps_running),
                    ch(3, enrich_steps=steps_done),
                ],
            }
        )
        self.assertEqual(p["phase"], "enrichment")
        self.assertEqual(p["exercises"]["done"], 2)
        self.assertEqual(p["audio"]["failed"], 2)

        # 习题/语音都终态、图谱未完 -> nodes
        p = summarize_generation_progress(
            {**base, "chapters": [ch(i, enrich_steps=steps_done) for i in (1, 2, 3)]}
        )
        self.assertEqual(p["phase"], "nodes")
        self.assertEqual(p["kg"]["done"], 0)

        # 全部终态 -> done
        all_done = {"exercises": "done", "audio": "done", "kg": "done"}
        p = summarize_generation_progress(
            {**base, "chapters": [ch(i, enrich_steps=all_done) for i in (1, 2, 3)]}
        )
        self.assertEqual(p["phase"], "done")
        self.assertEqual(p["kg"]["done"], 3)

    def test_generation_progress_handles_disabled_features_and_legacy_data(self):
        from repositories.session_repo import summarize_generation_progress

        legacy = {
            "planned_chapters": 2,
            "enable_exercises": True,
            "enable_audio": False,
            "chapters": [
                {
                    "chapter_id": 1,
                    "status": "ready",
                    "artifact_status": {"pdf": True, "exercises": True},
                },
                {
                    "chapter_id": 2,
                    "status": "ready",
                    "artifact_status": {"pdf": True, "exercises": True},
                },
            ],
        }
        p = summarize_generation_progress(legacy)
        self.assertIsNone(p["audio"])  # 语音未开启
        self.assertIsNone(p["kg"])  # 旧数据无图谱状态
        self.assertEqual(p["exercises"]["done"], 2)
        self.assertEqual(p["phase"], "done")

    def test_normalize_math_keeps_latex_commands_starting_with_n_r_t(self):
        text = r"变化链 $x \to u \to y$，以及 $\nu$、$\tau$、$\rho$。"
        self.assertEqual(service._normalize_math_in_text(text), text)

    def test_enrichment_starts_before_incoming_queue_is_closed(self):
        from tempfile import TemporaryDirectory

        async def run_case():
            with TemporaryDirectory() as directory:
                course = CourseLayout(Path(directory) / "course")
                course.ensure_dirs(chapter_ids=[1, 2])
                chapters = [
                    {"chapter_id": 1, "title": "第一章", "knowledge_points": []},
                    {"chapter_id": 2, "title": "第二章", "knowledge_points": []},
                ]
                workspace = {"workspace": {"chapters": []}, "canvas_blocks": []}
                published = {
                    ch["chapter_id"]: {
                        "chapter_id": ch["chapter_id"],
                        "title": ch["title"],
                        "pdf_block": {
                            "id": f"pdf_ch{ch['chapter_id']}",
                            "type": "pdf",
                            "status": "ready",
                            "chapter_id": ch["chapter_id"],
                            "data": {},
                        },
                        "status_block": {
                            "id": f"chapter_{ch['chapter_id']}_status",
                            "type": "chapter_status",
                            "status": "learning_ready",
                            "chapter_id": ch["chapter_id"],
                            "data": {},
                        },
                        "pdf_doc_id": f"pdf-{ch['chapter_id']}",
                        "pdf_rel": f"chapter_{ch['chapter_id']:02d}.pdf",
                        "pdf_revision": "rev",
                        "num_frames": 1,
                    }
                    for ch in chapters
                }
                started: list[int] = []
                first_started = asyncio.Event()

                def fake_update_workspace(_sid, **patch):
                    nested = patch.get("workspace") or {}
                    if nested:
                        workspace["workspace"] = {**workspace["workspace"], **nested}
                    return workspace

                async def fake_stream(_agent, prompt, *_args, **_kwargs):
                    ch_id = int(service.re.search(r"第 (\d+) 章", prompt).group(1))
                    started.append(ch_id)
                    first_started.set()
                    course.exercises_file(ch_id).write_text(
                        "题目" * 40, encoding="utf-8"
                    )
                    yield service.sse_event(
                        "agent_event", agent_type="exercises", chapter_id=ch_id
                    )

                incoming: asyncio.Queue = asyncio.Queue()

                async def consume():
                    return [
                        event
                        async for event in service._stream_parallel_chapter_enrichment(
                            session_id="session",
                            topic="射影几何",
                            chapters=chapters,
                            chapter_items=[],
                            course=course,
                            layout=object(),
                            user_id="user",
                            enable_audio=False,
                            enable_exercises=True,
                            tts_llm=None,
                            total_ch=2,
                            pct_per_chapter=10,
                            published_pdf_by_chapter=published,
                            state_write_lock=asyncio.Lock(),
                            max_concurrency=3,
                            incoming=incoming,
                        )
                    ]

                with (
                    patch.object(
                        service, "read_workspace", side_effect=lambda _s: workspace
                    ),
                    patch.object(
                        service, "update_workspace", side_effect=fake_update_workspace
                    ),
                    patch.object(service, "upsert_canvas_block"),
                    patch.object(service, "append_session_file"),
                    patch.object(
                        service,
                        "register_chapter_exercises",
                        side_effect=lambda **kw: f"ex-{kw['chapter_id']}",
                    ),
                    patch.object(
                        service, "_build_agent_by_name", side_effect=lambda *a: object()
                    ),
                    patch.object(
                        service, "stream_agent_events", side_effect=fake_stream
                    ),
                    patch.object(service, "archive_immersive_chapter"),
                    patch.object(service, "pack_chapter_bundle", return_value=None),
                    patch.object(service, "extract_and_persist_nodes", return_value=[]),
                    patch.object(service, "get_llm", return_value=object()),
                ):
                    consumer = asyncio.create_task(consume())
                    incoming.put_nowait((0, chapters[0]))
                    # 第 2 章尚未入队、队列未关闭，第 1 章也应已开始补全
                    await asyncio.wait_for(first_started.wait(), timeout=1)
                    self.assertEqual(started, [1])
                    self.assertFalse(consumer.done())
                    incoming.put_nowait((1, chapters[1]))
                    incoming.put_nowait(None)
                    await asyncio.wait_for(consumer, timeout=2)
            return started, published

        started, published = asyncio.run(run_case())
        self.assertEqual(sorted(started), [1, 2])
        self.assertEqual(len(published["__chapter_results__"]), 2)

    def test_resume_audit_queues_existing_pdf_when_exercises_are_missing(self):
        chapters = [{"chapter_id": 1, "title": "透视"}]
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            course = CourseLayout(Path(directory) / "course")
            course.ensure_dirs(chapter_ids=[1])
            course.tex_file(1).write_text("%" + "x" * 80, encoding="utf-8")
            course.pdf_file(1).write_bytes(b"%PDF-1.7\n" + b"x" * 80)

            with (
                patch.object(service, "_chapter_pdf_error", return_value=None),
                patch.object(service, "register_chapter_pdf", return_value="pdf-doc"),
                patch.object(service, "append_session_file"),
                patch.object(service, "upsert_canvas_block"),
            ):
                audited, pending, generated = service._audit_resume_chapters(
                    "session",
                    course,
                    chapters,
                    [{"chapter_id": 1, "title": "透视", "status": "learning_ready"}],
                    topic="射影几何",
                    user_id="user",
                    enable_audio=False,
                    enable_exercises=True,
                )

        self.assertEqual(pending, {1})
        self.assertEqual(generated, 1)
        self.assertEqual(audited[0]["status"], "learning_ready")
        self.assertIn("exercises", audited[0]["artifact_missing"])

    def test_publish_chapter_pdf_ready_emits_learning_ready_for_later_chapter(self):
        from tempfile import TemporaryDirectory

        async def run_case():
            workspace = {
                "workspace": {
                    "chapters": [
                        {"chapter_id": 1, "title": "第一章", "status": "pending"},
                        {"chapter_id": 2, "title": "第二章", "status": "pending"},
                    ]
                },
                "canvas_blocks": [],
            }
            blocks = []
            updates = []
            session_files = []
            all_files = []

            def fake_read_workspace(_session_id):
                return workspace

            def fake_update_workspace(_session_id, **patch):
                updates.append(patch)
                nested = patch.get("workspace") or {}
                if nested:
                    workspace["workspace"] = {
                        **workspace.get("workspace", {}),
                        **nested,
                    }
                for key, value in patch.items():
                    if key != "workspace" and value is not None:
                        workspace[key] = value
                return workspace

            def fake_upsert(_session_id, block, **_kwargs):
                blocks.append(block)
                existing_blocks = workspace.setdefault("canvas_blocks", [])
                for idx, item in enumerate(existing_blocks):
                    if item.get("id") == block.get("id"):
                        existing_blocks[idx] = {**item, **block}
                        break
                else:
                    existing_blocks.append(block)
                return workspace

            with TemporaryDirectory() as directory:
                course = CourseLayout(Path(directory) / "course")
                course.ensure_dirs(chapter_ids=[1, 2])
                chapters = [
                    {"chapter_id": 1, "title": "第一章"},
                    {"chapter_id": 2, "title": "第二章"},
                ]
                with (
                    patch.object(service, "_pdf_is_ready", return_value=True),
                    patch.object(service, "_pdf_revision", return_value="rev-2"),
                    patch.object(service, "count_beamer_frames", return_value=7),
                    patch.object(
                        service, "read_workspace", side_effect=fake_read_workspace
                    ),
                    patch.object(
                        service, "update_workspace", side_effect=fake_update_workspace
                    ),
                    patch.object(
                        service, "upsert_canvas_block", side_effect=fake_upsert
                    ),
                    patch.object(service, "register_chapter_pdf", return_value="doc-2"),
                    patch.object(
                        service,
                        "append_session_file",
                        side_effect=lambda *args: session_files.append(args),
                    ),
                ):
                    publication = await service._publish_chapter_pdf_ready(
                        session_id="session",
                        topic="射影几何",
                        user_id="user",
                        course=course,
                        chapters=chapters,
                        index=1,
                        ch_info=chapters[1],
                        total_ch=2,
                        enable_audio=True,
                        generation_started_at=None,
                        all_files_for_session=all_files,
                    )
            return publication, workspace, blocks, updates, session_files, all_files

        publication, workspace, blocks, updates, session_files, all_files = asyncio.run(
            run_case()
        )
        self.assertIsNotNone(publication)
        self.assertEqual(publication["chapter_id"], 2)
        self.assertEqual(publication["pdf_doc_id"], "doc-2")
        self.assertTrue(any(block.get("id") == "pdf_ch2" for block in blocks))
        self.assertTrue(any(block.get("id") == "chapter_2_status" for block in blocks))
        self.assertEqual(
            workspace["workspace"]["chapters"][1]["status"], "learning_ready"
        )
        self.assertEqual(workspace["workspace"]["chapters"][1]["pdf_doc_id"], "doc-2")
        self.assertEqual(
            all_files,
            [{"file_id": "doc-2", "file_type": "chapter_pdf", "title": "第2章 第二章"}],
        )
        self.assertEqual(session_files[0][1], "doc-2")
        events = [
            json.loads(event[len("data: ") :].strip())
            for event in publication["events"]
        ]
        self.assertEqual(events[0]["type"], "workspace_update")
        self.assertEqual(events[0]["block"]["id"], "pdf_ch2")
        self.assertEqual(events[-1]["type"], "chapter_learning_ready")
        self.assertEqual(events[-1]["data"]["chapter_id"], 2)

    def test_research_fallback_payload_contains_outline_context(self):
        payload = service._build_research_fallback_payload(
            5,
            "二次曲线初步",
            {
                "description": "理解二次曲线在射影平面中的统一表达。",
                "knowledge_points": ["齐次二次型", "极点极线"],
                "search_keywords": ["projective conic", "pole polar"],
            },
        )

        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["chapter_id"], 5)
        self.assertIn("二次曲线在射影平面", payload["raw_text"])
        self.assertIn("齐次二次型", payload["raw_text"])
        self.assertIn("projective conic", payload["raw_text"])

    def test_learning_ready_replaces_only_the_matching_chapter(self):
        workspace = {
            "workspace": {
                "chapters": [
                    {"chapter_id": 1, "title": "第一章", "status": "pending"},
                    {"chapter_id": 2, "title": "第二章", "status": "pending"},
                ]
            }
        }
        with patch.object(service, "update_workspace", return_value=workspace):
            chapters = service._replace_chapter_workspace_state(
                "session",
                1,
                {
                    "chapter_id": 1,
                    "title": "第一章",
                    "status": "learning_ready",
                    "pdf_doc_id": "pdf-1",
                },
            )
        self.assertEqual(chapters[0]["status"], "learning_ready")
        self.assertEqual(chapters[0]["pdf_doc_id"], "pdf-1")
        self.assertEqual(chapters[1], workspace["workspace"]["chapters"][1])

    def test_learning_ready_is_appended_when_a_legacy_workspace_lacks_chapter(self):
        with patch.object(service, "update_workspace", return_value={"workspace": {}}):
            chapters = service._replace_chapter_workspace_state(
                "session",
                3,
                {"chapter_id": 3, "title": "第三章", "status": "learning_ready"},
            )
        self.assertEqual(
            chapters, [{"chapter_id": 3, "title": "第三章", "status": "learning_ready"}]
        )


class ImmersiveSuggestionsTests(unittest.TestCase):
    def setUp(self):
        suggestions._suggestions_cache.clear()

    def test_suggestions_returns_backend_defaults_without_profile(self):
        with (
            patch.object(suggestions, "_read_profile", return_value=""),
            patch.object(suggestions, "_get_learned_topics", return_value=[]),
        ):
            result = asyncio.run(suggestions.generate_suggestions("user"))

        self.assertEqual(result["source"], "default")
        self.assertGreaterEqual(len(result["suggestions"]), 8)
        self.assertTrue(all(item.get("text") for item in result["suggestions"]))

    def test_suggestions_retries_empty_llm_response(self):
        class FakeLLM:
            def __init__(self):
                self.calls = 0

            async def async_think(self, messages, config=None):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(
                        content="",
                        is_error=False,
                        finish_reason="length",
                        usage={"completion_tokens": 1536},
                    )
                return SimpleNamespace(
                    content='{"suggestions":[{"text":"射影几何","emoji":"📐","size":"xl","reason":"适合深入空间直觉"}]}',
                    is_error=False,
                    finish_reason="stop",
                    usage={"completion_tokens": 64},
                )

        fake_llm = FakeLLM()
        with patch.object(suggestions, "get_llm", return_value=fake_llm):
            result = asyncio.run(
                suggestions._call_llm_for_suggestions(
                    "user",
                    "用户喜欢几何与推导",
                    ["透视", "齐次坐标"],
                )
            )

        self.assertEqual(fake_llm.calls, 2)
        self.assertEqual(result[0]["text"], "射影几何")

    def test_suggestions_falls_back_to_non_empty_defaults_when_llm_fails(self):
        class EmptyLLM:
            async def async_think(self, messages, config=None):
                return SimpleNamespace(
                    content="",
                    is_error=False,
                    finish_reason="length",
                    usage={"completion_tokens": 1536},
                )

        with (
            patch.object(suggestions, "_read_profile", return_value="用户喜欢物理"),
            patch.object(suggestions, "_get_learned_topics", return_value=["牛顿力学"]),
            patch.object(suggestions, "get_llm", return_value=EmptyLLM()),
        ):
            result = asyncio.run(suggestions.generate_suggestions("user"))

        self.assertEqual(result["source"], "default")
        self.assertGreaterEqual(len(result["suggestions"]), 8)


if __name__ == "__main__":
    unittest.main()
