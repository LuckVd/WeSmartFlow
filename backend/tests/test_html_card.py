"""Offline regressions for HTML cards; no model calls or production database writes."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lxml import html as dom
from agent_core.agent.events import AgentFinalEvent, AgentFinishReason
from agent_core.runtime import new_context
from agents.tools import generate_html_card as card
from agents.tools.html_card_document import (
    CardValidationError,
    archive_card_images,
    prepare_card_html,
)


VALID_CARD = '<h1 class="card-title">惯性</h1><p class="card-body">物体具有保持原有运动状态的性质，质量越大，惯性越大。</p>'


class CardDocumentTests(unittest.TestCase):
    def test_nested_math_and_unicode_survive_without_instruction_filler(self):
        formula = r"$$\sum_{i=1}^{n} x_i = \frac{n(n+1)}{2}$$"
        explanation = "保留适用条件和符号含义，" * 13
        raw = (
            '<section><h1>求和 𠮷</h1><div class="two-col"><div class="col-item">'
            + explanation
            + formula
            + '</div><div class="col-item"><strong>条件</strong>n 为正整数。</div></div></section>'
        )
        result, _ = prepare_card_html(raw, title="求和")
        self.assertIn(explanation, result)
        self.assertIn(formula, result)
        self.assertIn("𠮷", result)
        short, _ = prepare_card_html(VALID_CARD, title="惯性")
        self.assertNotIn("核心提示", short)

    def test_full_document_and_nested_titles_have_one_hosted_style(self):
        raw = """```html
<!DOCTYPE html><html><head><style>body { display: none }</style></head>
<body onload="alert(1)"><div class="card"><h1 class="card-title">标题</h1>
<section><h1 class="card-title">补充</h1><p style="color:white;position:fixed" onclick="alert(1)">完整解释</p></section>
<script>alert(1)</script></div></body></html>
```"""
        result, _ = prepare_card_html(raw, title="标题")
        tree = dom.fragment_fromstring(result, create_parent="div")
        self.assertEqual(len(tree.find_class("card-title")), 1)
        self.assertEqual(len(tree.find_class("card-subtitle")), 1)
        self.assertFalse(tree.find_class("card"))
        self.assertFalse(tree.xpath(".//script|.//style|.//*[@style]|.//*[@onclick]"))
        self.assertIn("完整解释", result)

    def test_title_only_and_plain_text_do_not_become_fake_successes(self):
        for raw in (
            "",
            "这是模型的说明文字。" * 10,
            '<div><h1 class="card-title">只有标题</h1></div>',
            "<script>alert(1)</script>",
        ):
            with self.subTest(raw=raw), self.assertRaises(CardValidationError):
                prepare_card_html(raw, title="标题")

    def test_nested_density_is_reported_instead_of_silently_deleted(self):
        raw = (
            "<section><h1>标题</h1>"
            + "".join(f'<p class="card-body">第 {i} 个完整观点</p>' for i in range(4))
            + "</section>"
        )
        with self.assertRaisesRegex(CardValidationError, "card-body"):
            prepare_card_html(raw, title="标题")
        table = "<table>" + "<tr><td>比较维度</td><td>解释</td></tr>" * 6 + "</table>"
        with self.assertRaisesRegex(CardValidationError, "5 行"):
            prepare_card_html(table, title="对比")

    def test_progress_value_survives_but_arbitrary_styles_do_not(self):
        result, _ = prepare_card_html(
            VALID_CARD
            + '<div class="progress-bar" style="color:white; --pct: 37.5%; width:9000px"></div>',
            title="标题",
        )
        self.assertIn('style="--pct: 37.5%"', result)
        self.assertNotIn("9000px", result)
        for value in ("", "--pct: 500%", "--pct: calc(5%)"):
            with self.subTest(value=value), self.assertRaises(CardValidationError):
                prepare_card_html(
                    VALID_CARD + f'<div class="progress-bar" style="{value}"></div>',
                    title="标题",
                )

    def test_nested_images_are_archived_and_only_src_is_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, output = Path(tmp) / "work", Path(tmp) / "output"
            source = work / "nested" / "diagram one.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"image fixture")
            raw = (
                VALID_CARD
                + '<img src="nested/diagram one.png" width=1000 height=200 style="object-fit:cover" alt="示意图">'
            )
            result, _ = prepare_card_html(raw, title="惯性", work_dir=work)
            self.assertNotIn("height=", result)
            self.assertNotIn("object-fit", result)
            result += f"<p>{source}</p>"
            archived = archive_card_images(
                result, work_dir=work, card_dir=output, card_id="card-id"
            )
            self.assertIn(
                "/api/documents/card-id/asset/images/nested/diagram%20one.png", archived
            )
            self.assertIn(str(source), archived)
            self.assertTrue((output / "images/nested/diagram one.png").is_file())
            # Both lexical and resolved paths work (notably /tmp on macOS).
            for path in (str(source), str(source.resolve()), source.as_uri()):
                prepare_card_html(
                    VALID_CARD + f'<img src="{path}">', title="惯性", work_dir=work
                )

    def test_missing_external_and_escaping_images_require_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            outside = Path(tmp) / "outside.png"
            outside.write_bytes(b"outside")
            (work / "link.png").symlink_to(outside)
            for src in (
                "missing.png",
                "../outside.png",
                "link.png",
                "https://example.com/image.png",
            ):
                with self.subTest(src=src), self.assertRaises(CardValidationError):
                    prepare_card_html(
                        VALID_CARD + f'<img src="{src}">', title="惯性", work_dir=work
                    )

    def test_document_title_is_escaped(self):
        result = card._wrap_html(VALID_CARD, "</title><script>alert(1)</script>")
        self.assertIn("&lt;/title&gt;&lt;script&gt;", result)

    def test_image_tool_matches_prompt_and_owns_its_output_directory(self):
        delegate = MagicMock()
        delegate.parameters = {
            "properties": {
                "prompt": {"type": "string"},
                "output_dir": {"type": "string"},
            }
        }
        image_tool = card._CardImageTool(delegate, Path("/tmp/card-image"))
        self.assertEqual(image_tool.name, "generate_teaching_image")
        self.assertNotIn("output_dir", image_tool.parameters["properties"])
        image_tool.run(prompt="教学图", output_dir="/unrelated")
        self.assertEqual(delegate.run.call_args.kwargs["output_dir"], "/tmp/card-image")
        self.assertTrue(image_tool.run(prompt="再画一张").startswith("Error:"))
        delegate.run.assert_called_once()


class FakeWriter:
    def __init__(self, results):
        self.results = iter(results)
        self.requests = []
        self.contexts = []

    async def async_stream(self, request, ctx=None):
        self.requests.append(request)
        self.contexts.append(ctx)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        if result is not None:
            yield result


def stop(body):
    return AgentFinalEvent(body, AgentFinishReason.STOP)


class CardGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def run_tool(self, results, *, fail_save=False, user_id="user", ctx=None):
        with tempfile.TemporaryDirectory() as tmp:
            writer = FakeWriter(results)
            with (
                patch.object(card, "CARDS_DIR", Path(tmp)),
                patch.object(
                    card, "_build_html_card_writer_agent", return_value=writer
                ),
                patch.object(card, "DocumentRepository") as repo,
            ):
                if fail_save:
                    repo.return_value.register_produced.side_effect = RuntimeError(
                        "database unavailable"
                    )
                tool = card.GenerateHtmlCardTool(user_id=user_id).bind_context(ctx)
                events = [
                    e
                    async for e in tool.async_stream_run(
                        title="惯性", content="解释惯性，不要复述此指令"
                    )
                ]
                files = list(Path(tmp).rglob("card.html"))
                return (
                    events,
                    writer,
                    repo.return_value.register_produced.call_count,
                    [p.read_text() for p in files],
                    list(Path(tmp).iterdir()),
                )

    async def test_valid_card_uses_one_pass_and_success_follows_registration(self):
        events, writer, saves, files, _ = await self.run_tool([stop(VALID_CARD)])
        self.assertEqual(len(writer.requests), 1)
        self.assertEqual(saves, 1)
        self.assertEqual(len(files), 1)
        self.assertIn("file_id", json.loads(events[-1]))
        self.assertNotIn("不要复述此指令", files[0])

    async def test_invalid_card_has_one_bounded_repair_with_concrete_feedback(self):
        events, writer, saves, _, _ = await self.run_tool(
            [stop("<h1>惯性</h1>"), stop(VALID_CARD)]
        )
        self.assertEqual(len(writer.requests), 2)
        self.assertIn("卡片只有标题", writer.requests[1])
        self.assertEqual(saves, 1)
        self.assertIn("file_id", json.loads(events[-1]))

    async def test_failed_repair_and_missing_final_do_not_publish(self):
        for results in (
            [stop(""), stop("")],
            [None],
            [RuntimeError("provider failed")],
        ):
            with self.subTest(results=results):
                events, writer, saves, _, entries = await self.run_tool(results)
                self.assertTrue(events[-1].startswith("Error:"))
                self.assertLessEqual(len(writer.requests), 2)
                self.assertEqual(saves, 0)
                self.assertEqual(entries, [])

    async def test_interrupted_outputs_are_not_published_or_retried(self):
        for reason in (
            AgentFinishReason.CANCELLED,
            AgentFinishReason.BUDGET,
            AgentFinishReason.MAX_STEPS,
            "error",
            "",
        ):
            with self.subTest(reason=reason):
                events, writer, saves, _, entries = await self.run_tool(
                    [AgentFinalEvent(VALID_CARD, reason)]
                )
                self.assertTrue(events[-1].startswith("Error:"))
                self.assertEqual(len(writer.requests), 1)
                self.assertEqual(saves, 0)
                self.assertEqual(entries, [])

    async def test_registration_failure_cleans_up_and_never_reports_success(self):
        events, _, saves, _, entries = await self.run_tool(
            [stop(VALID_CARD)], fail_save=True
        )
        self.assertTrue(events[-1].startswith("Error:"))
        self.assertNotIn("卡片生成完成", events)
        self.assertEqual(saves, 1)
        self.assertEqual(entries, [])

    async def test_missing_user_fails_before_model_and_parent_context_is_inherited(
        self,
    ):
        events, writer, saves, _, _ = await self.run_tool([], user_id=None)
        self.assertTrue(events[-1].startswith("Error:"))
        self.assertFalse(writer.requests)
        parent = new_context(principal="user:user", scope="tutor")
        _, writer, _, _, _ = await self.run_tool([stop(VALID_CARD)], ctx=parent)
        child = writer.contexts[0]
        self.assertIs(child.budget, parent.budget)
        self.assertIs(child.is_cancelled, parent.is_cancelled)
        self.assertEqual(child.principal, parent.principal)


if __name__ == "__main__":
    unittest.main()
