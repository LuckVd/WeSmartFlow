"""业务侧 ContextProvider 实现。

每个 provider 负责向 system prompt 注入一段动态内容。框架只按顺序调用并
拼接，不知道内容是什么——这断开了此前 ``agent_core`` 反向 import
``services.profile_service`` 的依赖倒置。

三个 provider 分别取代了改造前的三处 hack：

===========================  ==============================================
改造前                        现在
===========================  ==============================================
框架内 import 业务画像服务      :class:`ProfileProvider`
Service 内动态定义闭包子类      :class:`StaticSuffixProvider`
KG 检索硬编码在 prompt 拼装     :class:`KGPreRAGProvider`
===========================  ==============================================
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from agent_core.runtime.run_context import RunContext

logger = logging.getLogger(__name__)


class ProfileProvider:
    """注入用户画像总览。

    只读已编译的 overview，不触发 LLM，因此开销可控。
    """

    name = "profile"
    title = "用户画像（统一总览）"

    def __init__(self, user_id: str):
        self._user_id = user_id

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        if not self._user_id:
            return None
        from services.profile_service import ProfileMemoryService

        return ProfileMemoryService().build_profile_text(self._user_id).strip()

    def __repr__(self) -> str:
        return f"<ProfileProvider user_id={self._user_id}>"


class StaticSuffixProvider:
    """注入调用方预先算好的文本片段。

    用于上层已完成计算、只需原样追加的场景（如 court 等业务拼好的
    动态后缀）。

    取代改造前"在方法内动态定义 SystemPromptBuilder 子类以闭包捕获后缀"的写法。
    """

    name = "dynamic_suffix"
    title = ""  # 内容自带标题，不再包一层

    def __init__(self, text: str, name: str = "dynamic_suffix"):
        self.name = name
        self._text = (text or "").strip()

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        return self._text or None

    def __repr__(self) -> str:
        return f"<StaticSuffixProvider {self.name} len={len(self._text)}>"


class LazySuffixProvider:
    """注入延迟计算的文本片段。

    与 :class:`StaticSuffixProvider` 的区别：文本在每步推理时才计算，
    因此可反映运行期变化。回调可以是同步或异步函数。
    """

    name = "lazy_suffix"
    title = ""

    def __init__(
        self,
        fn: Callable[[], Any],
        name: str = "lazy_suffix",
        title: str = "",
    ):
        self.name = name
        self.title = title
        self._fn = fn

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        import inspect

        ret = self._fn()
        if inspect.isawaitable(ret):
            ret = await ret
        return str(ret).strip() if ret else None

    def __repr__(self) -> str:
        return f"<LazySuffixProvider {self.name}>"


class KGPreRAGProvider:
    """按用户输入检索公共知识图谱，注入相关概念作为前置上下文。

    这是"检索增强"的注入点：把与本轮提问相关的概念提前放进 system prompt，
    减少 Agent 主动调用 ``kg_search`` 工具的轮次（省一次往返）。

    检索失败或降级时静默跳过——前置注入是增强而非必需。

    Args:
        top_k: 注入的概念条数上限。
        summary_limit: 每条概念摘要的字符上限。
    """

    name = "kg_prerag"
    title = "相关知识概念（自动检索）"

    def __init__(self, top_k: int = 5, summary_limit: int = 200):
        self._top_k = top_k
        self._summary_limit = summary_limit

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        query = (user_input or "").strip()
        if not query:
            return None

        try:
            from kg.models import RetrieveRequest
            from services import kg_facade
        except ImportError:
            logger.debug("KG 检索不可用，跳过前置注入")
            return None

        try:
            resp = kg_facade.retrieve(
                RetrieveRequest(
                    query=query,
                    need_facets=False,
                    graph_expand=False,
                    anchor_max_entries=self._top_k,
                )
            )
        except Exception:  # pylint: disable=broad-except
            logger.warning("KG 前置检索失败，跳过注入", exc_info=True)
            return None

        concepts = getattr(resp, "concepts", None) or []
        if not concepts:
            return None

        lines = []
        for concept in concepts[: self._top_k]:
            name = getattr(concept, "canonical_name", "") or ""
            summary = (getattr(concept, "summary", "") or "").strip()
            if not name:
                continue
            if summary:
                lines.append(f"- **{name}**：{summary[: self._summary_limit]}")
            else:
                lines.append(f"- **{name}**")

        return "\n".join(lines) if lines else None

    def __repr__(self) -> str:
        return f"<KGPreRAGProvider top_k={self._top_k}>"


# ── 会话级 provider ──────────────────────────────────────────────
#
# 画像激活与交互建议经 provider 注入 system；会话滚动摘要**不在此处**——
# 由 ``agent_core.memory.SessionMemory`` 的 ``summary`` 属性经装配层
# （``assemble._merge_summary``）自动合并进 system prompt。
# 历史窗口裁剪同样交给框架 memory（SessionMemory / WindowMemory）。


# task_type 关键词规则（与 ProfileSkillRepository.list_for_task 的
# trigger_conditions 对齐；列表有序：靠前的优先匹配）。
_TASK_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "quiz",
        ("测验", "练习", "出题", "做题", "题目", "考考", "测试一下", "刷题", "小测"),
    ),
    (
        "review",
        ("复习", "回顾", "巩固", "记不住", "忘了", "忘记", "温习", "默写"),
    ),
    (
        "path",
        (
            "学习路径",
            "学习计划",
            "怎么学",
            "从哪开始",
            "从哪学",
            "学习路线",
            "规划一下",
            "制定计划",
        ),
    ),
    (
        "explanation",
        (
            "讲解",
            "解释",
            "为什么",
            "怎么",
            "是什么",
            "原理",
            "推导",
            "证明",
            "不懂",
            "不理解",
            "看不懂",
            "举例",
            "举个例子",
            "通俗",
            "详细讲",
        ),
    ),
]


def infer_task_type(user_message: str) -> str:
    """按关键词推断本轮任务类型（轻量规则，零成本可解释）。"""
    text = (user_message or "").lower()
    if not text:
        return "general"
    for task_type, keywords in _TASK_RULES:
        for kw in keywords:
            if kw in text:
                return task_type
    return "general"


class ActivatedProfileProvider:
    """按本轮任务类型注入「激活后」的画像片段（主题感知召回）。

    与 :class:`ProfileProvider`（全量总览）的区别：只注入与本轮任务
    相关的画像内容（整体判断 + 知识面 + 学习行为与策略），
    task_type 在构造时按用户消息推断（纯规则，零 LLM）。
    """

    name = "activated_profile"
    title = "用户画像（按当前话题激活）"

    def __init__(self, user_id: str, user_message: str = "", limit: int = 1200):
        self._user_id = user_id
        self._task_type = infer_task_type(user_message)
        self._limit = limit

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        if not self._user_id:
            return None
        from services.profile_service import ProfileMemoryService

        text = (
            ProfileMemoryService().build_activated_profile_text(
                self._user_id, self._task_type
            )
            or ""
        ).strip()
        if len(text) > self._limit:
            text = text[: self._limit - 1].rstrip() + "…"
        return text or None

    def __repr__(self) -> str:
        return (
            f"<ActivatedProfileProvider user_id={self._user_id} task={self._task_type}>"
        )


class InteractionHintProvider:
    """注入本轮交互模式建议（纯规则判定，零 LLM）。

    构造时用 :class:`~services.policy.interaction.InteractionPolicy`
    完成判定（首轮/近期卡片等信号在此时计算），provide 只返回渲染
    好的建议文本——判定逻辑见 :mod:`services.policy.interaction`。
    """

    name = "interaction_hint"
    title = ""  # render_hint 自带结构，不再包一层

    def __init__(self, user_message: str, chat_history: list, session: Any):
        from services.policy.interaction import (
            InteractionPolicy,
            has_recent_card,
            is_first_turn,
        )

        self._decision = InteractionPolicy().decide(
            user_message,
            first_turn=is_first_turn(chat_history),
            recent_card=has_recent_card(chat_history, session),
        )
        logger.debug(
            "[InteractionHint] mode=%s rule=%s",
            self._decision.mode,
            self._decision.rule,
        )

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        return self._decision.render_hint() or None

    def __repr__(self) -> str:
        return f"<InteractionHintProvider mode={self._decision.mode}>"


__all__ = [
    "ActivatedProfileProvider",
    "InteractionHintProvider",
    "KGPreRAGProvider",
    "LazySuffixProvider",
    "ProfileProvider",
    "StaticSuffixProvider",
    "infer_task_type",
]
