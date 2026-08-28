"""单个 weclaw bot 的长轮询通道（async 协程，非线程）。

一个 ``WeclawChannel`` = 一个已绑定用户的 bot：
  - ``run()`` 是一个长轮询协程（≈ 一条 idle 长连接），由 ChannelManager 调度；
  - 收到文本消息 → 交给 ``bridge.generate_reply`` → 把回复发回微信。

MVP：只处理文本消息；富产物以链接形式随文本发回。媒体接收 / 流式 / 扫码登录为后续阶段。
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict

from config import (
    WECLAW_BASE_URL,
    WECLAW_CDN_BASE_URL,
    WECLAW_LONG_POLL_TIMEOUT_MS,
    WECLAW_RENDER_CARDS,
)
from channels import bridge, store
from channels.protocol import (
    ClawbridgeClient,
    MESSAGE_TYPE,
    SESSION_EXPIRED_ERRCODE,
    extract_context_token,
    extract_text_from_msg,
)
from channels.store import WeclawBot
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)

_RETRY_DELAY_S = 3.0
_BACKOFF_DELAY_S = 30.0
_MAX_CONSECUTIVE_FAILURES = 5


class WeclawChannel:
    def __init__(self, bot: WeclawBot, client: ClawbridgeClient):
        self.bot = bot
        self.client = client
        self.base_url = bot.base_url or WECLAW_BASE_URL
        self.route_tag = bot.route_tag or ""
        self._processed_ids: "OrderedDict[str, None]" = OrderedDict()
        self._peer_locks: dict[str, asyncio.Lock] = {}

    # ── 长轮询主循环 ─────────────────────────────────────────────

    async def run(self, stop_event: asyncio.Event) -> None:
        logger.info(
            "weclaw[%s] 通道启动 base_url=%s allow_from=%s login_user_id=%s",
            safe_log(self.bot.user_id),
            self.base_url,
            self.bot.allow_from,
            safe_log(self.bot.login_user_id or "<none>"),
        )
        try:
            ns_resp = await self.client.notify_start(
                base_url=self.base_url, token=self.bot.token, route_tag=self.route_tag
            )
            logger.info(
                "weclaw[%s] notifyStart ok ret=%s",
                safe_log(self.bot.user_id),
                ns_resp.get("ret", ns_resp.get("errcode", "<none>")),
            )
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "weclaw[%s] notifyStart 失败", safe_log(self.bot.user_id), exc_info=True
            )

        buf = self.bot.get_updates_buf or ""
        timeout_ms = WECLAW_LONG_POLL_TIMEOUT_MS
        failures = 0
        poll_count = 0

        while not stop_event.is_set():
            try:
                resp = await self.client.get_updates(
                    base_url=self.base_url,
                    token=self.bot.token,
                    route_tag=self.route_tag,
                    get_updates_buf=buf,
                    timeout_ms=timeout_ms,
                )
                poll_count += 1
                msgs = resp.get("msgs") or []
                logger.info(
                    "weclaw[%s] getUpdates #%d ret=%s msgs=%d buf=%s",
                    safe_log(self.bot.user_id),
                    poll_count,
                    resp.get("ret", resp.get("errcode", "<none>")),
                    len(msgs),
                    "changed"
                    if resp.get("get_updates_buf")
                    and str(resp.get("get_updates_buf")) != buf
                    else "same",
                )
                if resp.get("longpolling_timeout_ms"):
                    timeout_ms = int(resp["longpolling_timeout_ms"])

                err = (resp.get("ret") not in (None, 0)) or (
                    resp.get("errcode") not in (None, 0)
                )
                if err:
                    if SESSION_EXPIRED_ERRCODE in (
                        resp.get("ret"),
                        resp.get("errcode"),
                    ):
                        logger.error(
                            "weclaw[%s] 会话过期，暂停该 bot（需重新扫码登录）",
                            safe_log(self.bot.user_id),
                        )
                        store.set_enabled(self.bot.user_id, False)
                        return
                    failures += 1
                    logger.error(
                        "weclaw[%s] getUpdates 出错 ret=%s errcode=%s errmsg=%s",
                        safe_log(self.bot.user_id),
                        resp.get("ret"),
                        resp.get("errcode"),
                        resp.get("errmsg", ""),
                    )
                    await asyncio.sleep(
                        _BACKOFF_DELAY_S
                        if failures >= _MAX_CONSECUTIVE_FAILURES
                        else _RETRY_DELAY_S
                    )
                    if failures >= _MAX_CONSECUTIVE_FAILURES:
                        failures = 0
                    continue

                failures = 0
                new_buf = resp.get("get_updates_buf")
                if new_buf and str(new_buf) != buf:
                    buf = str(new_buf)
                    store.save_get_updates_buf(self.bot.user_id, buf)

                for full in resp.get("msgs") or []:
                    await self._on_message(full)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                if stop_event.is_set():
                    return
                failures += 1
                logger.exception(
                    "weclaw[%s] 轮询异常 (%s): %s",
                    safe_log(self.bot.user_id),
                    failures,
                    exc,
                )
                await asyncio.sleep(
                    _BACKOFF_DELAY_S
                    if failures >= _MAX_CONSECUTIVE_FAILURES
                    else _RETRY_DELAY_S
                )
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    failures = 0

        try:
            await self.client.notify_stop(
                base_url=self.base_url, token=self.bot.token, route_tag=self.route_tag
            )
        except Exception:  # pylint: disable=broad-except
            pass

    # ── 单条消息处理 ─────────────────────────────────────────────

    def _is_allowed(self, sender_id: str) -> bool:
        allow = self.bot.allow_from or ["*"]
        return "*" in allow or sender_id in allow

    async def _on_message(self, full: dict) -> None:
        msg_id = str(full.get("message_id") or full.get("client_id") or "")
        mtype = full.get("message_type")
        sender_id = str(full.get("from_user_id") or "").strip()
        logger.info(
            "weclaw[%s] 收到消息 msg_id=%s type=%s from=%s keys=%s",
            safe_log(self.bot.user_id),
            msg_id or "<none>",
            mtype,
            safe_log(sender_id or "<none>"),
            sorted(str(k) for k in full.keys()),
        )
        if msg_id:
            if msg_id in self._processed_ids:
                logger.info(
                    "weclaw[%s] 消息已处理过，跳过 msg_id=%s",
                    safe_log(self.bot.user_id),
                    msg_id,
                )
                return
            self._processed_ids[msg_id] = None
            while len(self._processed_ids) > 1000:
                self._processed_ids.popitem(last=False)

        if mtype == MESSAGE_TYPE["BOT"]:
            logger.info("weclaw[%s] 跳过 bot 自身消息", safe_log(self.bot.user_id))
            return

        if not sender_id or not self._is_allowed(sender_id):
            logger.warning(
                "weclaw[%s] 消息被白名单拦截 from=%s allow_from=%s（若应放行请检查 login_user_id 是否匹配）",
                safe_log(self.bot.user_id),
                safe_log(sender_id or "<none>"),
                self.bot.allow_from,
            )
            return

        # 首个发消息者绑定为 login_user_id，并把白名单收窄（对齐 AIFS 行为）
        if not self.bot.login_user_id and "*" in (self.bot.allow_from or ["*"]):
            self.bot.login_user_id = sender_id
            self.bot.allow_from = [sender_id]
            store.save_login_user_id(self.bot.user_id, sender_id, [sender_id])

        text = extract_text_from_msg(full)
        context_token = extract_context_token(full)

        lock = self._peer_locks.setdefault(sender_id, asyncio.Lock())
        async with lock:
            if not text:
                await self._safe_send(
                    sender_id, "当前只支持文本消息哦～", context_token
                )
                return
            try:
                reply = await bridge.generate_reply(self.bot.user_id, sender_id, text)
                await self._safe_send(
                    sender_id, reply.render_for_wechat(), context_token
                )
                # 卡片类产物：渲染成图片发送 + 附一句网页端交互提示
                for card in getattr(reply, "cards", []) or []:
                    await self._send_card(sender_id, card, context_token)
            except Exception:  # pylint: disable=broad-except
                logger.exception("weclaw[%s] 生成回复失败", safe_log(self.bot.user_id))
                await self._safe_send(
                    sender_id, "处理消息时出错了，请稍后再试。", context_token
                )

    async def _send_card(self, to: str, card: dict, context_token: str) -> None:
        """把一张卡片渲染成图片发送；失败则退化为发链接。"""
        title = card.get("title") or "卡片"
        url = card.get("url") or ""
        ctype = card.get("card_type", "")
        logger.info(
            "weclaw[%s] 处理卡片 type=%s doc=%s render_enabled=%s",
            safe_log(self.bot.user_id),
            ctype,
            safe_log(card.get("doc_id", "")),
            WECLAW_RENDER_CARDS,
        )
        png = None
        if WECLAW_RENDER_CARDS:
            try:
                from channels.render import renderer

                png = await renderer.render(ctype, card.get("doc_id", ""), title)
            except Exception:  # pylint: disable=broad-except
                logger.exception("weclaw[%s] 卡片渲染异常", safe_log(self.bot.user_id))
        logger.info(
            "weclaw[%s] 卡片渲染结果 type=%s png_bytes=%s",
            safe_log(self.bot.user_id),
            ctype,
            len(png) if png else 0,
        )

        if png:
            try:
                await self.client.send_image(
                    base_url=self.base_url,
                    cdn_base_url=WECLAW_CDN_BASE_URL,
                    token=self.bot.token,
                    route_tag=self.route_tag,
                    to_user_id=to,
                    image_bytes=png,
                    context_token=context_token or None,
                )
                # 图片后补一句可交互提示
                note = f"🔗 「{title}」在网页端可交互查看"
                await self._safe_send(to, note, context_token)
                return
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    "weclaw[%s] 发送卡片图片失败，退化为链接",
                    safe_log(self.bot.user_id),
                )

        # 兜底：发链接
        if url:
            await self._safe_send(to, f"📎 {title}：{url}", context_token)

    async def _safe_send(self, to: str, text: str, context_token: str) -> None:
        try:
            await self.client.send_text(
                base_url=self.base_url,
                token=self.bot.token,
                route_tag=self.route_tag,
                to_user_id=to,
                text=text,
                context_token=context_token or None,
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "weclaw[%s] 发送失败 to=%s", safe_log(self.bot.user_id), safe_log(to)
            )
