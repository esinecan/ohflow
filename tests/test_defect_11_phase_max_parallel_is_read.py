"""Defect 11: a phase declared its own concurrency limit and the engine ignored it.

What went wrong. `Phase.max_parallel` has existed since the workflow model was
written. `Engine.__init__` built one run-wide semaphore from the workflow default and
`_guarded_step` acquired it, so a phase value was parsed, validated, written into
`workflow.json`, and never read. `mcp_cli_pruning.py` sets it on two phases; both
happen to equal that workflow's default, which is why no production run ever showed
the deadness.

What is asserted here. A phase runs at its own limit, above or below the workflow
default. `--max-parallel` sets the default and also caps every phase, so an
operator can throttle a whole run without editing a workflow. A detached run
forwards the flag only when it was given, because forwarding the workflow default
would silently cap every phase override. `--max-parallel 0` is a fault rather
than a synonym for absent. Every numeric knob rejects a boolean, because
`isinstance(True, int)` is true in Python and a workflow that wrote `max_parallel=
True` would otherwise run at one agent and never be told.

The peak is measured in the fake harness executor, where the semaphore actually binds: a
launch holds its slot until it returns, and the harness executor counts how many were in
flight at once.
"""

from __future__ import annotations

from ohflow.cli import main as cli_main
from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import Phase, Workflow, WorkflowError, validate
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight,
                     agent_step)


def _phase(name: str, ids: list[str], limit: int | None) -> Phase:
    return Phase(name=name, steps=tuple(agent_step(i) for i in ids),
                 on_step_failure="continue", min_success="any",
                 max_parallel=limit)


class APhaseRunsAtItsOwnLimit(TempCase):

    def _run(self, *, workflow_default: int, phase_limit: int | None,
             cli_limit: int | None = None, gate_at: int = 3):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        harness_executor = install_fake_harness_executor(self, FakeHarnessExecutor(
            default=AgentScript(final_text="DONE\n"), gate_at=gate_at))
        workflow = simple_workflow(repo, max_parallel=workflow_default, phases=(
            _phase("Only phase", ["a", "b", "c"], phase_limit),))
        run_dir = self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        max_parallel=cli_limit,
                        harness_executors=self.harness_executors)
        engine.run()
        return engine, harness_executor, run_dir

    def test_a_phase_below_the_workflow_default_holds_that_lower_limit(self):
        _engine, harness_executor, _run_dir = self._run(workflow_default=3, phase_limit=1)
        self.assertEqual(harness_executor.peak, 1,
                         "the phase asked for one agent and the engine ran "
                         f"{harness_executor.peak}")
        self.assertEqual(len(harness_executor.launched), 3, "every step must still run")

    def test_a_phase_above_the_workflow_default_gets_what_it_asked_for(self):
        """The phase value is the phase's own limit. It is not clamped to the
        workflow default, which is only the value for a phase that declares none."""
        _engine, harness_executor, _run_dir = self._run(workflow_default=1, phase_limit=3)
        self.assertEqual(harness_executor.peak, 3)

    def test_a_phase_that_declares_nothing_takes_the_workflow_default(self):
        _engine, harness_executor, _run_dir = self._run(workflow_default=2, phase_limit=None,
                                                        gate_at=2)
        self.assertEqual(harness_executor.peak, 2)

    def test_the_cli_value_caps_a_higher_phase_override(self):
        _engine, harness_executor, _run_dir = self._run(workflow_default=1, phase_limit=3,
                                                        cli_limit=2, gate_at=2)
        self.assertEqual(harness_executor.peak, 2,
                         "--max-parallel is a ceiling on every phase")

    def test_the_cli_value_does_not_raise_a_lower_phase_override(self):
        _engine, harness_executor, _run_dir = self._run(workflow_default=1, phase_limit=1,
                                                        cli_limit=3)
        self.assertEqual(harness_executor.peak, 1)


class TheEffectiveLimitIsOnTheRecord(TempCase):

    def test_the_run_log_and_the_board_both_carry_it(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, max_parallel=3, phases=(
            _phase("Only phase", ["a"], 1),))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(state.phases["01.only-phase"]["max_parallel"], 1,
                         "a run must record the limit it actually applied")
        board = (run_dir / "board.md").read_text(encoding="utf-8")
        self.assertIn("max_parallel", board)

    def test_the_limit_is_computed_without_running_anything(self):
        workflow = simple_workflow(self.tmp / "repo", max_parallel=4, phases=(
            _phase("wide", ["a"], 6), _phase("narrow", ["b"], 2),
            _phase("silent", ["c"], None)))
        run_dir = self.run_dir()
        free = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors)
        self.assertEqual([free.phase_limit(p) for p in workflow.phases], [6, 2, 4])
        capped = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        max_parallel=3,
                        harness_executors=self.harness_executors)
        self.assertEqual([capped.phase_limit(p) for p in workflow.phases], [3, 2, 3],
                         "the CLI value caps every phase and replaces the "
                         "workflow default for a phase that declares none")


class TheDetachedChildGetsTheSameInstruction(TempCase):
    """A detached run used to be handed `--max-parallel <workflow default>` whether
    or not the flag was given. Under these semantics that value is a ceiling on
    every phase, so a detached run would have honoured fewer phase overrides
    than an attached one."""

    def _argv(self, cli_value: int | None) -> list[str]:
        """The argv `--detach` would have handed its child.

        `subprocess.Popen` is replaced only around the `cli_main` call. Patching
        it earlier would also replace the one `git_repo` uses, because the CLI
        holds the module and not its own copy of the name.
        """
        import subprocess as real_subprocess

        workflow_path = self.tmp / "tiny_workflow.py"
        workflow_path.write_text(
            "from pathlib import Path\n"
            "from ohflow.workflow import Phase, Workflow, Step\n"
            "def build(args):\n"
            "    step = Step(id='s', kind='command', command='echo hi')\n"
            "    return Workflow(name='tiny', repo=Path(args['repo']),\n"
            "                max_parallel=7,\n"
            "                phases=(Phase(name='Only', steps=(step,)),))\n",
            encoding="utf-8")
        repo = git_repo(self.tmp / "repo")
        argv = ["run", "--workflow", str(workflow_path), "--args", f"repo={repo}",
                "--out", str(self.tmp / "runs"), "--detach"]
        if cli_value is not None:
            argv += ["--max-parallel", str(cli_value)]

        seen: dict = {}

        class FakePopen:
            def __init__(self, child_argv, **kw):
                seen["argv"] = child_argv
                self.pid = 4242

        original = real_subprocess.Popen
        real_subprocess.Popen = FakePopen
        try:
            with quiet():
                self.assertEqual(cli_main(argv), 0)
        finally:
            real_subprocess.Popen = original
        return seen["argv"]

    def test_an_absent_flag_stays_absent(self):
        self.assertNotIn("--max-parallel", self._argv(None),
                         "the workflow default was injected as a ceiling")

    def test_a_given_flag_is_forwarded_verbatim(self):
        argv = self._argv(2)
        self.assertIn("--max-parallel", argv)
        self.assertEqual(argv[argv.index("--max-parallel") + 1], "2")


class TheNumericKnobsAreValidated(TempCase):

    def test_max_parallel_zero_on_the_command_line_is_a_fault(self):
        """`ns.max_parallel or workflow.max_parallel` read zero as absent, so an
        operator asking for no agents silently got the workflow default."""
        workflow_path = self.tmp / "tiny_workflow.py"
        workflow_path.write_text(
            "from pathlib import Path\n"
            "from ohflow.workflow import Phase, Workflow, Step\n"
            "def build(args):\n"
            "    step = Step(id='s', kind='command', command='echo hi')\n"
            "    return Workflow(name='tiny', repo=Path(args['repo']),\n"
            "                phases=(Phase(name='Only', steps=(step,)),))\n",
            encoding="utf-8")
        repo = git_repo(self.tmp / "repo")
        with quiet() as out:
            code = cli_main(["run", "--workflow", str(workflow_path),
                             "--args", f"repo={repo}",
                             "--out", str(self.tmp / "runs"),
                             "--max-parallel", "0"])
        self.assertEqual(code, 2, "a zero limit must be a workflow fault")
        self.assertIn("--max-parallel must be at least 1", out.out)

    def test_a_phase_limit_of_zero_is_a_workflow_fault(self):
        workflow = simple_workflow(self.tmp / "repo", phases=(
            _phase("Only phase", ["a"], 0),))
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        self.assertIn("max_parallel must be at least 1", str(caught.exception))

    def test_a_boolean_is_not_an_integer(self):
        """`isinstance(True, int)` is true, so a workflow that wrote `True` would
        have run at a limit of one and never been told."""
        workflow = simple_workflow(self.tmp / "repo", phases=(
            _phase("Only phase", ["a"], True),))
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        self.assertIn("must be an integer, got the boolean", str(caught.exception))

    def test_a_negative_workflow_default_is_a_workflow_fault(self):
        workflow = simple_workflow(self.tmp / "repo", max_parallel=-1)
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        self.assertIn("workflow: max_parallel must be at least 1",
                      str(caught.exception))
