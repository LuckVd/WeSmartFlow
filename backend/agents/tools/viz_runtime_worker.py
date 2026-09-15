"""Isolated browser worker. Invoked as a script; never imports app configuration."""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


_PROBE = r"""() => {
  const controls = [];
  const methods = {slider:'onChange', toggle:'onChange', select:'onChange',
                   stepper:'onStep', timeline:'onFrame', button:'onClick'};
  for (const [kind, method] of Object.entries(methods)) {
    const create = EduViz[kind];
    EduViz[kind] = (...args) => {
      const ctrl = create(...args);
      const record = {kind, ctrl, args, bound:false};
      const bind = ctrl[method];
      ctrl[method] = fn => { record.bound = true; return bind.call(ctrl, fn); };
      controls.push(record);
      return ctrl;
    };
  }
  const viz = EduViz.getContainer();
  const info = viz.nextElementSibling;
  function snapshot() {
    const canvases = [...viz.querySelectorAll('canvas')].map(c => c.toDataURL());
    return JSON.stringify([viz.innerHTML, info.innerHTML, canvases]);
  }
  function summary() {
    const box = viz.getBoundingClientRect();
    const canvases = [...viz.querySelectorAll('canvas')];
    const painted = canvases.some(canvas => {
      if (!canvas.width || !canvas.height) return false;
      // WebGL's default drawing buffer is cleared after compositing. Pixel changes
      // are captured through browser screenshots below rather than toDataURL.
      if (!canvas.getContext('2d')) return true;
      const copy = document.createElement('canvas');
      copy.width = canvas.width; copy.height = canvas.height;
      const ctx = copy.getContext('2d');
      ctx.drawImage(canvas, 0, 0);
      const data = ctx.getImageData(0, 0, copy.width, copy.height).data;
      for (let i = 4; i < data.length; i += 4) {
        if (data[i] !== data[0] || data[i+1] !== data[1] ||
            data[i+2] !== data[2] || data[i+3] !== data[3]) return true;
      }
      return false;
    });
    return {
      controls: controls.map(r => ({kind:r.kind, bound:r.bound, name:r.args[0],
        range:r.kind === 'slider' ? {min:r.ctrl.min, max:r.ctrl.max, step:r.ctrl.step, default:r.ctrl.value} : null})),
      visible: Boolean((viz.textContent + info.textContent).trim() || viz.querySelector('canvas,svg')),
      visual: Boolean(box.width > 0 && box.height > 0 &&
        (painted || viz.querySelector('svg path,svg line,svg circle,svg rect,svg text') || viz.innerText.trim())),
      overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
      height: document.body.scrollHeight,
      mathErrors: document.querySelectorAll('.katex-error').length,
    };
  }
  function values(index) {
    const r = controls[index], c = r.ctrl;
    switch (r.kind) {
      case 'slider': return [c.min, c.min + Math.floor((c.max-c.min)/2/c.step)*c.step, c.max];
      case 'toggle': return [false, true];
      case 'select': return (r.args[1]?.choices || []).map(v => typeof v === 'object' ? v.value : v).slice(0,8);
      case 'stepper': return [0, Math.floor((c.total-1)/2), c.total-1];
      case 'timeline': return [0, c.duration/2, c.duration];
      case 'button': return [null];
    }
  }
  function act(index, value) {
    const {kind, ctrl} = controls[index];
    if (kind === 'button') ctrl.el.click();
    else if (kind === 'stepper') ctrl.goto(value);
    else if (kind === 'timeline') ctrl.seek(value);
    else ctrl.setValue(value);
  }
  function pause() { controls.forEach(r => r.ctrl.pause?.()); }
  function gpuRects() {
    return [...viz.querySelectorAll('canvas')].filter(c => !c.getContext('2d')).map(c => {
      const r = c.getBoundingClientRect();
      return {x:r.x+scrollX, y:r.y+scrollY, width:r.width, height:r.height};
    }).filter(r => r.width > 0 && r.height > 0);
  }
  window.__vizProbe = {snapshot, summary, values, act, pause, gpuRects};
}"""


def check(payload):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "ok": False,
            "environment_error": True,
            "errors": ["缺少 Playwright，请安装后执行 playwright install chromium"],
        }
    sdk = Path(payload["sdk_path"]).read_text(encoding="utf-8")
    code = Path(payload["code_path"]).read_text(encoding="utf-8")
    # Only the exact SDK library assets and KaTeX fonts may access the network.
    assets = set(re.findall(r'https://cdn\.jsdelivr\.net/[^"\s]+', sdk))
    errors, warnings, checks, network_errors = [], [], [], []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, timeout=10_000)
        except Exception:
            return {
                "ok": False,
                "environment_error": True,
                "errors": [
                    "无法启动 Chromium，请执行 playwright install chromium 并确认运行权限"
                ],
            }
        try:
            context = browser.new_context(
                viewport={"width": 900, "height": 600},
                service_workers="block",
                accept_downloads=False,
            )

            def route_asset(route):
                url = route.request.url
                parsed = urlsplit(url)
                font = (
                    parsed.netloc == "cdn.jsdelivr.net"
                    and parsed.path.startswith("/npm/katex@0.16.9/dist/fonts/")
                    and parsed.path.endswith((".woff", ".woff2", ".ttf"))
                )
                if (
                    (url in assets or font)
                    and not parsed.query
                    and route.request.method == "GET"
                ):
                    route.continue_()
                else:
                    route.abort()

            context.route("**/*", route_asset)
            context.route_web_socket("**/*", lambda ws: ws.close())
            page = context.new_page()
            page.on(
                "requestfailed",
                lambda request: (
                    network_errors.append(request.url)
                    if request.url in assets
                    else None
                ),
            )
            page.set_default_timeout(8_000)
            page.on("pageerror", lambda error: errors.append(str(error)[:500]))
            page.on(
                "console",
                lambda message: (
                    errors.append(message.text[:500])
                    if message.type == "error"
                    else None
                ),
            )
            page.on("dialog", lambda dialog: dialog.dismiss())
            page.set_content(
                '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box;margin:0;padding:0} canvas{display:block;border-radius:8px} svg{overflow:visible}</style></head><body></body></html>'
            )
            page.add_script_tag(content=sdk)
            page.evaluate(_PROBE)

            def snapshot():
                return (
                    page.evaluate("__vizProbe.snapshot()"),
                    [
                        page.screenshot(clip=rect)
                        for rect in page.evaluate("__vizProbe.gpuRects()")
                    ],
                )

            page.evaluate("EduViz.setTheme('light')")
            if any(d["type"] == "latex" for d in payload["spec"].get("display", [])):
                page.evaluate("() => EduViz.loadLib('katex')")
            page.evaluate(
                """code => {
                const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
                window.__vizDone = false;
                new AsyncFunction(code)().catch(e => console.error(e.stack || String(e)))
                  .finally(() => { window.__vizDone = true; });
            }""",
                code,
            )
            page.wait_for_function("window.__vizDone === true")
            page.wait_for_timeout(120)
            page.evaluate("__vizProbe.pause()")
            initial = page.evaluate("__vizProbe.summary()")
            if not initial["visible"]:
                errors.append("首屏没有可见教学内容")
            if payload["spec"]["canvas"]["type"] != "none" and not initial["visual"]:
                errors.append("设计要求的主画面没有渲染出来")
            expected = [c["type"] for c in payload["spec"]["controls"]]
            actual = [c["kind"] for c in initial["controls"]]
            if sorted(actual) != sorted(expected):
                warnings.append(
                    f"控件类型或数量与设计不符：需要 {expected}，实际 {actual}"
                )
            if expected and not actual:
                errors.append("没有创建可操作的 EduViz 控件")
            for planned in payload["spec"]["controls"]:
                if planned["type"] == "slider" and planned.get("range"):
                    matching = [
                        c
                        for c in initial["controls"]
                        if c["kind"] == "slider" and c["name"] == planned["name"]
                    ]
                    if not matching or matching[0]["range"] != planned["range"]:
                        warnings.append(
                            f"滑块 {planned['name']} 的名称、范围或默认值与设计不符"
                        )
            for index, control in enumerate(initial["controls"][:8]):
                if not control["bound"]:
                    errors.append(
                        f"控件 {index + 1} ({control['kind']}) 未绑定交互回调"
                    )
                    continue
                before = snapshot()
                changed = False
                for value in page.evaluate("i => __vizProbe.values(i)", index):
                    page.evaluate("([i,v]) => __vizProbe.act(i,v)", [index, value])
                    page.wait_for_timeout(80)
                    changed |= snapshot() != before
                checks.append(
                    {
                        "control": index + 1,
                        "type": control["kind"],
                        "output_changed": changed,
                    }
                )
                # A reset button may legitimately be pressed at its initial state.
                if not changed and control["kind"] != "button":
                    warnings.append(
                        f"控件 {index + 1} ({control['kind']}) 在短时抽样中未观察到变化，需结合代码判断异步更新或条件依赖"
                    )
            for theme, width in (("light", 900), ("dark", 900), ("light", 600)):
                page.set_viewport_size({"width": width, "height": 600})
                page.evaluate("theme => EduViz.setTheme(theme)", theme)
                page.wait_for_timeout(80)
                scene = page.evaluate("__vizProbe.summary()")
                if scene["overflow"] > 2:
                    # The frontend renders at 900px and scales the whole iframe.
                    # A narrow reflow probe is advisory, not the deployed viewport.
                    target = errors if width == 900 else warnings
                    target.append(f"{theme}/{width}px 横向溢出 {scene['overflow']}px")
                if scene["height"] > 1000:
                    warnings.append(f"{theme}/{width}px 内容较高，建议减少组件堆叠")
                if scene["mathErrors"]:
                    errors.append("存在无法渲染的数学公式")
            # Preview is evidence for humans; semantic accuracy is reviewed separately.
            page.set_viewport_size({"width": 900, "height": 600})
            page.screenshot(path=payload["screenshot_path"], full_page=True)
            return {
                "ok": not errors and not network_errors,
                "environment_error": bool(network_errors),
                "errors": list(dict.fromkeys(errors))[:12],
                "warnings": list(dict.fromkeys(warnings))[:12],
                "interactions": checks,
                "initial": initial,
            }
        except Exception as exc:
            return {
                "ok": False,
                "environment_error": bool(network_errors),
                "errors": [f"运行检查失败：{str(exc)[:800]}", *errors[:5]],
            }
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        result = check(json.load(sys.stdin))
    except Exception as exc:
        result = {
            "ok": False,
            "environment_error": True,
            "errors": [f"运行检查不可用：{type(exc).__name__}"],
        }
    print(json.dumps(result, ensure_ascii=False))
