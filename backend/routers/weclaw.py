"""weclaw 微信通道路由：扫码登录 / 绑定状态 / 解绑。

均需登录（JWT）：每个 edu-agent 用户绑定/管理自己的 weclaw bot。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weclaw", tags=["weclaw"])


class PollRequest(BaseModel):
    verify_code: Optional[str] = None


@router.post("/login/start")
async def weclaw_login_start(user_id: str = Depends(get_current_user)):
    """发起扫码绑定，返回二维码。"""
    from channels import login

    return await login.start_login(user_id)


@router.post("/login/poll")
async def weclaw_login_poll(
    body: PollRequest, user_id: str = Depends(get_current_user)
):
    """轮询扫码状态（前端每隔数秒调用一次）。"""
    from channels import login

    return await login.poll_login(user_id, verify_code=body.verify_code)


@router.get("/status")
def weclaw_status(user_id: str = Depends(get_current_user)):
    """查询当前用户的绑定状态。"""
    from channels import login

    return login.get_bind_status(user_id)


@router.post("/unbind")
def weclaw_unbind(user_id: str = Depends(get_current_user)):
    """解绑（停用）当前用户的 bot。"""
    from channels import login

    login.unbind(user_id)
    return {"ok": True}
