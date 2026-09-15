"""子 Agent 工厂：planner / researcher / tex_writer / exercises。

改造后本模块只是 :mod:`agents.registry` 的薄适配层——Agent 的 prompt、
工具集、预算全部在注册表中声明，prompt 已外置为
``agents/prompts/immersive/*.md``。

改造前这里内联了上百行 Python 字符串 prompt，且 4 处 ToolRegistry
各自构造工具实例，无法与其他场景复用。
"""

from __future__ import annotations

import logging
from typing import Dict

from agent_core.agent import ReActAgent
from agent_core.layout import UserDataLayout

logger = logging.getLogger(__name__)

#: 课程生成流水线的四个子 Agent（注册表中的名字）
SUB_AGENT_NAMES = {
    "planner": "course.planner",
    "researcher": "course.researcher",
    "tex_writer": "course.tex_writer",
    "exercises": "course.exercises",
}


def build_sub_agents(layout: UserDataLayout, user_id: str) -> Dict[str, ReActAgent]:
    """构建 4 个独立子 Agent。

    每个子 Agent 持有独立实例（含独立记忆），因此可安全并发执行。

    Args:
        layout:  用户工作空间布局，决定技能加载路径。
        user_id: 用户 ID，用于 LLM 装配与画像注入。

    Returns:
        ``{短名: Agent 实例}``，短名为 planner / researcher / tex_writer / exercises。
    """
    from agents.registry import build_agent

    # 搜索 / 图像工具经 tool_catalog → services/*_factory 装配，
    # 额度拦截与记账统一挂在工厂产出的客户端上（与 LLM 同构）
    agents: Dict[str, ReActAgent] = {}
    for short_name, spec_name in SUB_AGENT_NAMES.items():
        agents[short_name] = build_agent(
            spec_name,
            user_id=user_id,
            workspace_dir=layout.root,
        )
    return agents


__all__ = ["SUB_AGENT_NAMES", "build_sub_agents"]
