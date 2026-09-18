"""
QuizService：出题与评分

- 调用 LLM 为指定节点出题
- 自动/手动评分（选择题/判断题自动，主观题 LLM 评分）
- 调用 MemoryService 更新 SM-2 状态
"""

from __future__ import annotations

import logging
import random
import time

from typing import Optional

from json_repair import repair_json

from models.quiz import QuizSchema
from repositories import NodeRepository
from repositories.quiz_repo import QuestionBankRepository, QuizRepository
from services.llm_factory import get_llm
from services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# ── 出题思考强度 ────────────────────────────────────────────────
# 推理模型（如 deepseek-v4-flash）默认会产生大量 thinking token：
# 实测出一道题平均耗时 125 秒（最差 310 秒），90%+ 的 completion_tokens
# 都是思考过程。降低思考强度后可到 2 秒左右。
#
# 这里把它抽象成用户可选的「出题模式」，而不是让前端直接传模型参数：
#   - 用户不需要理解 reasoning_effort 是什么
#   - 取值受服务端白名单约束，避免任意字符串直达上游 API
#   - 不同厂商对该参数的支持差异由 _normalize_params 兜底剔除
#
# effort 为 None 表示不传该参数，完全交给模型默认行为。
QUIZ_EFFORT_MODES = {
    "fast": {
        "effort": "none",
        "label": "快速",
        "hint": "约 3 秒 · 题目偏基础",
    },
    "balanced": {
        "effort": "low",
        "label": "均衡",
        "hint": "约 20 秒 · 推荐",
    },
    "quality": {
        "effort": "medium",
        "label": "深度",
        "hint": "1~2 分钟 · 题目更有深度",
    },
}
DEFAULT_QUIZ_EFFORT_MODE = "balanced"

# 出题采样参数。
#   temperature/top_p：默认确定性解码会让相同 prompt 反复产出同一道题。
#   reasoning_effort：由 _sampling_for() 按出题模式注入。
QUIZ_SAMPLING = {
    "temperature": 1.0,
    "top_p": 0.95,
}

# 判题采样参数：主观题评分同样无需深度推理，且用户正在等待结果。
GRADE_SAMPLING = {"reasoning_effort": "low"}


def resolve_effort_mode(mode: Optional[str]) -> str:
    """把外部传入的模式名归一化为合法值，非法输入回落到默认模式。"""
    if mode and mode in QUIZ_EFFORT_MODES:
        return mode
    if mode:
        logger.warning("未知出题模式 %r，回落到 %s", mode, DEFAULT_QUIZ_EFFORT_MODE)
    return DEFAULT_QUIZ_EFFORT_MODE


def _sampling_for(mode: Optional[str]) -> dict:
    """构造出题采样参数：基础采样 + 该模式对应的思考强度。"""
    cfg = dict(QUIZ_SAMPLING)
    effort = QUIZ_EFFORT_MODES[resolve_effort_mode(mode)]["effort"]
    if effort:
        cfg["reasoning_effort"] = effort
    return cfg


# 出题视角轮换池：每出一题换一个考察角度，从 prompt 层面打破确定性。
QUIZ_ANGLES = [
    "考察对核心定义的准确理解，避免只考字面记忆",
    "给出一个具体应用场景，考察能否在场景中正确选用该知识",
    "设置一个常见误区/易混概念作为干扰，考察辨析能力",
    "考察该知识与相邻知识之间的区别或联系",
    "给出一个结果或现象，考察能否反推原因",
    "考察边界条件、特例或适用范围",
    "给出一段有错误的描述，考察能否定位问题所在",
    "考察该知识在实践中的取舍与权衡",
]

# 历史题干注入上限：条数与单条长度都做截断，避免 prompt 无限膨胀。
_MAX_RECENT_QUESTIONS = 20
_MAX_QUESTION_CHARS = 120

# 数学公式书写约束：前端用 KaTeX 渲染 $...$，若 LLM 输出 Unicode 上标（n²）
# 或纯文本近似写法，公式无法正确排版。
_MATH_HINT = (
    "涉及数学公式、符号、上下标时，必须用 LaTeX 并以 $...$ 包裹"
    "（行内如 $O(n \\log n)$、$x^2$、$\\frac{a}{b}$），"
    "不要使用 Unicode 上下标字符（如 n²、xᵢ）或纯文本近似写法。"
)


def _parse_llm_json(raw: str) -> dict:
    """解析 LLM 返回的 JSON，自动处理代码块包裹、非法转义等常见问题。"""
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1].lstrip("json").strip()
    return repair_json(text, return_objects=True)


class AlreadyAnsweredError(ValueError):
    """题目已作答，拒绝重复提交。

    继承 ValueError 以兼容既有 `except ValueError` 调用方，
    同时让路由层能单独识别并返回 409 而非 404。
    """


class QuizService:
    def __init__(self):
        self.node_repo = NodeRepository()
        self.quiz_repo = QuizRepository()
        self.bank_repo = QuestionBankRepository()
        self.memory_service = MemoryService()

    # ── 权属校验 ──────────────────────────────────────
    def _resolve_node(self, user_id: str, node_id: str, *, strict: bool = True):
        """解析并校验节点归属。

        Args:
            strict: True 时节点无效直接抛 ValueError（HTTP 入口语义）；
                    False 时回退到该用户任一已有节点（Agent 工具语义——
                    LLM 可能传入臆造的 node_id，不应让整轮对话崩掉）。

        Returns:
            NodeSchema

        Raises:
            ValueError: strict=True 且节点无效；或 strict=False 但用户没有任何节点。
        """
        node = self.node_repo.get_by_id(node_id) if node_id else None
        if node and node.user_id == user_id:
            return node

        if strict:
            raise ValueError(f"节点 {node_id} 不存在")

        # get_all 返回轻量 NodeBrief（不含 content），需再取一次完整节点，
        # 因为 LLM 出题依赖 content.key_points。
        briefs = self.node_repo.get_all(user_id)
        if not briefs:
            raise ValueError("当前没有可关联的知识节点，请先创建知识点后再出题。")
        fallback = self.node_repo.get_by_id(briefs[0].id)
        if not fallback:
            raise ValueError("当前没有可关联的知识节点，请先创建知识点后再出题。")
        logger.warning("node_id=%r 无效，回退到已有节点 %s", node_id, fallback.id)
        return fallback

    def _assert_node_owner(self, user_id: str, node_id: str):
        """断言节点存在且属于该用户；否则抛 ValueError（上层译为 404）。"""
        return self._resolve_node(user_id, node_id, strict=True)

    def _assert_quiz_owner(self, user_id: str, quiz_id: str):
        """断言题目存在且属于该用户；否则抛 ValueError（上层译为 404）。"""
        quiz = self.quiz_repo.get_by_id(quiz_id)
        if not quiz or quiz.user_id != user_id:
            raise ValueError(f"题目 {quiz_id} 不存在")
        return quiz

    # ── 统一出题入口 ──────────────────────────────────
    async def serve_quiz(
        self,
        user_id: str,
        node_id: str,
        *,
        session_id: Optional[str] = None,
        quiz_type: str = "multiple_choice",
        provided: Optional[dict] = None,
        strict_node: bool = True,
        effort_mode: Optional[str] = None,
    ) -> QuizSchema:
        """出一道题并建立作答实例。所有出题入口的唯一实现。

        题目来源四级降级：
          0. ``provided`` 非空 —— 调用方（如 Agent）已构思好题目，直接采用。
             这类题同样入库，因此后续可被级别 1 复用。
          1. 题库命中 —— 取该用户**从未作答过**的题（零 LLM 开销）。
             「做过没」以 quizzes 中 answered_at 非空为准。
          2. 题库中没有未做过的题 —— 调 LLM 现场出新题并入库。
          3. LLM 出题失败 —— 复用做得最少的旧题兜底，不让答题流中断。

        无论走哪一级，最终都只做两件事：确定 question_id → 建 quizzes 作答实例。
        题目本体永远只存在于 question_bank。

        Args:
            provided:    ``{"question", "correct_answer", "options", "explanation"}``；
                         题干或答案为空时视为无效，降级到级别 1。
            strict_node: 见 ``_resolve_node``。
            effort_mode: 出题模式，见 ``QUIZ_EFFORT_MODES``。仅在走级别 2
                         （调 LLM 出新题）时生效；题库命中时本身就是毫秒级。
                         非法值回落到默认模式。

        Returns:
            QuizSchema（题目本体已 JOIN 拼回）

        Raises:
            ValueError: 节点无效、或出题失败。
        """
        node = self._resolve_node(user_id, node_id, strict=strict_node)
        node_id = node.id

        # 已作答过的题由 pick_unused 直接在 SQL 层排除；
        # 这里只需排除「已出但还没作答」的在途题，避免连续两次出同一道。
        pending = self.quiz_repo.get_pending_questions(user_id, node_id)
        # LLM 出新题时要避开所有近期题干（含已作答的），否则会重复造题
        recent = self.quiz_repo.get_recent_questions(
            user_id, node_id, limit=_MAX_RECENT_QUESTIONS
        )

        question_id = None

        # ── 级别 0：调用方指定题目 ──
        if provided:
            p_question = str(provided.get("question") or "").strip()
            p_answer = str(provided.get("correct_answer") or "").strip()
            p_options = provided.get("options")

            # 提前给出精确原因，便于 Agent 自行修正后重试
            if not p_question or not p_answer:
                raise ValueError("题目内容不完整：题干和正确答案都不能为空")
            if quiz_type == "multiple_choice":
                valid = [o for o in (p_options or []) if o and str(o).strip()]
                if len(valid) < 2:
                    raise ValueError(
                        "选择题必须提供至少 2 个选项（options），"
                        '格式如 ["A. 选项一", "B. 选项二"]'
                    )

            question_id = self.bank_repo.add(
                user_id=user_id,
                node_id=node_id,
                quiz_type=quiz_type,
                question=p_question,
                options=p_options,
                correct_answer=p_answer,
                explanation=provided.get("explanation") or "",
                source="llm",
            )
            if not question_id:
                raise ValueError("题目入库失败，请检查题目内容后重试")

        # ── 级别 1：题库中该用户从未作答过的题 ──
        if question_id is None:
            picked = self.bank_repo.pick_unused(
                user_id,
                node_id,
                quiz_type,
                require_unanswered=True,
                exclude_questions=pending,
            )
            if picked:
                question_id = picked["id"]

        # ── 级别 2：LLM 现场出题 ──
        if question_id is None:
            try:
                question_id = await self._generate_into_bank(
                    user_id, node, quiz_type, recent=recent, effort_mode=effort_mode
                )
            except Exception as exc:  # pylint: disable=broad-except
                # ── 级别 3：LLM 不可用/出题失败 → 复用做得最少的旧题兜底 ──
                # 宁可让用户重做一道旧题，也不要直接报错中断答题流。
                # 这里必须捕获所有异常而非仅 ValueError：LLM 客户端可能抛出
                # 网络超时、连接错误等任意异常类型。
                fallback = self.bank_repo.pick_unused(
                    user_id,
                    node_id,
                    quiz_type,
                    require_unanswered=False,
                    exclude_questions=pending,
                )
                if not fallback:
                    if isinstance(exc, ValueError):
                        raise
                    # 非 ValueError（如网络异常）统一转成 ValueError，
                    # 让路由层能按 4xx 语义处理而不是 500。
                    logger.warning("LLM 出题失败且题库无可用题", exc_info=True)
                    raise ValueError("出题失败：出题服务暂不可用，请稍后重试") from exc
                logger.warning(
                    "LLM 出题失败，回退复用题库旧题 %s", fallback["id"], exc_info=True
                )
                question_id = fallback["id"]

        quiz = self.quiz_repo.create(
            user_id=user_id,
            node_id=node_id,
            session_id=session_id,
            question_id=question_id,
        )
        self.bank_repo.mark_used(question_id)
        return quiz

    async def generate_quiz(
        self,
        user_id: str,
        node_id: str,
        session_id: str = None,
        quiz_type: str = "multiple_choice",
        effort_mode: Optional[str] = None,
    ) -> dict:
        """HTTP 出题入口：为某节点出一道题（题库优先，落空调 LLM）。

        返回体在 QuizSchema 基础上附加两个非持久化字段，供前端展示：
          - ``effort_mode``：本次实际生效的出题模式（非法入参已归一化）
          - ``elapsed_ms``：服务端耗时，便于前端校准「预计等待」提示
        """
        mode = resolve_effort_mode(effort_mode)
        t0 = time.perf_counter()
        quiz = await self.serve_quiz(
            user_id,
            node_id,
            session_id=session_id,
            quiz_type=quiz_type,
            effort_mode=mode,
        )
        data = quiz.model_dump(mode="json")
        data["effort_mode"] = mode
        data["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return data

    async def _generate_into_bank(
        self,
        user_id: str,
        node,
        quiz_type: str,
        *,
        recent: list[str],
        effort_mode: Optional[str] = None,
    ) -> str:
        """调 LLM 出一道新题并入库，返回 question_bank.id。

        node 由调用方传入已校验的完整节点，避免重复查库。
        """
        node_id = node.id
        cursor = self.quiz_repo.count_by_node(user_id, node_id)
        prompt = self._build_prompt(node, quiz_type, recent=recent, cursor=cursor)
        t0 = time.perf_counter()
        response = await get_llm(user_id, scene="quiz").async_think(
            messages=[
                {"role": "system", "content": "你是出题专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            config=_sampling_for(effort_mode),
        )
        logger.info(
            "LLM 出题耗时 %.2fs (mode=%s, node=%s)",
            time.perf_counter() - t0,
            resolve_effort_mode(effort_mode),
            node_id,
        )

        quiz_data = _parse_llm_json(response.content)
        if not isinstance(quiz_data, dict) or not quiz_data.get("question"):
            raise ValueError("出题失败：模型未返回合法题目，请重试")

        correct_answer = str(quiz_data.get("correct_answer", "")).strip()
        if not correct_answer:
            raise ValueError("出题失败：模型未给出正确答案，请重试")

        question_id = self.bank_repo.add(
            user_id=user_id,
            node_id=node_id,
            quiz_type=quiz_type,
            question=str(quiz_data["question"]).strip(),
            options=quiz_data.get("options"),
            correct_answer=correct_answer,
            explanation=quiz_data.get("explanation", "") or "",
            source="llm",
        )
        if not question_id:
            raise ValueError("出题失败：题目入库异常，请重试")
        return question_id

    def get_quiz(self, user_id: str, quiz_id: str) -> dict:
        """获取一道题，供前端答题卡片渲染。"""
        quiz = self._assert_quiz_owner(user_id, quiz_id)
        data = quiz.model_dump(mode="json")
        data["answered"] = bool(quiz.answered_at)
        return data

    async def submit_answer(self, user_id: str, quiz_id: str, user_answer: str) -> dict:
        """用户提交答案，自动评分并更新记忆状态。

        同一道作答实例只接受一次提交：重复提交会抛 ValueError。
        否则同一个 quiz_id 可被反复提交，掌握度被累加刷满，
        且 SM-2 的 repetitions 被污染导致复习间隔算错。
        """
        quiz = self._assert_quiz_owner(user_id, quiz_id)

        if quiz.answered_at:
            raise AlreadyAnsweredError(f"题目 {quiz_id} 已作答，不能重复提交")

        # 评分
        if quiz.quiz_type == "multiple_choice":
            is_correct = self._check_multiple_choice(
                user_answer, quiz.correct_answer, quiz.options
            )
            score = 1.0 if is_correct else 0.0
            graded = True
        elif quiz.quiz_type == "true_false":
            is_correct = self._check_true_false(user_answer, quiz.correct_answer)
            score = 1.0 if is_correct else 0.0
            graded = True
        else:
            # 主观题（填空题 / 简答题）：LLM 评分
            is_correct, score, graded = await self._llm_grade(
                user_id, quiz.question, quiz.correct_answer, user_answer
            )

        self.quiz_repo.submit_answer(quiz_id, user_answer, is_correct, score)

        # 评分失败（LLM 不可用/返回不可解析）时不动掌握度——
        # 否则用户答对了也会因为系统故障被扣分。
        if not graded:
            logger.warning(
                "quiz %s 评分失败，跳过掌握度更新（node=%s）", quiz_id, quiz.node_id
            )
            mastery_delta = 0.0
        else:
            # SM-2 quality: score 映射到 0~5。score 已在上游夹紧到 [0,1]，
            # 这里再兜一次，确保 quality 落在 sm2() 的合法域内。
            quality = max(0, min(5, round(max(0.0, min(1.0, score)) * 5)))
            memory_result = self.memory_service.review_node_for_user(
                user_id, quiz.node_id, quality
            )
            mastery_delta = memory_result["mastery_delta"]

        learning_map_evidence = None
        if graded:
            try:
                from services.learning_map_service import LearningMapService

                activity_type = (
                    "explain" if quiz.quiz_type == "open_ended" else "recall"
                )
                learning_map_evidence = LearningMapService().record_evidence(
                    user_id,
                    node_id=quiz.node_id,
                    source_type="quiz",
                    source_id=quiz_id,
                    activity_type=activity_type,
                    score=score,
                    payload={
                        "quiz_type": quiz.quiz_type,
                        "is_correct": is_correct,
                        "question": quiz.question[:500],
                    },
                    assessment_method="quiz",
                    verified_by="system"
                    if quiz.quiz_type in {"multiple_choice", "true_false"}
                    else "rubric",
                )
            except Exception:  # pylint: disable=broad-except
                # 学习地图是附加记录，不应因记录失败破坏用户已完成的作答。
                logger.exception("quiz %s 写入 learning-map evidence 失败", quiz_id)

        return {
            "quiz_id": quiz_id,
            "is_correct": is_correct,
            "score": score,
            "correct_answer": quiz.correct_answer,
            "explanation": quiz.explanation,
            "mastery_delta": mastery_delta,
            "learning_map_evidence": learning_map_evidence,
        }

    def _build_prompt(
        self,
        node,
        quiz_type: str,
        *,
        recent: list[str] | None = None,
        cursor: int = 0,
    ) -> str:
        """构造出题 prompt。

        Args:
            node:      知识节点
            quiz_type: 题目类型
            recent:    最近出过的题干列表（去重用）
            cursor:    该节点累计出题数，用于轮换角度与要点
        """
        content = node.content
        key_points = list(getattr(content, "key_points", None) or [])
        mistakes = list(getattr(content, "common_mistakes", None) or [])

        # 要点轮换：以 cursor 为偏移滚动取 3 个要点，而不是恒定取前 3 个
        focus_points = self._rotate(key_points, cursor, size=3)
        focus_mistakes = self._rotate(mistakes, cursor, size=2)
        node_info = f"""知识节点：{node.title}
描述：{node.description}
核心要点：{"; ".join(focus_points) if focus_points else "（无）"}
"""
        if focus_mistakes:
            node_info += f"可用作干扰项的常见误区：{'; '.join(focus_mistakes)}\n"

        # 角度轮换：cursor 决定主角度，再随机扰动一次，避免固定周期也能被记住
        angle = QUIZ_ANGLES[cursor % len(QUIZ_ANGLES)]
        if random.random() < 0.3:
            angle = random.choice(QUIZ_ANGLES)

        type_hint = {
            "multiple_choice": (
                "出一道单选题，提供4个选项（A/B/C/D），其中只有1个正确。"
                'correct_answer 必须只填选项字母（如 "B"），不要包含选项内容'
            ),
            "fill_in": "出一道填空题，答案为1~3个词或短句",
            "true_false": (
                "出一道判断题。"
                'correct_answer 必须填 "正确" 或 "错误"，不要用 True/False'
            ),
            "open_ended": "出一道简答题，考察对概念的深层理解",
        }[quiz_type]

        avoid_block = self._render_avoid_block(recent)
        dedup_hint = (
            "新题必须与「已出过的题目」在题干表述和考点上都明显不同，"
            "不要只是替换措辞或调整选项顺序。"
            if recent
            else ""
        )

        return f"""{node_info}
本次考察角度：{angle}
{avoid_block}
请{type_hint}。{dedup_hint}{_MATH_HINT}以如下 JSON 格式返回：
{{
  "question": "题目内容",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],  // 仅选择题需要
  "correct_answer": "正确答案（选择题只填字母如 B，判断题填「正确」或「错误」）",
  "explanation": "详细解析"
}}"""

    @staticmethod
    def _rotate(items: list[str], offset: int, *, size: int) -> list[str]:
        """从 items 中以 offset 为起点环形取 size 个元素。"""
        if not items:
            return []
        n = len(items)
        take = min(size, n)
        start = offset % n
        return [items[(start + i) % n] for i in range(take)]

    @staticmethod
    def _render_avoid_block(recent: list[str] | None) -> str:
        """把历史题干渲染成「禁止重复」清单；无历史时返回空串。"""
        if not recent:
            return ""
        lines = []
        for i, q in enumerate(recent, start=1):
            text = " ".join(q.split())
            if len(text) > _MAX_QUESTION_CHARS:
                text = text[:_MAX_QUESTION_CHARS] + "…"
            lines.append(f"{i}. {text}")
        return "已出过的题目（禁止重复，也不要出换皮题）：\n" + "\n".join(lines) + "\n"

    @staticmethod
    def _check_multiple_choice(
        user_answer: str, correct_answer: str, options: list[str] | None
    ) -> bool:
        """选择题判题：兼容多种 correct_answer 格式。

        LLM 生成的 correct_answer 可能是：
        - 纯字母："B"
        - 字母+内容："B. O(n log n)"
        - 纯内容："O(n log n)"

        前端发送的 user_answer 始终是纯字母："A"/"B"/"C"/"D"
        """
        ua = user_answer.strip().upper()  # 用户答案，如 "B"
        ca = correct_answer.strip()

        # 情况 1：correct_answer 以字母开头（如 "B" 或 "B. xxx"）
        if ca and ca[0].upper() in "ABCD":
            # 取第一个字符比较
            if ca[0].upper() == ua:
                return True
            # 如果 correct_answer 就是纯字母
            if len(ca) == 1:
                return False

        # 情况 2：correct_answer 是纯内容（如 "O(n log n)"），需要在 options 中查找
        if options:
            ca_lower = ca.lower()
            for i, opt in enumerate(options):
                opt_clean = opt.strip()
                # 去掉选项前缀 "A. " / "A、" / "A) " 等
                opt_content = opt_clean
                if (
                    len(opt_clean) >= 2
                    and opt_clean[0].upper() in "ABCD"
                    and opt_clean[1] in ".、) "
                ):
                    opt_content = opt_clean[2:].strip()
                elif (
                    len(opt_clean) >= 3
                    and opt_clean[0].upper() in "ABCD"
                    and opt_clean[1:3] in [". ", "、 "]
                ):
                    opt_content = opt_clean[3:].strip()

                # 如果 correct_answer 匹配某个选项的内容
                if ca_lower == opt_content.lower() or ca_lower == opt_clean.lower():
                    correct_letter = chr(65 + i)  # A=65
                    return ua == correct_letter

        # 兜底：直接比较
        return ua.lower() == ca.lower()

    @staticmethod
    def _check_true_false(user_answer: str, correct_answer: str) -> bool:
        """判断题判题：兼容多种 correct_answer 格式。

        前端发送的 user_answer 是 "true" 或 "false"（布尔值转字符串）。
        LLM 生成的 correct_answer 可能是："正确"/"错误"/"True"/"False"/"对"/"错"，
        也常见「对的」「正确的」「不正确」这类带后缀/前缀的变体。
        """
        ua = QuizService._to_bool(user_answer)
        ca = QuizService._to_bool(correct_answer)

        # 任一侧无法识别时退化为字面比较，避免把未知值误判成 False
        if ua is None or ca is None:
            return user_answer.strip().lower() == correct_answer.strip().lower()

        return ua == ca

    @staticmethod
    def _to_bool(text: str) -> Optional[bool]:
        """把判断题答案归一化为布尔值，无法识别返回 None。

        先做精确匹配，再按「否定词优先」做包含匹配，
        以覆盖「对的」「正确的」「不正确」「说法错误」等自然语言变体。
        """
        s = (text or "").strip().lower()
        if not s:
            return None

        true_exact = {"true", "正确", "对", "是", "yes", "y", "t", "1", "√", "✓"}
        false_exact = {"false", "错误", "错", "否", "no", "n", "f", "0", "×", "✗"}
        if s in true_exact:
            return True
        if s in false_exact:
            return False

        # 否定词优先：「不正确」「不对」含有「正确」「对」，必须先判否定
        false_marks = (
            "不正确",
            "不对",
            "不是",
            "错误",
            "错",
            "否",
            "false",
            "incorrect",
        )
        if any(m in s for m in false_marks):
            return False
        true_marks = ("正确", "对", "是", "true", "correct")
        if any(m in s for m in true_marks):
            return True
        return None

    async def _llm_grade(
        self, user_id: str, question: str, correct_answer: str, user_answer: str
    ) -> tuple[bool, float, bool]:
        """LLM 评分主观题。

        Returns:
            ``(is_correct, score, graded)``

            - score 已夹紧到 [0.0, 1.0]，避免越界值污染 SM-2 的 quality。
            - graded 为 False 表示评分链路本身失败（LLM 不可用或返回不可解析），
              此时调用方应跳过掌握度更新，不能把系统故障算作用户答错。
        """
        prompt = f"""请评估以下答题的准确性。

问题：{question}
参考答案：{correct_answer}
用户答案：{user_answer}

请返回 JSON：
{{"score": 0.8, "comment": "评语"}}

score 为 0~1 的浮点数，1.0 表示完全正确。"""

        try:
            response = await get_llm(user_id, scene="quiz").async_think(
                messages=[{"role": "user", "content": prompt}],
                config=dict(GRADE_SAMPLING),
            )
        except Exception:  # pylint: disable=broad-except
            logger.warning("主观题评分调用 LLM 失败", exc_info=True)
            return False, 0.0, False

        try:
            data = _parse_llm_json(response.content)
            if not isinstance(data, dict) or "score" not in data:
                raise ValueError(f"响应缺少 score 字段: {response.content[:120]!r}")
            score = max(0.0, min(1.0, float(data["score"])))
            return score >= 0.6, score, True
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "主观题评分结果不可解析，跳过掌握度更新: %r",
                (response.content or "")[:120],
                exc_info=True,
            )
            return False, 0.0, False
