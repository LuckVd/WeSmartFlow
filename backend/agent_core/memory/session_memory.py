"""跨 run 连续的会话记忆（持久化 + 懒压缩策略合一）。

解决的问题
----------
此前"跨请求压缩"与"运行时裁剪"分属两套互不知晓的机制（业务层 LLM
摘要 vs 每次运行重新加载全量历史的临时 memory），导致：双重压缩、
摘要游标与窗口起点脱钩的可见性盲区、长 ReAct 链把本轮任务挤出窗口。

结构
----
::

    可见性 = [system: 角色 prompt + summary(本类属性, 经 assemble 合并)]
           + [游标后历史·窗口兜底]     ← 撞窗/预算紧张时触发压缩
           + [锚点: 本轮 user_input]   ← 运行中第一条 append，刚性
           + [本轮运行轨迹]            ← assistant/tool 消息，刚性

懒压缩（render 驱动）
--------------------
压缩发生在**信息即将不可见的时刻**（render 时），而不是运行结束后：

- **撞窗**：历史段条数超过 ``window`` → 把窗口外增量压进摘要；
- **预算紧张**：装配层下发的 token 预算装不下历史段 → 先压缩腾预算，
  压不动（历史已到保底 / 无 LLM / 压缩失败）才退回纯裁剪。

压缩成功即写 summary 与游标（DB 持久化；写库失败仅告警，内存游标
照常推进——最坏情况是崩溃后重复压缩一次，幂等无害）。新摘要经
``summary`` 属性由装配层当步合并进 system——压缩当轮即可见。

锚点内化：运行中第一条 :meth:`append` 即本轮任务（无需显式
``set_anchor``）；之后的 append 全部进轨迹段。锚点与轨迹**刚性不裁**
；若装配后仍超过上下文预算，装配层会中止运行，避免发送超限请求。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from ..runtime.budget import AgentRunError

from .base import (
    BaseMemory,
    Message,
    estimate_tokens,
    normalize_history,
    safe_cut,
)

logger = logging.getLogger(__name__)

_SUMMARY_SYS_PROMPT = (
    "你是对话摘要助手。请把【既有摘要】与【新增对话】整合为一段连贯的中文摘要，"
    "保留对后续辅导有价值的信息：用户的学习目标、已讲过的知识点与结论、"
    "用户表现出的薄弱点/偏好、待办或悬而未决的问题。"
    "去除寒暄与冗余，控制在 300 字以内，只输出摘要正文。"
)


def _format_for_summary(messages: List[Message]) -> str:
    """把消息列表格式化为 ``角色：内容`` 文本（供摘要 LLM）。"""
    lines: List[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        content = str(content).strip()
        if not content:
            continue
        speaker = {"user": "用户", "assistant": "助教", "system": "系统"}.get(
            role, role
        )
        lines.append(f"{speaker}：{content}")
    return "\n".join(lines)


class SessionMemory(BaseMemory):
    """跨 run 连续的会话记忆：store 提供持久化，本类维护懒压缩与可见性。"""

    def __init__(
        self,
        store: Any,
        *,
        window: int = 24,
        recent_keep: int = 12,
        llm: Any = None,
    ):
        """
        Args:
            store:       ``SessionStore`` 协议实现（业务侧提供）。
            window:      历史段条数上限——撞线即触发压缩（压掉窗口外增量）。
            recent_keep: 压缩后保留最近 N 条原文（压缩目标量）。
            llm:         压缩用 LLM（带 ``async_think``）；None 则永不压缩，
                         退化为"切片 + 裁剪"的只读记忆。
        """
        self._store = store
        self._window = window
        self._recent_keep = recent_keep
        self._llm = llm

        # ── 加载持久化状态（切片交接：游标前不进内存）──
        self._summary, self._summarized_until = store.load_summary()
        self._history = normalize_history(
            store.load_messages(from_index=self._summarized_until)
        )

        # ── 运行态 ──
        self._anchor: Optional[Message] = None  # 本轮 user_input
        self._trail: List[Message] = []  # 本轮运行轨迹
        self._compressing = False  # 压缩防重入（render 串行，防御性）

    # ── BaseMemory 协议 ─────────────────────────────────

    def append(self, message: Message) -> None:
        """锚点未设时第一条即本轮任务（锚定）；之后全部进轨迹段。"""
        if self._anchor is None:
            self._anchor = message
        else:
            self._trail.append(message)

    async def render(
        self, ctx: Any, token_budget: Optional[int] = None
    ) -> List[Message]:
        """产出 history 段：[历史·按需压缩/兜底裁剪] + [锚点] + [轨迹]。

        压缩触发（懒压缩，见模块文档）：
        1. 历史段超过 ``window`` → 压掉窗口外增量；
        2. token 预算装不下历史段 → 压缩腾预算。
        压缩不可用（无 LLM / 失败 / 已到保底）才退回纯裁剪。
        """
        history = self._history

        # ── 懒压缩 1：撞窗 ──
        if len(history) > self._window:
            history = await self._compress_to(self._recent_keep, ctx) or history

        # ── 懒压缩 2：预算紧张 ──
        if token_budget and token_budget > 0 and history:
            rigid = ([self._anchor] if self._anchor else []) + self._trail
            budget = token_budget - estimate_tokens(rigid)
            if budget <= 0:
                # 刚性段已占满：历史压到保底再裁（锚点/轨迹刚性不动）
                history = await self._compress_to(2, ctx) or history
                if len(history) > 2:
                    history = safe_cut(history, 2)
                logger.warning("[SessionMemory] 刚性段已占满 token 预算，历史段仅保底")
            elif estimate_tokens(history) > budget and len(history) > self._recent_keep:
                # 历史超预算且还有压缩空间：压到保留量，再走折半收缩
                history = await self._compress_to(self._recent_keep, ctx) or history

        # ── 兜底裁剪（压缩不可用时的最终防线）──
        if len(history) > self._window:
            history = safe_cut(history, self._window)

        # ── 预算折半收缩（只作用历史段）──
        if token_budget and token_budget > 0 and history:
            rigid = ([self._anchor] if self._anchor else []) + self._trail
            budget = token_budget - estimate_tokens(rigid)
            if 0 < budget:
                while len(history) > 2 and estimate_tokens(history) > budget:
                    keep = max(2, len(history) // 2)
                    shrunk = safe_cut(history, keep)
                    if len(shrunk) >= len(history):
                        break
                    history = shrunk

        out: List[Message] = list(history)
        if self._anchor is not None:
            out.append(self._anchor)
        out.extend(self._trail)
        return out

    def all_messages(self) -> List[Message]:
        """全量消息（历史 + 锚点 + 轨迹），供持久化与调试。"""
        out = list(self._history)
        if self._anchor is not None:
            out.append(self._anchor)
        out.extend(self._trail)
        return out

    def clear(self) -> None:
        self._history.clear()
        self._anchor = None
        self._trail.clear()

    # ── 摘要呈现（assemble._merge_summary 鸭子探测）─────────

    @property
    def summary(self) -> str:
        """当前摘要文本。装配层在 render 之后合并 → 压缩当轮即可见。"""
        return self._summary

    @property
    def summarized_until(self) -> int:
        """摘要已覆盖到的消息索引（绝对游标，基于 store 全量口径）。"""
        return self._summarized_until

    # ── 懒压缩 ───────────────────────────────────────────

    async def _compress_to(self, keep: int, ctx: Any) -> Optional[List[Message]]:
        """把历史段压缩到保留最近 ``keep`` 条。

        - 压掉 ``history[:-keep]`` 增量：LLM 合并进既有摘要；
        - 成功：写 store（summary + 绝对游标，DB 失败仅告警）、收缩内存
          历史段，返回收缩后的列表；
        - 不满足条件 / 失败 / 防重入：返回 None（调用方退回裁剪兜底）。
        """
        if self._llm is None or self._compressing:
            return None
        pending_count = len(self._history) - len(safe_cut(self._history, keep))
        if pending_count <= 0:
            return None

        self._compressing = True
        try:
            pending = self._history[:pending_count]
            convo = _format_for_summary(pending)
            if not convo.strip():
                # 无可压内容（如全空消息）：仅推进游标语义上无意义，放弃
                return None

            ctx.checkpoint()
            response = await ctx.wait(
                self._llm.async_think(
                    messages=[
                        {"role": "system", "content": _SUMMARY_SYS_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"## 既有摘要\n{self._summary or '（无）'}\n\n"
                                f"## 新增对话\n{convo}"
                            ),
                        },
                    ]
                )
            )
            ctx.budget.add_tokens((response.usage or {}).get("total_tokens", 0))
            if ctx.budget.credits_fn is not None:
                ctx.budget.add_credits(
                    ctx.budget.credits_fn(self._llm.model_name, response.usage)
                )
            ctx.checkpoint()
            if response.is_error or not (response.content or "").strip():
                logger.warning("[SessionMemory] 懒压缩生成失败，退回裁剪兜底")
                return None

            new_summary = response.content.strip()
            new_until = self._summarized_until + pending_count
            try:
                self._store.save_summary(new_summary, new_until)
            except Exception:  # pylint: disable=broad-except
                # 写库失败：内存照常推进，崩溃重启后最多重复压缩一次（幂等）
                logger.warning("[SessionMemory] 摘要写库失败（内存游标照常推进）")

            self._summary = new_summary
            self._summarized_until = new_until
            self._history = self._history[pending_count:]
            logger.info(
                "[SessionMemory] 懒压缩 keep=%d until=%d summary=%dch",
                keep,
                new_until,
                len(new_summary),
            )
            return list(self._history)
        except AgentRunError:
            raise
        except Exception:  # pylint: disable=broad-except
            logger.warning("[SessionMemory] 懒压缩异常，退回裁剪兜底", exc_info=True)
            return None
        finally:
            self._compressing = False

    def __repr__(self) -> str:
        return (
            f"<SessionMemory history={len(self._history)} "
            f"anchor={self._anchor is not None} trail={len(self._trail)} "
            f"until={self._summarized_until}>"
        )


__all__ = ["SessionMemory"]
