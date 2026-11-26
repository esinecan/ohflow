"""Defect 3: a step thread that faults before it runs records its own failure.

Fixed in `15dae59`, "ohflow: a step thread records its own fault instead of
vanishing".

What went wrong. `_execute_step` guards its own body, but the step directory it
prepares first was outside that guard. A fault in `_prepare_step_dir` therefore
killed the step thread with the step still `pending`. The phase then settled
on a state nothing had written, and the run reported a step that had neither
started nor failed.

What is asserted here. The fault is real, not injected: the step directory is
occupied by a file, so `(d / "logs").mkdir(parents=True)` raises the way the
operating system raises it. After the phase settles, the step has a terminal
record naming the exception, and the phase's own settlement saw it.

This file also guards the tenth defect this suite found, which is described in
`ATenthDefect` below.
"""

from __future__ import annotations

from ohflow import failure
from ohflow.engine import Engine
from ohflow.run_log import TERMINAL, RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, simple_workflow, step_statuses,
                     stub_preflight, agent_step)


class AFaultBeforeTheStepRunsIsRecorded(TempCase):

    def _blocked_run(self, on_step_failure: str = "quarantine"):
        """A run in which step `blocked`'s directory is occupied by a file."""
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(
            repo,
            steps=[agent_step("blocked"), agent_step("healthy")],
            on_step_failure=on_step_failure,
            max_parallel=2,
        )
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        # The run owns its directory before the fixture injects a fault inside
        # that owned space. A different Engine must not be allowed to adopt a
        # directory containing this file.
        engine._reserve_run_dir()
        # Put a plain file exactly where the step directory must go. The first
        # thing `_prepare_step_dir` does is create `<step dir>/logs`, and that
        # now raises from the operating system.
        blocked = run_dir / "phases" / "01.only-phase" / "01.blocked"
        blocked.parent.mkdir(parents=True, exist_ok=True)
        blocked.write_text("not a directory", encoding="utf-8")

        summary = engine.run()
        return engine, run_dir, summary

    def test_the_faulting_step_reaches_a_terminal_state(self):
        _engine, run_dir, _summary = self._blocked_run()
        statuses = step_statuses(run_dir)
        blocked = "01.only-phase/01.blocked"
        self.assertIn(blocked, statuses,
                      "the thread vanished and wrote no record at all")
        self.assertIn(statuses[blocked], TERMINAL,
                      f"the step is still {statuses[blocked]!r}; a phase must "
                      "never settle on a state nothing wrote")
        self.assertNotEqual(statuses[blocked], "pending")

    def test_the_record_names_the_exception(self):
        _engine, run_dir, _summary = self._blocked_run()
        state = RunLog.replay(run_dir)
        rec = state.steps["01.only-phase/01.blocked"]
        self.assertTrue(rec.error, "the fault was swallowed")
        self.assertRegex(rec.error, r"^[A-Za-z]+Error:",
                         "the record must name the exception type")
        self.assertEqual(rec.failure_class, failure.STRUCTURAL,
                         "a fault in the orchestrator's own code is structural")

    def test_the_step_beside_it_still_runs(self):
        _engine, run_dir, _summary = self._blocked_run()
        statuses = step_statuses(run_dir)
        self.assertEqual(statuses["01.only-phase/02.healthy"], "passed",
                         "one bad step directory took the whole phase down")

    def test_the_phase_settles_and_the_run_finishes(self):
        _engine, run_dir, summary = self._blocked_run()
        state = RunLog.replay(run_dir)
        self.assertIn("01.only-phase", state.phases)
        self.assertIn(state.phases["01.only-phase"].get("status"),
                      ("failed", "deferred", "passed"))
        self.assertIsNotNone(state.finished,
                             "the run never reached run_finished")
        self.assertIn(summary["status"], ("failed", "finished", "paused"))

    def test_an_abort_policy_still_fires_on_such_a_fault(self):
        """The guard records the failure and then lets the policy act, rather
        than swallowing it into silence."""
        engine, _run_dir, _summary = self._blocked_run(on_step_failure="abort")
        self.assertTrue(engine._abort.is_set())


class ATenthDefect(TempCase):
    """An agent step with no worktree used to raise inside its own thread.

    Found while writing this suite, on 2026-09-16, and fixed in the same branch.

    `Step.worktree` is `str | None`, and `None` means "work in the repository
    itself". Six places implement that: `Engine._execute_step`,
    `coords._worktree_facts`, `coords._after`, `fingerprint.fingerprint_input`,
    `report.render_board_md` and `Engine._execute_step`'s head-sha read. The
    seventh, `Engine._prepare_step_dir`, called `workflow.worktree(None)`
    unconditionally and raised `KeyError: no worktree named None`.

    Nothing shipped hits it, because every workflow in `scripts/ohflow/workflows` gives
    its agents a worktree. It surfaced the moment a test wrote the simplest
    possible agent workflow. Before defect 3 was fixed it would have been invisible:
    the thread would have died silently with the step still `pending`.
    """

    def test_an_agent_step_with_no_worktree_prepares_against_the_repo(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[agent_step("no-worktree")])
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        engine.run()

        statuses = step_statuses(run_dir)
        self.assertEqual(statuses["01.only-phase/01.no-worktree"], "passed")

        import json
        spec = json.loads(
            (run_dir / "phases" / "01.only-phase" / "01.no-worktree" /
             "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["workspace"].replace("/", "\\"),
                         str(repo).replace("/", "\\"),
                         "the workspace must fall back to the repository")
