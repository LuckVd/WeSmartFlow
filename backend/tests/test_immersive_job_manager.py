"""Detached job lifecycle tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.immersive.job_manager import ImmersiveJobManager


class DetachedJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_continues_after_detach_and_replays_completed_events(self):
        manager = ImmersiveJobManager()
        release = asyncio.Event()

        async def generator():
            yield "one"
            await release.wait()
            yield "two"

        with patch("services.immersive.job_manager.update_workspace"):
            manager.start("session", "user", generator())
            seen = []
            stream = manager.subscribe("session")
            seen.append(await stream.__anext__())
            self.assertTrue(manager.detach("session"))
            release.set()
            seen.append(await stream.__anext__())
            with self.assertRaises(StopAsyncIteration):
                await stream.__anext__()

            replay = manager.subscribe("session")
            self.assertEqual(await replay.__anext__(), "one")
            self.assertEqual(await replay.__anext__(), "two")
            with self.assertRaises(StopAsyncIteration):
                await replay.__anext__()

        self.assertEqual(seen, ["one", "two"])

    async def test_snapshot_tracks_running_background_and_completion(self):
        manager = ImmersiveJobManager()
        release = asyncio.Event()

        async def generator():
            yield "one"
            await release.wait()

        with patch("services.immersive.job_manager.update_workspace"):
            manager.start("session", "user", generator())
            await asyncio.sleep(0)
            self.assertEqual(manager.snapshot("session")["status"], "running")
            self.assertTrue(manager.detach("session"))
            self.assertEqual(manager.snapshot("session")["status"], "background")
            release.set()
            await asyncio.sleep(0)
            self.assertEqual(manager.snapshot("session")["status"], "succeeded")

    async def test_cancel_marks_workspace_and_stops_job(self):
        manager = ImmersiveJobManager()
        blocker = asyncio.Event()

        async def generator():
            await blocker.wait()
            yield "never"

        with patch("services.immersive.job_manager.update_workspace") as update:
            manager.start("session", "user", generator())
            await asyncio.sleep(0)
            self.assertTrue(manager.cancel("session"))
            await asyncio.sleep(0)
            self.assertFalse(manager.is_running("session"))
            update.assert_called_once()
            self.assertEqual(update.call_args.kwargs["stage"], "cancelled")


if __name__ == "__main__":
    unittest.main()
