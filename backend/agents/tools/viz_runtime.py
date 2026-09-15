"""Run generated JavaScript in a disposable browser process with a hard deadline."""

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from config import EDUVIZ_SDK_PATH
from .viz_quality import VizQualityError


class VizRuntimeUnavailable(VizQualityError):
    """Infrastructure errors cannot be repaired by asking the model to rewrite code."""


def _runtime_payload(code_path: Path, spec: dict) -> dict:
    return {
        "code_path": str(code_path),
        "spec": spec,
        "sdk_path": str(EDUVIZ_SDK_PATH),
        "screenshot_path": str(code_path.parent / "preview.png"),
    }


def check_viz_runtime(code_path: Path, spec: dict, *, timeout: float = 35) -> dict:
    payload = _runtime_payload(code_path, spec)
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("viz_runtime_worker.py"))],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, _ = proc.communicate(json.dumps(payload), timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.communicate()
        return {
            "ok": False,
            "errors": ["浏览器运行检查超时，请检查死循环、递归回调或未结束的异步操作"],
        }
    return _parse_report(stdout)


def _parse_report(stdout: str) -> dict:
    try:
        report = json.loads(stdout)
        if not isinstance(report, dict) or type(report.get("ok")) is not bool:
            raise ValueError("invalid runtime report")
    except (ValueError, TypeError) as exc:
        raise VizRuntimeUnavailable("浏览器运行检查未返回有效结果") from exc
    if report.get("environment_error"):
        raise VizRuntimeUnavailable("；".join(report.get("errors", [])))
    return report


async def async_check_viz_runtime(
    code_path: Path,
    spec: dict,
    *,
    timeout: float = 35,
    checkpoint=None,
) -> dict:
    """Nonblocking browser checks; timeout/cancellation terminate the worker group."""
    if checkpoint:
        checkpoint()
    payload = _runtime_payload(code_path, spec)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("viz_runtime_worker.py")),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    communication = asyncio.create_task(proc.communicate(json.dumps(payload).encode()))
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while not communication.done():
            if checkpoint:
                checkpoint()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            await asyncio.wait({communication}, timeout=min(0.25, remaining))
        stdout, _ = await communication
        if checkpoint:
            checkpoint()
        return _parse_report(stdout.decode())
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "errors": ["浏览器运行检查超时，请检查死循环、递归回调或未结束的异步操作"],
        }
    finally:
        if proc.returncode is None:
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except ProcessLookupError:
                pass
        # Drain pipes and reap the worker before the caller removes its work directory.
        await asyncio.shield(communication)
