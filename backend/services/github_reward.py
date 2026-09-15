"""Verify GitHub Stars using the short-lived OAuth exchange token, never browser claims."""

import logging
import secrets
import time
from urllib.parse import urlencode

import requests
from fastapi import HTTPException
from config import GITHUB_CLIENT_ID
from database import get_db
from services.credit_wallet import grant_github, REPOSITORY

logger = logging.getLogger(__name__)


def authorize(user_id="", purpose="login"):
    if not GITHUB_CLIENT_ID:
        raise HTTPException(503, "GitHub 登录未配置")
    nonce = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute(
            "DELETE FROM github_oauth_states WHERE expires_at<?", (int(time.time()),)
        )
        if purpose == "reward":
            user = conn.execute(
                "SELECT github_id FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not user:
                raise HTTPException(401, "当前账户不存在，请重新登录")
        conn.execute(
            "INSERT INTO github_oauth_states VALUES (?,?,?,?)",
            (nonce, user_id, purpose, int(time.time()) + 600),
        )
    return {
        "authorize_url": "https://github.com/login/oauth/authorize?"
        + urlencode(
            {"client_id": GITHUB_CLIENT_ID, "scope": "user:email", "state": nonce}
        ),
        "state": nonce,
    }


def consume_state(nonce):
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT user_id,purpose,expires_at FROM github_oauth_states WHERE nonce=?",
            (nonce,),
        ).fetchone()
        if not row or row["expires_at"] < int(time.time()):
            raise HTTPException(400, "GitHub 授权已失效，请重新发起授权")
        conn.execute("DELETE FROM github_oauth_states WHERE nonce=?", (nonce,))
        return dict(row)


def bind_account(user_id, github_id, username, avatar=None):
    """Bind only the account captured by authenticated OAuth state, never by email."""
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute(
            "SELECT name,github_id FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not user:
            raise HTTPException(401, "当前账户不存在，请重新登录")
        if user["github_id"] and str(user["github_id"]) != str(github_id):
            raise HTTPException(
                403, "当前账户已绑定其他 GitHub 账号，请使用已绑定的账号授权"
            )
        owner = conn.execute(
            "SELECT id FROM users WHERE github_id=? AND id<>?",
            (str(github_id), user_id),
        ).fetchone()
        if owner:
            raise HTTPException(
                409, "该 GitHub 账号已绑定其他账户，无法绑定；当前登录账户保持不变"
            )
        conn.execute(
            "UPDATE users SET github_id=?,github_username=?,avatar_url=COALESCE(avatar_url,?) WHERE id=?",
            (str(github_id), username, avatar, user_id),
        )
        return user["name"]


def verify_and_grant(user_id, github_id, access_token):
    try:
        response = requests.get(
            f"https://api.github.com/user/starred/{REPOSITORY}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        if response.status_code == 404:
            return {
                "status": "not_starred",
                "message": "尚未检测到 Star，请 Star 仓库后重新验证。",
            }
        if response.status_code != 204:
            return {
                "status": "unavailable",
                "message": "GitHub 验证暂不可用，请稍后重试。",
            }
    except requests.RequestException:
        return {"status": "unavailable", "message": "GitHub 验证暂不可用，请稍后重试。"}
    awarded = grant_github(user_id, github_id)
    return {
        "status": "granted" if awarded else "already_claimed",
        "message": "Star 奖励 5,000,000 积分已到账。"
        if awarded
        else "该账户或 GitHub 账号已领取过奖励。",
    }
