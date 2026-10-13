"""WeChat Mini Program login adapter.

The temporary ``js_code`` and AppSecret only live in the adapter request body.
They are never included in a retry, log message, error response or metric.
"""

from __future__ import annotations

from collections.abc import Mapping

from .http import IntegrationHttpError, IntegrationPolicy, SyncIntegrationHttpClient

_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WeChatAuthorizationRejected(IntegrationHttpError):
    """WeChat rejected an expired or otherwise invalid mini-program code."""


class WeChatProtocolError(IntegrationHttpError):
    """WeChat returned a response that cannot safely identify an account."""


class WeChatMiniProgramClient:
    """Exchange a Mini Program temporary code exactly once."""

    def __init__(self, http: SyncIntegrationHttpClient | None = None) -> None:
        # A js_code is single-use and may expire very quickly.  A retry can race
        # with WeChat's first acceptance and must therefore remain disabled.
        self._http = http or SyncIntegrationHttpClient(
            IntegrationPolicy(
                name="wechat-mini-program",
                timeout_seconds=10,
                max_retries=0,
                retry_safe=False,
                follow_redirects=False,
                max_concurrency=8,
            )
        )

    def exchange_code(self, *, app_id: str, app_secret: str, code: str) -> str:
        """Return an OpenID from one ``jscode2session`` call."""

        payload = self._http.get_json(
            _JSCODE2SESSION_URL,
            params={
                "appid": app_id,
                "secret": app_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
        if not isinstance(payload, Mapping):
            raise WeChatProtocolError("wechat-mini-program returned invalid JSON data")
        errcode = payload.get("errcode")
        if errcode not in (None, 0, "0"):
            # Do not echo `errmsg`: it is provider-controlled and may contain
            # request-sensitive material or unstable implementation wording.
            raise WeChatAuthorizationRejected(
                "WeChat authorization was rejected", retryable=False
            )
        openid = payload.get("openid")
        if not isinstance(openid, str) or not openid.strip():
            raise WeChatProtocolError("wechat-mini-program returned no openid")
        return openid.strip()


def get_wechat_client() -> WeChatMiniProgramClient:
    """Build a stateless Mini Program adapter for the current request."""

    return WeChatMiniProgramClient()


__all__ = [
    "WeChatAuthorizationRejected",
    "WeChatMiniProgramClient",
    "WeChatProtocolError",
    "get_wechat_client",
]
