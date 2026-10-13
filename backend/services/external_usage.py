"""Authenticated attribution for demo HTTP clients and their background threads.

No default/demo pseudo-user: raw paid calls require an explicit scope. API
adapters establish it from JWT; background work copies it when it is submitted.
"""

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass
from threading import Thread
from fastapi import Depends
from dependencies import get_current_user
from services.credit_quota import assert_available
from services.pricing import calc_unit_credits
from services.usage_meter import record_usage


@dataclass(frozen=True)
class UsageScope:
    user_id: str
    scene: str


_scope = ContextVar("external_usage", default=None)


def current_usage() -> UsageScope:
    scope = _scope.get()
    if scope is None:
        raise RuntimeError(
            "外部 API 调用缺少用户计量上下文，请通过已登录的应用入口调用"
        )
    return scope


@contextmanager
def usage_scope(user_id: str, scene: str):
    token = _scope.set(UsageScope(user_id, scene))
    try:
        yield
    finally:
        _scope.reset(token)


def demo_usage(scene: str):
    async def dependency(user_id: str = Depends(get_current_user)):
        with usage_scope(user_id, scene):
            yield user_id

    return dependency


class UsageThread(Thread):
    """Snapshot attribution at submission, including nested generation threads."""

    def __init__(self, *args, **kwargs):
        context = copy_context()
        target = kwargs.pop("target", None)
        if target is None or args:
            raise TypeError("UsageThread requires a keyword target")
        target_args = kwargs.pop("args", ())
        target_kwargs = kwargs.pop("kwargs", {})
        super().__init__(
            target=context.run,
            args=(target, *target_args),
            kwargs=target_kwargs,
            **kwargs,
        )


def before_raw(category: str, *, model: str = "", provider: str = ""):
    scope = current_usage()
    if category not in {"llm", "embedding"}:
        calc_unit_credits(category, 1, model=model, provider=provider)
    # Raw demo clients explicitly use server credentials, even when the user
    # also has a personal key in settings.
    assert_available(scope.user_id, category, platform_key=True)


def record_raw(
    category: str, *, model: str = "", provider: str = "", units: float = 1, usage=None
):
    scope = current_usage()
    return record_usage(
        scope.user_id,
        scene=scope.scene,
        category=category,
        model=model,
        provider=provider,
        units=units,
        usage=usage,
        counts_quota=True,
    )
