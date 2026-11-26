"""Defect 73: an attempt killed with its supervisor stayed `running` for ever.

A supervisor killed while an agent ran leaves an `attempt_started` with no
`attempt_finished`. The read-outs call the run `orphaned` and the step
interrupted, and they derive both from a dead pid. The run log itself never
learned it: `--resume` started the next attempt beside the open one, the open
one replayed as `running` from then on, and a resumed run showed it running
while nothing ran.

Now `--resume` closes it before any step starts. The supervisor is the one
writer of the run log, so the resume is where the closure is written: one
`attempt_finished` per killed attempt, `deferred` with `abort_victim` and
`interrupted`. That is how a killed-in-flight abort victim closes, so no bound
changes: the start still spends from the total, and nothing counts toward the
exclusion. `status` and `watch` stay read-only.

A finish for an attempt older than the one the step is on closes that execution
and leaves the step's own record alone, so a run log from before this fix, with
attempt 1 open beside a passed attempt 2, settles without undoing the pass.

The closure is for a dead supervisor's attempts only. A resume of a run whose
recorded supervisor still runs it is refused before it writes a word, by the
supervisor and by the `run --detach` launcher before it starts one: beside a
live supervisor it closed attempts that still worked, and the live
supervisor's own results were then refused as already closed.

An open attempt of a step whose harness executor reattaches is left to the
reattach rule. When that rule finds nothing to continue, here a launch that
never reached the box, the attempt closes the same way as the step starts.
"""

from __future__ import annotations

from unittest import mock

from ohflow import attempts as ohattempts
from ohflow import cli, detach
from ohflow.engine import Engine
from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunLog, RunState
from ohflow.supervisor import RunOptions, run_workflow
from ohflow.workflow import Phase
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, quiet,
                     read_run_log, simple_workflow, step_statuses,
                     stub_preflight)
from verb_support import call, live_child
from test_durable_03_reattach import DurableFake, durable_step

COORD = "01.only-phase/01.flaky"
REASON = "the supervisor stopped before this attempt finished"


class KilledAttemptCase(TempCase):

    def _workflow(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        self.fake = install_fake_harness_executor(self, FakeHarnessExecutor(
            default=AgentScript(final_text="DONE\n")))
        return simple_workflow(repo, phases=(
            Phase(name="Only phase", steps=(agent_step("flaky"),)),))

    def _engine(self, workflow, run_dir, resume=False):
        return Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                      resume=resume, harness_executors=self.harness_executors)

    def _killed(self, workflow, run_dir, attempts=(1,)):
        """What a supervisor killed while the attempt ran leaves behind."""
        fp = fingerprint(workflow, RunState(), workflow.phases[0].steps[0])
        engine = self._engine(workflow, run_dir)
        engine.run_dir.mkdir(parents=True, exist_ok=True)
        engine.run_log.append("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        for attempt in attempts:
            engine.run_log.append("attempt_started", coord=COORD,
                                  attempt=attempt, payload={
                "step_id": "flaky", "kind": "agent", "fingerprint": fp,
                "start_kind": "initial"})
        return engine

    def _open(self, run_dir):
        return [e["attempt"] for e in RunLog.replay(run_dir).executions
                if e.get("started") and e.get("status") == "running"]


class AKilledAttemptSettlesOnResume(KilledAttemptCase):

    def test_a_resume_closes_the_killed_attempt_before_the_next_one_starts(self):
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        self.assertEqual(self._open(run_dir), [1])

        self._engine(workflow, run_dir, resume=True).run()

        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        self.assertEqual(self._open(run_dir), [],
                         "the killed attempt still replays as running")
        records = [r for r in read_run_log(run_dir) if r.get("coord") == COORD
                   and r["event"] in ("attempt_started", "attempt_finished")]
        self.assertEqual([(r["event"], r["attempt"]) for r in records], [
            ("attempt_started", 1), ("attempt_finished", 1),
            ("attempt_started", 2), ("attempt_finished", 2)])
        closure = records[1]["payload"]
        self.assertEqual(closure["status"], "deferred")
        self.assertTrue(closure["abort_victim"])
        self.assertTrue(closure["interrupted"])
        self.assertEqual(closure["error"], REASON)
        self.assertEqual(closure["step_id"], "flaky")
        self.assertEqual(len(self.fake.launched), 1)

    def test_the_closure_moves_no_bound(self):
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir, attempts=(1, 2))

        self._engine(workflow, run_dir, resume=True).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(self._open(run_dir), [])
        self.assertEqual(ohattempts.attempts(state, COORD), 2)
        self.assertEqual(ohattempts.abort_victims(state, COORD), 2)
        self.assertEqual(ohattempts.failed_executions(state, COORD), 0,
                         "a supervisor death is not a counted failure")
        self.assertEqual(state.exclusions, {})
        self.assertEqual(len(self.fake.launched), 0,
                         "two starts spent the total budget of two")
        self.assertIn("execution budget spent", state.steps[COORD].error)

    def test_a_second_resume_writes_no_second_closure(self):
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        self._engine(workflow, run_dir, resume=True).run()
        self._engine(workflow, run_dir, resume=True).run()

        closures = [r for r in read_run_log(run_dir)
                    if r["event"] == "attempt_finished"
                    and r.get("coord") == COORD and r["attempt"] == 1]
        self.assertEqual(len(closures), 1)

    def test_a_closure_for_an_older_attempt_leaves_a_passed_step_passed(self):
        """A run log from before the fix: attempt 1 open, attempt 2 passed."""
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        run_log = RunLog(run_dir)
        run_log.append("attempt_started", coord=COORD, attempt=2, payload={
            "step_id": "flaky", "kind": "agent", "fingerprint": "unknown",
            "start_kind": "initial"})
        run_log.append("attempt_finished", coord=COORD, attempt=2, payload={
            "status": "passed", "step_id": "flaky", "kind": "agent",
            "fingerprint": "unknown"})
        run_log.append("attempt_finished", coord=COORD, attempt=1, payload={
            "status": "deferred", "step_id": "flaky", "kind": "agent",
            "fingerprint": "unknown", "error": REASON, "abort_victim": True,
            "interrupted": True})

        state = RunLog.replay(run_dir)
        step = state.steps[COORD]
        self.assertEqual((step.status, step.attempt, step.error),
                         ("passed", 2, None))
        rows = ohattempts.executions(state, COORD)
        self.assertEqual([(r["attempt"], r["status"]) for r in rows],
                         [(1, "deferred"), (2, "passed")])
        self.assertTrue(rows[0]["abort_victim"])

    def test_a_durable_attempt_that_cannot_reattach_closes_the_same_way(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        fake = install_fake_harness_executor(self, DurableFake(
            default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[durable_step()])
        coord = "01.only-phase/01.s1"
        run_dir = self.run_dir()
        fp = fingerprint(workflow, RunState(), workflow.phases[0].steps[0])
        run_dir.mkdir(parents=True, exist_ok=True)
        run_log = RunLog(run_dir)
        run_log.append("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        run_log.append("attempt_started", coord=coord, attempt=1, payload={
            "step_id": "s1", "kind": "agent", "fingerprint": fp,
            "start_kind": "initial"})

        self._engine(workflow, run_dir, resume=True).run()

        self.assertEqual(step_statuses(run_dir)[coord], "passed")
        records = [r for r in read_run_log(run_dir) if r.get("coord") == coord
                   and r["event"] in ("attempt_started", "attempt_finished")]
        self.assertEqual([(r["event"], r["attempt"]) for r in records], [
            ("attempt_started", 1), ("attempt_finished", 1),
            ("attempt_started", 2), ("attempt_finished", 2)])
        closure = records[1]["payload"]
        self.assertEqual(closure["status"], "deferred")
        self.assertTrue(closure["abort_victim"])
        self.assertTrue(closure["interrupted"])
        self.assertNotIn("reattached", closure)
        self.assertEqual(closure["error"], REASON)
        self.assertEqual(records[2]["payload"]["start_kind"], "initial")
        self.assertEqual(len(fake.launched), 1)


MODULE = """
from pathlib import Path
from ohflow.workflow import Phase, Workflow, Step

def build(args):
    step = Step(id="a", kind="command", command="echo DONE")
    return Workflow(name="beside", repo=Path(args["repo"]),
                    phases=(Phase(name="P", steps=(step,)),))
"""


class AResumeBesideALiveSupervisorIsRefused(KilledAttemptCase):

    def _resume(self, workflow, run_dir, **options):
        with quiet():
            return run_workflow(workflow, run_dir, RunOptions(
                resume="yes", dashboard=False, estimate=False,
                harness_executors=self.harness_executors,
                say=lambda _line: None, **options))

    def test_the_resume_writes_nothing_while_the_supervisor_runs(self):
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        supervisor = live_child(self).pid
        (run_dir / "supervisor.pid").write_text(str(supervisor),
                                                encoding="utf-8")
        before = sorted(p.name for p in run_dir.iterdir())
        log = (run_dir / "run-log.jsonl").read_bytes()

        outcome = self._resume(workflow, run_dir)

        self.assertEqual(outcome.status, "refused")
        self.assertIn(f"still running under supervisor pid {supervisor}",
                      outcome.problem)
        self.assertEqual(len(outcome.problem.splitlines()), 1)
        self.assertEqual((run_dir / "run-log.jsonl").read_bytes(), log)
        self.assertEqual(sorted(p.name for p in run_dir.iterdir()), before)
        self.assertEqual(self._open(run_dir), [1])
        self.assertEqual(self.fake.launched, [])

    def test_a_dead_supervisor_is_resumed(self):
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        gone = live_child(self)
        gone.kill()
        gone.wait()
        (run_dir / "supervisor.pid").write_text(str(gone.pid),
                                                encoding="utf-8")

        outcome = self._resume(workflow, run_dir)

        self.assertEqual(outcome.status, "finished")
        self.assertEqual(self._open(run_dir), [])

    def test_a_stopped_run_is_resumed_whatever_its_record_names(self):
        """A campaign runs many runs in one process, so the record of a run
        that stopped may name a process that lives on."""
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir, attempts=())
        RunLog(run_dir).append("run_finished", payload={"status": "paused"})
        (run_dir / "supervisor.pid").write_text(str(live_child(self).pid),
                                                encoding="utf-8")

        outcome = self._resume(workflow, run_dir)

        self.assertEqual(outcome.status, "finished")
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")

    def test_the_detached_supervisor_trusts_the_launcher_that_asked(self):
        """The launcher writes the pid of the process it started, which may be
        a wrapper around the supervisor, before the supervisor looks."""
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        (run_dir / "supervisor.pid").write_text(str(live_child(self).pid),
                                                encoding="utf-8")

        outcome = self._resume(workflow, run_dir, resume_checked=True)

        self.assertEqual(outcome.status, "finished")
        self.assertEqual(self._open(run_dir), [])

    def test_the_launcher_refuses_before_it_starts_a_supervisor(self):
        workflow = self._workflow()
        run_dir = self.run_dir()
        self._killed(workflow, run_dir)
        supervisor = live_child(self).pid
        (run_dir / "supervisor.pid").write_text(str(supervisor),
                                                encoding="utf-8")
        module = self.tmp / "workflow.py"
        module.write_text(MODULE, encoding="utf-8")
        launches: list = []

        def launch(argv, **kw):
            launches.append(argv)
            return detach.Launched(pid=supervisor, method="direct")

        def detached():
            with mock.patch.object(detach, "launch", launch):
                return call(
                    "run", "--workflow", module, "--out", run_dir.parent,
                    "--resume", run_dir.name, "--detach", "--no-dashboard",
                    "--args", f"repo={(self.tmp / 'repo').as_posix()}")

        code, lines = detached()
        self.assertEqual(code, cli.EXIT_FAIL, lines)
        self.assertEqual(lines, [
            f"run {run_dir.name} is still running under supervisor pid "
            f"{supervisor}; resume it once that supervisor has stopped: "
            f"{cli.win(run_dir)}"])
        self.assertEqual(launches, [])
        self.assertEqual((run_dir / "supervisor.pid").read_text(
            encoding="utf-8"), str(supervisor))

        (run_dir / "supervisor.pid").write_text("2147483646", encoding="utf-8")
        code, lines = detached()
        self.assertEqual(code, cli.EXIT_OK, lines)
        self.assertEqual(len(launches), 1)
        self.assertIn("--resume-checked", launches[0])
