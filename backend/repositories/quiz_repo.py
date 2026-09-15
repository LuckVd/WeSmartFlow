"""
QuizRepository & QuestionBankRepository & StudyLogRepository

表分工（题目本体 与 作答记录 分离）：
  - question_bank：题目本体唯一存放处，可被反复取用
  - quizzes：一次作答实例，题目内容通过 question_id 引用，不冗余存储
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
from models.quiz import QuizSchema
from .base import BaseRepository, _loads, _dumps, new_id, utcnow_str

logger = logging.getLogger(__name__)

# 读取作答记录时统一 JOIN 题库，把题目本体拼回 QuizSchema。
# 集中定义避免各处 SELECT 列表漂移。
_QUIZ_SELECT = """
SELECT q.id, q.user_id, q.node_id, q.question_id, q.session_id,
       q.user_answer, q.is_correct, q.score, q.answered_at, q.created_at,
       b.quiz_type, b.question, b.options, b.correct_answer, b.explanation,
       b.difficulty, b.source
  FROM quizzes q
  JOIN question_bank b ON b.id = q.question_id
"""


class QuizRepository(BaseRepository):
    """作答记录仓储。写入只落作答字段，读取 JOIN 题库补齐题目本体。"""

    def get_by_node(self, node_id: str, limit: int = 20) -> list[QuizSchema]:
        rows = self._fetchall(
            _QUIZ_SELECT + " WHERE q.node_id=? ORDER BY q.created_at DESC LIMIT ?",
            (node_id, limit),
        )
        return [self._row_to_schema(r) for r in rows]

    def get_recent_questions(
        self, user_id: str, node_id: str, limit: int = 12
    ) -> list[str]:
        """取该用户在该节点下最近作答过的题干（供出题去重用）。

        只取 question 列，不构建完整 QuizSchema。
        """
        rows = self._fetchall(
            "SELECT b.question FROM quizzes q "
            "JOIN question_bank b ON b.id = q.question_id "
            "WHERE q.user_id=? AND q.node_id=? "
            "ORDER BY q.created_at DESC LIMIT ?",
            (user_id, node_id, limit),
        )
        return [r["question"] for r in rows if r["question"]]

    def get_pending_questions(self, user_id: str, node_id: str) -> list[str]:
        """取该用户在此节点下「已出但尚未作答」的题干。

        用于避免连续两次出同一道在途题。已作答的题不在此列——
        它们由 pick_unused 在 SQL 层直接排除。
        """
        rows = self._fetchall(
            "SELECT DISTINCT b.question FROM quizzes q "
            "JOIN question_bank b ON b.id = q.question_id "
            "WHERE q.user_id=? AND q.node_id=? AND q.answered_at IS NULL",
            (user_id, node_id),
        )
        return [r["question"] for r in rows if r["question"]]

    def count_by_node(self, user_id: str, node_id: str) -> int:
        """统计该用户在该节点下累计作答次数（用于角度/要点轮换的游标）。"""
        row = self._fetchone(
            "SELECT COUNT(*) AS c FROM quizzes WHERE user_id=? AND node_id=?",
            (user_id, node_id),
        )
        return int(row["c"]) if row else 0

    def get_by_id(self, quiz_id: str) -> Optional[QuizSchema]:
        row = self._fetchone(_QUIZ_SELECT + " WHERE q.id=?", (quiz_id,))
        return self._row_to_schema(row) if row else None

    def create(
        self,
        user_id: str,
        node_id: str,
        session_id: Optional[str],
        question_id: str,
    ) -> QuizSchema:
        """新建一条作答实例，引用题库中的既有题目。

        Args:
            question_id: question_bank.id，题目本体必须已入库。
        """
        quiz_id = new_id()
        self._execute(
            """
            INSERT INTO quizzes
              (id, user_id, node_id, question_id, session_id, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (quiz_id, user_id, node_id, question_id, session_id, utcnow_str()),
        )
        return self.get_by_id(quiz_id)

    def submit_answer(
        self, quiz_id: str, user_answer: str, is_correct: bool, score: float
    ) -> None:
        now = utcnow_str()
        self._execute(
            """
            UPDATE quizzes SET user_answer=?, is_correct=?, score=?, answered_at=?
            WHERE id=?
            """,
            (user_answer, int(is_correct), score, now, quiz_id),
        )

    @staticmethod
    def _row_to_schema(row: dict) -> QuizSchema:
        return QuizSchema(
            id=row["id"],
            user_id=row["user_id"],
            node_id=row["node_id"],
            question_id=row["question_id"],
            session_id=row["session_id"],
            quiz_type=row["quiz_type"],
            question=row["question"],
            options=_loads(row["options"]) if row["options"] else None,
            correct_answer=row["correct_answer"],
            explanation=row["explanation"] or "",
            difficulty=row.get("difficulty") or "medium",
            source=row.get("source") or "llm",
            user_answer=row["user_answer"],
            is_correct=bool(row["is_correct"])
            if row["is_correct"] is not None
            else None,
            score=row["score"],
            answered_at=row["answered_at"],
            created_at=row["created_at"],
        )


class QuestionBankRepository(BaseRepository):
    """题库仓储：题目本体唯一存放处。

    与 QuizRepository 的分工：
      - question_bank：题目本体，可被反复取用
      - quizzes：一次具体的作答实例，通过 question_id 引用本表
    """

    def add(
        self,
        *,
        user_id: str,
        node_id: str,
        quiz_type: str,
        question: str,
        options: Optional[list[str]],
        correct_answer: str,
        explanation: str = "",
        source: str = "llm",
        difficulty: str = "medium",
    ) -> Optional[str]:
        """入库一道题，返回题目 id。

        题干重复时不插入新行，直接返回已有题目的 id（幂等 upsert 语义），
        使调用方总能拿到可用于 quizzes.question_id 的引用。

        以下情况视为非法题目，返回 None（不入库）：
          - 题干或答案为空
          - 选择题但选项少于 2 个 —— 前端按 options 渲染选项区，
            无选项的选择题会变成用户无法作答的死题，且会永久留在题库里
            反复被取出（因为永远不会有作答记录）。
        """
        question = (question or "").strip()
        correct_answer = (correct_answer or "").strip()
        if not question or not correct_answer:
            return None

        if quiz_type == "multiple_choice":
            valid_options = [
                o for o in (options or []) if o is not None and str(o).strip()
            ]
            if len(valid_options) < 2:
                logger.warning(
                    "拒绝入库：选择题选项不足（node=%s, question=%.40r）",
                    node_id,
                    question,
                )
                return None
            options = valid_options

        bank_id = new_id()
        self._execute(
            """
            INSERT OR IGNORE INTO question_bank
              (id, user_id, node_id, source, quiz_type, question, options,
               correct_answer, explanation, difficulty, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                bank_id,
                user_id,
                node_id,
                source,
                quiz_type,
                question,
                _dumps(options) if options else None,
                correct_answer,
                explanation or "",
                difficulty,
                utcnow_str(),
            ),
        )
        # 无论是新插入还是命中已有行，都按唯一键回查真实 id
        row = self._fetchone(
            "SELECT id FROM question_bank WHERE user_id=? AND node_id=? AND question=?",
            (user_id, node_id, question),
        )
        return row["id"] if row else None

    def add_new(self, **kwargs) -> Optional[str]:
        """仅在题目确实是新题时返回 id，题干已存在则返回 None。

        用于统计「本次新增了多少题」的导入场景。
        """
        before = self.count(kwargs["user_id"], kwargs["node_id"])
        bank_id = self.add(**kwargs)
        after = self.count(kwargs["user_id"], kwargs["node_id"])
        return bank_id if after > before else None

    def pick_unused(
        self,
        user_id: str,
        node_id: str,
        quiz_type: str,
        *,
        require_unanswered: bool = True,
        exclude_questions: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """从题库取一道题。

        「该用户是否做过这道题」以 quizzes 中是否存在已作答记录为准
        （``answered_at IS NOT NULL``），而非题库上的全局 use_count——
        后者是「被取用次数」，取用过但用户没答的题不应算作做过。

        Args:
            require_unanswered: True 时只返回该用户从未作答过的题，
                没有这样的题就返回 None（交由上层降级去 LLM 出新题）；
                False 时允许复用旧题，按作答次数升序挑最少做过的那道。
            exclude_questions: 额外排除的题干（如刚出过但还没作答的题），
                避免连续两次出同一道。

        Returns:
            题目 dict，或 None。
        """
        # 该用户在这道题上的已作答次数
        answered_expr = (
            "(SELECT COUNT(*) FROM quizzes q "
            "  WHERE q.question_id = b.id AND q.user_id = ? "
            "    AND q.answered_at IS NOT NULL)"
        )
        sql = (
            f"SELECT b.*, {answered_expr} AS answered_count "
            "  FROM question_bank b "
            " WHERE b.user_id=? AND b.node_id=? AND b.quiz_type=?"
        )
        params: list = [user_id, user_id, node_id, quiz_type]

        if require_unanswered:
            sql += (
                " AND NOT EXISTS (SELECT 1 FROM quizzes q2 "
                "   WHERE q2.question_id = b.id AND q2.user_id = ? "
                "     AND q2.answered_at IS NOT NULL)"
            )
            params.append(user_id)

        excludes = [q.strip() for q in (exclude_questions or []) if q and q.strip()]
        if excludes:
            # 占位符数量由本地列表长度决定，不含任何外部字符串拼接
            placeholders = ",".join("?" * len(excludes))
            sql += f" AND b.question NOT IN ({placeholders})"
            params.extend(excludes)

        # 先挑做得最少的，再按取用次数分散，最后随机打散同档题目
        sql += " ORDER BY answered_count ASC, b.use_count ASC, RANDOM() LIMIT 1"
        row = self._fetchone(sql, tuple(params))  # type: ignore[arg-type]
        if not row:
            return None
        return {
            "id": row["id"],
            "quiz_type": row["quiz_type"],
            "question": row["question"],
            "options": _loads(row["options"]) if row["options"] else None,
            "correct_answer": row["correct_answer"],
            "explanation": row["explanation"] or "",
            "difficulty": row["difficulty"],
            "source": row["source"],
        }

    def mark_used(self, bank_id: str) -> None:
        """记录一次取用，使 pick_unused 能轮转到下一题。"""
        self._execute(
            "UPDATE question_bank SET use_count=use_count+1, last_used_at=? WHERE id=?",
            (utcnow_str(), bank_id),
        )

    def count(self, user_id: str, node_id: str, quiz_type: Optional[str] = None) -> int:
        """统计题库中该节点可用题目数。"""
        if quiz_type:
            row = self._fetchone(
                "SELECT COUNT(*) AS c FROM question_bank "
                "WHERE user_id=? AND node_id=? AND quiz_type=?",
                (user_id, node_id, quiz_type),
            )
        else:
            row = self._fetchone(
                "SELECT COUNT(*) AS c FROM question_bank WHERE user_id=? AND node_id=?",
                (user_id, node_id),
            )
        return int(row["c"]) if row else 0


class StudyLogRepository(BaseRepository):
    def add_log(
        self, user_id: str, minutes: int, session_id: Optional[str], node_ids: list[str]
    ) -> None:
        """直接插入一条今日学习记录（不合并，用于明确希望保留独立条目的场景，如 AI 课程）。"""
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        self._execute(
            """
            INSERT INTO study_logs (id, user_id, date, minutes, session_id, node_ids, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                new_id(),
                user_id,
                today,
                minutes,
                session_id,
                _dumps(node_ids),
                utcnow_str(),
            ),
        )

    def upsert_today(
        self, user_id: str, minutes: int, session_id: Optional[str], node_ids: list[str]
    ) -> None:
        """更新或插入今日学习记录（每天只保留一条聚合记录）"""
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        existing = self._fetchone(
            "SELECT id, minutes FROM study_logs WHERE user_id=? AND date=?",
            (user_id, today),
        )
        if existing:
            self._execute(
                "UPDATE study_logs SET minutes=minutes+?, node_ids=? WHERE id=?",
                (minutes, _dumps(node_ids), existing["id"]),
            )
        else:
            self._execute(
                """
                INSERT INTO study_logs (id, user_id, date, minutes, session_id, node_ids, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    new_id(),
                    user_id,
                    today,
                    minutes,
                    session_id,
                    _dumps(node_ids),
                    utcnow_str(),
                ),
            )

    def get_recent(self, user_id: str, days: int = 84) -> list[dict]:
        """获取最近 N 天的学习记录（用于热力图），同一天多条记录合并求和"""
        rows = self._fetchall(
            "SELECT date, SUM(minutes) as minutes "
            "FROM study_logs WHERE user_id=? GROUP BY date ORDER BY date DESC LIMIT ?",
            (user_id, days),
        )
        return [{"date": r["date"], "minutes": r["minutes"]} for r in rows]

    def get_streak(self, user_id: str) -> int:
        """计算连续学习天数（同一天多条记录去重）"""
        rows = self._fetchall(
            "SELECT DISTINCT date FROM study_logs WHERE user_id=? ORDER BY date DESC",
            (user_id,),
        )
        if not rows:
            return 0

        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        streak = 0
        prev = None
        for row in rows:
            d = datetime.fromisoformat(row["date"]).date()
            if prev is None:
                # 今天或昨天有记录才开始算连续
                if (today - d).days > 1:
                    break
                prev = d
                streak = 1
            else:
                if (prev - d).days == 1:
                    streak += 1
                    prev = d
                else:
                    break
        return streak
