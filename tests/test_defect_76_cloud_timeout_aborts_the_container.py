"""A cloud step that the engine kills stops its Worker operation and container.

The engine ends a step past `execution_timeout_s`, and the victims of a
phase abort, by killing the local runner. A stall and the command time cap
end inside the runner, which posts `abort`; a kill never reached that code,
so the Durable Object's container ran on, billed, with no step ever reading
it again: the retry is a fresh attempt with its own object. What is proved:

- a `pi-cloud` step past its execution timeout posts `abort` for its own
  key, and its record says the object was aborted;
- a `claude-cloud` attempt killed through the executor posts `abort` under
  the `/claude` prefix, so the CLI executors share the rule;
- a kill before the launch reached the transport posts nothing.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace

from ohflow import harness_executors
from ohflow.engine import Engine
from ohflow.harness_executor import RUNNING
from ohflow.workflow import ModelConfig
from pi_cloud_support import PiCloudCase, spec
from support import quiet, read_run_log, simple_workflow, step_statuses, stub_preflight
from test_pi_cloud_03_reattach import COORD, pi_cloud_step


class CloudKillAborts(PiCloudCase):

    def test_an_execution_timeout_aborts_the_object(self):
        stub_preflight(self)
        run_dir = self.tmp / "run"
        attempt_dir = run_dir / "phases" / "01.only-phase" / "01.s1" / "attempts" / "01"
        from ohflow import remote_git
        key = remote_git.attempt_key(COORD, 1, attempt_dir.resolve())
        self.worker.plan(key, 1, ["silent"])
        workflow = simple_workflow(self.repo, on_step_failure="continue",
                                   steps=[pi_cloud_step(execution_timeout_s=6)])
        with quiet():
            Engine(workflow, run_dir, run_id=run_dir.name, verbose=False).run()

        self.assertEqual(step_statuses(run_dir)[COORD], "timeout")
        self.assertEqual(self.worker.aborted, [key])
        [finished] = [r for r in read_run_log(run_dir)
                      if r["event"] == "attempt_finished" and r.get("coord") == COORD]
        self.assertIn("execution timeout", finished["payload"]["error"])
        result = json.loads((attempt_dir / "result.json").read_text(encoding="utf-8"))
        self.assertTrue(result["pi_cloud"]["aborted"])

    def test_a_killed_claude_cloud_attempt_aborts_under_its_prefix(self):
        executor = harness_executors.harness_executor_for("claude-cloud")
        out_dir = self.tmp / "claude"
        out_dir.mkdir()
        (out_dir / "brief.md").write_text("# Task\n", encoding="utf-8")
        key = self.key_of(out_dir)
        self.worker.plan(key, 1, ["silent"])
        handle = executor.launch(spec(self.repo, harness_executor="claude-cloud", model={
            "model": "claude-haiku-4-5-20251001", "base_url": "", "api_key_env": "",
            "params": {}, "extra_body": None}), out_dir)
        deadline = time.monotonic() + 30
        while not self.worker.step_answers.get(key) and time.monotonic() < deadline:
            self.assertEqual(executor.poll(handle), RUNNING)
            time.sleep(0.05)
        executor.kill(handle)
        self.assertEqual(self.worker.aborted, [key])
        self.assertTrue(any(r["path"].startswith("/claude/attempts/")
                            and r["path"].endswith("/abort")
                            for r in self.worker.requests))
        result = executor.collect(handle)
        self.assertTrue(result["pi_cloud"]["aborted"])

    def test_a_kill_before_the_transport_posts_nothing(self):
        executor = harness_executors.harness_executor_for("pi-cloud")
        out_dir = self.tmp / "never"
        out_dir.mkdir()
        from ohflow.harness_executor import Handle
        handle = Handle(coord=COORD, harness_executor="pi-cloud", out_dir=out_dir,
                        spec_path=out_dir / "spec.json", pid=0, process=None)
        executor.kill(handle)
        self.assertEqual(self.worker.aborted, [])
