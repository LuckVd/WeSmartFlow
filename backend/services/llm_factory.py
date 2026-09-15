"""
LLM 工厂：根据数据库 settings 表（或环境变量 fallback）创建 LLM 实例

优先使用用户配置的 OpenAI 兼容接口，否则 fallback 到环境变量 LLM_API_KEY。

横切关注点（额度拦截、用量记账）由 agent_core.hooks.hookwrapper 在
**实例外层**装配，provider 实现完全不感知它们的存在。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from agent_core.hooks import hookwrapper, observe
from agent_core.llm import BaseLLM, LLMResponse
from agent_core.llm.base import StreamFinishEvent
from agent_core.llm.openai_llm import OpenAILLM
from database import get_setting

logger = logging.getLogger(__name__)

# 系统后台任务的记账归属：不属于任何真实用户，用保留 id 隔离统计。
# usage_events 未对 user_id 建外键，正是为了容纳这类伪用户。
SYSTEM_USER_ID = "__system__"


def _get_cfg(user_id: str, key: str, env_fallback: str = "") -> str:
    """从 settings 表读取指定用户的配置，读取失败则 fallback 到环境变量。"""
    try:
        val = get_setting(user_id, key)
        if val:  # 非空才使用用户配置
            return val
    except Exception:  # pylint: disable=broad-except
        pass

    return os.getenv(env_fallback, "")


def _make_quota_pre_hook(user_id: str, platform_key=None):
    """额度拦截 pre hook：额度不足时抛异常，阻断本次调用。

    Returns:
        以 :func:`observe` 声明的**观察型** hook——它只校验、不改写入参。
        注意：观察型 hook 抛出的异常仍会向上传播并阻断真实调用，
        这正是额度拦截需要的语义（"观察"指不改数据，不是"不能拒绝"）。
    """

    @observe
    def _hook(*_args, **_kwargs):
        from services.credit_quota import assert_available

        # 按 credits 拦截（由 CREDITS_ENFORCEMENT_ENABLED 灰度开关控制；
        # 用户自配 key 时 is_using_platform_key 返回 False，直接放行）
        assert_available(user_id, "llm", platform_key=platform_key)

    return _hook


def _extract_usage_from_result(result) -> Optional[dict]:
    """从调用结果中取出 usage。

    非流式返回 LLMResponse；流式经 hookwrapper 后拿到的是最后一个
    StreamEvent（正常结束时为 StreamFinishEvent，内含完整 response）。
    """
    if isinstance(result, LLMResponse):
        return result.usage
    if isinstance(result, StreamFinishEvent):
        return result.response.usage
    return None


def _make_usage_post_hook(
    user_id: str, model: str, scene: str, is_system: bool, platform_key=None
):
    """用量记账 post hook：调用成功后按 token 折算 credits。

    与额度 pre hook 的分工：
      - pre  前置拦截（按 credits，事前软检查）
      - post 事后记账（按 token 折算 credits），只在成功时记录

    即便是不消耗用户额度的入口（用户自配 key、画像抽取、系统任务），
    也一律记账——否则平台侧成本无从观测。is_system 决定是否计入
    用户当期额度汇总。

    Returns:
        以 :func:`observe` 声明的**观察型** hook：返回值被忽略、
        调用结果原样透传、内部异常由框架吞掉——记账不会改写或
        破坏 LLM 的返回值。
    """

    @observe
    def _hook(result):
        usage = _extract_usage_from_result(result)
        if usage is None:
            return
        from services.usage_meter import record_usage

        record_usage(
            user_id,
            category="llm",
            scene=scene,
            model=model,
            usage=usage,
            is_system=is_system,
            counts_quota=platform_key,
        )

    return _hook


def _attach_hooks(
    llm: BaseLLM,
    *,
    user_id: str,
    scene: str,
    with_quota: bool,
    is_system: bool,
) -> BaseLLM:
    """在实例外层装配 pre/post hook，不改动 provider 内部实现。

    包装 ``think`` / ``async_think`` / ``stream_think`` 三个入口：
    OpenAILLM 对三者均为独立实现（同步 client / AsyncClient / 流式），
    互不委托，可安全并列包装而不产生双重记账。

    注意 BaseLLM 的默认 ``async_think`` 会委托 ``think``——若未来工厂
    产出其它未覆写 ``async_think`` 的实现类，需要改为只包装一个入口。
    """
    from contextvars import ContextVar
    from services.credit_quota import is_using_platform_key
    from services.pricing import ensure_usage

    platform_key = not is_system and is_using_platform_key(user_id, "llm")
    quota_pre = _make_quota_pre_hook(user_id, platform_key) if with_quota else None
    usage_post = _make_usage_post_hook(
        user_id, llm.model_name, scene, is_system, platform_key
    )
    inputs = ContextVar("llm_usage_inputs", default=[])

    @observe
    def pre(*args, **kwargs):
        inputs.set(kwargs.get("messages", args[0] if args else []))
        if quota_pre:
            quota_pre(*args, **kwargs)

    @observe
    def post(result):
        response = result.response if isinstance(result, StreamFinishEvent) else result
        if isinstance(response, LLMResponse) and not response.is_error:
            response.usage = ensure_usage(
                response.usage, inputs.get(), response.content, response.tool_calls
            )
        usage_post(result)

    # 绑定方法上打补丁：实例级替换，不影响类与其他实例。
    # think（同步）同样有大量调用方（设置页测试 / 课程节点抽取 /
    # 讲解稿 / 卡片音频 / 可视化 / 学习规划 / court），必须一并包装，
    # 否则这些用户操作会绕过额度拦截与记账。
    llm.think = hookwrapper(llm.think, pre=pre, post=post)  # type: ignore[method-assign]
    llm.async_think = hookwrapper(llm.async_think, pre=pre, post=post)  # type: ignore[method-assign]
    llm.stream_think = hookwrapper(llm.stream_think, pre=pre, post=post)  # type: ignore[method-assign]
    return llm


def create_openai_llm(
    user_id: str,
    *,
    api_key: str,
    base_url: str = "",
    model: str = "",
    with_quota: bool = True,
    scene: str = "unknown",
    is_system: bool = False,
    timeout: Optional[int] = None,
) -> BaseLLM:
    """创建 OpenAI 兼容 LLM 实例，并在外层装配额度与记账 hook。

    Args:
        user_id: 用户 ID
        api_key: OpenAI API Key（必传）。
        base_url: OpenAI 兼容 base URL，为空则使用 SDK 默认值。
        model: 模型名称，为空则使用 SDK 默认值。
        with_quota: 是否启用免费额度前置拦截（默认 True）。
        scene: 业务场景标签，用于用量归因（见 usage_meter.VALID_SCENES）。
        is_system: 是否为系统内部任务；系统任务仍记账但不计入用户额度。
    """
    if not api_key:
        raise RuntimeError(
            "未配置 LLM API Key。请在设置页面填写，或在 .env 中设置 LLM_API_KEY。"
        )
    llm = OpenAILLM(
        model_name=model or None,
        timeout=timeout,
        api_key=api_key,
        base_url=base_url or None,
    )
    return _attach_hooks(
        llm,
        user_id=user_id,
        scene=scene,
        with_quota=with_quota,
        is_system=is_system,
    )


def get_profile_llm(user_id: str) -> BaseLLM:
    """获取画像专用 LLM，默认不消耗用户额度。

    可通过 PROFILE_LLM_MODEL / PROFILE_LLM_BASE_URL / PROFILE_LLM_API_KEY 单独指定；
    未配置时复用 LLM_* 配置。适合使用更稳定的 tool_call 模型（如 deepseek-chat）。
    """
    api_key = os.getenv("PROFILE_LLM_API_KEY") or os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("PROFILE_LLM_BASE_URL") or os.getenv("LLM_BASE_URL", "")
    model = os.getenv("PROFILE_LLM_MODEL") or os.getenv("LLM_MODEL", "")
    return create_openai_llm(
        user_id,
        api_key=api_key,
        base_url=base_url,
        model=model,
        with_quota=False,
        scene="profile",
        is_system=True,
    )


def get_llm(
    user_id: str,
    with_quota: bool = True,
    scene: str = "unknown",
    timeout: Optional[int] = None,
) -> BaseLLM:
    """每次调用都从数据库/环境变量读取指定用户的最新配置，确保设置页修改后立即生效。

    with_quota=False 用于系统级内容生成（如内部知识维护），
    不消耗任何用户的免费对话额度。

    优先级：
      1. 用户在设置页配置了自己的 OpenAI key → 使用 OpenAI（不限额）
      2. 环境变量有 LLM_API_KEY → 使用 OpenAI（消耗免费额度）
      3. 都没有 → 报错

    用户自配 OpenAI key 不限额；
    只有 fallback 到平台 OpenAI key 时才会消耗免费对话额度。
    """
    # 一次性读取用户配置
    user_key = _get_cfg(user_id, "llm_api_key", "")
    base_url = _get_cfg(user_id, "llm_base_url", "")
    model = _get_cfg(user_id, "llm_model", "")

    # 用户自定义的 OpenAI key 优先, 不消耗免费额度
    if user_key:
        # 检查必须的用户配置项是否齐全
        if not base_url or not model:
            raise RuntimeError(
                "用户配置的 LLM 不完整。请确保同时设置了 llm_api_key, llm_base_url 和 llm_model。"
            )

        return create_openai_llm(
            user_id,
            timeout=timeout,
            api_key=user_key,
            base_url=base_url,
            model=model,
            with_quota=False,
            scene=scene,
        )

    # 环境变量 LLM_API_KEY, 消耗免费额度
    env_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "")
    model = os.getenv("LLM_MODEL", "")
    if env_key:
        # 检查必须的环境变量是否齐全
        if not base_url or not model:
            raise RuntimeError(
                "环境变量配置的 LLM 不完整。请确保同时设置了 LLM_API_KEY, LLM_BASE_URL 和 LLM_MODEL。"
            )

        return create_openai_llm(
            user_id,
            timeout=timeout,
            api_key=env_key,
            base_url=base_url,
            model=model,
            with_quota=with_quota,
            scene=scene,
            # 不消耗用户额度的调用（如内部知识维护）视为系统任务：
            # 仍记账以观测平台成本，但不计入用户当期额度
            is_system=not with_quota,
        )

    raise RuntimeError("未配置任何 LLM 服务。请在 .env 中设置 LLM_API_KEY。")


def get_system_llm(timeout: Optional[int] = None, scene: str = "system") -> BaseLLM:
    """系统内部组件专用的 LLM（KG builder/aggregator 等后台任务）。

    与 get_llm 的区别：
      - 只读环境变量，不查 settings 表（避免后台任务依赖某个真实用户的配置）
      - 不注入额度 hook（系统组件不属于任何用户，不应消费免费额度）
      - 可指定更短的 timeout（默认走 OpenAILLM 的 LLM_TIMEOUT env，通常较长）。
        后台 builder / aggregator 链路里推荐传 60s，避免单次卡住拖死整批。

    仍会注入用量记账 hook（is_system=True）：不计入任何用户额度，
    但成本必须可观测——后台任务恰恰是容易失控的部分。
    记在保留用户 ``__system__`` 名下，避免与真实用户混淆。
    """
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "")
    model = os.getenv("LLM_MODEL", "")
    if not api_key:
        raise RuntimeError(
            "系统 LLM 未配置。请在 .env 中设置 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL。"
        )
    if not base_url or not model:
        raise RuntimeError(
            "系统 LLM 配置不完整。请确保同时设置了 LLM_API_KEY, LLM_BASE_URL 和 LLM_MODEL。"
        )
    llm = OpenAILLM(
        model_name=model,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return _attach_hooks(
        llm,
        user_id=SYSTEM_USER_ID,
        scene=scene,
        with_quota=False,
        is_system=True,
    )
