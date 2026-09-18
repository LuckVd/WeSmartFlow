"""学生知识地图 API：3D 知识大脑与证据写入入口。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user
from services.learning_map_service import LearningMapService

router = APIRouter(prefix="/api/learning-map", tags=["learning-map"])


class EvidenceCreate(BaseModel):
    node_id: str
    source_type: Literal["chat", "quiz", "course", "experience", "project", "teacher"]
    source_id: str = ""
    activity_type: Literal[
        "encounter",
        "recall",
        "predict",
        "operate",
        "apply",
        "explain",
        "transfer",
        "reflect",
    ]
    score: float | None = Field(default=None, ge=0, le=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    assessment_method: str = "rule"
    verified_by: str = "system"


@router.get("/brain")
def brain_map(user_id: str = Depends(get_current_user)):
    return LearningMapService().build_brain(user_id)


@router.post("/evidence")
def create_evidence(body: EvidenceCreate, user_id: str = Depends(get_current_user)):
    try:
        return LearningMapService().record_evidence(
            user_id,
            node_id=body.node_id,
            source_type=body.source_type,
            source_id=body.source_id,
            activity_type=body.activity_type,
            score=body.score,
            payload=body.payload,
            assessment_method=body.assessment_method,
            verified_by=body.verified_by,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
