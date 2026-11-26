from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from ohflow import harness_executor as ohexecutor
from ohflow import kill as ohkill
from ohflow import rundir
from ohflow.engine import Engine
from ohflow.proc import pid_alive
from ohflow.run_log import RunLog
from ohflow.workflow import RetryPolicy, Step
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, read_run_log,
                     simple_workflow, stub_preflight)
from verb_support import call

VICTIM = "01.only-phase/01.victim"
SIBLING = "01.only-phase/02.sibling"
REASON = "it reruns the full suite"
SAFETY_S = 30.0


def _running(run_dir, coord: str, attempt: int = 1) -> bool:
    if not (run_dir / "run-log.jsonl").exists():
        return False
    state = RunLog.replay(run_dir)
    return any(ex.get("coord") == coord and ex.get("attempt") == attempt
               and ex.get("status") == "running" for ex in state.executions)


def _until(predicate, timeout: float = SAFETY_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class _Killer(threading.Thread):

    def __init__(self, run_dir, step: str, *extra: str, ready=lambda: True):
        super().__init__(daemon=True)
        self.run_dir, self.step, self.extra, self.ready = run_dir, step, extra, ready
        self.code: int | None = None
        self.lines: list[str] = []

    def run(self) -> None:
        coord = VICTIM if self.step == "victim" else self.step
        if not _until(lambda: _running(self.run_dir, coord) and self.ready()):
            return
        self.code, self.lines = call("kill", "--run", self.run_dir, "--step",
                                     self.step, "--timeout", "20", *self.extra)


def _hung(started: float) -> AgentScript:
    return AgentScript(
        exit_status=ohexecutor.RUNNING,
        on_poll=lambda: (ohexecutor.FINISHED
                         if time.monotonic() - started > SAFETY_S else None))


def _waits_for_the_kill(fake: FakeHarnessExecutor, started: float) -> AgentScript:
    return AgentScript(
        exit_status=ohexecutor.RUNNING,
        on_poll=lambda: (ohexecutor.FINISHED
                         if VICTIM in fake.killed
                         or time.monotonic() - started > SAFETY_S else None))


class KillOneStep(TempCase):

    def setUp(self) -> None:
        super().setUp()
        stub_preflight(self)
        self.repo = git_repo(self.tmp / "repo")

    def _engine(self, workflow, run_dir, *, resume: bool = False) -> Engine:
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        resume=resume, harness_executors=self.harness_executors)
        engine.poll_interval_s = 0.02
        return engine

    def _kill_run(self, workflow=None, *extra: str):
        started = time.monotonic()
        fake = install_fake_harness_executor(self, FakeHarnessExecutor())
        fake.scripts = {"victim": _hung(started),
                        "sibling": _waits_for_the_kill(fake, started)}
        workflow = workflow or simple_workflow(
            self.repo, steps=[agent_step("victim"), agent_step("sibling")],
            max_parallel=2)
        run_dir = self.run_dir()
        killer = _Killer(run_dir, "victim", "--reason", REASON, *extra)
        killer.start()
        summary = self._engine(workflow, run_dir).run()
        killer.join(timeout=SAFETY_S)
        return fake, run_dir, killer, summary

    def test_the_named_step_ends_and_its_sibling_passes(self):
        fake, run_dir, killer, summary = self._kill_run()

        self.assertEqual(killer.code, 0, killer.lines)
        self.assertEqual(killer.lines[0],
                         f"KILLED {VICTIM} attempt 1: killed by ohflow kill: {REASON}")
        self.assertEqual(fake.killed, [VICTIM])
        state = RunLog.replay(run_dir)
        self.assertEqual(state.steps[VICTIM].status, "deferred")
        self.assertEqual(state.steps[SIBLING].status, "passed")
        self.assertEqual(state.status, "paused")
        self.assertEqual(summary["status"], "paused")

    def test_the_run_log_records_the_kill_and_its_reason(self):
        _fake, run_dir, _killer, _summary = self._kill_run()

        finish = [r for r in read_run_log(run_dir)
                  if r["event"] == "attempt_finished" and r["coord"] == VICTIM]
        self.assertEqual(len(finish), 1)
        payload = finish[0]["payload"]
        self.assertEqual(payload["status"], "deferred")
        self.assertTrue(payload["abort_victim"])
        self.assertEqual(payload["error"], f"killed by ohflow kill: {REASON}")
        self.assertEqual(payload["killed"]["reason"], REASON)
        self.assertTrue(payload["killed"]["requested_at"])
        self.assertEqual(payload["gate"]["checks"], [])
        step_dir = rundir.step_dir(run_dir, VICTIM)
        self.assertFalse((step_dir / ohkill.REQUEST).exists())
        evidence = json.loads((rundir.attempt_dir(run_dir, VICTIM, 1)
                               / ohkill.REQUEST).read_text(encoding="utf-8"))
        self.assertEqual((evidence["attempt"], evidence["reason"]), (1, REASON))

    def test_the_kill_spends_no_retry_and_no_auto_resume(self):
        victim = replace(agent_step("victim"), retry=RetryPolicy(
            max=1, on=("agent_error", "gate:final_message_matches")))
        workflow = replace(simple_workflow(
            self.repo, steps=[victim, agent_step("sibling")], max_parallel=2),
            auto_resume=1)
        fake, run_dir, killer, _summary = self._kill_run(workflow)

        self.assertEqual(killer.code, 0, killer.lines)
        self.assertEqual(fake.launched.count(VICTIM), 1)
        state = RunLog.replay(run_dir)
        self.assertIn("ohflow kill ended", state.steps[VICTIM].retry_decision)
        self.assertEqual(state.status, "paused")

    def test_a_resume_runs_the_killed_step_again(self):
        _fake, run_dir, _killer, _summary = self._kill_run()
        fake = install_fake_harness_executor(self, FakeHarnessExecutor())
        workflow = simple_workflow(
            self.repo, steps=[agent_step("victim"), agent_step("sibling")],
            max_parallel=2)

        self._engine(workflow, run_dir, resume=True).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(fake.launched, [VICTIM])
        self.assertEqual(state.steps[VICTIM].status, "passed")
        self.assertEqual(state.steps[VICTIM].attempt, 2)
        self.assertEqual(state.steps[SIBLING].status, "cached")
        self.assertEqual(state.status, "finished")

    def test_the_reason_reaches_the_next_attempt_position(self):
        _fake, run_dir, _killer, _summary = self._kill_run()
        install_fake_harness_executor(self, FakeHarnessExecutor())
        workflow = simple_workflow(
            self.repo, steps=[agent_step("victim"), agent_step("sibling")],
            max_parallel=2)

        self._engine(workflow, run_dir, resume=True).run()

        position = (rundir.attempt_dir(run_dir, VICTIM, 2)
                    / "position.md").read_text(encoding="utf-8")
        self.assertIn("What failed last time (attempt 1):\n"
                      f"  killed by ohflow kill: {REASON}\n", position)

    def test_a_stale_request_does_not_kill_the_next_attempt(self):
        _fake, run_dir, _killer, _summary = self._kill_run()
        step_dir = rundir.step_dir(run_dir, VICTIM)
        (step_dir / ohkill.REQUEST).write_text(
            json.dumps({"attempt": 2, "reason": "left behind before attempt 2 began"}),
            encoding="utf-8")
        install_fake_harness_executor(self, FakeHarnessExecutor())
        workflow = simple_workflow(
            self.repo, steps=[agent_step("victim"), agent_step("sibling")],
            max_parallel=2)

        self._engine(workflow, run_dir, resume=True).run()

        self.assertEqual(RunLog.replay(run_dir).steps[VICTIM].status, "passed")
        self.assertFalse((step_dir / ohkill.REQUEST).exists())

    def test_a_step_with_no_running_attempt_is_refused(self):
        _fake, run_dir, _killer, _summary = self._kill_run()

        code, lines = call("kill", "--run", run_dir, "--step", "sibling")

        self.assertEqual(code, 1)
        self.assertEqual(lines, [f"NOT KILLED sibling: {SIBLING} has no running "
                                 f"attempt: its latest attempt 1 ended passed"])

    def test_a_run_without_a_live_supervisor_is_refused(self):
        _fake, run_dir, _killer, _summary = self._kill_run()
        (run_dir / "supervisor.pid").write_text("4194300", encoding="utf-8")
        self.assertFalse(pid_alive(4194300))

        code, lines = call("kill", "--run", run_dir, "--step", "victim")

        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith("NOT KILLED victim: no live supervisor"),
                        lines)

    def test_a_command_step_ends_with_its_process(self):
        marker = self.tmp / "child.pid"
        script = self.tmp / "sleeper.py"
        script.write_text(
            "import os, pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
            "time.sleep(120)\n", encoding="utf-8")
        command = Step(id="victim", kind="command", shell="sh",
                       command=" ".join(f'"{Path(p).as_posix()}"'
                                        for p in (sys.executable, script, marker)),
                       execution_timeout_s=300)
        started = time.monotonic()
        fake = install_fake_harness_executor(self, FakeHarnessExecutor())
        fake.scripts = {"sibling": AgentScript(
            exit_status=ohexecutor.RUNNING,
            on_poll=lambda: (ohexecutor.FINISHED
                             if not _running(run_dir, VICTIM) and marker.exists()
                             or time.monotonic() - started > SAFETY_S else None))}
        workflow = simple_workflow(self.repo, steps=[command, agent_step("sibling")],
                                   max_parallel=2)
        run_dir = self.run_dir()
        killer = _Killer(run_dir, "victim", "--reason", REASON, ready=marker.exists)
        killer.start()

        self._engine(workflow, run_dir).run()
        killer.join(timeout=SAFETY_S)

        self.assertEqual(killer.code, 0, killer.lines)
        self.assertLess(time.monotonic() - started, SAFETY_S)
        state = RunLog.replay(run_dir)
        self.assertEqual(state.steps[VICTIM].status, "deferred")
        self.assertEqual(state.steps[VICTIM].killed["reason"], REASON)
        self.assertEqual(state.steps[SIBLING].status, "passed")
        pid = int(marker.read_text(encoding="utf-8"))
        self.assertTrue(_until(lambda: not pid_alive(pid), 15))
        log = rundir.attempt_dir(run_dir, VICTIM, 1) / "logs" / "step-victim.err.log"
        self.assertIn("[ohflow] stopped on request", log.read_text(encoding="utf-8"))
