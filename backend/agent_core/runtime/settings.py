"""Agent 运行期配置。

替代散落在各工具/LLM 里的 ``os.getenv`` 直读：配置一次性收集为不可变
数据对象，随 :class:`~agent_core.runtime.run_context.RunContext` 注入。

这样带来三个好处：
- **可测试**：单测直接构造 ``AgentSettings(...)``，无需操作全局 ``os.environ``。
- **可并发隔离**：同一进程内可用不同配置跑多个 Agent（如 A 用户自带 Key、
  B 用户用平台 Key），互不干扰。
- **无隐式依赖**：不再需要"反向 import 业务 config 模块以触发 load_dotenv"
  这类靠副作用生效的写法。

本模块刻意只依赖标准库，保持 ``agent_core`` 对业务层零依赖。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping, Optional


def _env(source: Mapping[str, str], *names: str, default: str = "") -> str:
    """按优先级读取第一个非空的环境变量。"""
    for name in names:
        val = (source.get(name) or "").strip()
        if val:
            return val
    return default


def _env_int(source: Mapping[str, str], name: str, default: int) -> int:
    raw = (source.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


#: 常见模型的上下文窗口（token）。按**子串**匹配模型名，长键优先。
#:
#: 这张表只用于"没有显式配置时给一个安全的默认值"——宁可估小也不估大：
#: 估小只是多裁剪几轮历史，估大会直接触发 API 报错。
#:
#: 键包含具体型号与**系列兜底**（如 ``deepseek``）。系列兜底取该系列的
#: 保守值，使 ``deepseek-v4-flash`` 这类未收录的新版本也能得到合理估计，
#: 而不是退化为"不限制"。
_CONTEXT_WINDOWS: Dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o3": 200_000,
    # DeepSeek
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "deepseek": 64_000,  # 系列兜底
    # 通义千问
    "qwen-max": 32_768,
    "qwen-plus": 131_072,
    "qwen-turbo": 1_000_000,
    "qwen-long": 10_000_000,
    "qwen": 32_768,  # 系列兜底
    # Claude
    "claude-3-5": 200_000,
    "claude-3-7": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "claude": 200_000,  # 系列兜底
    # 智谱
    "glm-4": 128_000,
    "glm": 128_000,  # 系列兜底
    # Kimi
    "moonshot-v1-128k": 128_000,
    "moonshot-v1-32k": 32_768,
    "moonshot-v1-8k": 8_192,
    "moonshot": 32_768,  # 系列兜底
}


def resolve_context_window(model: str, default: int = 0) -> int:
    """按模型名推断上下文窗口。

    未识别时返回 ``default``（默认 0 = 不做预算控制）。这是刻意的保守设计：
    猜错窗口比不猜更危险——猜大了会直接触发 API 报错。

    Args:
        model:   模型标识，如 ``qwen-plus`` 或 ``gpt-4o-2024-08-06``。
        default: 未匹配时的回退值。
    """
    if not model:
        return default
    name = model.strip().lower()
    # 长键优先：确保 "gpt-4-turbo" 不被 "gpt-4" 抢先匹配
    for key in sorted(_CONTEXT_WINDOWS, key=len, reverse=True):
        if key in name:
            return _CONTEXT_WINDOWS[key]
    return default


@dataclass(frozen=True)
class ProviderSettings:
    """单个 AI 供应商端点的配置。

    Attributes:
        api_key:        端点凭据。
        base_url:       端点地址（决定实际供应商）。
        model:          模型标识。
        context_window: 模型上下文窗口（token）。0 表示未知——此时装配层
                        不做预算控制，行为退化为"全量塞入"。
        extra:          供应商特有的额外参数。
    """

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    context_window: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """是否具备最基本的调用条件（有 Key）。"""
        return bool(self.api_key)


@dataclass(frozen=True)
class AgentSettings:
    """一次 Agent 运行所需的全部外部配置。

    字段按能力而非供应商组织：框架只关心"有没有 LLM / 图像 / TTS / 搜索能力"，
    具体是 DashScope 还是 OpenAI 兼容端点由 ``base_url`` 决定。

    Attributes:
        llm:      对话模型端点。
        image:    图像生成端点。
        tts:      语音合成端点。
        embedding: 向量化端点。
        search:   联网搜索端点（api_key 为搜索服务 Key）。
        proxy:    出站 HTTP 代理，空表示直连。
        timeout:  单次出站请求超时（秒）。
        workspace_dir: Agent 可读写的工作目录根，None 表示不限制。
        env:      兜底环境变量快照，供尚未迁移的工具过渡期读取。
    """

    llm: ProviderSettings = field(default_factory=ProviderSettings)
    image: ProviderSettings = field(default_factory=ProviderSettings)
    tts: ProviderSettings = field(default_factory=ProviderSettings)
    embedding: ProviderSettings = field(default_factory=ProviderSettings)
    search: ProviderSettings = field(default_factory=ProviderSettings)

    proxy: str = ""
    timeout: int = 60
    workspace_dir: Optional[str] = None

    env: Dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, source: Optional[Mapping[str, str]] = None) -> "AgentSettings":
        """从环境变量装配配置。

        Args:
            source: 环境变量映射，默认取 ``os.environ``。显式传入便于测试。
        """
        src: Mapping[str, str] = source if source is not None else os.environ

        llm_model = _env(src, "LLM_MODEL", default="gpt-4o")
        # 显式配置优先；未配置时按模型名推断
        llm_window = _env_int(
            src, "LLM_CONTEXT_WINDOW", resolve_context_window(llm_model)
        )

        return cls(
            llm=ProviderSettings(
                api_key=_env(src, "LLM_API_KEY", "OPENAI_API_KEY", "DASHSCOPE_API_KEY"),
                base_url=_env(src, "LLM_BASE_URL", "OPENAI_BASE_URL"),
                model=llm_model,
                context_window=llm_window,
            ),
            image=ProviderSettings(
                api_key=_env(src, "IMG_API_KEY", "DASHSCOPE_API_KEY"),
                base_url=_env(src, "IMG_BASE_URL"),
                model=_env(src, "IMG_MODEL"),
            ),
            tts=ProviderSettings(
                api_key=_env(src, "TTS_API_KEY", "DASHSCOPE_API_KEY"),
                base_url=_env(src, "TTS_BASE_URL"),
                model=_env(src, "TTS_MODEL"),
            ),
            embedding=ProviderSettings(
                api_key=_env(src, "KG_EMBEDDING_API_KEY", "DASHSCOPE_API_KEY"),
                base_url=_env(src, "KG_EMBEDDING_BASE_URL"),
                model=_env(src, "KG_EMBEDDING_MODEL", default="text-embedding-v4"),
            ),
            search=ProviderSettings(
                api_key=_env(src, "TAVILY_API_KEY", "ANYSEARCH_API_KEY"),
            ),
            proxy=_env(src, "FETCH_PROXY", "HTTPS_PROXY", "HTTP_PROXY"),
            timeout=_env_int(src, "AGENT_HTTP_TIMEOUT", 60),
            workspace_dir=_env(src, "AGENT_WORKSPACE_DIR") or None,
            env=dict(src),
        )

    def with_overrides(self, **changes: Any) -> "AgentSettings":
        """返回覆盖部分字段后的新配置（原对象不变）。"""
        return replace(self, **changes)

    # ------------------------------------------------------------------
    # 过渡期兜底
    # ------------------------------------------------------------------

    def raw(self, name: str, default: str = "") -> str:
        """读取原始环境变量。

        供尚未迁移到强类型字段的工具过渡使用；新代码应优先使用上面的
        结构化字段，不要依赖此方法。
        """
        val = (self.env.get(name) or "").strip()
        return val or default


#: 进程级默认配置。惰性初始化，避免 import 时就固化环境变量。
_DEFAULT: Optional[AgentSettings] = None


def default_settings() -> AgentSettings:
    """获取进程级默认配置（首次调用时从环境变量装配并缓存）。"""
    global _DEFAULT  # pylint: disable=global-statement
    if _DEFAULT is None:
        _DEFAULT = AgentSettings.from_env()
    return _DEFAULT


def reset_default_settings() -> None:
    """清空默认配置缓存，下次 ``default_settings()`` 会重新装配（测试用）。"""
    global _DEFAULT  # pylint: disable=global-statement
    _DEFAULT = None


__all__ = [
    "AgentSettings",
    "ProviderSettings",
    "default_settings",
    "reset_default_settings",
    "resolve_context_window",
]
