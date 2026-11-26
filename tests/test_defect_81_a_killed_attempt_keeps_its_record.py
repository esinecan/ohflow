"""A runner killed before it opened its event log still leaves a record.

What went wrong. `CliHarnessExecutor.collect` rebuilt a killed attempt's
record only when the runner's event log existed. The runner opens that log
after its adapter prepared the process, and a cloud adapter posts the step to
the Worker in that preparation, which waits while the container starts. A
kill in that window returned the empty record `no result.json`: no `pi_cloud`,
no container time, although `remote.json` and `kill-abort.json` were on disk.
`test_a_killed_claude_cloud_attempt_aborts_under_its_prefix` killed its runner
right after the step post and met the window in about one run in three.

A rebuilt record also said nothing of the attempt's wall time or of the tool
call that was open at the kill: a `codex-cloud` attempt killed after 45
minutes, with one command open for 44 of them, recorded 0.0 s and no open call.

What is proved:

- a cloud attempt with `remote.json` and `kill-abort.json` and no event log
  collects a record with its `pi_cloud` block and the container time of the
  abort answer, and `record_source` says `attempt_files`;
- a record rebuilt from an event log says `event_log`, and carries the wall
  time since the runner started and the call the tool-output index left open;
- a local runner killed before its event log is recorded as killed;
- an executor with nothing to rebuild from writes `none`;
- the wall time of a rebuilt record ends at the kill the executor recorded,
  else at the attempt's last file write, and never at the later moment of the
  rebuild; `recovery.ended_basis` names which;
- `recovery.event_log` tells an absent log from an empty, a torn and an
  unreadable one, and a rebuild that fails leaves its fault in the record.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

from ohflow import harness_executors
from ohflow.cli_harness_executor import CliHarnessExecutor
from ohflow.tool_output import ToolOutputWriter
from pi_cloud_support import spec
from support import TempCase

KEY = "01.report-01.s1-a01-0badc0de"


def killed_attempt(out_dir: Path, executor: str, *, started_ago: float = 0.0,
                   kill_abort: bool = True) -> SimpleNamespace:
    out_dir.mkdir(parents=True)
    spec_path = out_dir / "spec.json"
    spec_path.write_text(json.dumps(spec(out_dir, harness_executor=executor)),
                         encoding="utf-8")
    pid = out_dir / "agent.pid"
    pid.write_text("4242\n", encoding="ascii")
    started = time.time() - started_ago
    os.utime(pid, (started, started))
    (out_dir / "remote.json").write_text(json.dumps({
        "url": "http://127.0.0.1:9/claude", "key": KEY,
        "branch": f"ohflow/{executor}/{KEY}", "remote_url": "origin",
        "start_sha": "a" * 40}), encoding="utf-8")
    if kill_abort:
        (out_dir / "kill-abort.json").write_text(json.dumps({
            "aborted": True,
            "answer": {"operationId": KEY, "aborted": True, "container": {
                "durable_object_id": "f" * 64, "instance": "standard-1",
                "seconds": 7.5, "launches": 1, "stopped": True}}}),
            encoding="utf-8")
    return SimpleNamespace(coord="01.report/01.s1", spec_path=spec_path,
                           out_dir=out_dir, error=None)


class AKilledAttemptKeepsItsRecord(TempCase):

    def test_a_cloud_attempt_killed_before_its_event_log_keeps_its_record(self):
        for name in ("pi-cloud", "claude-cloud", "codex-cloud"):
            with self.subTest(executor=name):
                handle = killed_attempt(self.tmp / name, name, started_ago=40)
                self.assertFalse((handle.out_dir / "logs").exists())
                result = harness_executors.harness_executor_for(name).collect(handle)
                self.assertEqual(result["record_source"], "attempt_files")
                self.assertEqual(result["recovery"]["event_log"], "absent")
                self.assertEqual(result["recovery"]["ended_basis"], "last_write")
                self.assertEqual(result["error"], f"{name} runner was killed")
                self.assertTrue(result["pi_cloud"]["aborted"])
                self.assertEqual(result["pi_cloud"]["key"], KEY)
                self.assertEqual(result["infra"]["container_seconds"], 7.5)
                self.assertEqual(result["infra"]["durable_object_id"], "f" * 64)
                self.assertGreaterEqual(result["wall_seconds"], 39.0)
                persisted = json.loads((handle.out_dir / "result.json")
                                       .read_text(encoding="utf-8"))
                self.assertEqual(persisted, result)

    def test_a_rebuilt_record_names_the_open_call_and_the_wall_time(self):
        handle = killed_attempt(self.tmp / "slow", "codex-cloud", started_ago=2700)
        logs = handle.out_dir / "logs"
        logs.mkdir()
        (logs / "codex-cloud-events.jsonl").write_text(
            json.dumps({"type": "pi_cloud_start", "operationId": KEY,
                        "durable_object_id": "f" * 64,
                        "instance": "standard-1"}) + "\n", encoding="utf-8")
        calls = ToolOutputWriter(handle.out_dir)
        calls.start("item_52", "shell", "git status", at=time.time() - 2650)
        calls.end("item_52", ok=True, at=time.time() - 2649)
        calls.start("item_53", "shell", "python3 tests/run_tests.py --shard 1/3",
                    at=time.time() - 2640)
        result = harness_executors.harness_executor_for("codex-cloud").collect(handle)
        self.assertEqual(result["record_source"], "event_log")
        self.assertGreaterEqual(result["wall_seconds"], 2699.0)
        open_call = result["open_tool_call"]
        self.assertEqual(open_call["id"], "item_53")
        self.assertEqual(open_call["command"],
                         "python3 tests/run_tests.py --shard 1/3")
        self.assertGreaterEqual(open_call["since_s"], 2639.0)
        self.assertEqual(open_call["file"], "logs/tool-output/002-item_53.log")

    def test_a_local_runner_killed_before_its_event_log_is_recorded_as_killed(self):
        for name in ("pi", "claude", "codex"):
            with self.subTest(executor=name):
                handle = killed_attempt(self.tmp / name, name, started_ago=5,
                                        kill_abort=False)
                result = harness_executors.harness_executor_for(name).collect(handle)
                self.assertEqual(result["record_source"], "attempt_files")
                self.assertEqual(result["error"], f"{name} runner was killed")
                self.assertEqual(result["coord"], "01.report/01.s1")

    def test_the_wall_time_ends_at_the_recorded_kill_not_at_the_rebuild(self):
        handle = killed_attempt(self.tmp / "late", "codex-cloud", started_ago=2700)
        (handle.out_dir / "kill.json").write_text(
            json.dumps({"at": time.time() - 600}), encoding="utf-8")
        calls = ToolOutputWriter(handle.out_dir)
        calls.start("item_1", "shell", "sleep 9999", at=time.time() - 2640)
        result = harness_executors.harness_executor_for("codex-cloud").collect(handle)
        self.assertEqual(result["recovery"]["ended_basis"], "kill")
        self.assertAlmostEqual(result["wall_seconds"], 2100.0, delta=5.0)
        self.assertAlmostEqual(result["open_tool_call"]["since_s"], 2040.0, delta=5.0)

    def test_without_a_recorded_kill_the_wall_time_ends_at_the_last_write(self):
        handle = killed_attempt(self.tmp / "died", "claude", started_ago=2700,
                                kill_abort=False)
        last = time.time() - 900
        for path in handle.out_dir.rglob("*"):
            if path.is_file() and path.name != "agent.pid":
                os.utime(path, (last, last))
        result = harness_executors.harness_executor_for("claude").collect(handle)
        self.assertEqual(result["recovery"]["ended_basis"], "last_write")
        self.assertAlmostEqual(result["wall_seconds"], 1800.0, delta=5.0)
        self.assertAlmostEqual(result["recovery"]["ended_at"], last, delta=2.0)

    def test_the_record_says_what_the_event_log_was(self):
        cases = {"empty": "", "torn": 'not json\n{"type": "pi_cloud_st'}
        for name, content in cases.items():
            with self.subTest(log=name):
                handle = killed_attempt(self.tmp / name, "codex-cloud")
                (handle.out_dir / "logs").mkdir()
                (handle.out_dir / "logs" / "codex-cloud-events.jsonl").write_text(
                    content, encoding="utf-8")
                result = harness_executors.harness_executor_for("codex-cloud").collect(handle)
                self.assertEqual(result["record_source"], "attempt_files")
                self.assertEqual(result["recovery"]["event_log"], "empty")
                self.assertEqual(result["recovery"]["unparsed_lines"],
                                 2 if name == "torn" else 0)
        handle = killed_attempt(self.tmp / "unreadable", "codex-cloud")
        (handle.out_dir / "logs" / "codex-cloud-events.jsonl").mkdir(parents=True)
        result = harness_executors.harness_executor_for("codex-cloud").collect(handle)
        self.assertEqual(result["recovery"]["event_log"], "unreadable")
        self.assertTrue(result["recovery"]["error"])
        self.assertTrue(result["pi_cloud"]["aborted"])

    def test_a_rebuild_that_fails_leaves_its_fault_in_the_record(self):
        handle = killed_attempt(self.tmp / "broken", "codex-cloud")
        handle.spec_path.write_text("{not json", encoding="utf-8")
        result = harness_executors.harness_executor_for("codex-cloud").collect(handle)
        self.assertEqual(result["record_source"], "none")
        self.assertIn("the record could not be rebuilt", result["error"])
        self.assertIn("JSONDecodeError", result["recovery"]["error"])

    def test_an_executor_with_nothing_to_rebuild_from_says_none(self):
        handle = killed_attempt(self.tmp / "bare", "pi", kill_abort=False)
        executor = CliHarnessExecutor(name="echo", runner_module="unused")
        result = executor.collect(handle)
        self.assertEqual(result["record_source"], "none")
        self.assertEqual(result["error"], "no result.json")
