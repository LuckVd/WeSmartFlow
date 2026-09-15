"""工具目录：按名字解析工具实例。

把"工具名 → 构造方式"的映射集中到一处，使 :mod:`agents.registry` 中的
Agent 声明只需列工具名。同一个工具可被多个 Agent 复用，无需重复构造代码。

改造前这些构造逻辑散落在 ``TutorService._build_tools()``（12 个工具）与
``immersive/agents.py``（4 处 ToolRegistry），互相无法复用。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, NamedTuple, Optional

if TYPE_CHECKING:
    from agent_core.tool import ToolRegistry

logger = logging.getLogger(__name__)

_AGENTS_SKILLS_DIR = Path(__file__).parent / "prompts" / "skills"


# ----------------------------------------------------------------------
# 工具构造器
# ----------------------------------------------------------------------
#
# 每个构造器签名统一为 (ctx: dict) -> BaseTool，ctx 内含 user_id /
# session_id 等装配参数。
#
# 搜索 / 图像 / TTS 等外部接口类工具一律通过 services/*_factory
# 获取客户端（额度拦截与记账挂在工厂产出物上），本目录不再
# 自行构造后端客户端。


def _make_catalog() -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    """构建工具名到构造器的映射（惰性 import 以避免启动期循环依赖）。"""

    def now(_c):
        from agents.tools.builtin import get_current_time

        return get_current_time

    def search_nodes(c):
        from agents.tools.search_nodes import SearchNodesTool

        return SearchNodesTool(c["user_id"])

    def get_node(c):
        from agents.tools.get_node import GetNodeTool

        return GetNodeTool(c["user_id"])

    def create_node(c):
        from agents.tools.create_node import SessionCreateNodeTool

        return SessionCreateNodeTool(c["user_id"], c["session_id"])

    def update_node(c):
        from agents.tools.update_node import UpdateNodeTool

        return UpdateNodeTool(c["user_id"])

    def update_mastery(c):
        from agents.tools.update_mastery import UpdateMasteryTool

        return UpdateMasteryTool(c["user_id"])

    def create_quiz(c):
        from agents.tools.create_quiz import CreateQuizTool

        return CreateQuizTool(c["user_id"], c["session_id"])

    def kg_search(_c):
        from agents.tools.kg_tools import KGSearchTool

        return KGSearchTool()

    def kg_resolve(_c):
        from agents.tools.kg_tools import KGResolveTool

        return KGResolveTool()

    def kg_propose_missing(c):
        from agents.tools.kg_tools import KGProposeMissingConceptTool

        return KGProposeMissingConceptTool(c["user_id"], c["session_id"])

    def kg_record_observation(c):
        from agents.tools.kg_tools import KGRecordObservationTool

        return KGRecordObservationTool(c["user_id"], c["session_id"])

    def generate_html_card(c):
        from agents.tools.generate_html_card import GenerateHtmlCardTool

        return GenerateHtmlCardTool(
            user_id=c["user_id"],
            session_id=c["session_id"],
        )

    def generate_viz(c):
        from agents.tools.generate_viz import GenerateInteractiveVizTool

        return GenerateInteractiveVizTool(
            user_id=c["user_id"],
            session_id=c["session_id"],
        )

    def smart_search(c):
        from services.search_factory import get_search_client
        from services.smart_search import SmartSearchTool

        return SmartSearchTool(
            user_id=c["user_id"],
            tavily_client=get_search_client(c["user_id"], scene="search"),
            anysearch_key=os.getenv("ANYSEARCH_API_KEY", ""),
        )

    def tavily(c):
        from agent_core.tool import TavilySearch
        from services.search_factory import get_search_client

        return TavilySearch(client=get_search_client(c["user_id"], scene="search"))

    def arxiv(_c):
        from agent_core.tool import ArxivSearch

        return ArxivSearch()

    def web_fetch(_c):
        from agent_core.tool import WebFetch

        return WebFetch()

    def read_file(_c):
        from agent_core.builtins import BUILTIN_SKILLS_DIR
        from agent_core.tool.filesystem import ReadFileTool

        return ReadFileTool(
            allowed_dir=BUILTIN_SKILLS_DIR,
            extra_allowed_dirs=[_AGENTS_SKILLS_DIR],
        )

    def list_dir(_c):
        from agent_core.builtins import BUILTIN_SKILLS_DIR
        from agent_core.tool.filesystem import ListDirTool

        return ListDirTool(
            allowed_dir=BUILTIN_SKILLS_DIR,
            extra_allowed_dirs=[_AGENTS_SKILLS_DIR],
        )

    def read_file_any(_c):
        """无目录限制的读文件（课程生成流水线需跨目录读写产物）。"""
        from agent_core.tool import ReadFileTool

        return ReadFileTool()

    def write_file(_c):
        from agent_core.tool import WriteFileTool

        return WriteFileTool()

    def image_gen(c):
        from agents.tools.image_gen_factory import build_image_gen_tool

        return build_image_gen_tool(c["user_id"])

    def latex_compile(_c):
        from agent_core.tool import LatexPdfCompileTool
        from config import TEX_TEMPLATE_DIR

        return LatexPdfCompileTool(TEX_TEMPLATE_DIR)

    return {
        "now": now,
        "search_nodes": search_nodes,
        "get_node": get_node,
        "create_node": create_node,
        "update_node": update_node,
        "update_mastery": update_mastery,
        "create_quiz": create_quiz,
        "kg_search": kg_search,
        "kg_resolve": kg_resolve,
        "kg_propose_missing": kg_propose_missing,
        "kg_record_observation": kg_record_observation,
        "generate_html_card": generate_html_card,
        "generate_viz": generate_viz,
        "smart_search": smart_search,
        "tavily": tavily,
        "arxiv": arxiv,
        "web_fetch": web_fetch,
        "read_file": read_file,
        "list_dir": list_dir,
        "read_file_any": read_file_any,
        "write_file": write_file,
        "image_gen": image_gen,
        "latex_compile": latex_compile,
    }


_CATALOG: Optional[Dict[str, Callable[[Dict[str, Any]], Any]]] = None

# ── 工具的治理 hook 需求声明 ────────────────────────────────────
# 工具实例本身不持有 hook（见 BaseTool 文档），由 ToolRegistry 在注册时绑定。
# 这里声明「哪个工具需要哪种 hook」，build_tools 据此产出绑定计划。
#
# 搜索 / 图像类工具的额度拦截与记账已下沉到工厂产出的客户端
# （services/search_factory / image_factory），注册时无需再绑；
# 此处只剩需要 on_result 的业务事件类工具。
#
# 取值：
#   "result"  会产出业务事件、需要 on_result hook
_TOOL_HOOK_NEEDS: Dict[str, str] = {
    "create_node": "result",
    "update_mastery": "result",
    "create_quiz": "result",
    "generate_html_card": "result",
    "generate_viz": "result",
}


class ToolPlan(NamedTuple):
    """工具装配计划：实例 + 该实例需要绑定的 hook。

    供调用方喂给 :meth:`ToolRegistry.register`：

    .. code-block:: python

        for plan in build_tools(...):
            registry.register(
                plan.tool, before_call=plan.before_call, on_result=plan.on_result
            )

    或直接用 :func:`build_registry` 一步到位。
    """

    tool: Any
    before_call: Optional[Callable] = None
    on_result: Optional[Callable] = None


def catalog() -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    """获取工具目录（首次调用时构建并缓存）。"""
    global _CATALOG  # pylint: disable=global-statement
    if _CATALOG is None:
        _CATALOG = _make_catalog()
    return _CATALOG


def build_plans(
    names: tuple[str, ...] | List[str],
    *,
    user_id: str = "",
    session_id: str = "",
    on_result_hook: Optional[Callable] = None,
    **extra: Any,
) -> List[ToolPlan]:
    """按名字批量构造工具，并给出各自需要绑定的 hook。

    未知工具名会告警并跳过，不中断装配——这样某个工具因缺少依赖不可用时，
    Agent 仍能带着其余工具工作（与 SkillsLoader 的降级策略一致）。

    Args:
        names:          工具名列表。
        user_id:        用户 ID。
        session_id:     会话 ID。
        on_result_hook: 结果 hook，绑定给声明需要 "result" 的工具。

    Returns:
        :class:`ToolPlan` 列表（顺序与 names 一致）。

    Note:
        搜索 / 图像类工具的额度 hook 已由工厂挂在客户端上
        （``services/search_factory`` / ``image_factory``），
        不再通过 ``before_call`` 绑定。
    """
    ctx: Dict[str, Any] = {
        "user_id": user_id,
        "session_id": session_id,
        **extra,
    }
    hook_by_kind = {
        "result": on_result_hook,
    }

    cat = catalog()
    plans: List[ToolPlan] = []
    for name in names:
        factory = cat.get(name)
        if factory is None:
            logger.warning("未知工具名: %s，已跳过", name)
            continue
        try:
            tool = factory(ctx)
        except Exception:  # pylint: disable=broad-except
            logger.warning("工具 %s 构造失败，已跳过", name, exc_info=True)
            continue

        kind = _TOOL_HOOK_NEEDS.get(name)
        if kind == "result":
            plans.append(ToolPlan(tool, on_result=hook_by_kind.get(kind)))
        else:
            plans.append(ToolPlan(tool))
    return plans


def build_tools(
    names: tuple[str, ...] | List[str],
    **kwargs: Any,
) -> List[Any]:
    """按名字批量构造工具实例（不含 hook 绑定）。

    仅在调用方不需要治理 hook 时使用（脚本、测试、以及那些确实无需
    额度检查的场景）。需要 hook 请改用 :func:`build_plans` 或
    :func:`build_registry`。

    Returns:
        工具实例列表（顺序与 names 一致）。
    """
    return [p.tool for p in build_plans(names, **kwargs)]


def build_registry(
    names: tuple[str, ...] | List[str],
    **kwargs: Any,
) -> "ToolRegistry":
    """构造工具并注册进一个新的 :class:`ToolRegistry`，同时完成 hook 绑定。

    这是业务层的推荐入口——一步得到治理就绪的 registry。
    """
    from agent_core.tool import ToolRegistry

    registry = ToolRegistry()
    for plan in build_plans(names, **kwargs):
        registry.register(
            plan.tool, before_call=plan.before_call, on_result=plan.on_result
        )
    return registry


__all__ = ["ToolPlan", "build_plans", "build_registry", "build_tools", "catalog"]
