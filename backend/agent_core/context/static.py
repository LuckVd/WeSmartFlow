"""固定文本system prompt 构建器。

适用于 system prompt 写死、无需动态拼装的场景（工具型子 Agent、
一次性生成任务等）。需要注入动态片段时改用
:class:`~agent_core.context.layered.LayeredPromptBuilder`。
"""

from __future__ import annotations

from typing import Any

from .builder import SystemPromptBuilder


class StaticPromptBuilder(SystemPromptBuilder):
    """固定 system prompt 的system prompt 构建器。

    最简实现：只有一段固定文本，不支持 provider 注入，也不加载技能。

    Example::

        builder = StaticPromptBuilder("你是一个教育助手。")
        agent = ReActAgent(llm=llm, prompt_builder=builder)
    """

    def __init__(self, system_prompt: str):
        """
        Args:
            system_prompt: 固定的 system prompt 文本。
        """
        self._system_prompt = system_prompt

    def build_system_prompt(self, **kwargs: Any) -> str:
        return self._system_prompt

    def __repr__(self) -> str:
        preview = self._system_prompt[:30].replace("\n", " ")
        return f"StaticPromptBuilder(prompt={preview!r}...)"
