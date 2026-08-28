"""weclaw / clawbridge 协议层（async httpx 实现）。

对应 AIFS-Desktop ``core/channels/weclaw.py`` 里的网络原语，但把同步 ``urllib +
asyncio.to_thread`` 换成**真正的异步 httpx**——这样每个 bot 的长轮询只是一个挂起
协程（≈ 一条 idle 长连接），不占线程池，单机可同时挂大量 bot。

clawbridge 鉴权没有 HMAC 签名，只需：
  - Header：``iLink-App-Id`` / ``iLink-App-ClientVersion`` / ``AuthorizationType:
    ilink_bot_token`` / ``Authorization: Bearer <token>`` / ``X-WECHAT-UIN`` /
    可选 ``SKRouteTag``
  - Body：紧凑 JSON（``separators=(",", ":")``），并在多数接口合入 ``base_info``
"""

from __future__ import annotations

import base64
import hashlib
import asyncio
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── 常量（与 clawbridge 对齐）────────────────────────────────────
WECLAW_CHANNEL_VERSION = "3.0.10"
WECLAW_ILINK_APP_ID = "weclaw_bot"
WECLAW_ILINK_BOT_TYPE = "3"
WECLAW_BOT_AGENT = "OpenClaw"
DEFAULT_API_TIMEOUT_MS = 15_000
QR_LONG_POLL_TIMEOUT_MS = 35_000
SESSION_EXPIRED_ERRCODE = -14

MESSAGE_TYPE = {"NONE": 0, "USER": 1, "BOT": 2}
MESSAGE_STATE = {"NEW": 0, "GENERATING": 1, "FINISH": 2}
MESSAGE_ITEM_TYPE = {
    "NONE": 0,
    "TEXT": 1,
    "IMAGE": 2,
    "VOICE": 3,
    "FILE": 4,
    "VIDEO": 5,
}


def _build_client_version(version: str) -> int:
    parts = [int(p) if p.isdigit() else 0 for p in version.split(".")]
    parts += [0, 0, 0]
    major, minor, patch = parts[:3]
    return ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)


_CLIENT_VERSION = _build_client_version(WECLAW_CHANNEL_VERSION)


def _base_info() -> dict[str, str]:
    return {"channel_version": WECLAW_CHANNEL_VERSION, "bot_agent": WECLAW_BOT_AGENT}


# ── AES-ECB（出站媒体加密，与 clawbridge CDN 约定一致）──────────────
def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def _aes_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def _aes_ecb_padded_size(plaintext_size: int) -> int:
    return ((plaintext_size // 16) + 1) * 16


def _encode_outbound_aes_key(aeskey_hex: str) -> str:
    return base64.b64encode(aeskey_hex.encode("utf-8")).decode("ascii")


def _random_uin() -> str:
    return base64.b64encode(str(secrets.randbits(32)).encode()).decode("ascii")


def generate_client_id() -> str:
    return f"openclaw-weclaw:{int(time.time() * 1000)}-{secrets.token_hex(4)}"


def _prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune_none(v) for v in value]
    return value


def _wire_json(value: Any) -> str:
    return json.dumps(_prune_none(value), ensure_ascii=False, separators=(",", ":"))


def _headers(*, token: Optional[str], route_tag: str = "") -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_uin(),
        "iLink-App-Id": WECLAW_ILINK_APP_ID,
        "iLink-App-ClientVersion": str(_CLIENT_VERSION),
    }
    if route_tag:
        headers["SKRouteTag"] = route_tag
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


class ClawbridgeClient:
    """共享连接池的 clawbridge 客户端。

    所有 bot 复用同一个 ``httpx.AsyncClient``（一个连接池）；``base_url`` /
    ``token`` / ``route_tag`` 都按调用传入，以支持多租户（每 bot 不同凭证/路由）。
    """

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=None),
            limits=httpx.Limits(max_connections=None, max_keepalive_connections=200),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(
        self,
        *,
        base_url: str,
        endpoint: str,
        route_tag: str,
        timeout_ms: Optional[int],
        label: str,
    ) -> dict[str, Any]:
        headers = {
            "iLink-App-Id": WECLAW_ILINK_APP_ID,
            "iLink-App-ClientVersion": str(_CLIENT_VERSION),
        }
        if route_tag:
            headers["SKRouteTag"] = route_tag
        url = f"{base_url.rstrip('/')}{endpoint}"
        timeout = httpx.Timeout(
            connect=10.0,
            read=(timeout_ms / 1000 if timeout_ms else 15.0),
            write=10.0,
            pool=10.0,
        )
        resp = await self._client.get(url, headers=headers, timeout=timeout)
        text = resp.text
        if resp.status_code >= 400:
            raise RuntimeError(f"{label} {resp.status_code}: {text}")
        return json.loads(text) if text.strip() else {}

    async def _post(
        self,
        *,
        base_url: str,
        endpoint: str,
        payload: dict[str, Any],
        token: Optional[str],
        route_tag: str,
        timeout_ms: Optional[int],
        label: str,
        with_base_info: bool = True,
    ) -> dict[str, Any]:
        body = dict(payload)
        if with_base_info:
            body["base_info"] = _base_info()
        body_text = _wire_json(body)
        headers = _headers(token=token, route_tag=route_tag)
        headers["Content-Length"] = str(len(body_text.encode("utf-8")))
        url = f"{base_url.rstrip('/')}{endpoint}"
        timeout = httpx.Timeout(
            connect=10.0,
            read=(timeout_ms / 1000 if timeout_ms else 15.0),
            write=10.0,
            pool=10.0,
        )
        resp = await self._client.post(
            url, content=body_text.encode("utf-8"), headers=headers, timeout=timeout
        )
        text = resp.text
        if resp.status_code >= 400:
            raise RuntimeError(f"{label} {resp.status_code}: {text}")
        if not text.strip():
            return {}
        return json.loads(text)

    # ── clawbridge 端点 ──────────────────────────────────────────

    async def get_updates(
        self,
        *,
        base_url: str,
        token: Optional[str],
        route_tag: str,
        get_updates_buf: str,
        timeout_ms: int,
    ) -> dict[str, Any]:
        try:
            return await self._post(
                base_url=base_url,
                endpoint="/ilink/clawbridge/getupdates",
                payload={"get_updates_buf": get_updates_buf},
                token=token,
                route_tag=route_tag,
                timeout_ms=timeout_ms,
                label="getUpdates",
            )
        except (httpx.TimeoutException, httpx.ReadTimeout):
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}

    async def notify_start(
        self, *, base_url: str, token: Optional[str], route_tag: str
    ) -> dict[str, Any]:
        return await self._post(
            base_url=base_url,
            endpoint="/ilink/clawbridge/notifystart",
            payload={},
            token=token,
            route_tag=route_tag,
            timeout_ms=10_000,
            label="notifyStart",
        )

    async def notify_stop(
        self, *, base_url: str, token: Optional[str], route_tag: str
    ) -> dict[str, Any]:
        return await self._post(
            base_url=base_url,
            endpoint="/ilink/clawbridge/notifystop",
            payload={},
            token=token,
            route_tag=route_tag,
            timeout_ms=10_000,
            label="notifyStop",
        )

    async def gen_message_id(
        self, *, base_url: str, token: Optional[str], route_tag: str, client_id: str
    ) -> int:
        resp = await self._post(
            base_url=base_url,
            endpoint="/ilink/clawbridge/genmessageidwithcliid",
            payload={"client_id": client_id, "base_info": _base_info()},
            token=token,
            route_tag=route_tag,
            timeout_ms=DEFAULT_API_TIMEOUT_MS,
            label="genMessageIdWithCliId",
            with_base_info=False,
        )
        if resp.get("ret") not in (None, 0):
            raise RuntimeError(f"genMessageIdWithCliId failed: {resp}")
        try:
            return int(resp.get("message_id") or 0)
        except (TypeError, ValueError):
            m = re.search(r'"message_id"\s*:\s*(\d+)', json.dumps(resp))
            return int(m.group(1)) if m else 0

    async def send_text(
        self,
        *,
        base_url: str,
        token: Optional[str],
        route_tag: str,
        to_user_id: str,
        text: str,
        context_token: Optional[str],
    ) -> dict[str, Any]:
        client_id = generate_client_id()
        message_id: Optional[int] = None
        try:
            message_id = await self.gen_message_id(
                base_url=base_url, token=token, route_tag=route_tag, client_id=client_id
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "weclaw genMessageId 失败，改为不带 message_id 发送: %s", exc
            )

        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE["BOT"],
            "message_state": MESSAGE_STATE["FINISH"],
            "item_list": [
                {"type": MESSAGE_ITEM_TYPE["TEXT"], "text_item": {"text": text}}
            ],
        }
        if message_id:
            msg["message_id"] = message_id
        if context_token:
            msg["context_token"] = context_token

        resp = await self._post(
            base_url=base_url,
            endpoint="/ilink/clawbridge/sendmessage",
            payload={"msg": msg},
            token=token,
            route_tag=route_tag,
            timeout_ms=DEFAULT_API_TIMEOUT_MS,
            label="sendMessage",
        )
        if resp.get("ret") not in (None, 0):
            logger.warning(
                "weclaw sendMessage ret=%s errmsg=%s",
                resp.get("ret"),
                resp.get("errmsg", ""),
            )
        else:
            logger.info(
                "weclaw sendMessage ok to=%s ret=%s chars=%d",
                to_user_id,
                resp.get("ret", 0),
                len(text),
            )
        return resp

    # ── 图片发送（getUploadUrl + CDN AES 上传 + IMAGE 消息）──────────

    async def _get_upload_url(
        self,
        *,
        base_url: str,
        token: Optional[str],
        route_tag: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._post(
            base_url=base_url,
            endpoint="/ilink/clawbridge/getuploadurl",
            payload=request,
            token=token,
            route_tag=route_tag,
            timeout_ms=DEFAULT_API_TIMEOUT_MS,
            label="getUploadUrl",
        )

    async def _upload_to_cdn(self, *, url: str, ciphertext: bytes) -> str:
        """上传密文到 CDN，返回响应头里的 x-encrypted-param（下载参数）。"""
        last_err: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                resp = await self._client.post(
                    url,
                    content=ciphertext,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=httpx.Timeout(
                        connect=10.0, read=30.0, write=30.0, pool=10.0
                    ),
                )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"CDN upload status {resp.status_code}: "
                        f"{resp.headers.get('x-error-message') or resp.text[:200]}"
                    )
                download_param = resp.headers.get("x-encrypted-param")
                if not download_param:
                    raise RuntimeError("CDN upload response missing x-encrypted-param")
                return download_param
            except Exception as exc:  # pylint: disable=broad-except
                last_err = exc
                if attempt < 3:
                    await asyncio.sleep(1)
        raise last_err or RuntimeError("CDN upload failed")

    async def send_image(
        self,
        *,
        base_url: str,
        cdn_base_url: str,
        token: Optional[str],
        route_tag: str,
        to_user_id: str,
        image_bytes: bytes,
        context_token: Optional[str],
    ) -> dict[str, Any]:
        """把 PNG/JPG 字节作为图片消息发送给微信对端。"""
        rawsize = len(image_bytes)
        rawfilemd5 = hashlib.md5(image_bytes).hexdigest()
        filesize = _aes_ecb_padded_size(rawsize)
        filekey = os.urandom(16).hex()
        aeskey = os.urandom(16)

        upload_resp = await self._get_upload_url(
            base_url=base_url,
            token=token,
            route_tag=route_tag,
            request={
                "filekey": filekey,
                "media_type": 1,  # 1=image
                "to_user_id": to_user_id,
                "rawsize": rawsize,
                "rawfilemd5": rawfilemd5,
                "filesize": filesize,
                "no_need_thumb": True,
                "aeskey": aeskey.hex(),
            },
        )
        upload_full_url = str(upload_resp.get("upload_full_url") or "").strip()
        upload_param = str(upload_resp.get("upload_param") or "").strip()
        if not upload_full_url and not upload_param:
            raise RuntimeError(
                "getUploadUrl 未返回上传地址: ret=%s errmsg=%s"
                % (
                    upload_resp.get("ret", upload_resp.get("errcode", "<none>")),
                    upload_resp.get("errmsg", ""),
                )
            )
        cdn_url = upload_full_url or (
            f"{cdn_base_url.rstrip('/')}/upload"
            f"?encrypted_query_param={urllib.parse.quote(upload_param, safe='')}"
            f"&filekey={urllib.parse.quote(filekey, safe='')}"
        )
        ciphertext = _aes_ecb_encrypt(image_bytes, aeskey)
        download_param = await self._upload_to_cdn(url=cdn_url, ciphertext=ciphertext)

        client_id = generate_client_id()
        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE["BOT"],
            "message_state": MESSAGE_STATE["FINISH"],
            "item_list": [
                {
                    "type": MESSAGE_ITEM_TYPE["IMAGE"],
                    "image_item": {
                        "media": {
                            "encrypt_query_param": download_param,
                            "aes_key": _encode_outbound_aes_key(aeskey.hex()),
                            "encrypt_type": 1,
                        },
                        "mid_size": filesize,
                    },
                }
            ],
        }
        if context_token:
            msg["context_token"] = context_token
        resp = await self._post(
            base_url=base_url,
            endpoint="/ilink/clawbridge/sendmessage",
            payload={"msg": msg},
            token=token,
            route_tag=route_tag,
            timeout_ms=DEFAULT_API_TIMEOUT_MS,
            label="sendImage",
        )
        if resp.get("ret") not in (None, 0):
            logger.warning(
                "weclaw sendImage ret=%s errmsg=%s",
                resp.get("ret"),
                resp.get("errmsg", ""),
            )
        else:
            logger.info("weclaw sendImage ok to=%s bytes=%d", to_user_id, rawsize)
        return resp

    # ── 扫码登录 ─────────────────────────────────────────────────

    async def fetch_qr_code(
        self,
        *,
        base_url: str,
        route_tag: str,
        local_token_list: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """获取绑定二维码：返回 {qrcode, qrcode_img_content, ...}。"""
        endpoint = f"/ilink/bot/get_bot_qrcode?bot_type={WECLAW_ILINK_BOT_TYPE}"
        return await self._post(
            base_url=base_url,
            endpoint=endpoint,
            payload={"local_token_list": local_token_list or []},
            token=None,
            route_tag=route_tag,
            timeout_ms=DEFAULT_API_TIMEOUT_MS,
            label="fetchQRCode",
            with_base_info=False,
        )

    async def poll_qr_status(
        self,
        *,
        base_url: str,
        route_tag: str,
        qrcode: str,
        verify_code: Optional[str] = None,
    ) -> dict[str, Any]:
        """轮询二维码状态（35s 长轮询）。返回 {status, ilink_bot_id, bot_token, baseurl, ilink_user_id, redirect_host}。"""
        import urllib.parse

        endpoint = f"/ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode)}"
        if verify_code:
            endpoint += f"&verify_code={urllib.parse.quote(verify_code)}"
        try:
            return await self._get(
                base_url=base_url,
                endpoint=endpoint,
                route_tag=route_tag,
                timeout_ms=QR_LONG_POLL_TIMEOUT_MS,
                label="pollQRStatus",
            )
        except (httpx.TimeoutException, httpx.ReadTimeout):
            return {"status": "wait"}
        except Exception:  # pylint: disable=broad-except
            return {"status": "wait"}


# ── 入站消息解析 ─────────────────────────────────────────────────


def extract_text_from_msg(full: dict[str, Any]) -> str:
    """从一条 getupdates 消息里抽取纯文本（拼接所有 TEXT item）。"""
    parts: list[str] = []
    for item in full.get("item_list") or []:
        if item.get("type") == MESSAGE_ITEM_TYPE["TEXT"]:
            text = (item.get("text_item") or {}).get("text") or ""
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


def extract_context_token(full: dict[str, Any]) -> str:
    for key in ("context_token", "contextToken"):
        val = str(full.get(key) or "").strip()
        if val:
            return val
    for nested_key in ("msg", "message", "context"):
        nested = full.get(nested_key)
        if isinstance(nested, dict):
            for key in ("context_token", "contextToken"):
                val = str(nested.get(key) or "").strip()
                if val:
                    return val
    return ""
