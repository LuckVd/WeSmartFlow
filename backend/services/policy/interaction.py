"""交互模式判定策略。

判断本轮对话应以哪种形态回应：纯对话 / 生成知识卡片 / 生成练习题 /
生成交互可视化。结果只作为 system prompt 的**建议**，不硬拦工具调用。

改造前这套逻辑（150 行、100+ 个中文关键词）硬编码在 ``TutorService`` 里，
新增一个交互模式必须改代码。现在关键词表外置为模块级常量并可被覆盖，
判定规则按优先级声明式排列。

设计取向：**规则优先，零 LLM 调用**。判定发生在主对话路径上，每轮都要执行，
用 LLM 会增加一次往返延迟与成本。规则不足时才考虑加 LLM 兜底
（见 :meth:`InteractionPolicy.decide` 的扩展点说明）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# 模式常量
# ----------------------------------------------------------------------

MODE_CHAT = "chat"
MODE_CARD = "card"
MODE_QUIZ = "quiz"
MODE_VIZ = "visualization"

MODE_LABELS: Dict[str, str] = {
    MODE_CHAT: "对话交流",
    MODE_CARD: "生成知识卡片",
    MODE_QUIZ: "生成练习题",
    MODE_VIZ: "生成交互可视化",
}

MODE_GUIDANCE: Dict[str, str] = {
    MODE_CHAT: (
        "本轮优先直接用文字交流，不要生成新的知识卡片；除非用户再次明确要求卡片。"
    ),
    MODE_CARD: (
        "本轮应生成知识卡片。若是快速学习首轮：必须先自主判断需要几页，"
        "正常生成 3-5 张图文并茂的入门卡片组；根据用户问题复杂度和画像习惯"
        "调整页数（简单主题 3 张，常规主题 4 张，复杂主题 5 张）。"
        "若用户问题需要超过 200 字解释，或包含公式、推导、表格、图片、插图、"
        "动画、流程图等结构化展示，也应生成知识卡片。"
        "后续轮次再按语境决定是否只聊天或追加少量卡片。"
    ),
    MODE_QUIZ: (
        "本轮优先调用 create_quiz 生成交互式题目，不要在文字里直接写题目和答案。"
    ),
    MODE_VIZ: (
        "本轮优先考虑 generate_interactive_viz；如还需要沉淀静态知识，再生成一张卡片。"
    ),
}


# ----------------------------------------------------------------------
# 关键词表（可覆盖）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class KeywordTable:
    """意图关键词表。

    所有关键词按"去空格后的紧凑文本"匹配，因此无需考虑用户输入中的空格。
    """

    explicit_card: Sequence[str] = (
        "生成卡片",
        "做张卡",
        "做一个卡片",
        "知识卡片",
        "整理成卡片",
        "总结成卡片",
        "生成一页",
        "可视化总结",
        "画一张",
        "画个图",
    )
    #: "卡片" + 任一动词 也视为显式要卡片
    card_verbs: Sequence[str] = ("生成", "做", "整理", "总结", "来一张")

    new_knowledge: Sequence[str] = (
        "讲一下",
        "介绍一下",
        "系统讲",
        "详细讲",
        "原理",
        "怎么工作",
        "如何工作",
        "区别",
        "对比",
        "流程",
        "步骤",
    )

    quiz: Sequence[str] = ("考考我", "出题", "练习", "测试一下", "小测", "刷题")

    rich_content: Sequence[str] = (
        "超过200字",
        "200字以上",
        "长篇",
        "详细解释",
        "系统解释",
        "完整讲",
        "全面讲",
        "展开讲",
        "梳理",
        "总结",
        "公式",
        "推导",
        "表格",
        "对比表",
        "图片",
        "插图",
        "图示",
        "图解",
        "流程图",
        "动画",
        "图文",
        "结构图",
        "示意图",
    )

    viz: Sequence[str] = ("交互", "动态演示", "模拟", "拖动", "可视化演示")

    dialogue: Sequence[str] = (
        "为什么",
        "什么意思",
        "没懂",
        "不懂",
        "换个说法",
        "举例",
        "再解释",
        "详细点",
        "简单说",
        "展开说",
        "刚才",
        "这个",
        "哪里",
        "怎么理解",
        "可以吗",
        "对吗",
        "是不是",
        "好的",
        "明白",
        "懂了",
    )

    greeting: Sequence[str] = ("你好", "hello", "你是谁", "怎么用", "谢谢", "再见")


DEFAULT_KEYWORDS = KeywordTable()

#: 短输入阈值：低于此长度且意图不明确时先对话澄清
SHORT_INPUT_THRESHOLD = 18


# ----------------------------------------------------------------------
# 判定结果
# ----------------------------------------------------------------------


@dataclass
class InteractionDecision:
    """交互模式判定结果。

    Attributes:
        mode:   模式标识，取 ``MODE_*`` 之一。
        reason: 判定依据，会写入 system prompt 供 Agent 理解意图。
        rule:   命中的规则名，便于日志排查与策略调优。
    """

    mode: str = MODE_CHAT
    reason: str = ""
    rule: str = ""

    def as_dict(self) -> Dict[str, str]:
        """兼容旧接口的字典形式。"""
        return {"mode": self.mode, "reason": self.reason}

    def render_hint(self) -> str:
        """渲染为可注入 system prompt 的建议段落。"""
        return (
            "## 本轮交互建议\n\n"
            f"推荐模式：{MODE_LABELS.get(self.mode, self.mode)}\n"
            f"判断依据：{self.reason}\n"
            f"执行要求：{MODE_GUIDANCE.get(self.mode, MODE_GUIDANCE[MODE_CHAT])}"
        )


# ----------------------------------------------------------------------
# 策略
# ----------------------------------------------------------------------


class InteractionPolicy:
    """交互模式判定器。

    Args:
        keywords: 关键词表，默认 :data:`DEFAULT_KEYWORDS`。可传入自定义表
                  以适配不同学科或用户群体。
    """

    def __init__(self, keywords: Optional[KeywordTable] = None):
        self.kw = keywords or DEFAULT_KEYWORDS

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def decide(
        self,
        user_message: str,
        *,
        first_turn: bool = False,
        recent_card: bool = False,
    ) -> InteractionDecision:
        """判定本轮交互模式。

        规则按优先级从高到低依次匹配，命中即返回。

        Args:
            user_message: 本轮用户输入。
            first_turn:   是否为会话首轮（助教尚未回复过）。
            recent_card:  最近两轮是否已生成过知识卡片。

        Returns:
            :class:`InteractionDecision`

        .. note::
           扩展点：若规则全部落空且需要更准的判定，可在此处接入 LLM 兜底。
           当前刻意不接——判定在主对话路径上每轮都执行，加 LLM 会引入额外
           往返延迟与成本，而规则的准确度已足够（模式只是建议不是硬约束）。
        """
        compact = re.sub(r"\s+", "", (user_message or "").strip().lower())

        if first_turn and compact:
            return InteractionDecision(
                MODE_CARD,
                "快速学习首轮固定生成知识卡片，并自主规划 3-5 页图文并茂的入门卡片组。",
                "first_turn",
            )

        if self._any(compact, self.kw.quiz):
            return InteractionDecision(
                MODE_QUIZ, "用户表达练习/测试意图，应生成交互式题目。", "quiz_intent"
            )

        if self._any(compact, self.kw.rich_content):
            return InteractionDecision(
                MODE_CARD,
                "用户问题需要长篇、公式、表格、图片或动画等结构化展示，适合生成知识卡片。",
                "rich_content",
            )

        if self._any(compact, self.kw.viz):
            return InteractionDecision(
                MODE_VIZ,
                "用户表达动态/交互可视化意图，优先生成交互可视化。",
                "viz_intent",
            )

        if self._is_explicit_card(compact):
            return InteractionDecision(
                MODE_CARD, "用户明确要求生成或整理成知识卡片。", "explicit_card"
            )

        if self._any(compact, self.kw.greeting):
            return InteractionDecision(
                MODE_CHAT, "用户是闲聊或元问题，直接对话。", "greeting"
            )

        dialogue_intent = self._any(compact, self.kw.dialogue)

        if recent_card and dialogue_intent:
            return InteractionDecision(
                MODE_CHAT,
                "近期已生成过卡片，当前是跟进追问，优先对话解释。",
                "followup_after_card",
            )

        if self._is_new_knowledge(compact) and not recent_card:
            return InteractionDecision(
                MODE_CARD,
                "用户提出新的知识讲解请求，适合沉淀为知识卡片。",
                "new_knowledge",
            )

        if dialogue_intent:
            return InteractionDecision(
                MODE_CHAT, "用户在追问/澄清/确认理解，优先对话交流。", "dialogue_intent"
            )

        if len(compact) <= SHORT_INPUT_THRESHOLD:
            return InteractionDecision(
                MODE_CHAT, "输入较短且意图不明确，先对话澄清。", "short_input"
            )

        return InteractionDecision(
            MODE_CARD,
            "用户提出新的实质知识学习请求，可沉淀为知识卡片。",
            "default_card",
        )

    # ------------------------------------------------------------------
    # 规则细节
    # ------------------------------------------------------------------

    @staticmethod
    def _any(text: str, keywords: Iterable[str]) -> bool:
        return any(kw in text for kw in keywords)

    def _is_explicit_card(self, compact: str) -> bool:
        """显式要卡片：命中固定短语，或"卡片" + 任一动词。"""
        if self._any(compact, self.kw.explicit_card):
            return True
        return "卡片" in compact and self._any(compact, self.kw.card_verbs)

    def _is_new_knowledge(self, compact: str) -> bool:
        """新知识讲解请求。

        "什么是X" 算新知识，但 "为什么是X" 属于追问，需排除。
        """
        if "什么是" in compact and "为什么是" not in compact:
            return True
        return self._any(compact, self.kw.new_knowledge)


# ----------------------------------------------------------------------
# 会话状态探测（供判定使用）
# ----------------------------------------------------------------------


def is_first_turn(chat_history: Sequence[Any]) -> bool:
    """判断是否为会话首轮（助教尚未回复过）。"""
    for msg in chat_history or []:
        if _role_of(msg) == "assistant":
            return False
    return True


def has_recent_card(
    chat_history: Sequence[Any], session: Any, lookback: int = 4
) -> bool:
    """最近两轮助教是否已经生成过 HTML 知识卡片。

    ``MessageArtifacts.files`` 里只存 ``file_id``（uuid），不携带扩展名，
    因此改为通过 ``session.files`` 中 ``file_type == 'html_card'`` 的记录
    反查其 ``from_message_id`` 是否落在最近的 assistant 消息里。

    Args:
        chat_history: 会话消息列表。
        session:      会话对象（需含 ``files``）。
        lookback:     回看的消息条数。
    """
    if session is None:
        return False

    recent_ids = {
        str(_attr(msg, "id"))
        for msg in reversed(list(chat_history or [])[-lookback:])
        if _role_of(msg) == "assistant" and _attr(msg, "id")
    }
    if not recent_ids:
        return False

    for sf in _attr(session, "files") or []:
        if (
            _attr(sf, "file_type") == "html_card"
            and str(_attr(sf, "from_message_id")) in recent_ids
        ):
            return True
    return False


def _attr(obj: Any, name: str) -> Any:
    """兼容读取对象属性或字典键。"""
    if obj is None:
        return None
    value = getattr(obj, name, None)
    if value is not None:
        return value
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def _role_of(msg: Any) -> str:
    return str(_attr(msg, "role") or "")


__all__ = [
    "DEFAULT_KEYWORDS",
    "MODE_CARD",
    "MODE_CHAT",
    "MODE_GUIDANCE",
    "MODE_LABELS",
    "MODE_QUIZ",
    "MODE_VIZ",
    "InteractionDecision",
    "InteractionPolicy",
    "KeywordTable",
    "has_recent_card",
    "is_first_turn",
]
