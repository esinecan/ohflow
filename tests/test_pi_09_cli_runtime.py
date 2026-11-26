"""The CLI runtime is agent-neutral, and it closes the process tree of a child it ran."""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

from ohflow.cli_harness_executor import (CliAgentRuntime, CliEventAction,
                                         CliPreparedProcess)
from support import TempCase


PINNED_BASH = r"C:\Program Files\Git\bin\bash.exe"
_FILETIME_EPOCH_OFFSET_S = 11644473600


def _pid_alive(pid: int, *, started_before: float | None = None) -> bool:
    """Return whether the PID is still active and has the recorded identity."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError, ValueError):
            return False
        return True

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        if code.value != 259:  # STILL_ACTIVE
            return False
        if started_before is None:
            return True
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(
                handle, *(ctypes.byref(value) for value in times)):
            return True
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        created_at = ticks / 1e7 - _FILETIME_EPOCH_OFFSET_S
        return created_at <= started_before
    finally:
        kernel32.CloseHandle(handle)


def _wait_until_not_alive(pid: int, *, started_before: float,
                          timeout_s: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while _pid_alive(pid, started_before=started_before):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.02, remaining))
    return True


class EchoAdapter:
    """Small non-pi adapter proving the runtime boundary is reusable."""

    name = "echo"
    event_log_name = "echo-events.jsonl"
    stderr_log_name = "echo-stderr.log"

    def prepare(self, spec: dict, out_dir: Path) -> CliPreparedProcess:
        if spec.get("grandchild_pid_path"):
            program = (
                "import json,subprocess,sys; from pathlib import Path; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                f"Path({str(spec['grandchild_pid_path'])!r}).write_text(str(p.pid)); "
                "print(json.dumps({'kind':'answer','text':'ECHO'}), flush=True)"
            )
        else:
            program = (
                "import json; "
                "print(json.dumps({'kind':'action','count':1}), flush=True); "
                "print(json.dumps({'kind':'answer','text':'ECHO'}), flush=True)"
            )
        return CliPreparedProcess(
            argv=(sys.executable, "-c", program),
            cwd=Path(spec["workspace"]),
            env=dict(os.environ),
            context={"prepared_by": self.name},
        )

    def parse_event(self, line: str) -> dict:
        return json.loads(line)

    def on_event(self, spec: dict, event: dict,
                 events: list[dict]) -> CliEventAction:
        if event.get("kind") == "action":
            return CliEventAction(heartbeat={"tool_calls": len(events)})
        return CliEventAction()

    def build_result(self, outcome):
        answer = next(event["text"] for event in outcome.events
                      if event.get("kind") == "answer")
        return ({"coord": outcome.spec["coord"], "attempt": outcome.spec["attempt"],
                 "execution_status": "finished", "error": outcome.stop_error,
                 "adapter": outcome.prepared.context["prepared_by"]}, answer + "\n")


class ExplodingAdapter(EchoAdapter):
    def on_event(self, spec: dict, event: dict,
                 events: list[dict]) -> CliEventAction:
        raise RuntimeError("adapter event failure")


class CliRuntimeTests(TempCase):

    def setUp(self):
        super().setUp()
        old = os.environ.get("OHFLOW_BASH")
        os.environ["OHFLOW_BASH"] = PINNED_BASH
        self.addCleanup(
            lambda: os.environ.pop("OHFLOW_BASH", None) if old is None
            else os.environ.__setitem__("OHFLOW_BASH", old))

    def test_non_pi_adapter_uses_process_stream_heartbeat_and_result_runtime(self):
        out_dir = self.tmp / "echo-attempt"
        out_dir.mkdir()
        result = CliAgentRuntime(EchoAdapter()).run(
            {"coord": "01.echo", "attempt": 1, "workspace": str(self.tmp),
             "stall_timeout_s": 5},
            out_dir,
        )

        self.assertEqual(result["adapter"], "echo")
        self.assertEqual((out_dir / "final.md").read_text(encoding="utf-8"),
                         "ECHO\n")
        persisted = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted, result)
        events = (out_dir / "logs" / "echo-events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind": "action"', events)
        heartbeat = json.loads(
            (out_dir / "logs" / "heartbeat.json").read_text(encoding="utf-8"))
        self.assertEqual(heartbeat["tool_calls"], 1)

    @unittest.skipUnless(sys.platform == "win32", "Windows inherited-pipe regression")
    def test_exited_child_with_grandchild_holding_stdout_cannot_deadlock_runtime(self):
        out_dir = self.tmp / "inherited-stdout"
        out_dir.mkdir()
        pid_path = self.tmp / "grandchild.pid"
        started = time.monotonic()

        result = CliAgentRuntime(EchoAdapter()).run(
            {"coord": "01.echo", "attempt": 1, "workspace": str(self.tmp),
             "stall_timeout_s": 5, "grandchild_pid_path": str(pid_path)},
            out_dir,
        )

        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual(result["execution_status"], "finished")
        self.assertTrue(pid_path.exists())
        pid = int(pid_path.read_text(encoding="ascii"))
        self.assertTrue(
            _wait_until_not_alive(
                pid, started_before=pid_path.stat().st_mtime),
            "the runtime's child job left the grandchild alive",
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows child-job cleanup")
    def test_adapter_event_failure_still_closes_job_and_kills_descendants(self):
        out_dir = self.tmp / "adapter-failure"
        out_dir.mkdir()
        pid_path = self.tmp / "failed-adapter-grandchild.pid"

        with self.assertRaisesRegex(RuntimeError, "adapter event failure"):
            CliAgentRuntime(ExplodingAdapter()).run(
                {"coord": "01.echo", "attempt": 1, "workspace": str(self.tmp),
                 "stall_timeout_s": 5, "grandchild_pid_path": str(pid_path)},
                out_dir,
            )

        self.assertTrue(pid_path.exists())
        pid = int(pid_path.read_text(encoding="ascii"))
        self.assertTrue(
            _wait_until_not_alive(
                pid, started_before=pid_path.stat().st_mtime),
            "adapter failure left the grandchild alive",
        )


if __name__ == "__main__":
    unittest.main()
