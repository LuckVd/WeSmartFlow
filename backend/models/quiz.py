"""
Quiz（测验）模型
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import Field
from .base import BaseSchema


class QuizSchema(BaseSchema):
    """一次作答实例的对外视图。

    存储上题目本体在 question_bank、作答记录在 quizzes；
    读取时 JOIN 拼成本 Schema，因此对外字段保持扁平不变。
    """

    id: str
    user_id: str
    node_id: str
    question_id: str = Field(default="", description="题库中的题目 id")
    session_id: Optional[str]
    # ── 题目本体（来自 question_bank）──
    quiz_type: Literal["multiple_choice", "fill_in", "true_false", "open_ended"]
    question: str
    options: Optional[list[str]]
    correct_answer: str
    explanation: str
    difficulty: str = Field(default="medium", description="easy / medium / hard")
    source: str = Field(default="llm", description="llm / exercises_md / manual")
    # ── 作答状态（来自 quizzes）──
    user_answer: Optional[str]
    is_correct: Optional[bool]
    score: Optional[float]
    answered_at: Optional[datetime]
    created_at: datetime


class QuizSubmit(BaseSchema):
    """用户提交答案"""

    answer: str


class QuizResult(BaseSchema):
    quiz_id: str
    is_correct: bool
    score: float
    correct_answer: str
    explanation: str
    mastery_delta: float = Field(description="该节点掌握度变化量")
