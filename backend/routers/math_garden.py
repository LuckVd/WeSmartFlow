"""Authenticated, metered LLM endpoint for the math garden example."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.external_usage import current_usage, demo_usage
from services.llm_factory import get_llm

router = APIRouter(
    prefix="/api/demo/dive-into-math-garden",
    dependencies=[Depends(demo_usage("math-garden"))],
)


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=20000)


class Request(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=30)


@router.post("/llm")
async def llm(req: Request):
    client = get_llm(current_usage().user_id, scene="math-garden", timeout=60)
    response = await client.async_think([m.model_dump() for m in req.messages])
    if response.is_error:
        raise HTTPException(502, "模型请求失败，请稍后重试")
    return {"ok": True, "text": response.content}
