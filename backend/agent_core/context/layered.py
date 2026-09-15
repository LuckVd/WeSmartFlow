"""分层system prompt 构建器：角色定义 + 动态片段 + 技能。

框架唯一的分层 Builder。System prompt 由以下 5 层按顺序拼接
（各层之间以 ``---`` 分隔）：

1. **角色定义** — 读取 ``prompt_file``（可为多个文件，按序拼接）
2. **动态片段** — Provider 注入（用户画像、检索结果、策略提示等）
3. **Always Skills** — 标记了 ``always: true`` 的技能，始终注入
4. **按需技能** — 通过 ``skill_names`` kwarg 传入
5. **Skills 摘要** — 仅列名称与路径，供 Agent 按需自行读取

两种角色定义来源
----------------

===================================  ==========================================
prompt 由代码/仓库固定                 ``LayeredPromptBuilder(prompt_file=p)``
prompt 属于用户工作空间、可编辑         :meth:`from_workspace`
===================================  ==========================================

后者从 ``workspace_dir/agent.md`` 加载身份定义（缺失则回退到内置默认），
使 Agent 的身份可被用户编辑、随工作空间迁移。

.. note::
   第 2 层通过 :class:`~agent_core.context.provider.ContextProvider` 协议实现，
   框架不知道注入的内容是什么——这取代了此前业务侧"在方法内动态定义子类以
   闭包捕获动态后缀"的 hack。

   第 5 层是渐进式加载的关键：技能正文不进 prompt，只给索引，由 Agent 决定
   是否读取，避免技能数量增长直接推高每步 token 成本。

build_system_prompt 支持的 kwargs：

- ``skill_names``: List[str] — 本次额外注入的技能名称
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Sequence, Tuple, Union

from ..skills.loader import SkillsLoader
from .builder import SystemPromptBuilder
from .provider import ContextProvider, gather_provider_sections

if TYPE_CHECKING:
    from ..runtime.run_context import RunContext


class LayeredPromptBuilder(SystemPromptBuilder):
    """分层拼装 system prompt 的system prompt 构建器。

    Args:
        prompt_file:          角色定义 .md 文件路径；也可传入多个路径，
                              按序拼接（不存在的文件静默跳过）。
        skills_loader:        SkillsLoader 实例，为 None 时不加载技能。
        providers:            动态片段提供者列表，按声明顺序注入。
        fallback_prompt_file: 当 ``prompt_file`` 全部不存在时的兜底文件。

    Example::

        # 仓库固定 prompt
        builder = LayeredPromptBuilder(prompt_file=Path("prompts/tutor.md"))

        # 用户工作空间可编辑的身份定义
        builder = LayeredPromptBuilder.from_workspace(
            Path("./data/users/user_001"),
            providers=[ProfileProvider("user_001")],
        )
    """

    def __init__(
        self,
        prompt_file: Optional[Union[Path, str, Sequence[Union[Path, str]]]] = None,
        skills_loader: Optional[SkillsLoader] = None,
        providers: Optional[List[ContextProvider]] = None,
        fallback_prompt_file: Optional[Union[Path, str]] = None,
    ):
        self._prompt_files: List[Path] = _as_path_list(prompt_file)
        self._fallback_prompt_file: Optional[Path] = (
            Path(fallback_prompt_file) if fallback_prompt_file else None
        )
        self._skills: Optional[SkillsLoader] = skills_loader
        self._prompt_cache: Optional[str] = None
        self._prompt_sig: Tuple[Tuple[str, float], ...] = ()
        self._providers: List[ContextProvider] = list(providers or [])

    # ------------------------------------------------------------------
    # 构造入口
    # ------------------------------------------------------------------

    @classmethod
    def from_workspace(
        cls,
        workspace_dir: Union[Path, str],
        extra_identity_files: Optional[Sequence[Union[Path, str]]] = None,
        providers: Optional[List[ContextProvider]] = None,
        skills_loader: Optional[SkillsLoader] = None,
    ) -> "LayeredPromptBuilder":
        """从用户工作空间构造：身份定义取自 ``workspace_dir/agent.md``。

        与直接构造的区别仅在角色定义来源——``agent.md`` 属于用户工作空间，
        可被编辑、随空间迁移；文件缺失时回退到 ``builtins/agent.md``。
        技能加载器默认指向 ``workspace_dir/skills``。

        Args:
            workspace_dir:        工作空间根目录。
            extra_identity_files: 追加的身份定义文件（绝对路径），按序拼在 agent.md 之后。
            providers:            动态片段提供者列表。
            skills_loader:        自定义技能加载器；为 None 时按工作空间约定创建。
        """
        from ..builtins import DEFAULT_AGENT_IDENTITY_FILE

        root = Path(workspace_dir).resolve()
        files: List[Path] = [root / "agent.md"]
        files.extend(Path(f) for f in (extra_identity_files or []))
        return cls(
            prompt_file=files,
            skills_loader=skills_loader
            or SkillsLoader(workspace_skills_dir=root / "skills"),
            providers=providers,
            fallback_prompt_file=DEFAULT_AGENT_IDENTITY_FILE,
        )

    # ------------------------------------------------------------------
    # Provider 管理
    # ------------------------------------------------------------------

    @property
    def providers(self) -> List[ContextProvider]:
        """当前已注册的动态片段提供者。"""
        return list(self._providers)

    def add_provider(self, provider: ContextProvider) -> "LayeredPromptBuilder":
        """追加一个动态片段提供者（排在末位），返回自身以便链式调用。"""
        self._providers.append(provider)
        return self

    def prepend_provider(self, provider: ContextProvider) -> "LayeredPromptBuilder":
        """插入一个动态片段提供者到首位，返回自身以便链式调用。

        用于让某个片段优先于其他片段出现（如把内联 role prompt 前置）。
        """
        self._providers.insert(0, provider)
        return self

    # ------------------------------------------------------------------
    # 核心接口
    # ------------------------------------------------------------------

    def build_system_prompt(
        self,
        skill_names: Optional[List[str]] = None,
        extra_sections: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """构建 system prompt（同步版，不含 provider 片段）。

        Args:
            skill_names:    本次额外注入的技能名称列表。
            extra_sections: 已渲染好的额外片段（由异步路径传入 provider 结果）。
        """
        parts: List[str] = []

        # 1. 从 .md 文件读取角色定义
        role_prompt = self._load_prompt_file()
        if role_prompt:
            parts.append(role_prompt)

        # 2. 动态片段（由 build_system_prompt_async 传入）
        if extra_sections:
            parts.extend(s for s in extra_sections if s and s.strip())

        if self._skills:
            # 3. Always Skills（始终注入）
            always_skills = self._skills.get_always_skills()
            if always_skills:
                always_content = self._skills.load_skills_for_context(always_skills)
                if always_content:
                    parts.append(f"## 激活技能\n\n{always_content}")

            # 4. 额外指定的技能（去重 always 已有的）
            if skill_names:
                extra = [n for n in skill_names if n not in always_skills]
                if extra:
                    extra_content = self._skills.load_skills_for_context(extra)
                    if extra_content:
                        parts.append(f"## 本次技能\n\n{extra_content}")

            # 5. Skills 摘要（供 Agent 按需读取，排除已注入的）
            injected = set(always_skills or [])
            if skill_names:
                injected.update(skill_names)
            skills_summary = self._skills.build_skills_summary(exclude=injected)
            if skills_summary:
                parts.append(
                    f"## 可用技能\n\n"
                    f"以下技能可扩展你的能力。如需使用某个技能，请读取其 SKILL.md 文件。\n\n"
                    f"{skills_summary}"
                )

        return "\n\n---\n\n".join(parts)

    async def build_system_prompt_async(
        self,
        ctx: "RunContext",
        user_input: str = "",
        skill_names: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """构建 system prompt（异步版，含 provider 动态片段）。

        Agent 循环走此路径，因此 provider 可以做 IO（查库、检索、调 LLM）。
        """
        sections = await gather_provider_sections(self._providers, ctx, user_input)
        return self.build_system_prompt(
            skill_names=skill_names, extra_sections=sections, **kwargs
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _load_prompt_file(self) -> str:
        """读取角色定义文本（多文件按序拼接，带 mtime 失效缓存）。

        解析顺序：``prompt_file`` 中存在的文件按序拼接；若全部不存在，
        回退到 ``fallback_prompt_file``。

        缓存签名由所有参与文件的 (路径, mtime) 组成：既避免每步推理重复
        磁盘 IO，又支持编辑任一文件后无需重启即生效。
        """
        files = [p for p in self._prompt_files if p.exists()]
        if not files and self._fallback_prompt_file:
            if self._fallback_prompt_file.exists():
                files = [self._fallback_prompt_file]

        if not files:
            self._prompt_cache = ""
            self._prompt_sig = ()
            return ""

        sig = tuple((str(p), p.stat().st_mtime) for p in files)
        if self._prompt_cache is None or sig != self._prompt_sig:
            parts = []
            for p in files:
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(text)
            self._prompt_cache = "\n\n".join(parts)
            self._prompt_sig = sig
        return self._prompt_cache

    def reload_prompt(self) -> None:
        """清除缓存，下次 build 时重新读取文件（用于热更新）。"""
        self._prompt_cache = None
        self._prompt_sig = ()

    def __repr__(self) -> str:
        shown = ", ".join(p.name for p in self._prompt_files) or "-"
        return f"LayeredPromptBuilder(prompt_file={shown})"


def _as_path_list(
    value: Optional[Union[Path, str, Sequence[Union[Path, str]]]],
) -> List[Path]:
    """把单个路径或路径序列统一规整为 List[Path]。"""
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        return [Path(value)]
    if isinstance(value, Iterable):
        return [Path(v) for v in value]
    return []
