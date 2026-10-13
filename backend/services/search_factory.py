"""搜索客户端工厂：装配额度拦截 + 记账 hook（与 llm_factory 同构）。

调用方（Agent 工具、路由、测试接口）一律通过 :func:`get_search_client`
获取客户端实例，不得自行构造后端 SDK 客户端——这是用量治理的
单一收口，与 LLM 的 ``get_llm`` 约定一致。

hook 语义（见 agent_core/hooks.py）：
  - pre  : :func:`services.credit_quota.assert_available` 事前软检查，
           超限抛 ``CreditsExceeded`` 阻断调用；
  - post : :func:`services.usage_meter.record_usage` 成功记账
           （fn 抛出则 post 不触发，失败不计费）。
"""

from __future__ import annotations

import logging
import os

from agent_core.hooks import hookwrapper, observe
from agent_core.tool.search.base import BaseSearchClient
from agent_core.tool.search.tavily import TavilySearchClient
from services.provider_gateway import get_provider_gateway

logger = logging.getLogger(__name__)


def _attach_hooks(
    client: BaseSearchClient,
    *,
    user_id: str,
    scene: str,
    with_quota: bool,
) -> BaseSearchClient:
    """在 ``client.search`` 外层装配额度拦截与记账 hook。"""

    from services.credit_quota import is_using_platform_key

    is_system = user_id == "__system__"
    platform_key = not is_system and is_using_platform_key(user_id, "search")

    # Search is read-only, so the provider profile explicitly allows one
    # transient transport retry.  The compatibility client still owns the SDK
    # details; the gateway only provides policy and observability.
    gateway = get_provider_gateway()
    profile = gateway.resolve(
        category="search",
        backend=client.backend,
        endpoint=getattr(client, "base_url", "") or "https://api.tavily.com",
    )
    client.search = gateway.instrument_sync(  # type: ignore[method-assign]
        profile,
        "search.query",
        client.search,
        scene=scene,
        success=lambda result: bool(getattr(result, "ok", False)),
    )
    client.provider_profile = profile  # type: ignore[attr-defined]

    def _pre(*_args, **_kwargs):
        from services.credit_quota import assert_available

        assert_available(user_id, "search", platform_key=platform_key)

    def _post(_result):
        from services.usage_meter import record_usage

        record_usage(
            user_id,
            category="search",
            scene=scene,
            provider="tavily",
            units=_result.api_credits,
            counts_quota=platform_key,
            is_system=is_system,
        )

    pre = observe(_pre) if with_quota else None
    post = observe(_post)
    client.search = hookwrapper(client.search, pre=pre, post=post)  # type: ignore[method-assign]
    return client


def get_search_client(
    user_id: str,
    *,
    with_quota: bool = True,
    scene: str = "search",
) -> BaseSearchClient:
    """构造搜索客户端并挂治理 hook。

    优先级：
      1. 用户在设置页配置了 tavily_api_key → 自配 Key
         （``assert_available`` 内部判定平台不承担成本，放行不拦截，记账照常）；
      2. 环境变量 TAVILY_API_KEY → 平台 Key（受额度限制）；
         平台 Key 可配合 TAVILY_BASE_URL 指向 Tavily 兼容服务。
         用户自配 Key 始终发往 Tavily 官方地址，不会发给平台的兼容服务。

    Args:
        user_id:    用户 ID，用于读配置与额度归属。
        with_quota: 是否启用事前拦截（默认 True）；系统级调用传 False。
        scene:      用量归因场景（见 usage_meter.VALID_SCENES）。
    """
    user_key = ""
    try:
        from database import get_setting

        user_key = (get_setting(user_id, "tavily_api_key") or "").strip()
    except Exception:  # pylint: disable=broad-except
        logger.warning("搜索配置读取失败，回退环境变量", exc_info=True)

    if user_key:
        client = TavilySearchClient(api_key=user_key)
    else:
        client = TavilySearchClient(
            api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            base_url=os.getenv("TAVILY_BASE_URL", ""),
        )
    return _attach_hooks(client, user_id=user_id, scene=scene, with_quota=with_quota)


__all__ = ["get_search_client"]
