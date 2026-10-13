"""将已有的 .tex 文件编译为 PDF。"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".pdf")
_INCLUDE_GRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}", re.DOTALL
)
_TEX_MACRO_RE = re.compile(
    r"\\(?:newcommand|renewcommand)\s*\{\\([A-Za-z@]+)\}\s*\{([^{}]*)\}"
)


def _cjk_font_chain() -> str:
    """生成跨平台的 CJK 主字体选择代码。

    用 fontspec 的 \\IfFontExistsTF 按优先级探测系统里真实存在的字体，
    避免硬编码某个字体导致在其它平台（如 macOS 缺 Droid Sans Fallback）
    编译失败。返回一串嵌套的 \\IfFontExistsTF{...}{...}{...}，最内层
    兜底为空（找不到任何中文字体则不设置，交由 xeCJK 默认处理）。
    """
    fonts = (
        "Droid Sans Fallback",  # Linux 服务器常见兜底
        "Noto Sans CJK SC",  # Linux / 跨平台
        "PingFang SC",  # macOS
        "Songti SC",  # macOS
        "Heiti SC",  # macOS
        "WenQuanYi Zen Hei",  # Linux
    )
    inner = ""
    for font in reversed(fonts):
        inner = f"\\IfFontExistsTF{{{font}}}{{\\setCJKmainfont{{{font}}}}}{{{inner}}}"
    return inner


def _prepare_tex_for_compile(src: Path, dst: Path) -> Path:
    r"""复制 .tex 到 dst 并预处理：
    注入 \setCJKmainfont 让 xeCJK 能找到字体（项目源 .tex 没设字体）。
    主题（SimplePlus-BeamerTheme）已通过 TEXINPUTS 注入编译环境，
    这里不再替换 \usetheme，直接使用源 tex 声明的主题。
    返回 dst 路径，调用方应使用此路径代替 src 调 xelatex。
    """
    raw = src.read_text(encoding="utf-8", errors="ignore")
    lines = raw.splitlines()
    out = []
    cjk_injected = False
    for ln in lines:
        if "\\usepackage{xeCJK}" in ln and not cjk_injected:
            out.append(ln)
            out.append(_cjk_font_chain())
            cjk_injected = True
            continue
        out.append(ln)
    dst.write_text("\n".join(out), encoding="utf-8")
    return dst


def validate_pdf_file(pdf_path: Path, min_size: int = 1024) -> Optional[str]:
    """校验 PDF 是否是可交付的完整文件；返回 None 表示有效，否则返回失败原因。"""
    try:
        if not pdf_path.exists():
            return f"PDF 文件不存在: {pdf_path}"
        if not pdf_path.is_file():
            return f"PDF 路径不是文件: {pdf_path}"

        size = pdf_path.stat().st_size
        if size < min_size:
            return f"PDF 文件过小: {size} bytes"

        with pdf_path.open("rb") as fh:
            head = fh.read(16)
            fh.seek(max(size - 4096, 0))
            tail = fh.read()

        if not head.startswith(b"%PDF-"):
            return "PDF 文件头无效，缺少 %PDF- 标记"
        if b"startxref" not in tail:
            return "PDF 文件尾部无效，缺少 startxref"
        if b"%%EOF" not in tail:
            return "PDF 文件尾部无效，缺少 %%EOF"

        return None
    except OSError as exc:
        return f"PDF 文件读取失败: {exc}"


def pdf_artifact_revision(pdf_path: Path) -> str:
    """Return a content revision suitable for invalidating a rendered PDF cache."""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _resolve_tex_image_reference(
    raw_reference: str,
    *,
    tex_path: Path,
    images_dir: Path,
    macros: dict[str, str],
) -> Optional[Path]:
    """Resolve the straightforward image paths emitted by the courseware writer."""
    reference = raw_reference.strip()
    for name, value in macros.items():
        reference = reference.replace(f"\\{name}", value)
    reference = reference.replace("{", "").replace("}", "").strip()
    if not reference:
        return None

    # A macro such as ``\imgdir figure.png`` intentionally has whitespace
    # between the directory macro and the file name.  It is never meaningful
    # in a generated image path, so normalize it before resolving.
    reference = re.sub(r"\s+", "", reference)
    source = Path(reference).expanduser()
    candidates = [source] if source.is_absolute() else [tex_path.parent / source]
    candidates.append(images_dir / source.name)

    for candidate in candidates:
        if candidate.suffix:
            if candidate.is_file():
                return candidate.resolve()
            continue
        for suffix in _IMAGE_EXTENSIONS:
            with_suffix = candidate.with_suffix(suffix)
            if with_suffix.is_file():
                return with_suffix.resolve()
    return None


def validate_chapter_pdf(
    pdf_path: Path,
    tex_path: Path,
    images_dir: Path,
) -> Optional[str]:
    """Validate a generated chapter PDF before it can be published or reused.

    A syntactically valid PDF can still be a stale pre-image build.  The
    courseware contract is therefore checked end to end: every TeX image
    reference must resolve to a source asset older than the PDF, the final PDF
    must embed at least that many image instances, and the image-bearing pages
    must rasterize successfully with PDFium.
    """
    pdf_error = validate_pdf_file(pdf_path)
    if pdf_error:
        return pdf_error
    if not tex_path.is_file():
        return f"TeX 文件不存在，无法校验图片完整性: {tex_path}"

    try:
        tex_source = tex_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return f"TeX 文件读取失败: {exc}"

    macros = {
        match.group(1): match.group(2).strip()
        for match in _TEX_MACRO_RE.finditer(tex_source)
    }
    references = _INCLUDE_GRAPHICS_RE.findall(tex_source)
    resolved_images: list[Path] = []
    for reference in references:
        image_path = _resolve_tex_image_reference(
            reference,
            tex_path=tex_path,
            images_dir=images_dir,
            macros=macros,
        )
        if image_path is None:
            return f"TeX 图片引用无法解析或源文件不存在: {reference.strip()}"
        try:
            if image_path.stat().st_size == 0:
                return f"TeX 图片源文件为空: {image_path.name}"
        except OSError as exc:
            return f"TeX 图片源文件读取失败: {exc}"
        resolved_images.append(image_path)

    if not resolved_images:
        return None

    try:
        pdf_mtime_ns = pdf_path.stat().st_mtime_ns
    except OSError as exc:
        return f"PDF 文件读取失败: {exc}"
    newer_sources = [
        image.name
        for image in resolved_images
        if image.stat().st_mtime_ns > pdf_mtime_ns
    ]
    if newer_sources:
        return "图片源文件晚于 PDF，必须重新编译: " + ", ".join(newer_sources[:4])

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path), strict=False)
        image_pages = [
            index for index, page in enumerate(reader.pages) if len(page.images) > 0
        ]
        embedded_images = sum(len(reader.pages[index].images) for index in image_pages)
    except Exception as exc:  # pylint: disable=broad-except
        return f"无法检查 PDF 内嵌图片: {exc}"

    expected_images = len(resolved_images)
    if embedded_images < expected_images:
        return (
            "PDF 内嵌图片不足: "
            f"TeX 引用了 {expected_images} 张，PDF 仅检测到 {embedded_images} 张"
        )

    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(pdf_path))
        for page_index in image_pages:
            bitmap = document[page_index].render(scale=0.25)
            rendered = bitmap.to_pil().convert("RGB")
            extrema = rendered.getextrema()
            if all(low == high for low, high in extrema):
                return f"PDF 图片页渲染为空白: 第 {page_index + 1} 页"
    except Exception as exc:  # pylint: disable=broad-except
        return f"PDF 图片页渲染校验失败: {exc}"

    return None


class LatexPdfCompileTool(BaseTool):
    """将已有的 .tex 文件编译为 PDF。"""

    name = "latex_pdf_compile"
    description = (
        "将指定的 .tex 文件编译为 PDF，输出 PDF 与 .tex 文件同目录同文件名。"
        "模板目录由系统配置自动注入，无需手动指定。"
        "成功时返回 PDF 文件的绝对路径，失败时返回 Error: 开头的错误信息。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "tex_path": {
                "type": "string",
                "description": "待编译的 .tex 文件绝对路径",
            },
            "engine": {
                "type": "string",
                "description": "编译器策略：auto / latexmk / xelatex，默认 auto",
            },
            "timeout": {
                "type": "integer",
                "description": "单次编译命令超时时间（秒），默认 240",
            },
            "runs": {
                "type": "integer",
                "description": "使用 xelatex 直接编译时的轮数，默认 1（单页卡片无需多次编译）",
            },
        },
        "required": ["tex_path"],
    }

    def __init__(self, template_dir: Optional[Path] = None):
        self.default_template_dir = template_dir.resolve() if template_dir else None
        super().__init__()

    # ── 内部工具方法 ──

    def _resolve_template_dir(self) -> Optional[Path]:
        """返回模板目录，不存在则返回 None（不强制要求）。"""
        if (
            self.default_template_dir
            and self.default_template_dir.exists()
            and self.default_template_dir.is_dir()
        ):
            return self.default_template_dir
        return None

    @staticmethod
    def _inject_search_path(env: Dict[str, str], key: str, extra_path: Path) -> None:
        current = env.get(key, "")
        prefix = str(extra_path)
        env[key] = (
            f"{prefix}{os.pathsep}{current}" if current else f"{prefix}{os.pathsep}"
        )

    def _build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        template_path = self._resolve_template_dir()
        if template_path:
            self._inject_search_path(env, "TEXINPUTS", template_path)
            self._inject_search_path(env, "BIBINPUTS", template_path)
            self._inject_search_path(env, "BSTINPUTS", template_path)
        return env

    @staticmethod
    def _run_command(
        command: list[str], cwd: Path, env: Dict[str, str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )

    def _compile_with_latexmk(
        self, tex_path: Path, env: Dict[str, str], timeout: int, output_dir: Path
    ) -> subprocess.CompletedProcess[str]:
        return self._run_command(
            [
                "latexmk",
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-outdir={output_dir}",
                tex_path.name,
            ],
            cwd=tex_path.parent,
            env=env,
            timeout=timeout,
        )

    def _compile_with_xelatex(
        self,
        tex_path: Path,
        env: Dict[str, str],
        timeout: int,
        runs: int,
        output_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        last_result: Optional[subprocess.CompletedProcess[str]] = None
        for _ in range(max(1, runs)):
            last_result = self._run_command(
                [
                    "xelatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-file-line-error",
                    "-output-directory",
                    str(output_dir),
                    tex_path.name,
                ],
                cwd=tex_path.parent,
                env=env,
                timeout=timeout,
            )
            if last_result.returncode != 0:
                break
        assert last_result is not None
        return last_result

    @staticmethod
    def _quarantine_invalid_pdf(pdf_path: Path, reason: str) -> Optional[Path]:
        """将坏 PDF 从正式路径移走，避免前端继续加载。"""
        if not pdf_path.exists():
            return None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        quarantine_path = pdf_path.with_name(f"{pdf_path.stem}.invalid_{timestamp}.pdf")
        try:
            pdf_path.replace(quarantine_path)
            logger.warning(
                "已隔离无效 PDF: %s -> %s，原因: %s", pdf_path, quarantine_path, reason
            )
            return quarantine_path
        except OSError as exc:
            logger.error(
                "隔离无效 PDF 失败: %s，原因: %s，错误: %s", pdf_path, reason, exc
            )
            return None

    @staticmethod
    def _copy_compile_log(tmp_log_path: Path, log_path: Path) -> None:
        """将临时编译日志复制到 tex 同目录，便于排查失败原因。"""
        if not tmp_log_path.exists():
            return
        try:
            shutil.copy2(tmp_log_path, log_path)
        except OSError as exc:
            logger.warning(
                "复制 PDF 编译日志失败: %s -> %s，错误: %s", tmp_log_path, log_path, exc
            )

    def run(
        self,
        tex_path: str = "",
        engine: str = "auto",
        timeout: int = 240,
        runs: int = 1,
        **kwargs: Any,
    ) -> str:
        tex = Path(tex_path).expanduser().resolve()
        if not tex.exists():
            return f"Error: .tex 文件不存在: {tex}"
        if tex.suffix.lower() != ".tex":
            return f"Error: 文件不是 .tex 文件: {tex}"

        pdf_path = tex.with_suffix(".pdf")
        log_path = tex.with_suffix(".log")
        env = self._build_env()

        selected_engine = (engine or "auto").lower()
        if selected_engine not in {"auto", "latexmk", "xelatex"}:
            return "Error: engine 只支持 auto / latexmk / xelatex"

        latexmk_exists = shutil.which("latexmk") is not None
        xelatex_exists = shutil.which("xelatex") is not None

        if selected_engine == "latexmk" and not latexmk_exists:
            return "Error: 系统中未找到 latexmk"
        if selected_engine == "xelatex" and not xelatex_exists:
            return "Error: 系统中未找到 xelatex"
        if selected_engine == "auto" and not (latexmk_exists or xelatex_exists):
            return "Error: 系统中既没有 latexmk，也没有 xelatex，无法编译 PDF"

        compiler_used = (
            "latexmk"
            if selected_engine in {"auto", "latexmk"} and latexmk_exists
            else "xelatex"
        )

        existing_pdf_error = validate_pdf_file(pdf_path) if pdf_path.exists() else None
        if existing_pdf_error:
            self._quarantine_invalid_pdf(pdf_path, existing_pdf_error)

        result: subprocess.CompletedProcess[str]
        tmp_pdf_path: Path
        tmp_log_path: Path
        try:
            with tempfile.TemporaryDirectory(
                prefix=f".{tex.stem}_compile_", dir=str(tex.parent)
            ) as tmp_dir_name:
                tmp_dir = Path(tmp_dir_name)
                tmp_pdf_path = tmp_dir / pdf_path.name
                tmp_log_path = tmp_dir / log_path.name
                # 预处理：注入 CJK 字体（主题由 TEXINPUTS 环境变量解析）
                compile_tex = _prepare_tex_for_compile(tex, tmp_dir / tex.name)

                if compiler_used == "latexmk":
                    result = self._compile_with_latexmk(
                        compile_tex, env=env, timeout=timeout, output_dir=tmp_dir
                    )
                else:
                    result = self._compile_with_xelatex(
                        compile_tex,
                        env=env,
                        timeout=timeout,
                        runs=runs,
                        output_dir=tmp_dir,
                    )

                self._copy_compile_log(tmp_log_path, log_path)
                validation_error = validate_chapter_pdf(
                    tmp_pdf_path, compile_tex, tex.parent / "images"
                )
                success = result.returncode == 0 and validation_error is None
                if success:
                    tmp_pdf_path.replace(pdf_path)
                    logger.info("PDF 编译并校验成功: %s", pdf_path)
                    return f"PDF 编译成功，路径：{str(pdf_path)}"
        except subprocess.TimeoutExpired:
            logger.error("PDF 编译超时: tex=%s timeout=%s", tex, timeout)
            return f"Error: PDF 编译超时（>{timeout} 秒），tex 文件: {tex}"

        # 失败时提取关键错误行
        file_log = (
            log_path.read_text(encoding="utf-8", errors="ignore")
            if log_path.exists()
            else ""
        )
        command_output = "\n".join(
            p for p in [result.stdout, result.stderr] if p
        ).strip()
        combined = "\n".join(p for p in [command_output, file_log] if p)
        error_lines = [
            line
            for line in combined.splitlines()
            if line.startswith("!") or "Error" in line or "error" in line
        ][:30]
        error_summary = "\n".join(error_lines) if error_lines else combined[:2000]
        validation_text = (
            f"\nPDF 校验失败: {validation_error}" if validation_error else ""
        )
        logger.error(
            "PDF 编译失败: compiler=%s returncode=%s tex=%s%s\n%s",
            compiler_used,
            result.returncode,
            tex,
            validation_text,
            error_summary,
        )
        return (
            f"Error: PDF 编译失败（{compiler_used} 返回码 {result.returncode}）{validation_text}\n"
            f"tex 文件: {tex}\n"
            f"编译日志: {log_path}\n"
            f"错误摘要:\n{error_summary}"
        )


latex_pdf_compile_tool = LatexPdfCompileTool()

__all__ = [
    "LatexPdfCompileTool",
    "latex_pdf_compile_tool",
    "pdf_artifact_revision",
    "validate_chapter_pdf",
    "validate_pdf_file",
]

if __name__ == "__main__":
    print(latex_pdf_compile_tool(tex_path="test_dir/chapter_01.tex"))
