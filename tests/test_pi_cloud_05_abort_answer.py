"""A cloud attempt that is stopped keeps what the Worker's abort answer says.

The Worker answers `POST abort` with the container's running time, the box
as it was just before the stop (`last_look`) and, for a Claude Code or Codex
step, the tokens the object had counted (`usage`). Those CLIs report their
tokens to ohflow only when the operation settles, so a stopped attempt used
to record 0 tokens, and nothing said what ran in the box at the stop.

What is proved:

- a `claude-cloud` attempt the executor kills records the abort answer's
  tokens, and `usage` reads the same count, so the token reconcile agrees;
- a `codex-cloud` attempt its own runner stops on a stall records them too,
  and keeps the answer in `runner-abort.json`;
- the look lands in `logs/box-last-look.txt`, and the record points at it;
- a `pi-cloud` attempt keeps the tokens of its event stream and gains the look;
- an abort that left no look says why: the container was not running, the
  Worker sent none, or the abort post failed;
- a count of zero tokens is a count, and tokens no abort answer carries are
  `unknown` in the record and a fault for `usage`.

The fake's stream under `/claude` and `/codex` holds no `message_end`, as the
real stream of a step that has not settled.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ohflow import harness_executors, pi_cloud_runner
from ohflow.harness_executor import FINISHED, RUNNING
from pi_cloud_support import PiCloudCase, spec

CLAUDE = {"model": "claude-haiku-4-5-20251001", "base_url": "", "api_key_env": "",
          "params": {}, "extra_body": None}
CODEX = {"model": "gpt-5.6-luna", "base_url": "", "api_key_env": "",
         "params": {}, "extra_body": None}


class AbortAnswer(PiCloudCase):

    def launch(self, name: str, executor_name: str, **changes):
        executor = harness_executors.harness_executor_for(executor_name)
        out_dir = self.tmp / name
        out_dir.mkdir()
        (out_dir / "brief.md").write_text("# Task\n", encoding="utf-8")
        self.worker.plan(self.key_of(out_dir), 1, ["silent"])
        handle = executor.launch(
            spec(self.repo, harness_executor=executor_name, **changes), out_dir)
        return executor, out_dir, handle

    def finish(self, executor, handle, timeout: float = 60.0) -> dict:
        deadline = time.monotonic() + timeout
        state = RUNNING
        while state == RUNNING and time.monotonic() < deadline:
            state = executor.poll(handle)
            time.sleep(0.05)
        if state == RUNNING:
            executor.kill(handle)
            self.fail("the runner did not stop on its stall")
        self.assertEqual(state, FINISHED)
        return executor.collect(handle)

    def killed(self, name: str) -> tuple[Path, dict]:
        executor, out_dir, handle = self.launch(name, "claude-cloud", model=CLAUDE)
        event_log = out_dir / "logs" / "claude-cloud-events.jsonl"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.assertEqual(executor.poll(handle), RUNNING)
            if event_log.is_file() and event_log.stat().st_size:
                break
            time.sleep(0.05)
        executor.kill(handle)
        return out_dir, executor.collect(handle)

    def stalled(self, name: str) -> tuple[Path, dict]:
        executor, out_dir, handle = self.launch(name, "codex-cloud", model=CODEX,
                                                stall_timeout_s=2)
        return out_dir, self.finish(executor, handle)

    def test_a_killed_claude_cloud_attempt_keeps_its_tokens_and_the_last_look(self):
        out_dir, result = self.killed("killed")

        self.assertEqual(result["record_source"], "event_log")
        self.assertEqual(result["recovery"]["event_log"], "read")
        self.assertEqual(result["recovery"]["tokens"], "abort_answer")
        self.assertEqual(result["recovery"]["ended_basis"], "kill")
        self.assertEqual(result["tokens"]["prompt_tokens"], 1200)
        self.assertEqual(result["tokens"]["completion_tokens"], 300)
        self.assertEqual(result["cost_source"], "subscription")
        look = result["pi_cloud"]["last_look"]
        self.assertEqual(look["file"], "logs/box-last-look.txt")
        self.assertEqual(look["exit"], 0)
        self.assertEqual(look["took_ms"], 1180)
        self.assertIsNone(look["absent"])
        text = (out_dir / look["file"]).read_text(encoding="utf-8")
        self.assertIn("run_tests.py --shard 1/3", text)
        self.assertIn("1 zombies", text)
        module = harness_executors.harness_executor_module("claude-cloud")
        usage, problem = module.usage(out_dir)
        self.assertIsNone(problem)
        self.assertEqual(usage, result["tokens"])

    def test_a_stalled_codex_cloud_attempt_keeps_them_too(self):
        out_dir, result = self.stalled("stalled")

        self.assertEqual(result["error"], "stall")
        self.assertEqual(result["record_source"], "runner")
        self.assertTrue(result["pi_cloud"]["aborted"])
        self.assertEqual(result["tokens"]["prompt_tokens"], 1200)
        self.assertEqual(result["tokens"]["completion_tokens"], 300)
        self.assertEqual(result["pi_cloud"]["last_look"]["file"], "logs/box-last-look.txt")
        kept = json.loads((out_dir / "runner-abort.json").read_text(encoding="utf-8"))
        self.assertTrue(kept["aborted"])
        self.assertEqual(kept["answer"]["usage"]["input"], 1200)
        module = harness_executors.harness_executor_module("codex-cloud")
        usage, problem = module.usage(out_dir)
        self.assertIsNone(problem)
        self.assertEqual(usage, result["tokens"])

    def test_a_pi_cloud_attempt_keeps_its_stream_tokens_and_gains_the_look(self):
        executor, out_dir, handle = self.launch("pi", "pi-cloud", stall_timeout_s=2)
        result = self.finish(executor, handle)

        self.assertEqual(result["error"], "stall")
        usage, problem = self.module.usage(out_dir)
        self.assertIsNone(problem)
        self.assertEqual(usage, result["tokens"])
        self.assertNotEqual(result["tokens"]["prompt_tokens"], 1200)
        self.assertEqual(result["pi_cloud"]["last_look"]["file"], "logs/box-last-look.txt")
        self.assertTrue((out_dir / "logs" / "box-last-look.txt").is_file())

    def test_a_container_that_was_not_running_says_so_and_leaves_no_file(self):
        self.worker.last_look = None
        out_dir, result = self.stalled("gone")

        look = result["pi_cloud"]["last_look"]
        self.assertEqual(look["absent"], pi_cloud_runner.LOOK_NOT_RUNNING)
        self.assertIsNone(look["file"])
        self.assertFalse((out_dir / "logs" / "box-last-look.txt").exists())

    def test_a_worker_that_sends_no_look_is_named(self):
        self.worker.sends_last_look = False
        _out_dir, result = self.stalled("old-worker")

        self.assertEqual(result["pi_cloud"]["last_look"]["absent"],
                         pi_cloud_runner.LOOK_NOT_SENT)

    def test_a_look_that_passed_its_limit_keeps_the_workers_error(self):
        self.worker.last_look = {"at": 1794769303000, "took_ms": 10001,
                                 "error": "the last look did not answer in 10000 ms"}
        _out_dir, result = self.stalled("slow-look")

        look = result["pi_cloud"]["last_look"]
        self.assertEqual(look["error"], "the last look did not answer in 10000 ms")
        self.assertIsNone(look["absent"])
        self.assertIsNone(look["file"])
        self.assertTrue(result["pi_cloud"]["aborted"])

    def test_a_failed_abort_leaves_the_tokens_unknown_and_says_no_look_was_taken(self):
        self.worker.abort_fails = True
        out_dir, result = self.stalled("no-abort")

        self.assertFalse(result["pi_cloud"]["aborted"])
        self.assertEqual(result["pi_cloud"]["last_look"]["absent"],
                         pi_cloud_runner.LOOK_ABORT_FAILED)
        self.assertEqual(result["tokens"]["prompt_tokens"], 0)
        usage, problem = harness_executors.harness_executor_module(
            "codex-cloud").usage(out_dir)
        self.assertIsNone(usage)
        self.assertIn("no assistant message_end usage records", problem)

    def test_a_count_of_zero_tokens_is_a_count(self):
        self.worker.abort_usage = {"input": 0, "output": 0, "notional_cost_usd": 0.0}
        out_dir, result = self.stalled("zero")

        usage, problem = harness_executors.harness_executor_module(
            "codex-cloud").usage(out_dir)
        self.assertIsNone(problem)
        self.assertEqual(usage, result["tokens"])
        self.assertEqual(usage["prompt_tokens"], 0)

    def test_an_object_that_counted_nothing_leaves_the_tokens_unknown(self):
        self.worker.abort_usage = None
        out_dir, result = self.killed("uncounted")

        self.assertEqual(result["recovery"]["tokens"], "unknown")
        usage, problem = harness_executors.harness_executor_module(
            "claude-cloud").usage(out_dir)
        self.assertIsNone(usage)
        self.assertIsNotNone(problem)
