"""上下文工程（Context Engineering）：决定 LLM 每一步"看到什么"。

本包拥有**最终 messages**。它向 memory 要历史、向 provider 要知识、
向 tool 要 schema，然后装配成一次请求的完整输入。

上下文的四个来源
----------------

=========  ==========================================  ==================
来源        提供方                                       进入位置
=========  ==========================================  ==================
指令        :class:`SystemPromptBuilder`（本包）           system 段
知识        :class:`ContextProvider`（本包协议，业务实现）  system 段
历史        ``memory`` 包                                history 段
工具        ``tool`` 包的 schema 投影                     tools 参数
=========  ==========================================  ==================

本包内部三层
------------

**Assemble（装配者）** — :func:`assemble` 是框架内**唯一**产生最终 messages
的地方，也是唯一能产生 ``role="system"`` 消息的地方。它扣除 system 与
tool schema 的固定开销后，把剩余 token 预算下发给 memory。

**Builder（装订机）** — 决定 system prompt 分几段、按什么顺序排列：

===============================  ==============================================
:class:`StaticPromptBuilder`    固定文本，1 段
:class:`LayeredPromptBuilder`   角色定义 + 动态片段 + 技能，5 段
===============================  ==============================================

角色定义可来自仓库固定的 prompt 文件，也可来自用户工作空间中可编辑的
``agent.md``（用 :meth:`LayeredPromptBuilder.from_workspace` 构造）。
Builder 只产出 ``str``，从不产出 ``Message``——它不知道消息列表的存在。

**Provider（稿件供应商）** — 只负责交出其中**一段**文字，不知道自己排第几。
框架仅提供无业务语义的通用壳（:class:`StaticProvider` /
:class:`CallableProvider` / :class:`FileProvider`）；带业务语义的实现
（用户画像、知识图谱检索等）由业务侧提供，框架通过
:class:`ContextProvider` 协议消费——这使框架无需反向 import 业务模块。

.. note::
   ``agent_core.runtime.run_context.RunContext`` 与本包名字相近但职责无关：
   前者是"账本 + 遥控器"（预算、取消、追踪、事件），后者决定"写什么给 LLM"。
   ctx 被传入 :meth:`build_system_prompt_async` 仅为转交给 provider
   （供其读取 ``principal`` / ``settings``）。

一句话记忆
----------

``assemble`` 拼成品，``builder`` 管话的骨架，``provider`` 管话的血肉，
``memory`` 管话的历史，``ctx`` 管钱和命。
"""

from .assemble import assemble, measure
from .builder import SystemPromptBuilder
from .layered import LayeredPromptBuilder
from .provider import (
    CallableProvider,
    ContextProvider,
    FileProvider,
    StaticProvider,
    gather_provider_sections,
)
from .static import StaticPromptBuilder

__all__ = [
    # Assemble：拥有最终 messages
    "assemble",
    "measure",
    # Builder：决定骨架与顺序
    "SystemPromptBuilder",
    "StaticPromptBuilder",
    "LayeredPromptBuilder",
    # Provider：决定单个片段的内容
    "ContextProvider",
    "StaticProvider",
    "CallableProvider",
    "FileProvider",
    "gather_provider_sections",
]
