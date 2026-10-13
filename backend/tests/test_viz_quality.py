"""Offline regressions for visualization contracts, retries and publication."""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.runtime import new_context
from agent_core.runtime.budget import Budget
from agent_core.llm.base import LLMResponse, StreamChunkEvent, StreamFinishEvent
from agents.tools import generate_viz as viz
from agents.tools.viz_quality import VizQualityError, VizSpec, VizReview, parse_contract
from agents.tools.viz_runtime import VizRuntimeUnavailable
from agents.tools.validate_viz_code import ValidateVizCodeTool

SPEC = {
    "title": "斜率",
    "concept": "直线斜率决定倾斜方向与程度",
    "viz_pattern": "parameter_exploration",
    "controls": [
        {
            "type": "slider",
            "name": "斜率 k",
            "purpose": "改变斜率",
            "expected_change": "直线转动，k=0 时水平",
            "range": {"min": -2, "max": 2, "step": 0.1, "default": 1},
        }
    ],
    "canvas": {"type": "axis2d", "description": "坐标系中的直线 y=kx，标明 x、y"},
    "display": [{"type": "metric", "name": "斜率", "purpose": "显示当前 k"}],
    "initial_state": "k=1，过原点的上升直线",
    "interaction_flow": "拖动 k 观察倾斜方向和程度",
    "key_insight": "正负决定方向，绝对值决定陡缓",
    "interaction_checks": [
        {"action": "k=0", "expected": "直线水平"},
        {"action": "k=-2", "expected": "直线从左向右下降"},
    ],
}
PASS = json.dumps({"blocking_issues": [], "suggestions": []})
FAIL = json.dumps(
    {
        "blocking_issues": ["控制回调没有更新主图或反馈，请在回调中调用 render"],
        "suggestions": [],
    }
)
CODE = "const k = EduViz.slider('斜率 k', {min:-2,max:2,step:0.1,default:1});\nconst m = EduViz.metric('斜率', {value:1});\nconst canvas = EduViz.createCanvas(520,300);\ncanvas.style.maxWidth='100%'; canvas.style.height='auto';\nconst ax = EduViz.axis2d(canvas, {xRange:[-3,3], yRange:[-6,6]});\nfunction render() { ax.redraw(() => ax.plot(x => k.value*x, {color:'brand'})); m.set(k.value); }\nk.onChange(render); EduViz.onThemeChange(render);"


def fake_llm(*outputs):
    llm = MagicMock(model_name="fixture")
    remaining = iter(outputs)

    async def stream(*args, **kwargs):
        output = next(remaining)
        yield StreamChunkEvent(delta=output, content=output)
        yield StreamFinishEvent(
            response=LLMResponse(content=output, usage={"total_tokens": 10})
        )

    llm.stream_think.side_effect = stream
    return llm


async def collect_stage(stream):
    result = None
    async for event in stream:
        if isinstance(event, viz._StageResult):
            result = event.value
    return result


async def collect_tool(tool):
    return [
        event async for event in tool.async_stream_run(title="斜率", concept="概念")
    ]


class ContractTests(unittest.TestCase):
    def test_select_choices_must_match_sdk_object_shape(self):
        control = {
            "type": "select",
            "name": "方向",
            "purpose": "选择方向",
            "expected_change": "图形方向改变",
        }
        for choices in (
            ["上升", "下降"],
            [{"label": "上升", "value": "up"}, {"label": "下降", "value": "up"}],
        ):
            with self.subTest(choices=choices), self.assertRaises(VizQualityError):
                parse_contract(
                    json.dumps({**SPEC, "controls": [{**control, "choices": choices}]}),
                    VizSpec,
                )

    def test_complete_spec_and_fenced_json(self):
        self.assertEqual(
            parse_contract("```json\n" + json.dumps(SPEC) + "\n```", VizSpec).title,
            "斜率",
        )

    def test_invalid_ranges_and_incomplete_designs_rejected(self):
        for change in (
            {"controls": []},
            {"initial_state": ""},
            {"viz_pattern": "invented"},
        ):
            with self.subTest(change=change), self.assertRaises(VizQualityError):
                parse_contract(json.dumps({**SPEC, **change}), VizSpec)
        for range_ in (
            {"min": 2, "max": -2, "step": 1, "default": 1},
            {"min": 0, "max": 1, "step": 0, "default": 2},
        ):
            bad = {**SPEC, "controls": [{**SPEC["controls"][0], "range": range_}]}
            with self.assertRaises(VizQualityError):
                parse_contract(json.dumps(bad), VizSpec)

    def test_review_requires_explicit_blockers_but_suggestions_do_not_block(self):
        for raw in (
            "{}",
            "[]",
            '{"blocking_issues":false,"suggestions":[]}',
            "unparseable",
        ):
            with self.subTest(raw=raw), self.assertRaises(VizQualityError):
                parse_contract(raw, VizReview)
        self.assertFalse(parse_contract(FAIL, VizReview).accepted)
        self.assertTrue(
            parse_contract(
                json.dumps(
                    {
                        "blocking_issues": [],
                        "suggestions": ["优化配色", "600px 布局溢出"],
                    }
                ),
                VizReview,
            ).accepted
        )


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_design_is_retried_but_never_published(self):
        llm = fake_llm("{}", "{}", "{}")
        with self.assertRaises(VizQualityError):
            await collect_stage(viz._design_viz(llm, "斜率", "概念", ""))
        self.assertEqual(llm.stream_think.call_count, 3)

    async def test_valid_design_proceeds_without_another_scoring_loop(self):
        llm = fake_llm("{}", json.dumps(SPEC))
        self.assertEqual(
            (await collect_stage(viz._design_viz(llm, "斜率", "概念", "")))["title"],
            "斜率",
        )
        self.assertEqual(llm.stream_think.call_count, 2)

    async def _code_loop(self, outputs, static="ok", runtime=None):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(viz, "get_llm", return_value=fake_llm(*outputs)),
            patch.object(ValidateVizCodeTool, "environment_error", return_value=None),
            patch.object(ValidateVizCodeTool, "run", return_value=static),
            patch.object(
                viz,
                "async_check_viz_runtime",
                return_value=runtime or {"ok": True, "errors": []},
            ),
        ):
            return await collect_stage(
                viz._run_code_loop(Path(tmp), SPEC, "user", "SDK", "")
            )

    async def test_static_failures_never_return_last_broken_code(self):
        with self.assertRaisesRegex(VizQualityError, "语法错误"):
            await self._code_loop([CODE] * 3, static="Error: 语法错误")

    async def test_runtime_failures_never_reach_review_or_publish(self):
        with self.assertRaisesRegex(VizQualityError, "无效控件"):
            await self._code_loop(
                [CODE] * 3, runtime={"ok": False, "errors": ["无效控件"]}
            )

    async def test_last_code_round_requires_valid_passing_review(self):
        with self.assertRaises(VizQualityError):
            await self._code_loop([item for _ in range(3) for item in (CODE, FAIL)])
        code, quality = await self._code_loop([CODE, FAIL, CODE, FAIL, CODE, PASS])
        self.assertEqual(code, CODE)
        self.assertEqual(quality["code_rounds"], 3)

    async def test_malformed_review_retries_reviewer_without_regenerating_code(self):
        code, quality = await self._code_loop([CODE, "{}", PASS])
        self.assertEqual(code, CODE)
        self.assertEqual(quality["code_rounds"], 1)
        with self.assertRaisesRegex(RuntimeError, "评审未返回有效"):
            await self._code_loop([CODE, "{}", "{}"])

    async def test_layout_warnings_and_optional_suggestions_allow_publication(self):
        review = json.dumps({"blocking_issues": [], "suggestions": ["建议缩短说明"]})
        code, quality = await self._code_loop(
            [CODE, review],
            runtime={
                "ok": True,
                "errors": [],
                "warnings": ["light/600px 横向溢出 284px"],
            },
        )
        self.assertEqual(code, CODE)
        self.assertEqual(quality["code_rounds"], 1)
        self.assertTrue(quality["runtime"]["warnings"])

    async def test_browser_unavailable_does_not_trigger_model_rewrite(self):
        llm = fake_llm(CODE)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(viz, "get_llm", return_value=llm),
            patch.object(ValidateVizCodeTool, "environment_error", return_value=None),
            patch.object(ValidateVizCodeTool, "run", return_value="ok"),
            patch.object(
                viz,
                "async_check_viz_runtime",
                side_effect=VizRuntimeUnavailable("无浏览器"),
            ),
        ):
            with self.assertRaises(VizRuntimeUnavailable):
                await collect_stage(
                    viz._run_code_loop(Path(tmp), SPEC, "user", "SDK", "")
                )
        self.assertEqual(llm.stream_think.call_count, 1)

    async def test_runtime_task_finishing_during_review_is_collected(self):
        llm = fake_llm(CODE)
        runtime_gate = None

        async def runtime_finishes_during_review(*args, **kwargs):
            await runtime_gate.wait()
            return {"ok": True, "errors": []}

        async def review_releases_runtime(*args, **kwargs):
            runtime_gate.set()
            await asyncio.sleep(0)
            yield viz._StageResult(parse_contract(PASS, VizReview))

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(viz, "get_llm", return_value=llm),
            patch.object(ValidateVizCodeTool, "environment_error", return_value=None),
            patch.object(ValidateVizCodeTool, "run", return_value="ok"),
            patch.object(
                viz,
                "async_check_viz_runtime",
                side_effect=runtime_finishes_during_review,
            ),
            patch.object(viz, "_review_code", side_effect=review_releases_runtime),
        ):
            runtime_gate = asyncio.Event()
            code, quality = await collect_stage(
                viz._run_code_loop(Path(tmp), SPEC, "user", "SDK", "")
            )
        self.assertEqual(code, CODE)
        self.assertTrue(quality["runtime"]["ok"])

    async def test_parent_budget_and_cancel_prevent_further_calls(self):
        ctx = new_context(budget=Budget(max_steps=1))
        llm = fake_llm("{}")
        with self.assertRaisesRegex(RuntimeError, "max_steps"):
            await collect_stage(viz._design_viz(llm, "斜率", "概念", "", ctx))
        self.assertEqual(llm.stream_think.call_count, 1)
        self.assertEqual(ctx.budget.tokens, 10)
        cancelled = new_context(is_cancelled=lambda: True)
        with self.assertRaises(Exception):
            await collect_stage(viz._design_viz(llm, "斜率", "概念", "", cancelled))
        self.assertEqual(llm.stream_think.call_count, 1)

    async def test_persistence_failure_removes_artifact_and_returns_error(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(viz, "VIZ_DIR", Path(tmp)),
            patch.object(
                viz,
                "get_llm",
                side_effect=[
                    fake_llm(json.dumps(SPEC)),
                    fake_llm(CODE, PASS),
                    fake_llm(json.dumps(SPEC)),
                    fake_llm(CODE, PASS),
                ],
            ),
            patch.object(ValidateVizCodeTool, "environment_error", return_value=None),
            patch.object(ValidateVizCodeTool, "run", return_value="ok"),
            patch.object(
                viz, "async_check_viz_runtime", return_value={"ok": True, "errors": []}
            ),
        ):
            tool = viz.GenerateInteractiveVizTool("user")
            with patch.object(
                tool, "_create_document_record", side_effect=RuntimeError("数据库失败")
            ):
                self.assertIn("Error:", (await collect_tool(tool))[-1])
            self.assertEqual(list(Path(tmp).iterdir()), [])
            with patch.object(tool, "_create_document_record") as register:
                viz_id = (await collect_tool(tool))[-1]
                register.assert_called_once()
            self.assertEqual((Path(tmp) / viz_id / "viz.js").read_text(), CODE)
            self.assertTrue(
                json.loads((Path(tmp) / viz_id / "meta.json").read_text())["quality"][
                    "runtime"
                ]["ok"]
            )
            timings = json.loads((Path(tmp) / viz_id / "meta.json").read_text())[
                "quality"
            ]["timings_ms"]
            self.assertIn("design_total", timings)
            self.assertIn("code_total", timings)


class StaticValidatorTests(unittest.TestCase):
    def test_missing_node_and_eslint_fail_closed(self):
        with patch("agents.tools.validate_viz_code._find_node", return_value=None):
            self.assertIsNotNone(ValidateVizCodeTool()._check_syntax(CODE))
        with patch(
            "agents.tools.validate_viz_code._ESLINT_BIN", Path("/missing/eslint")
        ):
            self.assertTrue(ValidateVizCodeTool()._check_eslint(CODE))

    def test_real_node_eslint_and_removed_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "viz.js"
            path.write_text(CODE)
            self.assertEqual(ValidateVizCodeTool().run(str(path)), "ok")
            path.write_text(CODE + "\nundefinedVariable();")
            self.assertIn("no-undef", ValidateVizCodeTool().run(str(path)))
            path.write_text(CODE + '\nEduViz.emit("fake");')
            self.assertIn("[API]", ValidateVizCodeTool().run(str(path)))


if __name__ == "__main__":
    unittest.main()
