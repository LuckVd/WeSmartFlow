"""system prompt 构建器基类 —— "装订机"的统一接口。

Builder 的职责边界：**只决定 system prompt 分几段、按什么顺序排**。
单段文字的内容由 :class:`~agent_core.context.provider.ContextProvider` 提供，
对话历史由 ``memory`` 包提供，二者都不属于 Builder。

子类实现要点
------------

必须实现 :meth:`build_system_prompt`（同步）；若支持 provider 注入，
应额外提供 ``build_system_prompt_async(ctx, user_input, **kwargs)`` ——
Agent 循环优先走异步路径，因此 provider 可以做 IO（查库、检索、调 LLM）。

.. note::
   Builder 不提供 ``build_messages`` 与 ``add_*`` 系列方法。完整 messages
   由 :func:`~agent_core.context.assemble.assemble` 独家装配为
   ``[system] + memory.render(ctx)``——这也是框架内唯一能产生
   ``role="system"`` 消息的地方。单条消息的构造见
   :mod:`agent_core.agent.history`。

   这样"历史怎么裁剪"只有 memory 一个归属，"system 段写什么"只有
   builder + provider 一个来源，"两者怎么拼"只有 assemble 一个拥有者。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SystemPromptBuilder(ABC):
    """system prompt 构建器抽象基类。

    子类只需实现 :meth:`build_system_prompt`——把若干片段按既定顺序拼成
    一段 system prompt 文本。history 与 messages 的组装不在此处。
    """

    @abstractmethod
    def build_system_prompt(self, **kwargs: Any) -> str:
        """构建 system prompt 字符串。

        基类签名采用 ``**kwargs``，子类应在自身签名中以带默认值的关键字
        参数显式声明所需参数（如 ``skill_names: list = None`` 加 ``**kwargs``
        兜底），调用方统一以关键字方式传入。

        Returns:
            完整的 system prompt 文本。
        """
        ...
