"""Defect 8: a run directory records the workflow it ran.

Fixed in `9c436f5`, "ohflow: a run directory records the plan it ran", and
`278d52e`, "ohflow: a detached run resolves its plan from the caller's
directory".

What went wrong. `run.json` recorded the workflow's *name* and the arguments the workflow
module chose to copy back, and nothing else. `ohflow position --run <dir>` read
`workflow_path` from `run.json`, which was never written, so the command always
demanded `--workflow` as well. A preserved run could therefore not say what had
produced it, which is exactly the question an archived run gets asked.

What is asserted here. `run.json` carries `workflow_path` and `workflow_args`,
`workflow_path` is absolute when it names a file, `position --run` resolves without
`--workflow`, a run that predates the key gains it on its first `--resume`, and a
workflow that has since moved gets a message naming the problem rather than a
traceback.
"""

from __future__ import annotations

import json

from ohflow import cli
from ohflow.engine import Engine
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight,
                     agent_step)

WORKFLOW_MODULE = '''
"""A one-step workflow whose shape depends on its arguments."""
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             AgentSpec)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def _step(step_id, flavour):
    return Step(id=step_id, kind="agent",
                gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                                {"regex": "DONE"}),)),
                agent=AgentSpec(harness_executor="pi", role=f"{flavour}-{step_id}",
                                brief=f"be {flavour}", model=MODEL,
                                max_iterations=3))


def build(args):
    # `flavour` changes the role and the brief, so a position rendered with the
    # wrong arguments describes a different workflow.
    flavour = args.get("flavour", "plain")
    return Workflow(
        name="workflow-path-run",
        repo=Path(args["repo"]),
        base_branch="main",
        max_parallel=1,
        transient_backoff_s=0,
        # Deliberately copies nothing back: `Workflow.args` stays empty, so only
        # `workflow_args` can rebuild this workflow.
        phases=(Phase(name="Only phase",
                      steps=(_step("alpha", flavour),)),),
    )
'''


def run_the_workflow(case: TempCase, *, flavour: str = "spicy"):
    """Run `WORKFLOW_MODULE` through the CLI. Returns (run_dir, workflow_file, repo)."""
    repo = git_repo(case.tmp / "repo")
    stub_preflight(case)
    install_fake_harness_executor(case, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
    workflow_file = case.tmp / "workflow_path_workflow.py"
    workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
    out = case.tmp / "runs"
    with quiet():
        code = cli.main(["run", "--workflow", str(workflow_file), "--out", str(out),
                         "--run-id", "r-recorded", "--args", f"repo={repo}",
                         "--args", f"flavour={flavour}"], harness_executors=case.harness_executors)
    case.assertEqual(code, cli.EXIT_OK)
    return out / "r-recorded", workflow_file, repo


class RunJsonRecordsTheWorkflow(TempCase):

    def test_workflow_path_and_workflow_args_are_both_written(self):
        run_dir, workflow_file, repo = run_the_workflow(self)
        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertIn("workflow_path", recorded)
        self.assertIn("workflow_args", recorded)
        self.assertEqual(recorded["workflow_path"], str(workflow_file.resolve()))
        self.assertEqual(recorded["workflow_args"],
                         {"repo": str(repo), "flavour": "spicy"})

    def test_workflow_args_holds_what_the_cli_was_given_not_what_the_workflow_kept(self):
        """`Workflow.args` is only what the workflow module chose to copy back. This
        workflow copies nothing, so `args` is empty and `workflow_args` is the only
        record that can rebuild it."""
        run_dir, _workflow_file, _repo = run_the_workflow(self)
        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["args"], {})
        self.assertTrue(recorded["workflow_args"])

    def test_a_dotted_module_name_is_stored_verbatim(self):
        self.assertEqual(cli.workflow_ref("ohflow.workflows.rollcall"),
                         "ohflow.workflows.rollcall")


class PositionResolvesFromTheRunAlone(TempCase):

    def test_position_run_needs_no_workflow_flag(self):
        run_dir, _workflow_file, _repo = run_the_workflow(self, flavour="spicy")

        with quiet() as q:
            code = cli.main(["position", "--run", str(run_dir),
                             "--step", "alpha"])
        self.assertEqual(code, cli.EXIT_OK,
                         "position --run still demands --workflow")
        self.assertIn("Your position in this run", q.out)
        self.assertIn("r-recorded", q.out)
        self.assertIn("`alpha`", q.out)

    def test_position_rebuilds_the_workflow_with_the_arguments_the_run_used(self):
        run_dir, _workflow_file, _repo = run_the_workflow(self, flavour="spicy")

        # The brief is a function of `flavour`. If `workflow_args` were ignored the
        # workflow would rebuild with the default and the step directory's own brief
        # would disagree with what `position` prints.
        brief = (run_dir / "phases" / "01.only-phase" / "01.alpha" /
                 "brief.md").read_text(encoding="utf-8")
        self.assertIn("be spicy", brief)

    def test_position_describes_the_workflow_the_runs_own_arguments_built(self):
        run_dir, _workflow_file, _repo = run_the_workflow(self, flavour="spicy")

        with quiet() as q:
            code = cli.main(["position", "--run", str(run_dir),
                             "--step", "alpha"])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("spicy-alpha", q.out,
                      "position rebuilt the workflow with arguments the run "
                      "did not use")

    def test_a_run_with_no_recorded_workflow_says_so_instead_of_crashing(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[agent_step("only")])
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()
        # Written by the Engine directly, with no workflow_path.
        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertIsNone(recorded.get("workflow_path"))

        with quiet() as q:
            code = cli.main(["position", "--run", str(run_dir), "--step", "only"])
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("run.json carries no workflow path", q.out)

    def test_a_workflow_that_has_moved_is_named_rather_than_imported(self):
        run_dir, workflow_file, _repo = run_the_workflow(self)
        workflow_file.unlink()

        with quiet() as q:
            code = cli.main(["position", "--run", str(run_dir), "--step", "alpha"])
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("the workflow this run recorded is gone", q.out)
        self.assertIn("Give --workflow with its new location", q.out)


class AnOlderRunGainsTheKeyOnResume(TempCase):

    def test_backfill_adds_workflow_path_and_touches_nothing_else(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[agent_step("only")])
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        before = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        # A run started before the key existed did not carry it at all.
        before.pop("workflow_path", None)
        before.pop("workflow_args", None)
        (run_dir / "run.json").write_text(json.dumps(before, indent=2),
                                          encoding="utf-8")

        Engine(workflow, run_dir, run_id=run_dir.name, resume=True, verbose=False,
               workflow_path=r"C:\somewhere\workflow.py",
               workflow_args={"repo": str(repo)},
               harness_executors=self.harness_executors).run()

        after = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(after["workflow_path"], r"C:\somewhere\workflow.py")
        self.assertEqual(after["workflow_args"], {"repo": str(repo)})
        for key, value in before.items():
            self.assertEqual(after[key], value,
                             f"the backfill rewrote {key}")

    def test_backfill_never_overwrites_a_workflow_path_that_is_already_there(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[agent_step("only")])
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               workflow_path=r"C:\original\workflow.py",
               harness_executors=self.harness_executors).run()

        Engine(workflow, run_dir, run_id=run_dir.name, resume=True, verbose=False,
               workflow_path=r"C:\different\workflow.py",
               harness_executors=self.harness_executors).run()

        after = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(after["workflow_path"], r"C:\original\workflow.py",
                         "a resume rewrote the workflow the run actually used")

    def test_backfill_is_silent_when_run_json_is_unreadable(self):
        workflow = simple_workflow(self.tmp / "repo")
        run_dir = self.run_dir()
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text("{ not json", encoding="utf-8")
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        workflow_path=r"C:\somewhere\workflow.py",
                        harness_executors=self.harness_executors)
        engine._backfill_workflow_path()          # must not raise
        self.assertEqual((run_dir / "run.json").read_text(encoding="utf-8"),
                         "{ not json")
