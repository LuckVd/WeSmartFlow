"""Opt-in real browser checks: RUN_VIZ_BROWSER_TESTS=1 python -m pytest ..."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.tools.viz_runtime import check_viz_runtime, async_check_viz_runtime
from test_viz_quality import CODE, SPEC

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    os.environ.get("RUN_VIZ_BROWSER_TESTS") == "1", "opt-in Chromium integration"
)
class BrowserTests(unittest.TestCase):
    def test_async_runtime_executes_real_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "viz.js"
            path.write_text(CODE)
            report = asyncio.run(async_check_viz_runtime(path, SPEC))
            self.assertTrue(report["ok"], report)
            self.assertTrue((Path(tmp) / "preview.png").exists())

    def run_fixture(self, code, spec=SPEC, timeout=35):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "viz.js"
            path.write_text(code)
            return check_viz_runtime(path, spec, timeout=timeout)

    def test_interactive_canvas_and_theme_pass(self):
        report = self.run_fixture(CODE)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["interactions"][0]["output_changed"])

    def test_toggle_select_stepper_timeline_and_reset_are_exercised(self):
        code = """
const t = EduViz.toggle('显示', {default:true});
const s = EduViz.select('方向', {choices:[{label:'上升',value:'up'},{label:'下降',value:'down'}]});
const step = EduViz.stepper({total:4});
const time = EduViz.timeline({duration:2,autoPlay:false});
const b = EduViz.button('重置');
const text = EduViz.text('');
function render(){text.set(`${t.value} / ${s.value} / ${step.step} / ${time.time}`)}
t.onChange(render);s.onChange(render);step.onStep(render);time.onFrame(render);
b.onClick(()=>{step.reset();time.reset();render()});
"""
        spec = {
            **SPEC,
            "canvas": {"type": "none"},
            "controls": [
                {"type": k}
                for k in ["toggle", "select", "stepper", "timeline", "button"]
            ],
        }
        report = self.run_fixture(code, spec)
        self.assertTrue(report["ok"], report)
        self.assertTrue(all(c["output_changed"] for c in report["interactions"]))

    def test_blank_canvas_callback_error_and_host_overflow_fail(self):
        cases = {
            "blank": CODE.replace(
                "ax.redraw(() => ax.plot(x => k.value*x, {color:'brand'}));", ""
            ),
            "callback": CODE.replace(
                "m.set(k.value);",
                'if (k.value === 2) throw new Error("boundary broken"); m.set(k.value);',
            ),
            "overflow": CODE
            + '\ncanvas.style.width="1400px"; canvas.style.maxWidth="none";',
            "empty": "EduViz.getContainer();",
        }
        for name, code in cases.items():
            with self.subTest(name=name):
                report = self.run_fixture(code)
                self.assertFalse(report["ok"], report)
                self.assertTrue(report["errors"])

    def test_narrow_reflow_is_advisory_when_900px_host_fits(self):
        code = CODE + "\ncanvas.style.width='868px'; canvas.style.maxWidth='none';"
        report = self.run_fixture(code)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["initial"]["overflow"], 0)
        self.assertIn("light/600px 横向溢出 284px", report["warnings"])

    def test_short_probe_and_content_height_are_advisory(self):
        code = CODE.replace(
            "k.onChange(render)",
            "render(); k.onChange(() => {setTimeout(render, 800)})",
        )
        code += "\nEduViz.getContainer().style.paddingBottom='1000px';"
        report = self.run_fixture(code)
        self.assertTrue(report["ok"], report)
        self.assertTrue(any("短时抽样" in w for w in report["warnings"]), report)
        self.assertTrue(any("内容较高" in w for w in report["warnings"]), report)

    def test_infinite_loop_has_hard_deadline(self):
        report = self.run_fixture("for (;;) {}", timeout=4)
        self.assertFalse(report["ok"])
        self.assertIn("超时", report["errors"][0])

    def test_real_frontend_reports_initial_and_sdk_callback_errors(self):
        from playwright.sync_api import sync_playwright

        template_path = ROOT / "frontend/src/components/EduViz/sandboxTemplate.js"
        source = template_path.read_text().replace(
            "export const SANDBOX_HTML", "const SANDBOX_HTML"
        )
        node = Path(sys.executable).with_name("node")
        template = subprocess.check_output(
            [
                str(node),
                "--input-type=module",
                "-e",
                source + "\nprocess.stdout.write(SANDBOX_HTML)",
            ],
            text=True,
        )
        sdk = (template_path.parent / "eduviz-sdk.js").read_text()
        # These fixtures do not use math or external libraries; remove CDN assets.
        import re

        template = re.sub(r'<link[^>]+>|<script src="[^"]+"></script>', "", template)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                for code, expected in (
                    ("const = ;", "Unexpected"),
                    ("throw new Error('initial failure')", "initial failure"),
                    (
                        CODE.replace(
                            "m.set(k.value);", 'throw new Error("callback failure");'
                        ),
                        "callback failure",
                    ),
                    ('Promise.reject(new Error("async failure"));', "async failure"),
                ):
                    with self.subTest(expected=expected):
                        html = (
                            template.replace(
                                "__EDUVIZ_SDK_PLACEHOLDER__",
                                "<script>" + sdk + "</script>",
                            )
                            .replace("__THEME__", "light")
                            .replace(
                                "__USER_CODE_JSON__",
                                json.dumps(code).replace("<", "\\u003c"),
                            )
                        )
                        page.set_content("<html><body></body></html>")
                        page.evaluate(
                            "html => {window.messages=[];window.onmessage=e=>messages.push(e.data);const f=document.createElement('iframe');f.srcdoc=html;document.body.append(f)}",
                            html,
                        )
                        page.wait_for_function("messages.some(m => m.type === 'error')")
                        page.wait_for_timeout(250)
                        messages = page.evaluate("messages")
                        self.assertTrue(
                            any(
                                expected in m.get("message", "")
                                for m in messages
                                if m["type"] == "error"
                            ),
                            messages,
                        )
                        if expected != "async failure":
                            self.assertFalse(
                                any(m["type"] == "ready" for m in messages), messages
                            )
                # Canvas keeps its logical aspect ratio when the iframe is narrower.
                page.set_viewport_size({"width": 360, "height": 600})
                page.set_content("<body></body>")
                page.add_script_tag(content=sdk)
                ratio = page.evaluate(
                    "() => {const c=EduViz.createCanvas(520,300);const r=c.getBoundingClientRect();return r.width/r.height}"
                )
                self.assertAlmostEqual(ratio, 520 / 300, places=3)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
