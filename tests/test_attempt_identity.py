"""WP2 A1: agent specs/results carry attempts and closed attempts stay closed."""

from __future__ import annotations

import json

from ohflow.engine import Engine
from ohflow.run_log import RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, read_run_log, simple_workflow,
                     stub_preflight, agent_step)


class AttemptIdentity(TempCase):

    def _open_attempt(self):
        repo = git_repo(self.tmp / "repo")
        run_dir = self.run_dir()
        engine = Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
                        verbose=False,
                        harness_executors=self.harness_executors)
        engine._transition("run_started", payload={
            "run_id": run_dir.name, "workflow": "attempt", "meta": {}})
        engine._transition("attempt_started", coord_="01.only-phase/01.s1",
                           attempt=1, payload={
                               "step_id": "s1", "kind": "agent",
                               "fingerprint": "abc"})
        return engine

    def test_spec_and_result_name_the_attempt(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        run_dir = self.run_dir()
        Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
               verbose=False,
               harness_executors=self.harness_executors).run()
        attempt_dir = (run_dir / "phases" / "01.only-phase" / "01.s1"
                       / "attempts" / "01")
        spec = json.loads((attempt_dir / "spec.json").read_text())
        result = json.loads((attempt_dir / "result.json").read_text())
        self.assertEqual(spec["attempt"], 1)
        self.assertEqual(result["attempt"], 1)

    def test_completion_for_an_already_closed_attempt_is_ignored(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        engine_box: list[Engine] = []

        class ClosingHarnessExecutor(FakeHarnessExecutor):
            def collect(self, handle):
                result = super().collect(handle)
                engine_box[0]._transition(
                    "attempt_finished", coord_=handle.coord,
                    attempt=handle.attempt, payload={
                        "status": "failed", "step_id": "s1",
                        "kind": "agent", "fingerprint": "preclosed",
                        "error": "closed before collect",
                        "abort_victim": False,
                    })
                return result

        install_fake_harness_executor(self, ClosingHarnessExecutor(default=AgentScript()))
        run_dir = self.run_dir()
        engine = Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
                        verbose=False,
                        harness_executors=self.harness_executors)
        engine_box.append(engine)
        engine.run()

        finishes = [r for r in read_run_log(run_dir)
                    if r["event"] == "attempt_finished"
                    and r.get("coord") == "01.only-phase/01.s1"]
        self.assertEqual(len(finishes), 1)
        rec = RunLog.replay(run_dir).steps["01.only-phase/01.s1"]
        self.assertEqual(rec.error, "closed before collect")

    def test_missing_attempt_is_refused(self):
        engine = self._open_attempt()
        error = engine._completion_refusal(
            "01.only-phase/01.s1", 1, {"coord": "01.only-phase/01.s1"})
        self.assertIn("no attempt", error or "")

    def test_mismatched_attempt_is_refused(self):
        engine = self._open_attempt()
        error = engine._completion_refusal(
            "01.only-phase/01.s1", 1,
            {"coord": "01.only-phase/01.s1", "attempt": 2})
        self.assertIn("names attempt 2", error or "")
