"""卡片 → PNG 渲染（Playwright 无头 Chromium）。

三类卡片都在后端自包含渲染成图片，无需前端参与、无需重新构建前端：

- **html_card**：读磁盘 ``card.html``，把伴生图片（``/api/documents/{id}/asset/images/x``）
  内联为 data URL，再 set_content 截图（KaTeX 仍走 CDN，需联网）。
- **viz_card**：读 ``viz.js``，复刻前端 EduViz 沙箱（SANDBOX 模板 + eduviz-sdk.js +
  用户代码），set_content 后等待内容渲染稳定再截图。
- **quiz_card**：从数据库取题目，后端渲染一张简洁 HTML 再截图。

一个进程共享一个浏览器实例（懒启动），每次开新 page 截图后关闭。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional

from config import (
    CARDS_DIR,
    EDUVIZ_SDK_PATH,
    VIZ_DIR,
    WECLAW_RENDER_TIMEOUT_MS,
    WECLAW_RENDER_WIDTH,
)
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)


# ── EduViz 沙箱模板（与 frontend/src/components/EduViz/sandboxTemplate.js 对齐）──
# 用占位符 __EDUVIZ_SDK__ / __THEME__ / __USER_CODE__，运行时替换。
_SANDBOX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: auto !important; overflow: visible !important; }
    body { font-family: Inter, -apple-system, sans-serif; padding: 12px; background: #0f1117; }
    canvas { border-radius: 8px; display: block; }
    svg { overflow: visible; }
  </style>
</head>
<body>
  __EDUVIZ_SDK__
  <script>
    document.documentElement.setAttribute('data-theme', '__THEME__');
    if (window.EduViz && typeof window.EduViz.setTheme === 'function') {
      window.EduViz.setTheme('__THEME__');
    }
    window.onerror = function(){ return true; };
    window.onunhandledrejection = function(e){ e.preventDefault(); };
    (async function() {
      __USER_CODE__
    })().catch(function(err){ console.warn('[EduViz]', err && err.message); });
  </script>
</body>
</html>"""


class CardRenderer:
    """共享一个 Chromium 实例，把卡片渲染成 PNG。"""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._sdk_cache: Optional[str] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        async with self._lock:
            if self._browser is not None:
                return self._browser
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            logger.info("weclaw CardRenderer: Chromium 已启动")
            return self._browser

    async def aclose(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
            if self._pw is not None:
                await self._pw.stop()
        except Exception:  # pylint: disable=broad-except
            pass
        self._browser = None
        self._pw = None

    def _load_sdk(self) -> str:
        if self._sdk_cache is None:
            try:
                self._sdk_cache = Path(EDUVIZ_SDK_PATH).read_text(encoding="utf-8")
            except Exception:  # pylint: disable=broad-except
                logger.warning(
                    "weclaw CardRenderer: 读取 EduViz SDK 失败 path=%s", EDUVIZ_SDK_PATH
                )
                self._sdk_cache = ""
        return self._sdk_cache

    # ── 入口 ─────────────────────────────────────────────────────

    async def render(
        self, card_type: str, doc_id: str, title: str = ""
    ) -> Optional[bytes]:
        """把卡片渲染成 PNG 字节；失败返回 None。"""
        ct = (card_type or "").lower()
        try:
            if ct in ("html", "html_card"):
                html = self._build_html_card(doc_id)
            elif ct in ("viz", "viz_card"):
                html = self._build_viz_card(doc_id)
            elif ct in ("quiz", "quiz_card"):
                html = self._build_quiz_card(doc_id, title)
            else:
                return None
            if not html:
                return None
            return await self._screenshot(html)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "weclaw CardRenderer: 渲染失败 type=%s doc=%s", ct, safe_log(doc_id)
            )
            return None

    # ── 截图 ─────────────────────────────────────────────────────

    async def _screenshot(self, html: str) -> Optional[bytes]:
        browser = await self._ensure_browser()
        page = await browser.new_page(
            viewport={"width": WECLAW_RENDER_WIDTH, "height": 800},
            device_scale_factor=2,  # 高清
        )
        try:
            await page.set_content(
                html, wait_until="load", timeout=WECLAW_RENDER_TIMEOUT_MS
            )
            # 等网络（KaTeX/CDN 库）与渲染稳定
            try:
                await page.wait_for_load_state(
                    "networkidle", timeout=WECLAW_RENDER_TIMEOUT_MS
                )
            except Exception:  # pylint: disable=broad-except
                pass
            await page.wait_for_timeout(600)  # 给 JS 动画/布局收尾
            png = await page.screenshot(full_page=True, type="png")
            return png
        finally:
            await page.close()

    # ── 各类型 HTML 构造 ─────────────────────────────────────────

    def _build_html_card(self, doc_id: str) -> Optional[str]:
        card_dir = Path(CARDS_DIR) / doc_id
        card_html = card_dir / "card.html"
        if not card_html.exists():
            logger.warning("weclaw: html_card 文件不存在 %s", card_html)
            return None
        html = card_html.read_text(encoding="utf-8")
        # 把 /api/documents/{id}/asset/images/xxx 内联成 data URL（iframe 外无鉴权）
        images_dir = card_dir / "images"

        def _inline(match: re.Match) -> str:
            fname = match.group("fname")
            fpath = images_dir / fname
            if not fpath.exists():
                return match.group(0)
            mime = mimetypes.guess_type(str(fpath))[0] or "image/png"
            b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
            return f'src="data:{mime};base64,{b64}"'

        html = re.sub(
            r'src="[^"]*?/api/documents/[^"/]+/asset/images/(?P<fname>[^"]+)"',
            _inline,
            html,
        )
        return html

    def _build_viz_card(self, doc_id: str) -> Optional[str]:
        viz_js = Path(VIZ_DIR) / doc_id / "viz.js"
        if not viz_js.exists():
            logger.warning("weclaw: viz.js 不存在 %s", viz_js)
            return None
        code = viz_js.read_text(encoding="utf-8")
        sdk = self._load_sdk()
        sdk_script = "<" + "script>" + sdk + "</" + "script>"
        html = (
            _SANDBOX_HTML.replace("__EDUVIZ_SDK__", sdk_script)
            .replace("__THEME__", "dark")
            .replace("__USER_CODE__", code)
        )
        return html

    def _build_quiz_card(self, doc_id: str, title: str = "") -> Optional[str]:
        from repositories.quiz_repo import QuizRepository

        quiz = QuizRepository().get_by_id(doc_id)
        if not quiz:
            logger.warning("weclaw: quiz 不存在 %s", safe_log(doc_id))
            return None
        return _render_quiz_html(quiz)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_quiz_html(quiz) -> str:
    """把一道 quiz 渲染成简洁 HTML（含题干/选项/答案/解析）。"""
    type_label = {
        "multiple_choice": "选择题",
        "true_false": "判断题",
        "fill_in": "填空题",
        "open_ended": "简答题",
    }.get(quiz.quiz_type, "题目")

    options_html = ""
    if quiz.options:
        items = "".join(f'<div class="opt">{_esc(o)}</div>' for o in quiz.options)
        options_html = f'<div class="opts">{items}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "PingFang SC", Inter, sans-serif;
         background: #0f1117; color: #e5e7ff; padding: 16px; }}
  .card {{ background: #1b1e2b; border: 1px solid rgba(139,92,246,.35);
           border-radius: 12px; padding: 18px; }}
  .badge {{ display: inline-block; font-size: 12px; padding: 3px 10px;
            border-radius: 999px; background: rgba(139,92,246,.2);
            color: #c4b5fd; margin-bottom: 12px; }}
  .q {{ font-size: 16px; font-weight: 600; line-height: 1.6; margin-bottom: 14px; }}
  .opts {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }}
  .opt {{ padding: 10px 12px; border: 1px solid rgba(255,255,255,.12);
          border-radius: 8px; font-size: 14px; line-height: 1.5; }}
  .ans {{ margin-top: 8px; padding: 10px 12px; border-radius: 8px;
          background: rgba(16,185,129,.15); color: #34d399; font-size: 14px; }}
  .exp {{ margin-top: 8px; font-size: 13px; line-height: 1.6; color: #b9c0d4; }}
  .exp b {{ color: #e5e7ff; }}
</style></head>
<body><div class="card">
  <div class="badge">{type_label}</div>
  <div class="q">{_esc(quiz.question)}</div>
  {options_html}
  <div class="ans">✅ 正确答案：{_esc(quiz.correct_answer)}</div>
  {f'<div class="exp"><b>解析：</b>{_esc(quiz.explanation)}</div>' if quiz.explanation else ""}
</div></body></html>"""


# 进程级单例
renderer = CardRenderer()
