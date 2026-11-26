"""The reattach rule: a supervisor death or a host loss continues the attempt.

An in-process fake harness executor stands in for the durable one: the step
names harness executor `durable`, whose registry row carries `CAP_REATTACH`,
and the engine asks the real module's `reattach_target` about the attempt's
own directory. The fake writes the `remote.json` a real launch leaves behind.

What is proved, from the run log:

- a `host_lost` closes attempt 1 `deferred` with `abort_victim` and
  `reattached`, and starts attempt 1 again with `start_kind: "reattach"` in
  the same directory, the closure carrying the execution's measured wall time;
- the reattach launches with the spec the attempt started with, its skills
  included, plus `reattach: true` (read from the specs the fake received);
- a run log that ends with attempt 1 open is reattached by `--resume`, the
  closure carrying the seconds the attempt was last seen working;
- a step that never comes back stops on the execution budget and is never
  excluded;
- a `stall` is a judgement, not a connection loss: it starts attempt 2;
- a retry after a reattach, whichever route opened the reattach - a host
  loss in this run or a supervisor death answered by `--resume` - answers
  the reattach's verdict with a new attempt number in a directory of its
  own.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import replace

from ohflow import attempts as ohattempts
from ohflow.engine import Engine
from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunLog, RunState
from ohflow.workflow import RetryPolicy
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, quiet,
                     read_run_log, simple_workflow, step_statuses,
                     stub_preflight)

HOST_LOST = ("host_lost: ssh exited 255; the host on fakebox ended without "
             "durable_end")
COORD = "01.only-phase/01.s1"


class DurableFake(FakeHarnessExecutor):
    """The engine's view of the durable harness executor: one that reattaches."""

    name = "durable"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.specs: list[dict] = []

    def launch(self, spec, out_dir):
        self.specs.append(dict(spec))
        handle = super().launch(spec, out_dir)
        (out_dir / "remote.json").write_text(json.dumps({
            "box": "fakebox", "key": "fake-key",
            "branch": "ohflow/durable/fake-key",
            "remote_url": "nowhere", "start_sha": "abc123",
            "dir": r"C:\Users\<user>\.pi-durable\ohflow\fake-key"}),
            encoding="utf-8")
        return handle


def durable_step(**changes):
    step = agent_step("s1")
    step = replace(step, agent=replace(step.agent, harness_executor="durable"))
    return replace(step, **changes) if changes else step


class Reattach(TempCase):

    def _engine(self, workflow, run_dir, resume=False):
        return Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                      resume=resume, harness_executors=self.harness_executors)

    def _open_attempt(self, workflow, run_dir, *, seen_working_after=None):
        """The run log and attempt directory a dead supervisor leaves behind.

        Attempt 1 is started and never closed. `seen_working_after` stamps the
        newest file in the attempt's `logs/` folder that many seconds after the
        attempt started: the last moment it was seen working.
        """
        fp = fingerprint(workflow, RunState(), workflow.phases[0].steps[0])
        opener = self._engine(workflow, run_dir)
        opener._transition("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        opener._transition("attempt_started", coord_=COORD, attempt=1, payload={
            "step_id": "s1", "kind": "agent", "fingerprint": fp,
            "start_kind": "initial"})
        attempt_dir = (run_dir / "phases" / "01.only-phase" / "01.s1"
                       / "attempts" / "01")
        attempt_dir.mkdir(parents=True)
        (attempt_dir / "spec.json").write_text(json.dumps(
            {"coord": COORD, "attempt": 1, "harness_executor": "durable"}),
            encoding="utf-8")
        (attempt_dir / "remote.json").write_text(json.dumps(
            {"box": "fakebox", "key": "fake-key",
             "branch": "ohflow/durable/fake-key", "remote_url": "nowhere",
             "start_sha": "abc123"}), encoding="utf-8")
        if seen_working_after is not None:
            logs = attempt_dir / "logs"
            logs.mkdir()
            seen = logs / "durable-events.jsonl"
            seen.write_text("", encoding="utf-8")
            at = time.time() + float(seen_working_after)
            os.utime(seen, (at, at))
        return attempt_dir

    def _events(self, run_dir, name):
        return [r for r in read_run_log(run_dir)
                if r["event"] == name and r.get("coord") == COORD]

    def test_a_host_loss_once_closes_deferred_and_reattaches_the_same_attempt(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript(
            sequence=[{"error": HOST_LOST}, {"error": None}],
            on_poll=lambda: time.sleep(1.2))))
        workflow = simple_workflow(git_repo(self.tmp / "repo"),
                                   steps=[durable_step()])
        run_dir = self.run_dir()
        with quiet():
            self._engine(workflow, run_dir).run()

        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([r["attempt"] for r in starts], [1, 1])
        self.assertEqual([r["payload"]["start_kind"] for r in starts],
                         ["initial", "reattach"])
        finishes = self._events(run_dir, "attempt_finished")
        self.assertEqual(len(finishes), 2)
        closed = finishes[0]["payload"]
        self.assertEqual(closed["status"], "deferred")
        self.assertTrue(closed["abort_victim"])
        self.assertTrue(closed["reattached"])
        self.assertIn("host_lost", closed["error"])
        # The closure carries the execution's measured wall time, so hours of
        # work before a host loss are not recorded as 0.0.
        self.assertGreaterEqual(closed["wall_seconds"], 1.0)
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        state = RunLog.replay(run_dir)
        self.assertEqual(ohattempts.failed_executions(state, COORD), 0)
        self.assertEqual(ohattempts.attempts(state, COORD), 2)

    def test_a_reattach_launches_with_the_spec_of_the_attempt_it_continues(self):
        stub_preflight(self)
        fake = install_fake_harness_executor(self, DurableFake(default=AgentScript(
            sequence=[{"error": HOST_LOST}, {"error": None}])))
        step = durable_step()
        step = replace(step, agent=replace(step.agent, skills=("codebase-design",)))
        workflow = simple_workflow(git_repo(self.tmp / "repo"), steps=[step])
        with quiet():
            self._engine(workflow, self.run_dir()).run()

        first, second = fake.specs
        self.assertEqual(first["skills"], ["codebase-design"])
        self.assertTrue(second.pop("reattach"))
        self.assertEqual(second, first)

    def test_a_resume_reattaches_an_attempt_the_supervisor_left_open(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript()))
        workflow = simple_workflow(git_repo(self.tmp / "repo"),
                                   steps=[durable_step()])
        run_dir = self.run_dir()
        attempt_dir = self._open_attempt(workflow, run_dir)

        with quiet():
            self._engine(workflow, run_dir, resume=True).run()

        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts],
                         [(1, "initial"), (1, "reattach")])
        finishes = self._events(run_dir, "attempt_finished")
        self.assertEqual(finishes[0]["payload"]["status"], "deferred")
        self.assertTrue(finishes[0]["payload"]["abort_victim"])
        self.assertTrue(finishes[0]["payload"]["reattached"])
        self.assertIn("the supervisor stopped while this attempt ran",
                      finishes[0]["payload"]["error"])
        # No file in the attempt's logs/ folder: nothing was ever seen working.
        self.assertEqual(finishes[0]["payload"]["wall_seconds"], 0.0)
        # The reattach continued in the interrupted attempt's own directory,
        # and its spec told the host a session file is already there.
        spec = json.loads((attempt_dir / "spec.json").read_text(encoding="utf-8"))
        self.assertTrue(spec["reattach"])
        self.assertEqual(spec["attempt"], 1)

    def test_a_resume_closes_the_open_attempt_with_the_time_it_was_seen_working(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript()))
        workflow = simple_workflow(git_repo(self.tmp / "repo"),
                                   steps=[durable_step()])
        run_dir = self.run_dir()
        # The attempt worked for half a minute after it started, and the newest
        # file in its logs/ folder is the last moment it was seen working.
        self._open_attempt(workflow, run_dir, seen_working_after=30)

        with quiet():
            self._engine(workflow, run_dir, resume=True).run()

        finishes = self._events(run_dir, "attempt_finished")
        self.assertEqual(finishes[0]["payload"]["status"], "deferred")
        wall = finishes[0]["payload"]["wall_seconds"]
        self.assertGreaterEqual(wall, 29.0)
        self.assertLessEqual(wall, 32.0)

    def test_a_step_that_never_comes_back_stops_on_the_execution_budget(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript(
            sequence=[{"error": HOST_LOST}])))
        workflow = simple_workflow(git_repo(self.tmp / "repo"),
                                   steps=[durable_step()])
        run_dir = self.run_dir()
        with quiet():
            self._engine(workflow, run_dir).run()

        self.assertEqual(step_statuses(run_dir)[COORD], "deferred")
        decisions = self._events(run_dir, "retry_decided")
        self.assertIn("execution budget spent",
                      decisions[-1]["payload"]["retry_decision"])
        state = RunLog.replay(run_dir)
        self.assertEqual(ohattempts.attempts(state, COORD), 2)
        self.assertEqual(ohattempts.failed_executions(state, COORD), 0)
        self.assertEqual(state.exclusions, {})

    def test_a_stall_starts_attempt_2_not_a_reattach(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript(
            sequence=[{"error": "stall"}, {"error": None}])))
        workflow = simple_workflow(git_repo(self.tmp / "repo"), steps=[durable_step(
            retry=RetryPolicy(max=1, on=("agent_error",)))])
        run_dir = self.run_dir()
        with quiet():
            self._engine(workflow, run_dir).run()

        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts],
                         [(1, "initial"), (2, "retry")])
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        finishes = self._events(run_dir, "attempt_finished")
        self.assertFalse(finishes[0]["payload"].get("reattached"))

    def test_a_retry_after_a_host_lost_reattach_mints_its_own_attempt(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript(
            sequence=[{"error": HOST_LOST}, {"error": "stall"},
                      {"error": None}])))
        workflow = simple_workflow(git_repo(self.tmp / "repo"),
                                   steps=[durable_step(
                                       retry=RetryPolicy(max=2, on=("agent_error",)))])
        run_dir = self.run_dir()
        with quiet():
            self._engine(workflow, run_dir).run()

        # The reattach continues attempt 1, and the verdict it reached - a
        # stall - is answered by a retry with a number of its own, not by a
        # second execution handed the reattach's number.
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts],
                         [(1, "initial"), (1, "reattach"), (2, "retry")])
        second = (run_dir / "phases" / "01.only-phase" / "01.s1"
                  / "attempts" / "02")
        spec = json.loads((second / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["attempt"], 2)
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")

    def test_a_retry_after_a_resume_reattach_mints_its_own_attempt(self):
        stub_preflight(self)
        install_fake_harness_executor(self, DurableFake(default=AgentScript(
            sequence=[{"error": "stall"}, {"error": None}])))
        workflow = simple_workflow(git_repo(self.tmp / "repo"),
                                   steps=[durable_step(
                                       retry=RetryPolicy(max=1, on=("agent_error",)))])
        run_dir = self.run_dir()
        attempt_dir = self._open_attempt(workflow, run_dir)

        with quiet():
            self._engine(workflow, run_dir, resume=True).run()

        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts],
                         [(1, "initial"), (1, "reattach"), (2, "retry")])
        second = attempt_dir.parent / "02"
        spec = json.loads((second / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["attempt"], 2)
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
