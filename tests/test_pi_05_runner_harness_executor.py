"""The pi harness executor is process-backed, replayable, and kills descendant trees."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from ohflow.cli_harness_executor import PiHarnessExecutor
from ohflow.harness_executor import ERROR, FINISHED, RUNNING
from support import TempCase, fake_pi_executable


PINNED_BASH = r"C:\Program Files\Git\bin\bash.exe"


def _alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    try:
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel32.CloseHandle(handle)


class PiRunnerHarnessExecutorTests(TempCase):

    def setUp(self):
        super().setUp()
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.fake_pi = fake_pi_executable(self.tmp)
        self.state = self.tmp / "fake-state"
        self._set_env("OHFLOW_PI_EXE", str(self.fake_pi))
        self._set_env("OHFLOW_BASH", PINNED_BASH)
        self._set_env("OHFLOW_FAKE_PI_STATE", str(self.state))
        self._set_env("OHFLOW_TEST_FAKE_KEY", "not-a-key")
        self.harness_executor = PiHarnessExecutor()

    def _set_env(self, name: str, value: str) -> None:
        old = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(
            lambda: os.environ.pop(name, None) if old is None
            else os.environ.__setitem__(name, old))

    def _spec(self, **changes) -> dict:
        spec = {
            "coord": "01.only/01.pi",
            "attempt": 1,
            "role": "pi-test",
            "harness_executor": "pi",
            "workspace": str(self.workspace),
            "model": {
                "model": "zai/glm-5.3-flash",
                "base_url": "https://api.z.ai/api/coding/paas/v4",
                "api_key_env": "OHFLOW_TEST_FAKE_KEY",
                "params": {"thinking": "low"},
                "extra_body": {},
            },
            "tools": {"preset": "default", "only": [], "allow": []},
            "skills": [],
            "skills_dir": None,
            "mcp_config": None,
            "max_iterations": 2,
            "execution_timeout_s": 20,
            "stall_timeout_s": None,
            "write_scope": [],
            "fork_session": None,
            "brief_path": "brief.md",
            "schema_path": None,
            "out_dir": ".",
        }
        spec.update(changes)
        return spec

    def _attempt(self, name: str, *, schema: dict | None = None) -> Path:
        attempt = self.tmp / name
        attempt.mkdir()
        (attempt / "brief.md").write_text("Reply with DONE.\n", encoding="utf-8")
        if schema is not None:
            (attempt / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
        return attempt

    def _wait(self, predicate, timeout: float = 12.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        self.fail("condition did not become true before timeout")

    def _wait_harness_executor(self, handle, timeout: float = 12.0) -> str:
        state = RUNNING
        deadline = time.monotonic() + timeout
        while state == RUNNING and time.monotonic() < deadline:
            state = self.harness_executor.poll(handle)
            if state == RUNNING:
                time.sleep(0.05)
        self.assertNotEqual(state, RUNNING, "pi runner did not finish")
        return state

    def test_launch_poll_collect_success_and_schema(self):
        rows = (
            ("success", None, "DONE\n", None),
            ("schema", {
                "type": "object",
                "required": ["answer", "count"],
                "properties": {
                    "answer": {"type": "string"},
                    "count": {"type": "integer"},
                },
            }, None, {"answer": "ok", "count": 2}),
        )
        for scenario, schema, final, structured in rows:
            with self.subTest(scenario=scenario):
                os.environ["OHFLOW_FAKE_PI_SCENARIO"] = scenario
                attempt = self._attempt(scenario, schema=schema)
                spec = self._spec(schema_path="schema.json" if schema else None)
                handle = self.harness_executor.launch(spec, attempt)
                self.assertGreater(handle.pid, 0)
                self.assertIn(self.harness_executor.poll(handle), (RUNNING, FINISHED))
                self.assertEqual(self._wait_harness_executor(handle), FINISHED)
                result = self.harness_executor.collect(handle)
                self.assertEqual(result["execution_status"], "finished")
                self.assertEqual(result["conversation_id"], "fake-session")
                self.assertEqual(result["error"], None)
                self.assertEqual(result["structured"], structured)
                self.assertEqual(result["schema_error"], None)
                if final is not None:
                    self.assertEqual((attempt / "final.md").read_text(encoding="utf-8"), final)
                self.assertEqual(result["tool_calls"], 1 if scenario == "success" else 0)
                self.assertEqual(result["tokens"]["prompt_tokens"], 14)
                self.assertEqual(result["tokens"]["completion_tokens"], 3)

    def test_exit_zero_provider_error_is_read_from_message_event(self):
        for scenario, code in (("429", "429"), ("401", "401")):
            with self.subTest(scenario=scenario):
                os.environ["OHFLOW_FAKE_PI_SCENARIO"] = scenario
                attempt = self._attempt("provider-" + scenario)
                handle = self.harness_executor.launch(self._spec(), attempt)
                self.assertEqual(self._wait_harness_executor(handle), FINISHED)
                self.assertEqual(handle.process.returncode, 0)
                result = self.harness_executor.collect(handle)
                self.assertEqual(result["execution_status"], "error")
                self.assertIn(code, result["error"])
                self.assertEqual(result["llm_calls"], 1)

    def test_collect_after_external_kill_replays_events_and_ignores_torn_tail(self):
        os.environ["OHFLOW_FAKE_PI_SCENARIO"] = "torn-tail"
        attempt = self._attempt("torn")
        custom_model = {**self._spec()["model"],
                        "base_url": "http://127.0.0.1:9876/v1"}
        handle = self.harness_executor.launch(self._spec(model=custom_model), attempt)
        events = attempt / "logs" / "pi-events.jsonl"
        self._wait(lambda: events.exists() and "rate_limit_exceeded" in
                   events.read_text(encoding="utf-8", errors="replace"))
        marker = json.loads(
            (attempt / "pi-agent" / "ohflow-model.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["cost_source"], "unpriced")
        self.harness_executor.kill(handle)
        with events.open("a", encoding="utf-8", newline="") as stream:
            stream.write('{"type":"message_end","message":')
        self.assertEqual(self.harness_executor.poll(handle), ERROR)
        result = self.harness_executor.collect(handle)
        self.assertEqual(result["execution_status"], "error")
        self.assertIn("429", result["error"])
        self.assertEqual(result["llm_calls"], 1)
        self.assertEqual(result["conversation_id"], "fake-session")
        self.assertEqual(result["cost_source"], "unpriced")

    @unittest.skipUnless(sys.platform == "win32", "Windows Job Object contract")
    def test_kill_catches_grandchild_spawned_immediately(self):
        os.environ["OHFLOW_FAKE_PI_SCENARIO"] = "immediate-grandchild"
        attempt = self._attempt("tree")
        handle = self.harness_executor.launch(self._spec(), attempt)
        pid_path = self.state / "grandchild.pid"
        # Path.write_text creates the file before its contents are visible. Waiting
        # for existence alone races that short window on fast Windows runners.
        self._wait(lambda: pid_path.exists() and pid_path.stat().st_size > 0)
        grandchild = int(pid_path.read_text(encoding="ascii"))
        self.assertTrue(_alive(grandchild))
        self.harness_executor.kill(handle)
        self._wait(lambda: not _alive(grandchild))
        self.assertFalse(_alive(grandchild))

    def test_stall_is_a_distinct_runner_error(self):
        os.environ["OHFLOW_FAKE_PI_SCENARIO"] = "slow"
        attempt = self._attempt("stall")
        handle = self.harness_executor.launch(self._spec(stall_timeout_s=1), attempt)
        self.assertEqual(self._wait_harness_executor(handle), FINISHED)
        result = self.harness_executor.collect(handle)
        self.assertEqual(result["execution_status"], "error")
        self.assertEqual(result["error"], "stall")
        self.assertNotIn("exited", result["error"])

    def test_max_iterations_stops_a_tool_loop(self):
        os.environ["OHFLOW_FAKE_PI_SCENARIO"] = "iterations"
        attempt = self._attempt("iterations")
        handle = self.harness_executor.launch(self._spec(max_iterations=1), attempt)
        self.assertEqual(self._wait_harness_executor(handle), FINISHED)
        result = self.harness_executor.collect(handle)
        self.assertEqual(result["execution_status"], "error")
        self.assertEqual(result["error"], "max iterations 1 exceeded")


if __name__ == "__main__":
    unittest.main()
