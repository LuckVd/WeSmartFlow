"""Streaming events, terminal-result compatibility and cancellation regressions."""

import asyncio
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.agent.events import (
    AgentThinkChunkEvent,
    AgentToolRunEvent,
    AgentToolResultEvent,
)
from agent_core.llm.base import LLMResponse, StreamChunkEvent, StreamFinishEvent
from agent_core.runtime import new_context
from agent_core.runtime.budget import CancelledByCaller
from agent_core.tool.registry import ToolRegistry
from agents.tools import generate_viz as viz
from agents.tools import viz_runtime as runtime
from test_viz_quality import SPEC, CODE, PASS, fake_llm


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    def setup_tool(self, directory, llm):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(viz, "VIZ_DIR", Path(directory)))
        stack.enter_context(patch.object(viz, "get_llm", return_value=llm))
        stack.enter_context(
            patch.object(
                viz.ValidateVizCodeTool, "environment_error", return_value=None
            )
        )
        stack.enter_context(
            patch.object(viz.ValidateVizCodeTool, "run", return_value="ok")
        )
        stack.enter_context(
            patch.object(
                viz, "async_check_viz_runtime", return_value={"ok": True, "errors": []}
            )
        )
        self.register = stack.enter_context(
            patch.object(viz.GenerateInteractiveVizTool, "_create_document_record")
        )
        return viz.GenerateInteractiveVizTool("user")

    async def test_tokens_arrive_before_generation_finishes_and_registry_gets_only_id(
        self,
    ):
        gate = asyncio.Event()
        llm = fake_llm(json.dumps(SPEC), CODE, PASS)
        original = llm.stream_think.side_effect
        first = True

        async def delayed(*args, **kwargs):
            nonlocal first
            async for event in original(*args, **kwargs):
                yield event
                if first and isinstance(event, StreamChunkEvent):
                    first = False
                    await gate.wait()

        llm.stream_think.side_effect = delayed
        with tempfile.TemporaryDirectory() as tmp:
            tool = self.setup_tool(tmp, llm)
            hook = MagicMock(return_value=None)
            registry = ToolRegistry([tool], on_result=hook)
            ctx = new_context()
            stream = registry.async_stream_execute(
                "call", tool.name, {"title": "斜率", "concept": "概念"}, step=1, ctx=ctx
            )
            seen = []
            async for event in stream:
                seen.append(event)
                if isinstance(event, AgentToolRunEvent) and isinstance(
                    event.content, AgentThinkChunkEvent
                ):
                    break
            self.register.assert_not_called()
            hook.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])
            gate.set()
            seen.extend([event async for event in stream])
            result = seen[-1]
            self.assertIsInstance(result, AgentToolResultEvent)
            self.assertEqual(str(UUID(result.result)), result.result)
            self.assertEqual(hook.call_args.args[2], result.result)
            self.assertEqual(ctx.budget.tokens, 30)
            self.assertEqual(ctx.budget.steps, 3)
            self.assertEqual((Path(tmp) / result.result / "viz.js").read_text(), CODE)
            self.assertTrue(
                any(
                    isinstance(e, AgentToolRunEvent) and "浏览器" in str(e.content)
                    for e in seen
                )
            )
            llm.think.assert_not_called()

    async def test_cancel_during_llm_stream_closes_it_and_publishes_nothing(self):
        waiting = asyncio.Event()
        closed = asyncio.Event()
        llm = MagicMock(model_name="fixture")

        async def stream(*args, **kwargs):
            try:
                yield StreamChunkEvent(delta="partial", content="partial")
                waiting.set()
                await asyncio.Event().wait()
            finally:
                closed.set()

        llm.stream_think.side_effect = stream
        with tempfile.TemporaryDirectory() as tmp:
            tool = self.setup_tool(tmp, llm)

            async def consume():
                return [
                    e async for e in tool.async_stream_run(title="斜率", concept="概念")
                ]

            task = asyncio.create_task(consume())
            await asyncio.wait_for(waiting.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(closed.is_set())
            self.register.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    async def test_truncated_or_missing_model_final_never_becomes_success(self):
        for finish in ("length", None):
            with self.subTest(finish=finish), tempfile.TemporaryDirectory() as tmp:
                llm = MagicMock(model_name="fixture")

                async def stream(*args, **kwargs):
                    yield StreamChunkEvent(delta="partial", content="partial")
                    if finish:
                        yield StreamFinishEvent(
                            response=LLMResponse(
                                content=json.dumps(SPEC), finish_reason=finish
                            )
                        )

                llm.stream_think.side_effect = stream
                tool = self.setup_tool(tmp, llm)
                events = [
                    e async for e in tool.async_stream_run(title="斜率", concept="概念")
                ]
                self.assertTrue(events[-1].startswith("Error:"))
                self.register.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])

    async def test_legacy_json_route_consumes_stream(self):
        from routers import viz as route

        viz_id = "82c4c897-30ee-4ecb-939c-3fe1e687d8af"

        async def stream(**kwargs):
            yield "生成中"
            yield AgentThinkChunkEvent(delta="code", content="code", step=1)
            yield viz_id

        tool = MagicMock()
        tool.async_stream_run.side_effect = stream
        with patch.object(route, "GenerateInteractiveVizTool", return_value=tool):
            result = await route.generate_viz(
                route.GenerateVizRequest(title="斜率", concept="概念"), user_id="user"
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.viz_id, viz_id)
        tool.run.assert_not_called()


class RuntimeCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_worker_timeout_and_both_cancellation_paths_are_reaped(self):
        # A stand-in worker isolates process lifecycle from browser installation.
        real_spawn = asyncio.create_subprocess_exec
        for mode in ("timeout", "task_cancel", "parent_cancel"):
            with self.subTest(mode=mode):
                spawned = asyncio.Event()
                processes = []

                async def spawn(*args, **kwargs):
                    process = await real_spawn(
                        sys.executable,
                        "-c",
                        "import sys,time; sys.stdin.read(); time.sleep(30)",
                        **kwargs,
                    )
                    processes.append(process)
                    spawned.set()
                    return process

                cancelled = False

                def checkpoint():
                    if cancelled:
                        raise CancelledByCaller("取消")

                with patch.object(
                    runtime.asyncio, "create_subprocess_exec", side_effect=spawn
                ):
                    task = asyncio.create_task(
                        runtime.async_check_viz_runtime(
                            Path("/tmp/unused-viz.js"),
                            SPEC,
                            timeout=0.05 if mode == "timeout" else 10,
                            checkpoint=checkpoint,
                        )
                    )
                    await asyncio.wait_for(spawned.wait(), 2)
                    if mode == "task_cancel":
                        # Let the worker's communication/finally scope start.
                        await asyncio.sleep(0)
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await asyncio.wait_for(task, 2)
                    elif mode == "parent_cancel":
                        cancelled = True
                        with self.assertRaises(CancelledByCaller):
                            await asyncio.wait_for(task, 2)
                    else:
                        report = await asyncio.wait_for(task, 2)
                        self.assertFalse(report["ok"])
                        self.assertIn("超时", report["errors"][0])
                    self.assertIsNotNone(processes[0].returncode)


if __name__ == "__main__":
    unittest.main()
