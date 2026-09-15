"""
create_quiz：Agent 出题工具

题目内容由 Agent 在参数里给定，落库与作答实例创建统一委托给
``QuizService.serve_quiz``（级别 0：调用方指定题目），
与 HTTP 出题入口 ``/api/quiz/generate`` 共用同一套管道。
"""

from __future__ import annotations

import asyncio
import json
import logging

from agent_core.tool.base import BaseTool

logger = logging.getLogger(__name__)


class CreateQuizTool(BaseTool):
    """
    生成答题卡片并保存到数据库。Agent 自己构思好题目内容、选项和答案后调用此工具，
    前端会自动渲染成交互式答题卡片供用户作答。
    """

    name = "create_quiz"
    description = (
        "生成一张交互式答题卡片。当你需要出题考察用户对知识点的掌握情况时，"
        "先自行构思好题目内容、选项（选择题）和正确答案，然后调用此工具——"
        "前端会渲染成可点击作答的卡片，用户答完后系统会自动将结果反馈给你。"
        "注意：不要在回复文本中直接展示题目，必须通过此工具生成卡片。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "description": "目标知识节点 id"},
            "quiz_type": {
                "type": "string",
                "enum": ["multiple_choice", "fill_in", "true_false", "open_ended"],
                "description": "题目类型",
            },
            "question": {"type": "string", "description": "已生成的题目内容"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": '选择题选项列表（如 ["A. 选项一", "B. 选项二"]），非选择题不填',
            },
            "correct_answer": {
                "type": "string",
                "description": "正确答案（选择题填选项字母，简答题填参考答案）",
            },
            "explanation": {
                "type": "string",
                "description": "答题解析，说明为什么这个答案是正确的",
            },
        },
        "required": [
            "node_id",
            "quiz_type",
            "question",
            "correct_answer",
            "explanation",
        ],
    }

    def __init__(self, user_id: str, session_id: str):
        super().__init__()
        self._user_id = user_id
        self._session_id = session_id

    async def async_run(
        self,
        node_id: str = "",
        quiz_type: str = "",
        question: str = "",
        correct_answer: str = "",
        explanation: str = "",
        options: list[str] = None,
        **kwargs,
    ) -> str:
        # 延迟导入：agents 与 services 互相引用，模块级导入会形成循环
        from services.quiz_service import QuizService

        try:
            quiz = await QuizService().serve_quiz(
                self._user_id,
                node_id,
                session_id=self._session_id,
                quiz_type=quiz_type or "multiple_choice",
                provided={
                    "question": question,
                    "options": options,
                    "correct_answer": correct_answer,
                    "explanation": explanation,
                },
                # LLM 可能传入臆造的 node_id，回退到已有节点而非报错中断对话
                strict_node=False,
            )
        except ValueError as exc:
            # 把失败原因交回 Agent，让它自行修正后重试，不抛异常中断整轮
            logger.warning("create_quiz 出题失败: %s", exc)
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

        result = {
            "quiz_id": quiz.id,
            "question": quiz.question,
            "type": quiz.quiz_type,
        }
        if quiz.options:
            result["options"] = quiz.options
        return json.dumps(result, ensure_ascii=False)

    def run(
        self,
        node_id: str = "",
        quiz_type: str = "",
        question: str = "",
        correct_answer: str = "",
        explanation: str = "",
        options: list[str] = None,
        **kwargs,
    ) -> str:
        """同步兜底路径（正常调用走 async_run）。"""
        return asyncio.run(
            self.async_run(
                node_id=node_id,
                quiz_type=quiz_type,
                question=question,
                correct_answer=correct_answer,
                explanation=explanation,
                options=options,
                **kwargs,
            )
        )
