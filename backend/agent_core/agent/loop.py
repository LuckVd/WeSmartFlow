"""工具调用循环 — 框架唯一的 ReAct 循环实现。

改造前 ``ReActAgent`` 里有三份几乎相同的循环（``_run`` / ``_async_run`` /
``async_stream``），合计约 300 行。三份实现已经出现**行为分叉**：同步/异步
路径把工具 hook 的 ``index`` 硬编码为 0，而流式路径传真实序号——依赖 index
做顺序插槽的业务逻辑在非流式路径下会静默丢数据。

本模块把循环收敛为一份**流式实现**（流式是超集），同步/异步入口通过消费
它并只取终态来实现。一份逻辑，三个入口，行为必然一致。

同时在循环骨架里内建了此前完全缺失的能力：
- 每步检查取消信号与预算（``ctx.checkpoint()``）
- token 消耗累加进预算
- 工具序号由 ``ctx.next_tool_indices()`` 统一分配（不再挂在 LLM 上）
- 业务事件经 ``ctx.emit`` 有序并入事件流（不再需要业务侧手工 flush 队列）
- 每次 LLM 调用与工具执行都产生 trace span
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from ..context.assemble import assemble
from ..llm.base import (
    BaseLLM,
    LLMResponse,
    StreamChunkEvent,
    StreamFinishEvent,
    ToolCallDeltaEvent,
)
from ..memory.base import BaseMemory, Message
from ..runtime.budget import BudgetExceeded, CancelledByCaller
from ..runtime.run_context import RunContext
from ..runtime.trace import SPAN_LLM, SPAN_TOOL
from ..tool.registry import ToolRegistry
from .events import (
    AgentFinalEvent,
    AgentFinishReason,
    AgentStreamEvent,
    AgentThinkChunkEvent,
    AgentThinkEvent,
    AgentToolCallChunkEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    extract_event_text,
)
from .history import assistant_message as _assistant_message
from .history import tool_message as _tool_message

logger = logging.getLogger(__name__)

#: 构建 system prompt 的回调。每步调用一次，允许动态内容（如按需注入画像）。
#: 返回 None 表示本次不带 system 消息。
SystemPromptFn = Callable[[RunContext], Awaitable[Optional[str]]]

#: 工具结果落库前的钩子，供子类插入额外逻辑（保留 ReActAgent 的扩展点语义）。
ToolResultCallback = Callable[
    [str, Dict[str, Any], str, List[Message]], Awaitable[None]
]


async def tool_calling_loop(
    *,
    llm: BaseLLM,
    tools: ToolRegistry,
    ctx: RunContext,
    memory: BaseMemory,
    system_prompt: SystemPromptFn,
    llm_config: Optional[Dict[str, Any]] = None,
    on_tool_result: Optional[ToolResultCallback] = None,
    context_window: Optional[int] = None,
) -> AsyncGenerator[AgentStreamEvent, None]:
    """执行循环，并把组装、推理阶段的预算/取消中止转为统一终态。"""
    try:
        async for event in _tool_calling_loop(
            llm=llm,
            tools=tools,
            ctx=ctx,
            memory=memory,
            system_prompt=system_prompt,
            llm_config=llm_config,
            on_tool_result=on_tool_result,
            context_window=context_window,
        ):
            yield event
    except (CancelledByCaller, BudgetExceeded) as exc:
        yield _abort_event(exc)


def _abort_event(exc: Exception) -> AgentFinalEvent:
    if isinstance(exc, CancelledByCaller):
        reason = AgentFinishReason.CANCELLED
    elif isinstance(exc, BudgetExceeded) and exc.limit_name == "max_steps":
        reason = AgentFinishReason.MAX_STEPS
    else:
        reason = AgentFinishReason.BUDGET
    return AgentFinalEvent(content="", finish_reason=reason, detail=str(exc))


async def _stream_with_deadline(stream, ctx: RunContext):
    try:
        while True:
            try:
                event = await ctx.wait(stream.__anext__())
            except StopAsyncIteration:
                return
            yield event
    finally:
        await stream.aclose()


async def _tool_calling_loop(
    *,
    llm: BaseLLM,
    tools: ToolRegistry,
    ctx: RunContext,
    memory: BaseMemory,
    system_prompt: SystemPromptFn,
    llm_config: Optional[Dict[str, Any]] = None,
    on_tool_result: Optional[ToolResultCallback] = None,
    context_window: Optional[int] = None,
) -> AsyncGenerator[AgentStreamEvent, None]:
    """执行 ReAct 工具调用循环，逐事件 yield。

    循环结构::

        loop:
            ctx.checkpoint()                  # 取消 / 预算检查
            messages = assemble(system, memory, tools)
            response = llm.stream_think(messages, tools)
            memory.append(assistant)
            if not response.has_tool_calls:
                yield AgentFinalEvent; return
            并行执行工具 → yield 过程事件 → memory.append(tool results)

    Args:
        llm:           LLM 实例。
        tools:         工具注册表。
        ctx:           运行上下文，承载预算、取消、追踪、事件出口。
        memory:        对话记忆，负责在预算内产出 history。
        system_prompt: 每步构建 system prompt 的异步回调。
        llm_config:    透传给 LLM 的额外参数。
        on_tool_result: 每个工具结果写入 history 后的回调（子类扩展点）。
        context_window: 模型上下文窗口（token）。传入时装配层会扣除 system
                        与 tool schema 的开销，把剩余预算下发给 memory。

    Yields:
        :data:`AgentStreamEvent`
    """
    tool_defs = tools.get_definitions() or None
    step = 0

    while True:
        # ── 步进与检查点 ─────────────────────────────────────────
        step += 1
        try:
            ctx.checkpoint()
            if (
                ctx.budget.max_steps is not None
                and ctx.budget.steps >= ctx.budget.max_steps
            ):
                raise BudgetExceeded(
                    "max_steps", f"已达到推理步数上限 {ctx.budget.max_steps}"
                )
        except CancelledByCaller as e:
            logger.info("[Loop] 运行被取消于 step %d: %s", step, e)
            yield AgentFinalEvent(
                content="", finish_reason=AgentFinishReason.CANCELLED, detail=str(e)
            )
            return
        except BudgetExceeded as e:
            logger.warning("[Loop] 预算超限于 step %d: %s", step, e)
            reason = (
                AgentFinishReason.MAX_STEPS
                if e.limit_name == "max_steps"
                else AgentFinishReason.BUDGET
            )
            yield AgentFinalEvent(content="", finish_reason=reason, detail=str(e))
            return

        # ── 组装 messages（唯一入口：context.assemble）────────────
        messages = await assemble(
            system_prompt=await system_prompt(ctx) or "",
            memory=memory,
            ctx=ctx,
            tool_schemas=tool_defs,
            context_window=context_window,
        )
        ctx.checkpoint()
        # 父子循环共享累计值；局部 step 仅用于事件展示。
        if (
            ctx.budget.max_steps is not None
            and ctx.budget.steps >= ctx.budget.max_steps
        ):
            raise BudgetExceeded(
                "max_steps", f"已达到推理步数上限 {ctx.budget.max_steps}"
            )
        ctx.budget.steps += 1

        # ── LLM 推理（流式）─────────────────────────────────────
        response: Optional[LLMResponse] = None
        with ctx.tracer.span(
            "llm.think", SPAN_LLM, step=step, model=llm.model_name
        ) as span:
            async for event in _stream_with_deadline(
                llm.stream_think(
                    messages,
                    tools=tool_defs,
                    tool_choice="auto" if tool_defs else None,
                    config=llm_config or None,
                ),
                ctx,
            ):
                if isinstance(event, StreamChunkEvent):
                    yield AgentThinkChunkEvent(
                        delta=event.delta, content=event.content, step=step
                    )
                elif isinstance(event, ToolCallDeltaEvent):
                    yield AgentToolCallChunkEvent(
                        index=event.index,
                        id=event.id,
                        tool_name=event.name,
                        arguments_delta=event.arguments_delta,
                        arguments_so_far=event.arguments_so_far,
                        step=step,
                    )
                elif isinstance(event, StreamFinishEvent):
                    response = event.response
                    used = (response.usage or {}).get("total_tokens", 0)
                    ctx.budget.add_tokens(used)
                    if ctx.budget.credits_fn is not None:
                        ctx.budget.add_credits(
                            ctx.budget.credits_fn(llm.model_name, response.usage)
                        )
                    span.set(tokens=used, tool_calls=len(response.tool_calls))

        ctx.checkpoint()

        # ── 错误处理 ────────────────────────────────────────────
        if (
            response is None
            or response.is_error
            or response.finish_reason
            in {"length", "content_filter", "error", "aborted"}
        ):
            error_msg = (
                response.metadata.get(
                    "error_message", f"模型响应未完整完成：{response.finish_reason}"
                )
                if response
                else "流式调用异常"
            )
            logger.error("[Loop] LLM 错误于 step %d: %s", step, error_msg)
            yield AgentFinalEvent(
                content=f"[Error] {error_msg}",
                finish_reason=AgentFinishReason.ERROR,
                detail=error_msg,
            )
            return

        # ── 本轮思考汇总 ────────────────────────────────────────
        if response.content:
            logger.debug("[Loop] step %d Thought: %s", step, response.content[:200])
            yield AgentThinkEvent(content=response.content, step=step)

        ctx.checkpoint()
        memory.append(_assistant_message(response))

        # ── 无工具调用 → 终态 ───────────────────────────────────
        if not response.has_tool_calls:
            logger.debug("[Loop] 完成，共 %d 步", step)
            yield AgentFinalEvent(
                content=response.content, finish_reason=AgentFinishReason.STOP
            )
            return

        # ── 宣告即将调用的工具 ──────────────────────────────────
        for tc in response.tool_calls:
            yield AgentToolCallEvent(
                id=tc.id,
                tool_name=tc.name,
                arguments=tc.arguments,
                step=step,
                index=tc.index,
            )
            logger.debug("[Loop] Action: %s(%s)", tc.name, tc.arguments)

        # ── 并行执行工具 ────────────────────────────────────────
        # 全局序号由 ctx 统一分配：本轮第 i 个工具 = base + i。
        # 这取代了原先 `llm.tool_call_count` 的做法——循环状态不该挂在
        # LLM 实例上，否则复用 LLM 客户端时并发 Agent 会互相污染。
        base_index = ctx.next_tool_indices(len(response.tool_calls))

        results: Dict[str, Any] = {}
        aborted = None
        try:
            async for event in _run_tools_parallel(
                tools=tools,
                ctx=ctx,
                tool_calls=response.tool_calls,
                step=step,
                base_index=base_index,
                results=results,
            ):
                yield event
        except (CancelledByCaller, BudgetExceeded) as e:
            aborted = e

        # ── 工具结果按原始顺序写入 history ──────────────────────
        observations = []
        for tc in response.tool_calls:
            result = results.get(
                tc.id, f"Error: 工具调用中止，未获得结果：{aborted}" if aborted else ""
            )
            result_str = extract_event_text(result)
            logger.debug("[Loop] Observation[%s]: %s", tc.name, result_str[:200])
            memory.append(
                _tool_message(
                    tc.id, tc.name, result if isinstance(result, list) else result_str
                )
            )
            observations.append((tc, result_str))
        if aborted:
            yield _abort_event(aborted)
            return
        # 先完整写入整批配对，再执行可能抛出中止异常的扩展回调。
        if on_tool_result is not None:
            for tc, result_str in observations:
                await on_tool_result(
                    tc.name, tc.arguments, result_str, memory.all_messages()
                )


async def _run_tools_parallel(
    *,
    tools: ToolRegistry,
    ctx: RunContext,
    tool_calls: List[Any],
    step: int,
    base_index: int,
    results: Dict[str, Any],
) -> AsyncGenerator[AgentStreamEvent, None]:
    """并行流式执行本轮所有工具，按到达顺序 yield 事件。

    用 Queue 汇聚多个生成器：每个工具在独立 task 中执行，事件推入队列，
    主协程按到达顺序消费——这样慢工具不会阻塞快工具的过程事件。

    业务事件（``DomainEvent`` 及遗留三类）与过程事件走同一队列，因此顺序
    由框架保证；业务侧不再需要维护旁路队列并手工 flush。

    Args:
        results: 出参，收集每个 tool_call 的最终结果（键为 tool_call id）。
    """
    _DONE = object()
    queue: asyncio.Queue = asyncio.Queue()
    aborted: List[BaseException] = []

    async def _run_one(tc: Any, global_index: int) -> None:
        try:
            with ctx.tracer.span(
                f"tool.{tc.name}", SPAN_TOOL, step=step, index=global_index
            ):
                async for run_event in tools.async_stream_execute(
                    tc.id, tc.name, tc.arguments, step, global_index, ctx=ctx
                ):
                    await queue.put(run_event)
        except (CancelledByCaller, BudgetExceeded) as e:
            # 可预期中止：记录后由外层统一转为终态事件
            aborted.append(e)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("[Loop] 工具 %s 执行异常", tc.name)
            await queue.put(
                AgentToolResultEvent(
                    id=tc.id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    step=step,
                    result=f"Error: 工具 {tc.name} 执行失败: {e}",
                    index=global_index,
                )
            )
        finally:
            await queue.put(_DONE)

    tasks = [
        asyncio.create_task(_run_one(tc, base_index + i))
        for i, tc in enumerate(tool_calls)
    ]
    pending = len(tasks)

    try:
        while pending > 0:
            item = await ctx.wait(queue.get())
            if item is _DONE:
                pending -= 1
                continue
            if isinstance(item, AgentToolResultEvent):
                results[item.id] = item.result
            yield item
    finally:
        # 调用方提前退出（如 SSE 断开）时取消未完成的工具 task，避免泄漏
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if aborted:
        raise aborted[0]


__all__ = [
    "SystemPromptFn",
    "ToolResultCallback",
    "tool_calling_loop",
]
