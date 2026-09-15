"""Offline regression checks for agent_core concurrency, budgets, history and recovery."""

import asyncio
import json
import logging
import pathlib
import sys
import tempfile

# Run with: conda run -n agent python backend/tests/verify_agent_core_regressions.py
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent_core.agent.react import ReActAgent
from agent_core.agent.events import (
    AgentFinalEvent,
    AgentFinishReason,
    AgentToolResultEvent,
    extract_event_text,
)
from agent_core.agent.workflow import Workflow, Node, MemoryCheckpointStore
from agent_core.llm.base import BaseLLM, LLMResponse, ToolCallRequest
from agent_core.tool.base import BaseTool
from agent_core.tool.registry import ToolRegistry
from agent_core.tool.agent_tool import AgentTool
from agent_core.tool.filesystem import ReadFileTool
from agent_core.runtime.run_context import new_context
from agent_core.runtime.budget import Budget, BudgetExceeded, CancelledByCaller
from agent_core.memory.base import is_pair_complete
from agent_core.memory.session_memory import SessionMemory
from agent_core.context.assemble import assemble

logging.disable(logging.CRITICAL)


class ScriptedLLM(BaseLLM):
    def __init__(self, responses, delay=0):
        super().__init__("fake")
        self.responses = responses
        self.calls = 0
        self.delay = delay
        self.inputs = []

    def think(self, messages, tools=None, tool_choice=None, config=None):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        self.inputs.append(messages)
        return response

    async def async_think(self, messages, tools=None, tool_choice=None, config=None):
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.think(messages, tools, tool_choice, config)


class RecordingTool(BaseTool):
    name = "record"
    description = "Records calls"
    parameters = {"type": "object", "properties": {}}

    def __init__(self):
        super().__init__()
        self.calls = 0

    def run(self, **kwargs):
        self.calls += 1
        return "written"


def call(name="record", tcid="c1", args=None):
    return ToolCallRequest(tcid, name, args or {})


def report(case, **data):
    print(json.dumps({"case": case, **data}, ensure_ascii=False))


async def main():
    tool = RecordingTool()
    model = ScriptedLLM(
        [LLMResponse("", [call()], finish_reason="length"), LLMResponse("done")]
    )
    result = await ReActAgent(model, tool_registry=ToolRegistry([tool])).async_run(
        "write"
    )
    assert tool.calls == 0 and result.finish_reason == AgentFinishReason.ERROR
    report(
        "truncated_response_rejected",
        executions=tool.calls,
        finish=result.finish_reason.value,
    )

    leaf_tool = RecordingTool()
    child_model = ScriptedLLM([LLMResponse("", [call()]), LLMResponse("child done")])
    child = ReActAgent(child_model, tool_registry=ToolRegistry([leaf_tool]))
    parent_model = ScriptedLLM(
        [
            LLMResponse("", [call("child", args={"input": "work"})]),
            LLMResponse("parent done"),
        ]
    )
    parent = ReActAgent(
        parent_model, tool_registry=ToolRegistry([child.as_tool("child", "Child")])
    )
    ctx = new_context(budget=Budget(max_steps=2))
    result = await parent.async_run("work", ctx)
    assert result.finish_reason == AgentFinishReason.MAX_STEPS
    assert child_model.calls + parent_model.calls == ctx.budget.steps == 2
    assert is_pair_complete(result.history)
    report(
        "nested_step_limit_enforced",
        max_steps=2,
        actual_llm_calls=child_model.calls + parent_model.calls,
        recorded_steps=ctx.budget.steps,
        finish=result.finish_reason.value,
    )

    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def before():
        nonlocal count
        count += 1
        if count == 1:
            entered.set()
            await release.wait()

    class ContextEchoAgent:
        async def async_stream(self, user_input, ctx, **kwargs):
            yield AgentFinalEvent(ctx.principal, AgentFinishReason.STOP)

    wrapped = AgentTool(ContextEchoAgent(), "child", "Echo context")
    registry = ToolRegistry([wrapped], before_call=before)

    async def invoke(principal):
        events = [
            e
            async for e in registry.async_stream_execute(
                principal,
                "child",
                {"input": "x"},
                1,
                ctx=new_context(principal=principal),
            )
        ]
        return extract_event_text(
            next(e.result for e in events if isinstance(e, AgentToolResultEvent))
        )

    task_a = asyncio.create_task(invoke("user:A"))
    await entered.wait()
    observed_b = await invoke("user:B")
    release.set()
    observed_a = await task_a
    assert observed_a == "user:A" and observed_b == "user:B"
    assert wrapped._parent_ctx is None
    report(
        "shared_agent_tool_context_isolated",
        caller_a_observes=observed_a,
        caller_b_observes=observed_b,
    )

    with tempfile.TemporaryDirectory(prefix="edu-agent-review-") as directory:
        file = pathlib.Path(directory) / "image.png"
        # ReadFileTool uses the PNG magic bytes to emit image content blocks.
        file.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"test")
        read = ReadFileTool(allowed_dir=pathlib.Path(directory))
        direct = read.run(path=str(file))
        model = ScriptedLLM(
            [
                LLMResponse("", [call("read_file", args={"path": str(file)})]),
                LLMResponse("done"),
            ]
        )
        result = await ReActAgent(model, tool_registry=ToolRegistry([read])).async_run(
            "read image"
        )
        observation = next(m["content"] for m in result.history if m["role"] == "tool")
        assert isinstance(direct, list) and observation == direct
        assert (
            next(m["content"] for m in model.inputs[-1] if m["role"] == "tool")
            == direct
        )
        report(
            "image_blocks_preserved",
            direct_type=type(direct).__name__,
            model_history_type=type(observation).__name__,
        )

    tool = RecordingTool()
    model = ScriptedLLM([LLMResponse("", [call()])])
    ctx = new_context(budget=Budget(max_tool_calls=0))
    result = await ReActAgent(model, tool_registry=ToolRegistry([tool])).async_run(
        "work", ctx
    )
    assert result.finish_reason == AgentFinishReason.BUDGET and is_pair_complete(
        result.history
    )
    assert tool.calls == 0
    report(
        "budget_abort_preserves_pairs",
        finish=result.finish_reason.value,
        roles=[m["role"] for m in result.history],
        complete_pairs=is_pair_complete(result.history),
    )

    class Store:
        def __init__(self, history):
            self.history = history

        def load_summary(self):
            return "", 0

        def load_messages(self, **kwargs):
            return self.history

        def save_summary(self, summary, until):
            pass

    memory = SessionMemory(Store([]))
    memory.append({"role": "user", "content": "inspect"})
    memory.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [call().to_openai_tool_call()],
        }
    )
    memory.append({"role": "tool", "tool_call_id": "c1", "content": "data " * 20000})
    try:
        await assemble("Tutor", memory, new_context(), context_window=8192)
    except BudgetExceeded as exc:
        assert exc.limit_name == "context_window"
    else:
        raise AssertionError("oversized context was accepted")
    model = ScriptedLLM([LLMResponse("done")])
    result = await ReActAgent(model, context_window=8192).async_run(
        "inspect", new_context(memory=memory)
    )
    assert result.finish_reason == AgentFinishReason.BUDGET and model.calls == 0
    report("context_overflow_rejected_before_model", finish=result.finish_reason.value)

    summary_llm = ScriptedLLM([LLMResponse("summary", usage={"total_tokens": 999})])
    memory = SessionMemory(
        Store(
            [
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"message {i}",
                }
                for i in range(30)
            ]
        ),
        llm=summary_llm,
    )
    ctx = new_context(
        budget=Budget(max_tokens=1, max_credits=1, credits_fn=lambda *args: 999)
    )
    try:
        await memory.render(ctx, 1000)
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("summary usage did not stop the run")
    assert summary_llm.calls == 1 and ctx.budget.tokens == ctx.budget.credits == 999
    report(
        "session_summary_metered",
        actual_usage=999,
        budget_tokens=ctx.budget.tokens,
        budget_credits=ctx.budget.credits,
    )

    ctx = new_context(budget=Budget.with_timeout(0.01))
    result = await ReActAgent(ScriptedLLM([LLMResponse("done")], delay=0.05)).async_run(
        "x", ctx
    )
    assert (
        result.finish_reason == AgentFinishReason.BUDGET
        and ctx.budget.exceeded() == "deadline"
    )
    report(
        "deadline_stops_model",
        finish=result.finish_reason.value,
        exceeded=ctx.budget.exceeded(),
    )

    executed = []

    async def fails(inputs, ctx):
        raise RuntimeError("failed")

    async def succeeds(inputs, ctx):
        executed.append("b")
        return {"saved": "yes"}

    workflow = Workflow([Node("a", fails), Node("b", succeeds)])
    store = MemoryCheckpointStore()
    ctx = new_context()
    for _ in range(2):
        _events = [e async for e in workflow.stream({}, ctx, store)]
    saved = await store.load(ctx.run_id)
    assert len(executed) == 1 and saved["b"] == {"saved": "yes"}
    report(
        "workflow_successful_sibling_checkpointed",
        successful_node_executions=len(executed),
        checkpoints=saved,
    )

    # No-tool final responses must still enforce usage limits.
    for limit in ["tokens", "credits"]:
        budget = Budget(**{f"max_{limit}": 1}, credits_fn=lambda *args: 10)
        ctx = new_context(budget=budget)
        model = ScriptedLLM([LLMResponse("done", usage={"total_tokens": 10})])
        result = await ReActAgent(model).async_run("go", ctx)
        assert result.finish_reason == AgentFinishReason.BUDGET
        assert budget.tokens == budget.credits == 10
    report("final_response_usage_limits_enforced")

    # Preserve successful siblings when another tool aborts the same batch.
    for error in [BudgetExceeded("max_tokens"), CancelledByCaller("cancelled")]:
        registry = ToolRegistry([RecordingTool()])

        async def abort():
            await asyncio.sleep(0.02)
            raise error

        aborted_tool = RecordingTool()
        aborted_tool.name = "abort"
        registry.register(aborted_tool, before_call=abort)
        model = ScriptedLLM([LLMResponse("", [call(), call("abort", "c2")])])
        result = await ReActAgent(model, tool_registry=registry).async_run("go")
        assert is_pair_complete(result.history)
        observations = [m["content"] for m in result.history if m["role"] == "tool"]
        assert observations[0] == "written" and "Error:" in observations[1]
        assert aborted_tool.calls == 0
        assert result.finish_reason == (
            AgentFinishReason.BUDGET
            if isinstance(error, BudgetExceeded)
            else AgentFinishReason.CANCELLED
        )
    report("partial_tool_batch_preserves_success_and_pairs")

    # A long-running async tool must not hold the run beyond its deadline.
    stopped = asyncio.Event()

    class SlowTool(RecordingTool):
        async def async_run(self, **kwargs):
            try:
                await asyncio.sleep(60)
            finally:
                stopped.set()

    model = ScriptedLLM([LLMResponse("", [call()])])
    ctx = new_context(budget=Budget.with_timeout(0.1))
    result = await asyncio.wait_for(
        ReActAgent(model, tool_registry=ToolRegistry([SlowTool()])).async_run(
            "go", ctx
        ),
        timeout=2,
    )
    assert stopped.is_set() and result.finish_reason == AgentFinishReason.BUDGET
    assert is_pair_complete(result.history)
    report("tool_deadline_cancels_wait_and_preserves_pairs")

    # Compression cannot silently swallow deadline/cancellation signals.
    history = [{"role": "user", "content": str(i)} for i in range(30)]
    for cancelled in [False, True]:
        memory = SessionMemory(
            Store(history), llm=ScriptedLLM([LLMResponse("summary")], delay=0.05)
        )
        ctx = new_context(
            budget=Budget.with_timeout(0.01), is_cancelled=lambda: cancelled
        )
        try:
            await memory.render(ctx, 1000)
        except (BudgetExceeded, CancelledByCaller):
            pass
        else:
            raise AssertionError("compression swallowed interruption")
        assert memory.summarized_until == 0 and not memory._compressing
    report("summary_interruption_propagated")

    # The new summary itself must be included in the final context check.
    memory = SessionMemory(
        Store(history), llm=ScriptedLLM([LLMResponse("large " * 10000)])
    )
    try:
        await assemble("Tutor", memory, new_context(), context_window=8192)
    except BudgetExceeded as exc:
        assert exc.limit_name == "context_window"
    else:
        raise AssertionError("new summary bypassed context limit")
    report("new_summary_included_in_context_limit")

    # The summary cursor may not cut through a multi-tool response.
    history = [
        {"role": "user", "content": "go"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                call().to_openai_tool_call(),
                call(tcid="c2").to_openai_tool_call(),
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "one"},
        {"role": "tool", "tool_call_id": "c2", "content": "two"},
        {"role": "assistant", "content": "done"},
    ]
    memory = SessionMemory(
        Store(history),
        window=4,
        recent_keep=3,
        llm=ScriptedLLM([LLMResponse("summary")]),
    )
    rendered = await memory.render(new_context())
    assert is_pair_complete(rendered) and memory.summarized_until == 1
    report("summary_cursor_preserves_tool_pairs")


if __name__ == "__main__":
    asyncio.run(main())
