"""WeclawChannelManager：统一调度多个 bot 的长轮询协程。

- 进程启动时加载所有 enabled 的 bot，各起一个 ``asyncio.Task`` 跑 ``WeclawChannel.run``；
- 所有 bot 共享一个 ``ClawbridgeClient``（单连接池）；
- 提供 start/stop 单个 bot 的能力（扫码登录成功后可热启一个新 bot）。

每个 bot 的成本 ≈ 一个挂起协程 + 一条 idle 长连接，与维持一个 SSE 连接同级。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from channels import store
from channels.protocol import ClawbridgeClient
from channels.store import WeclawBot
from channels.weclaw_channel import WeclawChannel
from utils.log_safe import safe_log

logger = logging.getLogger(__name__)


class WeclawChannelManager:
    def __init__(self):
        self._client: Optional[ClawbridgeClient] = None
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stops: Dict[str, asyncio.Event] = {}
        self._started = False

    @property
    def client(self) -> Optional[ClawbridgeClient]:
        return self._client

    def ensure_client(self) -> ClawbridgeClient:
        if not self._client:
            self._client = ClawbridgeClient()
        return self._client

    async def start(self) -> None:
        """加载所有 enabled 的 bot 并拉起长轮询协程。"""
        if self._started:
            return
        self._started = True
        self._client = ClawbridgeClient()
        bots = store.list_enabled_bots()
        logger.info("WeclawChannelManager 启动，加载 %d 个 bot", len(bots))
        for bot in bots:
            self.start_bot(bot)

    def start_bot(self, bot: WeclawBot) -> None:
        """为单个 bot 启动长轮询协程（已在跑则先停旧的）。"""
        if not self._client:
            self._client = ClawbridgeClient()
        if bot.user_id in self._tasks:
            self.stop_bot(bot.user_id)
        stop_event = asyncio.Event()
        channel = WeclawChannel(bot, self._client)
        task = asyncio.create_task(
            channel.run(stop_event), name=f"weclaw-{bot.user_id}"
        )
        self._tasks[bot.user_id] = task
        self._stops[bot.user_id] = stop_event
        logger.info("weclaw bot 已启动: user=%s", safe_log(bot.user_id))

    def stop_bot(self, user_id: str) -> None:
        stop_event = self._stops.pop(user_id, None)
        if stop_event:
            stop_event.set()
        task = self._tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
        logger.info("weclaw bot 已停止: user=%s", safe_log(user_id))

    async def stop(self) -> None:
        """停止所有 bot 并释放连接池。"""
        for user_id in list(self._tasks.keys()):
            self.stop_bot(user_id)
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        self._stops.clear()
        if self._client:
            await self._client.aclose()
            self._client = None
        self._started = False
        # 释放卡片渲染用的 Chromium
        try:
            from channels.render import renderer

            await renderer.aclose()
        except Exception:  # pylint: disable=broad-except
            pass
        logger.info("WeclawChannelManager 已全部停止")


# 单例
manager = WeclawChannelManager()
