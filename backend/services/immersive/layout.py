"""沉浸式课程的输出目录布局。

定义一门课程下所有产物的文件路径协议，作为 Agent 间数据传递的契约。

.. note::
   本模块原位于 ``agent_core/layout.py``。``chapter_01.tex`` /
   ``chapter_01_exercises.md`` / ``research.json`` 这些文件名是"沉浸式课程
   生成"这一个业务场景的约定，与通用 Agent 框架无关，故移至业务层。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_core.layout import register_course_layout_factory, slugify

__all__ = ["CourseLayout", "slugify"]


@dataclass
class CourseLayout:
    """单个课程的输出目录布局。

    管理一门课程下所有章节的文件路径，作为 Agent 间数据传递的文件系统协议。

    目录结构::

        <course_dir>/
        ├── outline.json
        ├── chapter_01/
        │   ├── research.json
        │   ├── chapter_01.tex
        │   ├── chapter_01.pdf
        │   ├── chapter_01_exercises.md
        │   └── images/
        └── ...

    Example::

        course = CourseLayout(course_dir=COURSES_DIR / "太阳系")
        course.ensure_dirs(chapter_ids=[1, 2, 3])

        # 顶层 Agent 写入大纲
        course.save_outline(outline_data)

        # researcher 写入资料
        course.save_research(1, research_data)

        # tex_writer 读取资料
        research = course.load_research(1)
    """

    course_dir: Path

    def __post_init__(self) -> None:
        self.course_dir = Path(self.course_dir).resolve()
        self.outline_file: Path = self.course_dir / "outline.json"

    # ---- 章节目录 ----

    def chapter_dir(self, chapter_id: int) -> Path:
        """获取指定章节的输出目录。"""
        return self.course_dir / f"chapter_{chapter_id:02d}"

    def chapter_images_dir(self, chapter_id: int) -> Path:
        """获取指定章节的图片目录。"""
        return self.chapter_dir(chapter_id) / "images"

    # ---- 章节文件路径 ----

    def research_file(self, chapter_id: int) -> Path:
        """获取指定章节的研究资料 JSON 路径。"""
        return self.chapter_dir(chapter_id) / "research.json"

    def tex_file(self, chapter_id: int) -> Path:
        """获取指定章节的 TeX 源码路径。"""
        return self.chapter_dir(chapter_id) / f"chapter_{chapter_id:02d}.tex"

    def pdf_file(self, chapter_id: int) -> Path:
        """获取指定章节的 PDF 路径。"""
        return self.chapter_dir(chapter_id) / f"chapter_{chapter_id:02d}.pdf"

    def exercises_file(self, chapter_id: int) -> Path:
        """获取指定章节的习题 Markdown 路径。"""
        return self.chapter_dir(chapter_id) / f"chapter_{chapter_id:02d}_exercises.md"

    # ---- 大纲读写 ----

    def save_outline(self, data: Dict[str, Any]) -> Path:
        """保存课程大纲到 outline.json。"""
        self.course_dir.mkdir(parents=True, exist_ok=True)
        self.outline_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.outline_file

    @staticmethod
    def _sanitize_json(raw: str) -> str:
        """清洗 LLM 输出的 JSON：去除非法控制字符 + 修复非法反斜杠转义。

        处理三类常见问题：
        1. 非法控制字符：LLM 在 JSON 字符串值中混入 raw \\n \\r 等
        2. 非法反斜杠转义：LLM 输出 LaTeX 命令如 \\to, \\infty, \\text 等，
           导致 json.loads 报 "Invalid \\escape" 错误。
           JSON 合法转义仅有：\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX
        3. LaTeX 伪合法转义：\\to, \\text, \\nabla, \\rightarrow 等以合法
           转义字符开头但实际是 LaTeX 命令的情况。
        """
        # 第一步：移除 JSON 字符串值内的 raw 控制字符（\x00-\x08, \x0a-\x1f 除 \x09）
        # 保留 \t (0x09) 因为它虽需转义但 Python json 解析器能容忍
        cleaned = re.sub(r"[\x00-\x08\x0a-\x1f]", "", raw)

        # 第二步：修复非法反斜杠转义（基础）
        # 将 \ 后面不是合法 JSON 转义字符的情况，把 \ 替换为 \\（双反斜杠）
        # 合法转义字符：" \ / b f n r t u
        cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", cleaned)

        # 第三步：修复 LaTeX "伪合法" 转义
        # \t, \n, \r, \b, \f 在 JSON 中是合法转义（制表符、换行等），
        # 但如果后面紧跟字母，则很可能是 LaTeX 命令
        # （如 \to, \text, \nabla, \rightarrow, \frac, \binom）
        cleaned = re.sub(r"\\([tnrbf])(?=[a-zA-Z])", r"\\\\\1", cleaned)

        return cleaned

    @staticmethod
    def _safe_json_loads(raw: str) -> Any:
        """尝试解析 JSON，失败时用激进策略修复后重试。"""
        sanitized = CourseLayout._sanitize_json(raw)
        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            # 激进策略：将所有非双反斜杠的单反斜杠都转义
            # 先把已有的 \\ 替换为占位符，再把剩余的 \ 替换为 \\，最后恢复占位符
            placeholder = "\x00BACKSLASH\x00"
            aggressive = sanitized.replace("\\\\", placeholder)
            aggressive = aggressive.replace("\\", "\\\\")
            aggressive = aggressive.replace(placeholder, "\\\\")
            return json.loads(aggressive)

    def load_outline(self) -> Optional[Dict[str, Any]]:
        """加载课程大纲，文件不存在返回 None。

        自动清洗 LLM 输出中可能包含的非法 JSON 控制字符和 LaTeX 转义。
        """
        if not self.outline_file.exists():
            return None
        raw = self.outline_file.read_text(encoding="utf-8")
        return self._safe_json_loads(raw)

    # ---- 研究资料读写 ----

    def save_research(self, chapter_id: int, data: Dict[str, Any]) -> Path:
        """保存章节研究资料到 research.json。"""
        ch_dir = self.chapter_dir(chapter_id)
        ch_dir.mkdir(parents=True, exist_ok=True)
        path = self.research_file(chapter_id)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_research(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        """加载章节研究资料，文件不存在返回 None。

        自动清洗 LLM 输出中可能包含的非法 JSON 控制字符和 LaTeX 转义。
        """
        path = self.research_file(chapter_id)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return self._safe_json_loads(raw)

    # ---- 目录创建 ----

    def ensure_dirs(self, chapter_ids: Optional[List[int]] = None) -> None:
        """确保课程目录和指定章节目录存在。

        Args:
            chapter_ids: 需要创建的章节 ID 列表。为 None 时只创建课程根目录。
        """
        self.course_dir.mkdir(parents=True, exist_ok=True)
        if chapter_ids:
            for cid in chapter_ids:
                self.chapter_dir(cid).mkdir(parents=True, exist_ok=True)
                self.chapter_images_dir(cid).mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"CourseLayout(course_dir={self.course_dir})"


# 向框架注册工厂，使 UserDataLayout.course() 能委托到本实现（控制反转）
register_course_layout_factory(lambda course_dir: CourseLayout(course_dir=course_dir))
