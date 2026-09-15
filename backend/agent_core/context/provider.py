"""ContextProvider — 向 system prompt 动态注入片段的协议。

Provider 的职责边界：**只负责交出一段文字**，不知道自己会被排在第几段
（顺序由 Builder 决定）。框架**不解释**片段内容是什么（用户画像？知识图谱
检索？交互策略提示？），只负责按序调用并拼接。

为什么需要这一层
----------------

Builder 是框架代码，若要拼「用户画像」就得反向 import 业务模块。抽出本协议
后依赖方向被掰正：**业务实现协议，框架消费协议**::

    业务：agents/providers.py  ──实现──> ContextProvider
    框架：context/layered.py   ──消费──> ContextProvider

这一次性消除了三类同构的 hack：框架内 import 业务服务、Service 内动态定义
闭包子类、检索逻辑硬编码在 prompt 拼装里——三者本质都是"按需往 system
prompt 拼片段"。

框架只提供无业务语义的通用壳（:class:`StaticProvider` /
:class:`CallableProvider` / :class:`FileProvider`）。

调用期保证
----------

:func:`gather_provider_sections` 为所有 provider 白送三项能力，实现方无需自理：

- **并发执行** — 总耗时取决于最慢的那个，而非累加
- **故障隔离** — 单个 provider 抛异常只丢自己那段，对话照常进行
- **顺序稳定** — 虽并发执行，但按**声明顺序**拼接，与返回快慢无关

业务侧实现示例::

    class ProfileProvider:
        name = "profile"
        title = "用户画像（统一总览）"

        def __init__(self, user_id: str):
            self._user_id = user_id

        async def provide(self, ctx, user_input):
            return ProfileMemoryService().build_profile_text(self._user_id)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..runtime.run_context import RunContext

logger = logging.getLogger(__name__)


@runtime_checkable
class ContextProvider(Protocol):
    """向 system prompt 注入动态片段的协议。

    Attributes:
        name:  provider 标识，用于日志与去重。
        title: 片段小标题；非空时会渲染为 ``## {title}`` 段落。
    """

    name: str
    title: str

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        """产出要注入的文本片段。

        Args:
            ctx:        运行上下文（可从中取 principal、settings 等）。
            user_input: 本轮用户输入，供需要按输入检索的 provider 使用。

        Returns:
            片段文本；返回 None 或空串表示本次不注入。
        """
        ...


class StaticProvider:
    """注入固定文本的 provider。"""

    def __init__(self, name: str, text: str, title: str = ""):
        self.name = name
        self.title = title
        self._text = text

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        return self._text

    def __repr__(self) -> str:
        return f"<StaticProvider {self.name}>"


class CallableProvider:
    """把普通函数 / 异步函数包装为 provider。

    便于业务侧快速接入，无需为每个片段定义一个类::

        CallableProvider("policy", lambda ctx, inp: hint_text, title="交互提示")
    """

    def __init__(self, name: str, fn: Any, title: str = ""):
        self.name = name
        self.title = title
        self._fn = fn

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        try:
            sig_params = len(inspect.signature(self._fn).parameters)
        except (TypeError, ValueError):
            sig_params = 2

        args = (ctx, user_input)[:sig_params] if sig_params <= 2 else (ctx, user_input)
        ret = self._fn(*args)
        if inspect.isawaitable(ret):
            ret = await ret
        return ret

    def __repr__(self) -> str:
        return f"<CallableProvider {self.name}>"


class FileProvider:
    """注入 Markdown / 文本文件内容的 provider（带 mtime 失效缓存）。"""

    def __init__(self, name: str, path: Any, title: str = ""):
        from pathlib import Path

        self.name = name
        self.title = title
        self._path = Path(path)
        self._cache: Optional[str] = None
        self._mtime: float = -1.0

    async def provide(self, ctx: "RunContext", user_input: str = "") -> Optional[str]:
        if not self._path.exists():
            return None
        mtime = self._path.stat().st_mtime
        if self._cache is None or mtime != self._mtime:
            self._cache = self._path.read_text(encoding="utf-8").strip()
            self._mtime = mtime
        return self._cache

    def __repr__(self) -> str:
        return f"<FileProvider {self.name} path={self._path}>"


async def gather_provider_sections(
    providers: List[ContextProvider],
    ctx: "RunContext",
    user_input: str = "",
) -> List[str]:
    """并发调用所有 provider，返回已渲染的片段列表（保持声明顺序）。

    单个 provider 异常或超时不影响其余——上下文注入是增强而非必需，
    任何一个片段失败都不应让整次对话失败。

    Args:
        providers:  provider 列表，按声明顺序渲染。
        ctx:        运行上下文。
        user_input: 本轮用户输入。

    Returns:
        渲染后的片段文本列表（已跳过空结果）。
    """
    if not providers:
        return []

    async def _safe(p: ContextProvider) -> Optional[str]:
        try:
            return await p.provide(ctx, user_input)
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "ContextProvider %s 执行失败，跳过该片段",
                getattr(p, "name", type(p).__name__),
                exc_info=True,
            )
            return None

    results = await asyncio.gather(*(_safe(p) for p in providers))

    sections: List[str] = []
    for provider, text in zip(providers, results):
        if not text or not str(text).strip():
            continue
        body = str(text).strip()
        title = getattr(provider, "title", "") or ""
        sections.append(f"## {title}\n\n{body}" if title else body)
    return sections


__all__ = [
    "CallableProvider",
    "ContextProvider",
    "FileProvider",
    "StaticProvider",
    "gather_provider_sections",
]
