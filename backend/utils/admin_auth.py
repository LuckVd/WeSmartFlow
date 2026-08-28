"""
Admin 审核台鉴权工具

独立于普通用户体系：
- 账号密码从 .env 读取（ADMIN_USERNAME / ADMIN_PASSWORD），明文比对
- token 复用现有 JWT 工具链，但 sub="admin"、claim role="admin"、有效期更短
- 仅 admin 路由用 require_admin 依赖；普通用户接口完全不受影响
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import (
    ADMIN_PASSWORD,
    ADMIN_TOKEN_EXPIRE_HOURS,
    ADMIN_USERNAME,
    JWT_ALGORITHM,
    JWT_SECRET,
)

logger = logging.getLogger(__name__)

_admin_security = HTTPBearer(auto_error=True)

ADMIN_SUB = "admin"
ADMIN_ROLE = "admin"


def admin_credentials_configured() -> bool:
    return bool(ADMIN_USERNAME) and bool(ADMIN_PASSWORD)


def verify_admin_credentials(username: str, password: str) -> bool:
    """明文比对。.env 未配置则永远返回 False。"""
    if not admin_credentials_configured():
        return False
    return (username or "") == ADMIN_USERNAME and (password or "") == ADMIN_PASSWORD


def create_admin_token() -> str:
    """生成 admin JWT，sub=admin、role=admin。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": ADMIN_SUB,
        "role": ADMIN_ROLE,
        "iat": now,
        "exp": now + timedelta(hours=ADMIN_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_admin_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin token 已过期",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Admin token",
        ) from exc

    if payload.get("sub") != ADMIN_SUB or payload.get("role") != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="非 admin 凭据",
        )
    return payload


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_admin_security),
) -> str:
    """FastAPI 依赖：要求请求带合法的 admin token，返回固定字符串 'admin'。"""
    token = credentials.credentials
    _decode_admin_token(token)
    return ADMIN_SUB
