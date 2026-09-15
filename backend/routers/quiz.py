"""测验（Quiz）路由：生成测验、提交答案。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from models.quiz import QuizSubmit
from services import QuizService
from services.quiz_service import (
    DEFAULT_QUIZ_EFFORT_MODE,
    QUIZ_EFFORT_MODES,
    AlreadyAnsweredError,
)
from utils.validators import is_valid_session_id

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


@router.get("/effort-modes")
async def list_effort_modes():
    """出题模式列表，供前端渲染选项与耗时提示。

    出题走推理模型时，思考强度对耗时影响极大（实测 2 秒 ~ 5 分钟），
    因此把它作为显式选项暴露给用户，并附带预期耗时说明。
    """
    return {
        "default": DEFAULT_QUIZ_EFFORT_MODE,
        "modes": [
            {"value": k, "label": v["label"], "hint": v["hint"]}
            for k, v in QUIZ_EFFORT_MODES.items()
        ],
    }


@router.post("/generate/{node_id}")
async def generate_quiz(
    node_id: str,
    quiz_type: str = "multiple_choice",
    session_id: Optional[str] = None,
    effort_mode: Optional[str] = None,
    user_id: str = Depends(get_current_user),
):
    if session_id is not None and not is_valid_session_id(session_id):
        raise HTTPException(status_code=400, detail="非法 session_id")
    try:
        return await QuizService().generate_quiz(
            user_id, node_id, session_id, quiz_type, effort_mode=effort_mode
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{quiz_id}")
async def get_quiz(
    quiz_id: str,
    user_id: str = Depends(get_current_user),
):
    try:
        return QuizService().get_quiz(user_id, quiz_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: str,
    body: QuizSubmit,
    user_id: str = Depends(get_current_user),
):
    try:
        return await QuizService().submit_answer(user_id, quiz_id, body.answer)
    except AlreadyAnsweredError as e:
        # 已作答 → 409，与「题目不存在」的 404 区分开
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
