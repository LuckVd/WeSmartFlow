"""声明式 Agent 注册表。

改造前 Agent 的定义（prompt + 工具集 + 参数）散落在各 Service 里现场拼装：
``TutorService._build_tools()`` 组装 12 个工具、``immersive/agents.py`` 把
上百行 prompt 硬编码为 Python 多行字符串。后果是新增一个 Agent 场景只能
整套复制——所以 ``court`` 和 ``examples`` 干脆绕过框架各写一套。

本模块把 Agent 定义收敛为**声明**：一个 Agent = prompt 文件 + 工具名列表 +
范式 + 预算 + 记忆策略。新增场景 = 加一条 :class:`AgentSpec` + 一个 md 文件。

用法::

    from agents.registry import build_agent

    agent = build_agent("tutor", user_id=uid, session_id=sid, ctx=ctx)

工具通过名字从 :mod:`agents.tool_catalog` 解析，因此同一个工具可被多个
Agent 复用而无需重复构造代码。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent_core.agent import ReActAgent
from agent_core.agent.base import BaseAgent
from agent_core.context.provider import ContextProvider
from agent_core.context.static import StaticPromptBuilder
from agent_core.context.layered import LayeredPromptBuilder
from agent_core.memory import BaseMemory, FullMemory, SummaryMemory, WindowMemory
from agent_core.runtime.budget import Budget
from agent_core.skills.loader import SkillsLoader
from agent_core.tool.registry import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
SKILLS_DIR = PROMPTS_DIR / "skills"

# ----------------------------------------------------------------------
# 声明结构
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MemorySpec:
    """记忆策略声明。

    Attributes:
        kind:    ``full`` / ``window`` / ``summary``。
        window:  保留原文的消息条数（window / summary 有效）。
        trigger: 触发摘要的总消息数阈值（summary 有效）。

    .. note::
       此前有 ``max_tokens`` 字段，语义是"单次请求 history 上限"。但它只
       统计 history、看不到 system 与 tool schema，预算形同虚设。现由
       ``agent_core.context.assemble`` 扣除固定开销后下发真实预算。
    """

    kind: str = "full"
    window: int = 30
    trigger: int = 40

    def build(self, llm: Any = None) -> BaseMemory:
        """按声明构造记忆实例。"""
        if self.kind == "window":
            return WindowMemory(window=self.window)
        if self.kind == "summary":
            if llm is None:
                logger.warning("SummaryMemory 需要 llm，降级为 WindowMemory")
                return WindowMemory(window=self.window)
            return SummaryMemory(llm=llm, window=self.window, trigger=self.trigger)
        return FullMemory()


@dataclass(frozen=True)
class AgentSpec:
    """一个 Agent 的完整声明。

    Attributes:
        prompt:     prompt 文件相对 ``agents/prompts/`` 的路径；为空则用 inline_prompt。
        inline_prompt: 直接内联的 prompt 文本（仅用于极短的角色定义）。
        tools:      工具名列表，由 tool_catalog 解析为实例。
        providers:  ContextProvider 名列表，由 provider_catalog 解析。
        skills:     是否启用技能加载（渐进式披露）。
        memory:     记忆策略声明。
        budget:     资源预算（步数、工具数、token、成本、时限）。
        llm_config: 透传给 LLM 的额外参数（temperature 等）。
        context_window: 覆盖模型上下文窗口（token）。0 表示按
                        ``LLM_CONTEXT_WINDOW`` 环境变量或模型名自动推断。
                        仅在需要为特定 Agent 收紧窗口时才显式设置。
        description: 供 ``as_tool()`` 使用的描述，多 Agent 协作时必填。
    """

    prompt: str = ""
    inline_prompt: str = ""
    tools: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    skills: bool = False
    memory: MemorySpec = field(default_factory=MemorySpec)
    budget: Budget = field(default_factory=lambda: Budget(max_steps=20))
    llm_config: Dict[str, Any] = field(default_factory=dict)
    context_window: int = 0
    description: str = ""

    @property
    def prompt_path(self) -> Optional[Path]:
        """prompt 文件的绝对路径。"""
        return (PROMPTS_DIR / self.prompt) if self.prompt else None


# ----------------------------------------------------------------------
# Agent 声明清单
# ----------------------------------------------------------------------

AGENTS: Dict[str, AgentSpec] = {
    # ── 主线：交互式辅导 ──────────────────────────────────
    "tutor": AgentSpec(
        prompt="tutor.md",
        tools=(
            "now",
            "search_nodes",
            "get_node",
            "create_node",
            "update_node",
            "update_mastery",
            "create_quiz",
            "kg_search",
            "kg_resolve",
            "kg_propose_missing",
            "kg_record_observation",
            "generate_html_card",
            "generate_viz",
            "smart_search",
            "read_file",
            "list_dir",
        ),
        providers=(),  # 画像激活/交互建议/KG 前置检索由 TutorService 按轮次经 extra_providers 注入
        skills=True,
        # 运行时 TutorService 经 ctx.memory 注入 SessionMemory（跨 run 连续：
        # 游标切片 + 锚点 + 轨迹 + 滚动摘要）；此声明仅为无 ctx.memory
        # 场景（如 as_tool 子 Agent）的兜底。
        memory=MemorySpec(kind="window", window=24),
        budget=Budget(max_steps=20, max_tool_calls=40),
        description="交互式学习辅导 Agent",
    ),
    # ── 沉浸式课程生成流水线的四个子 Agent ────────────────
    "course.planner": AgentSpec(
        prompt="immersive/planner.md",
        tools=("tavily", "arxiv", "web_fetch", "write_file"),
        providers=("profile",),
        budget=Budget(max_steps=10),
        description="课程大纲规划师，输出 outline.json",
    ),
    "course.researcher": AgentSpec(
        prompt="immersive/researcher.md",
        tools=("tavily", "arxiv", "web_fetch", "write_file"),
        budget=Budget(max_steps=14),
        description="章节资料检索与整理，输出 research.json",
    ),
    "course.tex_writer": AgentSpec(
        prompt="immersive/tex_writer.md",
        tools=("read_file_any", "write_file", "image_gen", "latex_compile"),
        providers=("profile",),
        skills=True,
        budget=Budget(max_steps=15),
        description="LaTeX Beamer 讲义撰写与编译",
    ),
    "course.exercises": AgentSpec(
        prompt="immersive/exercises.md",
        tools=("read_file_any", "write_file"),
        providers=("profile",),
        budget=Budget(max_steps=8),
        description="习题生成，输出 9 道单选题 Markdown",
    ),
}


# ----------------------------------------------------------------------
# 构建
# ----------------------------------------------------------------------


def get_spec(name: str) -> AgentSpec:
    """按名字取得 Agent 声明。

    Raises:
        KeyError: 未注册的 Agent 名。
    """
    if name not in AGENTS:
        raise KeyError(f"未注册的 Agent: {name}，可用: {sorted(AGENTS)}")
    return AGENTS[name]


def build_agent(
    name: str,
    *,
    llm: Any = None,
    user_id: str = "",
    session_id: str = "",
    tool_overrides: Optional[List[Any]] = None,
    extra_providers: Optional[List[ContextProvider]] = None,
    on_result_hook: Optional[Callable] = None,
    workspace_dir: Optional[Path] = None,
    **tool_kwargs: Any,
) -> BaseAgent:
    """按声明构建 Agent 实例。

    Args:
        name:            Agent 名，见 :data:`AGENTS`。
        llm:             LLM 实例；为 None 时通过 ``llm_factory`` 按 user_id 获取。
        user_id:         用户 ID，传递给需要它的工具与 provider。
        session_id:      会话 ID，传递给需要它的工具。
        tool_overrides:  直接指定工具实例列表，跳过 catalog 解析（测试/特殊场景）。
        extra_providers: 追加的 ContextProvider（如动态后缀）。
        on_result_hook:  统一挂给支持它的工具的结果 hook。
        workspace_dir:   工作空间目录，影响技能加载路径。
        **tool_kwargs:   透传给工具构造器的额外参数。

    Returns:
        已装配好的 Agent 实例。
    """
    spec = get_spec(name)

    if llm is None:
        from services.llm_factory import get_llm

        llm = get_llm(
            user_id, scene="immersive" if name.startswith("course.") else "chat"
        )

    # --- 工具 ---
    # hook 由 ToolRegistry 在注册时绑定（工具实例本身不持有 hook），
    # 因此这里直接构造出治理就绪的 registry。
    if tool_overrides is not None:
        tool_registry = ToolRegistry(list(tool_overrides))
    else:
        from agents.tool_catalog import build_registry

        tool_registry = build_registry(
            spec.tools,
            user_id=user_id,
            session_id=session_id,
            on_result_hook=on_result_hook,
            **tool_kwargs,
        )

    # --- system prompt 构建器 ---
    providers = _resolve_providers(spec.providers, user_id=user_id)
    if extra_providers:
        providers.extend(extra_providers)

    prompt_builder = _build_prompt_builder(
        spec, providers=providers, workspace_dir=workspace_dir
    )

    # --- 组装 ---
    return ReActAgent(
        llm=llm,
        prompt_builder=prompt_builder,
        tool_registry=tool_registry,
        max_steps=spec.budget.max_steps or 20,
        llm_config=dict(spec.llm_config) if spec.llm_config else None,
        memory_factory=lambda: spec.memory.build(llm),
        context_window=spec.context_window or None,
    )


def build_agent_as_tool(name: str, **kwargs: Any) -> Any:
    """构建 Agent 并包装为工具，供父 Agent 层级调用。"""
    spec = get_spec(name)
    agent = build_agent(name, **kwargs)
    return agent.as_tool(
        name=name.replace(".", "_"),
        description=spec.description or f"{name} 子 Agent",
    )


# ----------------------------------------------------------------------
# 内部辅助
# ----------------------------------------------------------------------


def _resolve_providers(
    names: tuple[str, ...], user_id: str = ""
) -> List[ContextProvider]:
    """把 provider 名解析为实例。"""
    if not names:
        return []

    from agents.providers import KGPreRAGProvider, ProfileProvider

    catalog: Dict[str, Callable[[], ContextProvider]] = {
        "profile": lambda: ProfileProvider(user_id),
        "kg_prerag": lambda: KGPreRAGProvider(),
    }

    resolved: List[ContextProvider] = []
    for n in names:
        factory = catalog.get(n)
        if factory is None:
            logger.warning("未知 ContextProvider: %s，已跳过", n)
            continue
        resolved.append(factory())
    return resolved


def _build_prompt_builder(
    spec: AgentSpec,
    providers: List[ContextProvider],
    workspace_dir: Optional[Path] = None,
) -> Any:
    """按声明构造 SystemPromptBuilder。"""
    prompt_path = spec.prompt_path

    # 无 prompt 文件且有内联文本 → StaticPromptBuilder
    if prompt_path is None and spec.inline_prompt:
        if not providers:
            return StaticPromptBuilder(spec.inline_prompt)
        # 有 provider 时需 Layered 以支持异步注入；内联 prompt 前置为首个片段
        from agent_core.context.provider import StaticProvider

        return LayeredPromptBuilder(providers=providers).prepend_provider(
            StaticProvider("role", spec.inline_prompt)
        )

    skills_loader = None
    if spec.skills:
        skills_dir = (workspace_dir / "skills") if workspace_dir else SKILLS_DIR
        skills_loader = SkillsLoader(workspace_skills_dir=skills_dir)

    return LayeredPromptBuilder(
        prompt_file=prompt_path,
        skills_loader=skills_loader,
        providers=providers,
    )


__all__ = [
    "AGENTS",
    "AgentSpec",
    "MemorySpec",
    "build_agent",
    "build_agent_as_tool",
    "get_spec",
]
