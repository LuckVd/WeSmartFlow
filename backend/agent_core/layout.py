"""Agent 工作空间目录布局。

框架只关心 Agent 自身需要的两个路径：

- ``agent.md``  — Agent 自我定义（identity）
- ``skills/``   — 用户自定义技能

业务产物（课程、章节、TeX、习题等）的目录协议属于业务领域，已移至
``services/immersive/layout.py``。

.. note::
   改造前本模块含 ``CourseLayout``（定义 ``chapter_01.tex`` /
   ``chapter_01_exercises.md`` 等文件名），那是"沉浸式课程生成"这一个业务
   场景的文件契约，与通用 Agent 框架无关。现已拆出。

   ``UserDataLayout`` 作为兼容别名保留，其 ``course()`` 方法委托给业务层实现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def slugify(text: str) -> str:
    """将文本转为安全的目录名片段。

    保留中文与字母数字，其余字符折叠为下划线，长度截断到 60。
    """
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", (text or "").strip()).strip("_")
    return slug[:60] or "untitled"


#: 兼容别名（改造前为模块私有函数，业务侧曾直接 import）
_slugify = slugify


@dataclass
class AgentWorkspace:
    """Agent 工作空间目录布局。

    一个实例对应一个用户（或一个 Agent 实例）的数据根目录。

    Args:
        root:    工作空间根目录路径。
        user_id: 用户 ID，用于日志与业务侧文件隔离。

    Example::

        ws = AgentWorkspace(root=Path("./data/documents"), user_id="u_abc123")
        loader = SkillsLoader(workspace_skills_dir=ws.skills_dir)
    """

    root: Path
    user_id: str = ""

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

        # Agent 自我定义
        self.identity_file: Path = self.root / "agent.md"

        # 用户自定义技能
        self.skills_dir: Path = self.root / "skills"

    def skill_file(self, name: str) -> Path:
        """获取指定技能的 SKILL.md 路径。

        Args:
            name: 技能名称（目录名）。

        Returns:
            ``<root>/skills/<name>/SKILL.md`` 路径。
        """
        return self.skills_dir / name / "SKILL.md"

    def ensure_dirs(self) -> None:
        """确保工作空间目录存在。

        不会自动调用，由使用方在需要写入时手动调用。
        """
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"AgentWorkspace(root={self.root}, user_id={self.user_id})"


#: 业务侧课程布局工厂。由业务层在导入时注册，框架不感知其具体类型。
#: 见 ``services/immersive/layout.py`` 底部的 ``register_course_layout()`` 调用。
_course_layout_factory: Any = None


def register_course_layout_factory(factory: Any) -> None:
    """注册业务侧的课程布局工厂（由业务层调用）。

    这是控制反转：框架提供挂载点，业务层提供实现，避免框架反向 import 业务模块。

    Args:
        factory: 签名为 ``(course_dir: Path) -> Any`` 的可调用对象。
    """
    global _course_layout_factory  # pylint: disable=global-statement
    _course_layout_factory = factory


class UserDataLayout(AgentWorkspace):
    """[兼容] 用户数据目录布局。

    保留 ``courses_dir`` 与 ``course()`` 以兼容既有业务调用；
    ``course()`` 通过已注册的工厂委托给业务层实现。

    新代码请直接使用 :class:`AgentWorkspace`（框架路径）与
    ``services.immersive.layout.CourseLayout``（业务路径）。
    """

    def __post_init__(self) -> None:
        super().__post_init__()
        self.courses_dir: Path = self.root / "courses"

    def course(self, topic: str) -> Any:
        """获取指定课程的布局实例（委托已注册的业务工厂）。

        Args:
            topic: 课程主题，会被 slugify 为目录名。

        Raises:
            RuntimeError: 业务侧未注册课程布局工厂。
        """
        if _course_layout_factory is None:
            raise RuntimeError(
                "课程布局工厂未注册。请先 import services.immersive.layout，"
                "或直接使用 CourseLayout(course_dir=...)"
            )
        return _course_layout_factory(self.courses_dir / slugify(topic))

    def ensure_dirs(self) -> None:
        super().ensure_dirs()
        self.courses_dir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"UserDataLayout(root={self.root}, user_id={self.user_id})"


__all__ = [
    "AgentWorkspace",
    "UserDataLayout",
    "register_course_layout_factory",
    "slugify",
]
