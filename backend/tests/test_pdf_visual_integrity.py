"""Regression coverage for the PDF image-publication gate."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.tool.pdf_compile import validate_chapter_pdf


class PdfVisualIntegrityTests(unittest.TestCase):
    def test_valid_pdf_without_the_tex_referenced_image_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            images.mkdir()
            (images / "figure.png").write_bytes(b"non-empty test image")
            tex = root / "chapter_01.tex"
            tex.write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\includegraphics{images/figure.png}\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            # Keep the source older than the output so this specifically tests
            # the missing embedded-image gate instead of freshness detection.
            time.sleep(0.01)
            pdf = root / "chapter_01.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            with pdf.open("wb") as output:
                writer.write(output)
            with pdf.open("ab") as output:
                output.write(b"% padding for PDF minimum-size validation\n" * 32)

            error = validate_chapter_pdf(pdf, tex, images)

        self.assertIn("PDF 内嵌图片不足", error or "")


if __name__ == "__main__":
    unittest.main()
