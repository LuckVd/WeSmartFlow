"""weclaw 扫码登录编排（每个 edu-agent 用户绑定自己的 bot）。

流程（对齐 AIFS clawbridge）：
  1. ``start_login``  → 取二维码，缓存到内存（按 user_id）；前端展示图片。
  2. ``poll_login``   → 轮询扫码状态（35s 长轮询）；前端每隔几秒调一次。
     - need_verifycode：前端弹输入框，带 verify_code 再调；
     - confirmed：拿到 account_id/token → 落库 weclaw_bots + 热启该 bot 的长轮询协程。

登录会话仅存内存（进程级），5 分钟 TTL；重启后需重新发起。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from config import WECLAW_BASE_URL
from channels import store
from channels.manager import manager
from channels.store import WeclawBot

logger = logging.getLogger(__name__)

_ACTIVE_LOGIN_TTL_MS = 5 * 60_000
_MAX_QR_REFRESH = 3

# user_id -> {qrcode, qrcode_url, started_at, refresh, base_url}
_active_logins: dict[str, dict[str, Any]] = {}


def _now_ms() -> float:
    return time.time() * 1000


def _is_fresh(login: dict[str, Any]) -> bool:
    return _now_ms() - float(login["started_at"]) < _ACTIVE_LOGIN_TTL_MS


def _purge_expired() -> None:
    for key in [k for k, v in _active_logins.items() if not _is_fresh(v)]:
        _active_logins.pop(key, None)


# 二维码图片可能出现在这些字段之一（不同网关/版本命名不一）
_QR_IMG_KEYS = (
    "qrcode_img_content",
    "qrcode_img",
    "qrcode_image",
    "img_content",
    "image_content",
    "qr_img",
    "qrcode_url",
    "image",
)


def _pick_qr_image(qr: dict[str, Any]) -> str:
    """从二维码响应里挑出图片内容（base64/data-url/http url），做多字段兜底。"""
    if not isinstance(qr, dict):
        return ""
    # 有些网关会把数据裹在 data 里
    for container in (qr, qr.get("data") if isinstance(qr.get("data"), dict) else None):
        if not container:
            continue
        for key in _QR_IMG_KEYS:
            val = container.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _pick_qr_code(qr: dict[str, Any]) -> str:
    if not isinstance(qr, dict):
        return ""
    val = qr.get("qrcode")
    if isinstance(val, str) and val.strip():
        return val.strip()
    data = qr.get("data")
    if isinstance(data, dict):
        val = data.get("qrcode")
        if isinstance(val, str):
            return val.strip()
    return ""


async def start_login(user_id: str, *, route_tag: str = "") -> dict[str, Any]:
    """发起登录，返回二维码。"""
    _purge_expired()
    client = manager.ensure_client()
    try:
        qr = await client.fetch_qr_code(base_url=WECLAW_BASE_URL, route_tag=route_tag)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("weclaw 取二维码失败 user=%s: %s", user_id, exc)
        return {
            "session_key": user_id,
            "status": "failed",
            "message": f"取二维码失败：{exc}",
        }

    qrcode = _pick_qr_code(qr)
    qrcode_img = _pick_qr_image(qr)
    logger.info(
        "weclaw get_bot_qrcode: user=%s ret=%s keys=%s has_qrcode=%s img_len=%s",
        user_id,
        qr.get("ret", qr.get("errcode", "<none>")),
        sorted(str(k) for k in qr.keys()),
        bool(qrcode),
        len(qrcode_img),
    )
    if not qrcode:
        return {
            "session_key": user_id,
            "status": "failed",
            "message": "网关未返回二维码，请稍后重试。",
        }

    _active_logins[user_id] = {
        "qrcode": qrcode,
        "qrcode_url": qrcode_img,
        "started_at": _now_ms(),
        "refresh": 1,
        "base_url": WECLAW_BASE_URL,
        "route_tag": route_tag,
    }
    return {
        "session_key": user_id,
        "status": "waiting",
        "message": "请用微信扫描二维码以绑定。",
        "qrcode": qrcode,
        "qrcode_url": qrcode_img,
    }


async def poll_login(
    user_id: str, *, verify_code: Optional[str] = None
) -> dict[str, Any]:
    """轮询一次扫码状态。"""
    login = _active_logins.get(user_id)
    if not login:
        return {"status": "not_found", "message": "没有进行中的登录，请先发起绑定。"}
    if not _is_fresh(login):
        _active_logins.pop(user_id, None)
        return {"status": "expired", "message": "二维码已过期，请重新绑定。"}

    client = manager.ensure_client()
    base_url = str(login.get("base_url") or WECLAW_BASE_URL)
    route_tag = str(login.get("route_tag") or "")
    resp = await client.poll_qr_status(
        base_url=base_url,
        route_tag=route_tag,
        qrcode=login["qrcode"],
        verify_code=verify_code,
    )
    status = str(resp.get("status") or "wait").strip().lower()

    if status == "scaned_but_redirect":
        redirect_host = str(resp.get("redirect_host") or "").strip()
        if redirect_host:
            login["base_url"] = f"https://{redirect_host}"
        return {"status": "scanned", "message": "已扫码，正在连接…"}

    if status == "need_verifycode":
        return {
            "status": "need_verifycode",
            "message": "请输入手机微信上显示的数字验证码。",
        }

    if status == "verify_code_blocked":
        return {
            "status": "verify_code_blocked",
            "message": "验证码多次错误，请稍后重试。",
        }

    if status == "binded_redirect":
        _active_logins.pop(user_id, None)
        return {
            "status": "already_connected",
            "message": "该微信已绑定过，无需重复绑定。",
        }

    if status == "confirmed":
        _active_logins.pop(user_id, None)
        account_id = str(resp.get("ilink_bot_id") or "").strip()
        bot_token = str(resp.get("bot_token") or "").strip()
        if not account_id or not bot_token:
            return {"status": "failed", "message": "绑定失败：未返回完整账号信息。"}
        login_user_id = str(resp.get("ilink_user_id") or "").strip()
        resolved_base_url = (
            str(resp.get("baseurl") or base_url).strip() or WECLAW_BASE_URL
        )
        # 先放行所有来源（allow_from=["*"]）：登录返回的 ilink_user_id 与入站消息的
        # from_user_id 可能命名空间不同，若预先收窄到 [login_user_id] 会把消息全部挡掉。
        # channel 首次收到消息时会把首个 sender 绑定为 login_user_id 并自动收窄白名单。
        allow_from = ["*"]

        bot = WeclawBot(
            user_id=user_id,
            account_id=account_id,
            token=bot_token,
            base_url=resolved_base_url,
            route_tag=route_tag,
            allow_from=allow_from,
            login_user_id=login_user_id,
            enabled=True,
        )
        store.upsert_bot(bot)
        try:
            manager.start_bot(bot)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("weclaw 绑定成功但启动 bot 失败 user=%s: %s", user_id, exc)
        logger.info("weclaw 绑定成功: user=%s account_id=%s", user_id, account_id)
        return {"status": "confirmed", "message": "绑定成功！你的微信助手已上线。"}

    if status in ("scaned", "scanned"):
        return {"status": "scanned", "message": "已扫码，请在微信中确认。"}

    if status == "expired":
        refresh = int(login.get("refresh") or 1) + 1
        if refresh > _MAX_QR_REFRESH:
            _active_logins.pop(user_id, None)
            return {"status": "expired", "message": "二维码多次过期，请重新绑定。"}
        try:
            qr = await client.fetch_qr_code(
                base_url=WECLAW_BASE_URL, route_tag=route_tag
            )
        except Exception as exc:  # pylint: disable=broad-except
            return {"status": "failed", "message": f"刷新二维码失败：{exc}"}
        new_qrcode = _pick_qr_code(qr)
        new_img = _pick_qr_image(qr)
        login.update(
            {
                "qrcode": new_qrcode,
                "qrcode_url": new_img,
                "started_at": _now_ms(),
                "refresh": refresh,
                "base_url": WECLAW_BASE_URL,
            }
        )
        return {
            "status": "waiting",
            "message": "二维码已刷新，请重新扫描。",
            "qrcode": new_qrcode,
            "qrcode_url": new_img,
        }

    return {"status": "waiting", "message": "等待扫码…"}


def get_bind_status(user_id: str) -> dict[str, Any]:
    bot = store.get_bot(user_id)
    if not bot:
        return {"bound": False}
    return {
        "bound": True,
        "enabled": bot.enabled,
        "account_id": bot.account_id,
        "login_user_id": bot.login_user_id,
    }


def unbind(user_id: str) -> None:
    store.set_enabled(user_id, False)
    try:
        manager.stop_bot(user_id)
    except Exception:  # pylint: disable=broad-except
        logger.warning("weclaw 解绑时停止 bot 失败 user=%s", user_id, exc_info=True)
