"""Tests for the generic job primitive and v1 read/stream/cancel contract."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.jobs import AsyncJobManager, JobStatus


class JobManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_sequence_and_cancel(self):
        manager = AsyncJobManager()
        release = asyncio.Event()

        async def runner():
            yield {"type": "progress", "message": "started"}
            await release.wait()
            yield {"type": "done"}

        job = manager.start(owner_id="u1", kind="demo", runner=runner())
        stream = manager.subscribe(job.id)
        first = await stream.__anext__()
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(first["job_id"], job.id)
        self.assertTrue(first["event_id"].startswith("evt_"))
        self.assertIn("occurred_at", first)
        self.assertIn("request_id", first)
        await manager.cancel(job.id)
        await asyncio.sleep(0)
        self.assertEqual(manager.get(job.id).status, JobStatus.CANCELLED)

    async def test_cancel_state_becomes_terminal_on_next_loop_turn(self):
        manager = AsyncJobManager()
        blocker = asyncio.Event()

        async def runner():
            await blocker.wait()
            yield {"type": "done"}

        job = manager.start(owner_id="u1", kind="demo", runner=runner())
        await asyncio.sleep(0)
        self.assertTrue(await manager.cancel(job.id))
        await asyncio.sleep(0)
        self.assertEqual(manager.get(job.id).status, JobStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
