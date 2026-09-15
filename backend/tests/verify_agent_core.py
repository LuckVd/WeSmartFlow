"""agent_core 改造后的行为验证。

覆盖本轮重构的关键改动：
1. 三个入口（run / async_run / async_stream）行为一致，工具 index 正确传递
2. 工具 index 跨轮次单调递增，且不再依赖 LLM 实例状态
3. hook 返回的业务事件被有序并入事件流
4. 预算超限、调用方取消能正确中止循环
5. 记忆截断不破坏 tool_calls 配对
6. 子 Agent 与父 Agent 共享预算

运行::

    python backend/tests/verify_agent_core.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.agent import AgentFinishReason, ReActAgent
from agent_core.agent.events import (
    AgentFinalEvent,
    AgentToolResultEvent,
)
from agent_core.llm.base import (
    BaseLLM,
    LLMResponse,
    StreamChunkEvent,
    StreamFinishEvent,
    ToolCallRequest,
)
from agent_core.memory import (
    FullMemory,
    WindowMemory,
    is_pair_complete,
    safe_cut,
)
from agent_core.runtime import (
    Budget,
    DomainEvent,
    MemoryTracer,
    collect_events,
    new_context,
)
from agent_core.tool.base import BaseTool
from agent_core.tool.registry import ToolRegistry

PASS, FAIL = "  ok  ", " FAIL "
_failures: List[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"[{PASS if cond else FAIL}] {label}" + (f"  → {extra}" if extra else ""))
    if not cond:
        _failures.append(label)


# ======================================================================
# 测试替身
# ======================================================================


class ScriptedLLM(BaseLLM):
    """按脚本逐轮返回预设响应的假 LLM。"""

    def __init__(self, script: List[LLMResponse]):
        super().__init__(model_name="scripted")
        self.script = script
        self.calls = 0

    def think(self, messages, tools=None, tool_choice=None, config=None):
        idx = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return self.script[idx]

    async def async_think(self, messages, tools=None, tool_choice=None, config=None):
        return self.think(messages, tools, tool_choice, config)

    async def stream_think(self, messages, tools=None, tool_choice=None, config=None):
        resp = self.think(messages, tools, tool_choice, config)
        if resp.content:
            yield StreamChunkEvent(delta=resp.content, content=resp.content)
        yield StreamFinishEvent(response=resp)


class RecordingTool(BaseTool):
    """记录每次调用收到的 index，并通过 hook 返回业务事件。"""

    name = "record"
    description = "记录调用序号"
    parameters = {
        "type": "object",
        "properties": {"tag": {"type": "string", "description": "标记"}},
        "required": ["tag"],
    }

    def __init__(self, **kw):
        self.seen_indices: List[int] = []
        super().__init__(**kw)

    def hook(self, tool_name: str, params: Dict[str, Any], result: Any, index: int):
        """供 ToolRegistry.register(on_result=...) 绑定的结果 hook。"""
        self.seen_indices.append(index)
        return DomainEvent("recorded", {"tag": params.get("tag"), "index": index})

    def run(self, tag: str = "", **kw) -> str:
        return f"done:{tag}"


def tc(call_id: str, tag: str, index: int) -> ToolCallRequest:
    return ToolCallRequest(
        id=call_id, name="record", arguments={"tag": tag}, index=index
    )


def two_round_script() -> List[LLMResponse]:
    """第一轮 2 个并行工具，第二轮 1 个工具，第三轮收尾。"""
    return [
        LLMResponse(content="T1", tool_calls=[tc("a", "A", 0), tc("b", "B", 1)]),
        LLMResponse(content="T2", tool_calls=[tc("c", "C", 0)]),
        LLMResponse(content="最终答案"),
    ]


# ======================================================================
# 1. 三入口一致性 + index 正确传递
# ======================================================================


async def test_three_entries_consistent() -> None:
    print("\n── 1. 三个入口行为一致 + 工具 index 跨轮递增 ──")

    # --- async_stream ---
    tool_s = RecordingTool()
    agent_s = ReActAgent(
        llm=ScriptedLLM(two_round_script()),
        tool_registry=ToolRegistry([tool_s], on_result=tool_s.hook),
    )
    events = [e async for e in agent_s.async_stream("go")]
    final_s = [e for e in events if isinstance(e, AgentFinalEvent)]

    # --- async_run ---
    tool_a = RecordingTool()
    agent_a = ReActAgent(
        llm=ScriptedLLM(two_round_script()),
        tool_registry=ToolRegistry([tool_a], on_result=tool_a.hook),
    )
    result_a = await agent_a.async_run("go")

    # --- run（同步）---
    tool_r = RecordingTool()
    agent_r = ReActAgent(
        llm=ScriptedLLM(two_round_script()),
        tool_registry=ToolRegistry([tool_r], on_result=tool_r.hook),
    )
    result_r = await asyncio.to_thread(agent_r.run, "go")

    check(
        "async_stream 产出终态 AgentFinalEvent",
        len(final_s) == 1 and final_s[0].finish_reason is AgentFinishReason.STOP,
    )
    check("async_run 正常完成", result_a.ok, result_a.output)
    check("run（同步）正常完成", result_r.ok, result_r.output)
    check(
        "三入口最终输出一致",
        final_s[0].content == result_a.output == result_r.output == "最终答案",
    )

    # 关键回归：改造前同步/异步路径把 index 硬编码为 0
    expect = [0, 1, 2]
    check(
        "async_stream 的 index 跨轮递增",
        sorted(tool_s.seen_indices) == expect,
        str(sorted(tool_s.seen_indices)),
    )
    check(
        "async_run 的 index 跨轮递增（改造前为 [0,0,0]）",
        sorted(tool_a.seen_indices) == expect,
        str(sorted(tool_a.seen_indices)),
    )
    check(
        "run 的 index 跨轮递增（改造前为 [0,0,0]）",
        sorted(tool_r.seen_indices) == expect,
        str(sorted(tool_r.seen_indices)),
    )


# ======================================================================
# 2. 业务事件有序并入事件流
# ======================================================================


async def test_domain_events() -> None:
    print("\n── 2. 业务事件并入事件流 ──")

    bucket, emit = collect_events()
    ctx = new_context(emit=emit, scope="test")
    tool = RecordingTool()
    agent = ReActAgent(
        llm=ScriptedLLM(two_round_script()),
        tool_registry=ToolRegistry([tool], on_result=tool.hook),
    )

    stream: List[Any] = [e async for e in agent.async_stream("go", ctx=ctx)]
    domain_in_stream = [e for e in stream if isinstance(e, DomainEvent)]

    check(
        "业务事件出现在事件流中",
        len(domain_in_stream) == 3,
        f"{len(domain_in_stream)} 个",
    )
    # 业务事件只走事件流这一条路。ctx.emit 原本是并行的第二条通道，
    # 但生产代码从不传 emit（全部落到 _noop_emit），已移除以避免双轨误导。
    check(
        "业务事件不再走 ctx.emit 旁路",
        len(bucket) == 0,
        f"{len(bucket)} 个",
    )
    check(
        "业务事件自动填充 source",
        all(e.source == "record" for e in domain_in_stream),
    )

    # 顺序验证：每个 DomainEvent 必须在对应的 ToolResultEvent 之前
    kinds = [
        "domain"
        if isinstance(e, DomainEvent)
        else "result"
        if isinstance(e, AgentToolResultEvent)
        else None
        for e in stream
    ]
    seq = [k for k in kinds if k]
    pairs_ok = all(
        seq[i] == "domain" and seq[i + 1] == "result" for i in range(0, len(seq), 2)
    )
    check("业务事件紧邻其工具结果之前（顺序由框架保证）", pairs_ok, str(seq))


# ======================================================================
# 3. 预算与取消
# ======================================================================


async def test_budget_and_cancel() -> None:
    print("\n── 3. 预算超限与调用方取消 ──")

    # 无限循环脚本：永远返回工具调用
    endless = [LLMResponse(content="loop", tool_calls=[tc("x", "X", 0)])]

    # --- max_steps ---
    ctx = new_context(budget=Budget(max_steps=3))
    agent = ReActAgent(
        llm=ScriptedLLM(endless), tool_registry=ToolRegistry([RecordingTool()])
    )
    finals = [
        e
        async for e in agent.async_stream("go", ctx=ctx)
        if isinstance(e, AgentFinalEvent)
    ]
    check(
        "max_steps 触发后循环中止",
        len(finals) == 1 and finals[0].finish_reason is AgentFinishReason.MAX_STEPS,
        finals[0].detail if finals else "无终态",
    )

    # --- deadline ---
    ctx2 = new_context(budget=Budget(max_steps=100, deadline=0.0))
    agent2 = ReActAgent(
        llm=ScriptedLLM(endless), tool_registry=ToolRegistry([RecordingTool()])
    )
    finals2 = [
        e
        async for e in agent2.async_stream("go", ctx=ctx2)
        if isinstance(e, AgentFinalEvent)
    ]
    check(
        "deadline 触发后循环中止",
        len(finals2) == 1 and finals2[0].finish_reason is AgentFinishReason.BUDGET,
        finals2[0].detail if finals2 else "无终态",
    )

    # --- 取消 ---
    state = {"n": 0}

    def cancelled() -> bool:
        state["n"] += 1
        return state["n"] > 2  # 第 3 次检查时取消

    ctx3 = new_context(budget=Budget(max_steps=100), is_cancelled=cancelled)
    agent3 = ReActAgent(
        llm=ScriptedLLM(endless), tool_registry=ToolRegistry([RecordingTool()])
    )
    finals3 = [
        e
        async for e in agent3.async_stream("go", ctx=ctx3)
        if isinstance(e, AgentFinalEvent)
    ]
    check(
        "调用方取消后循环立即中止（改造前会继续烧 token）",
        len(finals3) == 1 and finals3[0].finish_reason is AgentFinishReason.CANCELLED,
    )

    # --- token 累加 ---
    script = [
        LLMResponse(
            content="a", tool_calls=[tc("x", "X", 0)], usage={"total_tokens": 100}
        ),
        LLMResponse(content="end", usage={"total_tokens": 50}),
    ]
    ctx4 = new_context(budget=Budget(max_steps=10))
    agent4 = ReActAgent(
        llm=ScriptedLLM(script), tool_registry=ToolRegistry([RecordingTool()])
    )
    await agent4.async_run("go", ctx=ctx4)
    check("token 消耗累加进预算", ctx4.budget.tokens == 150, str(ctx4.budget.tokens))
    check(
        "工具调用计数累加进预算",
        ctx4.budget.tool_calls == 1,
        str(ctx4.budget.tool_calls),
    )


# ======================================================================
# 4. 记忆截断安全
# ======================================================================


def test_memory_safety() -> None:
    print("\n── 4. 记忆截断不破坏 tool_calls 配对 ──")

    msgs = [
        {"role": "user", "content": "q1"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "t1",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "t1", "name": "f", "content": "r1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "t2",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "t2", "name": "f", "content": "r2"},
        {"role": "assistant", "content": "a2"},
    ]

    check("完整列表配对合法", is_pair_complete(msgs))

    # 逐个切点验证：任何 keep 值都不应产生非法配对
    bad: List[int] = []
    for keep in range(1, len(msgs) + 1):
        cut = safe_cut(msgs, keep)
        if cut and cut[0].get("role") == "tool":
            bad.append(keep)
        elif not is_pair_complete(cut):
            bad.append(keep)
    check(
        "所有切点均产出合法配对（否则 API 报 400）",
        not bad,
        f"非法切点 keep={bad}" if bad else "",
    )


async def test_window_memory() -> None:
    print("\n── 5. WindowMemory 生效 ──")

    mem = WindowMemory(window=4)
    for i in range(20):
        mem.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"})

    ctx = new_context()
    rendered = await mem.render(ctx)
    check("render 结果被裁剪", len(rendered) <= 6, f"{len(rendered)} 条")
    check("all_messages 保留全量", len(mem.all_messages()) == 20)

    full = FullMemory()
    for i in range(20):
        full.append({"role": "user", "content": f"m{i}"})
    check("FullMemory 不裁剪（向后兼容）", len(await full.render(ctx)) == 20)


# ======================================================================
# 6. 子 Agent 共享预算 + trace
# ======================================================================


async def test_sub_agent_and_trace() -> None:
    print("\n── 6. 子 Agent 共享预算 + trace span 树 ──")

    sub = ReActAgent(
        llm=ScriptedLLM([LLMResponse(content="子答案", usage={"total_tokens": 30})]),
        tool_registry=ToolRegistry(),
    )
    sub_tool = sub.as_tool(name="helper", description="子 Agent")

    parent_script = [
        LLMResponse(
            content="委派",
            tool_calls=[
                ToolCallRequest(
                    id="s1", name="helper", arguments={"input": "帮忙"}, index=0
                )
            ],
            usage={"total_tokens": 70},
        ),
        LLMResponse(content="父答案", usage={"total_tokens": 20}),
    ]
    parent = ReActAgent(
        llm=ScriptedLLM(parent_script), tool_registry=ToolRegistry([sub_tool])
    )

    tracer = MemoryTracer()
    ctx = new_context(budget=Budget(max_steps=10), tracer=tracer, scope="parent")
    result = await parent.async_run("开始", ctx=ctx)

    check("父 Agent 正常完成", result.ok, result.output)
    check(
        "子 Agent token 计入父预算（70+20+30）",
        ctx.budget.tokens == 120,
        str(ctx.budget.tokens),
    )

    spans = tracer.export()
    llm_spans = [s for s in spans if s["kind"] == "llm"]
    tool_spans = [s for s in spans if s["kind"] == "tool"]
    check("trace 记录了 LLM span", len(llm_spans) == 3, f"{len(llm_spans)} 个")
    check("trace 记录了工具 span", len(tool_spans) == 1)
    check(
        "span 具备父子关系（可重建调用树）",
        any(s["parent_id"] for s in spans),
    )
    print("\n     调用树:")
    for line in tracer.render_tree().splitlines():
        print(f"       {line}")

    # 预算超限应中止子 Agent
    ctx_tight = new_context(budget=Budget(max_steps=10, max_tokens=50))
    parent2 = ReActAgent(
        llm=ScriptedLLM(
            [
                LLMResponse(
                    content="x",
                    tool_calls=[tc("y", "Y", 0)],
                    usage={"total_tokens": 60},
                ),
                LLMResponse(content="end"),
            ]
        ),
        tool_registry=ToolRegistry([RecordingTool()]),
    )
    r2 = await parent2.async_run("go", ctx=ctx_tight)
    check(
        "max_tokens 超限中止运行",
        r2.finish_reason is AgentFinishReason.BUDGET,
        f"{r2.finish_reason.value} / {r2.error}",
    )


# ======================================================================
# 7. 无 ctx 调用保持向后兼容
# ======================================================================


async def test_backward_compat() -> None:
    print("\n── 7. 不传 ctx 时保持原有行为 ──")

    tool = RecordingTool()
    agent = ReActAgent(
        llm=ScriptedLLM(two_round_script()),
        tool_registry=ToolRegistry([tool]),
        max_steps=5,
    )
    result = await agent.async_run("go")
    check("不传 ctx 也能正常运行", result.ok, result.output)

    events = [
        e
        async for e in ReActAgent(
            llm=ScriptedLLM(two_round_script()),
            tool_registry=ToolRegistry([RecordingTool()]),
        ).async_stream("go")
    ]
    check(
        "不传 ctx 的流式调用正常", any(isinstance(e, AgentFinalEvent) for e in events)
    )

    # max_steps 通过构造参数生效
    endless = [LLMResponse(content="loop", tool_calls=[tc("x", "X", 0)])]
    agent2 = ReActAgent(
        llm=ScriptedLLM(endless),
        tool_registry=ToolRegistry([RecordingTool()]),
        max_steps=2,
    )
    r2 = await agent2.async_run("go")
    check(
        "构造参数 max_steps 仍然生效",
        r2.finish_reason is AgentFinishReason.MAX_STEPS,
        r2.finish_reason.value,
    )


# ======================================================================
# 8. 框架层零业务依赖
# ======================================================================


def test_no_business_import() -> None:
    print("\n── 8. runtime / memory 不依赖业务模块 ──")

    import subprocess

    code = (
        "import sys; "
        "sys.modules['config'] = None; "
        "import agent_core.runtime, agent_core.memory; "
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    check(
        "runtime/memory 在 config 不可用时仍可导入",
        proc.returncode == 0 and "ok" in proc.stdout,
        proc.stderr.strip().splitlines()[-1] if proc.returncode else "",
    )


# ======================================================================
# 入口
# ======================================================================


async def main() -> int:
    print("=" * 68)
    print("agent_core 改造验证")
    print("=" * 68)

    await test_three_entries_consistent()
    await test_domain_events()
    await test_budget_and_cancel()
    test_memory_safety()
    await test_window_memory()
    await test_sub_agent_and_trace()
    await test_backward_compat()
    test_no_business_import()

    print("\n" + "=" * 68)
    if _failures:
        print(f"失败 {len(_failures)} 项：")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
