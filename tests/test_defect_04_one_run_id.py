"""Defect 4: one run id per run, minted by the CLI and handed to the engine.

Fixed in `d2161a4`, "ohflow: one run id per run, minted by the CLI and handed to
the engine".

What went wrong. `new_run_id()` was called three times for one run: once by the
CLI to name the directory, once by the detached child re-running `cmd_run`, and
once by the engine. Each call reads the wall clock, so the three disagreed
whenever a second ticked between them. A run directory could then hold a
`run.json` naming a different run, and a detached child could write into a
directory the parent was not watching.

What is asserted here. The directory name is the run id, the engine is handed
that string rather than making one, `run.json` and the run log both carry it,
and the detached child is told the same id on its command line.

No process is started. The detached path is proved by capturing the argument
vector the CLI builds, with `subprocess.Popen` replaced for the duration.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from unittest import mock

from ohflow import cli, detach
from ohflow.engine import Engine
from ohflow.run_log import RunLog
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight,
                     agent_step)

WORKFLOW_MODULE = '''
"""A one-step workflow, written by the test into a temporary directory."""
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             AgentSpec)


def build(args):
    return Workflow(
        name="run-id-workflow",
        repo=Path(args["repo"]),
        base_branch="main",
        max_parallel=1,
        transient_backoff_s=0,
        phases=(Phase(name="Only phase", steps=(Step(
            id="only",
            kind="agent",
            gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                            {"regex": "DONE"}),)),
            agent=AgentSpec(harness_executor="pi", 
                role="only",
                brief=args.get("brief", "do the trivial thing"),
                model=ModelConfig(model="fake/deterministic",
                                  base_url="http://127.0.0.1:0/never-called",
                                  api_key_env="OHFLOW_TEST_FAKE_KEY"),
                max_iterations=3),
        ),)),),
    )
'''


class TheEngineNeverMintsAnIdOfItsOwn(TempCase):

    def test_the_engine_falls_back_to_the_directory_name_not_the_clock(self):
        """With no id the engine takes the directory's name. It must never call
        `new_run_id`, because that would disagree with the directory."""
        workflow = simple_workflow(self.tmp / "repo")
        run_dir = self.run_dir("r-20260916-120343")
        engine = Engine(workflow, run_dir, verbose=False, harness_executors=self.harness_executors)
        self.assertEqual(engine.run_id, "r-20260916-120343")
        self.assertEqual(engine.run_id, run_dir.name)

    def test_the_directory_the_run_log_and_run_json_all_agree(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        workflow = simple_workflow(repo, steps=[agent_step("only")])
        run_dir = self.run_dir("r-20260916-120343")
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False, harness_executors=self.harness_executors).run()

        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["run_id"], run_dir.name)
        self.assertEqual(RunLog.replay(run_dir).run_id, run_dir.name)
        self.assertEqual(summary["run_id"], run_dir.name)


class TheCliMintsItOnce(TempCase):

    def _workflow_file(self, repo) -> str:
        p = self.tmp / "run_id_workflow.py"
        p.write_text(WORKFLOW_MODULE, encoding="utf-8")
        return str(p)

    def test_the_run_directory_is_named_by_the_id_the_cli_chose(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        out = self.tmp / "runs"
        with quiet():
            code = cli.main(["run", "--workflow", self._workflow_file(repo),
                             "--out", str(out), "--run-id", "r-chosen-by-the-cli",
                             "--args", f"repo={repo}"],
                            harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)
        run_dir = out / "r-chosen-by-the-cli"
        self.assertTrue(run_dir.exists(), f"{run_dir} was not created")
        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["run_id"], "r-chosen-by-the-cli")

    def test_without_run_id_the_minted_id_still_names_the_directory(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript(final_text="DONE\n")))
        out = self.tmp / "runs"
        with quiet():
            code = cli.main(["run", "--workflow", self._workflow_file(repo),
                             "--out", str(out), "--args", f"repo={repo}"],
                            harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)
        made = [d for d in out.iterdir() if d.is_dir()]
        self.assertEqual(len(made), 1, f"expected one run directory, got {made}")
        run_dir = made[0]
        self.assertRegex(run_dir.name, r"^r-\d{8}-\d{6}-[0-9a-f]{8}$")
        recorded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["run_id"], run_dir.name,
                         "the directory and run.json name different runs")
        self.assertEqual(RunLog.replay(run_dir).run_id, run_dir.name)


class TheDetachedChildIsToldTheSameId(TempCase):
    """The third mint. The child re-ran `cmd_run` and made an id of its own."""

    def _capture_argv(self):
        import subprocess as real_subprocess
        captured: dict = {}

        class FakePopen:
            def __init__(self, argv, **kw):
                captured["argv"] = list(argv)
                captured["kwargs"] = kw
                self.pid = 4242

        original = subprocess.Popen
        subprocess.Popen = FakePopen
        self.addCleanup(setattr, subprocess, "Popen", original)
        return captured

    def test_the_child_command_line_carries_the_parents_run_id(self):
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "run_id_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        captured = self._capture_argv()
        out = self.tmp / "runs"

        with quiet():
            code = cli.main(["run", "--workflow", str(workflow_file), "--out", str(out),
                             "--run-id", "r-parent-chose-this", "--detach",
                             "--args", f"repo={repo}"],
                            harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)

        argv = captured["argv"]
        self.assertIn("--run-id", argv,
                      "the child was left to mint its own id")
        self.assertEqual(argv[argv.index("--run-id") + 1], "r-parent-chose-this")
        # And the directory the parent made is the one the child will resolve.
        self.assertEqual(argv[argv.index("--out") + 1], str(out))
        self.assertTrue((out / "r-parent-chose-this").exists())
        token_element = next(a for a in argv
                             if a.startswith("--reservation-token="))
        token = token_element.partition("=")[2]
        handoff = json.loads((out / "r-parent-chose-this"
                              / ".ohflow-handoff.json").read_text())
        self.assertEqual(handoff["token"], token)

    def test_a_token_that_starts_with_a_dash_still_reaches_the_child(self):
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "run_id_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        captured = self._capture_argv()
        out = self.tmp / "runs"

        with mock.patch.object(cli.secrets, "token_urlsafe",
                               return_value="-leading-dash-token-0123456789"), quiet():
            code = cli.main(["run", "--workflow", str(workflow_file), "--out", str(out),
                             "--run-id", "r-dash-led-token", "--detach",
                             "--args", f"repo={repo}"],
                            harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)

        argv = captured["argv"]
        self.assertIn("--reservation-token=-leading-dash-token-0123456789", argv)
        handoff = json.loads((out / "r-dash-led-token"
                              / ".ohflow-handoff.json").read_text())
        self.assertEqual(handoff["token"], "-leading-dash-token-0123456789")

    def test_detached_launch_is_windowless_on_windows(self):
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "run_id_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        captured = self._capture_argv()

        with quiet():
            code = cli.main([
                "run", "--workflow", str(workflow_file), "--out", str(self.tmp / "runs"),
                "--run-id", "r-windowless", "--detach",
                "--args", f"repo={repo}",
            ])

        self.assertEqual(code, cli.EXIT_OK)
        expected, breakaway = detach.creationflags()
        actual = captured["kwargs"].get("creationflags")
        self.assertEqual(actual, expected)
        if os.name == "nt":
            self.assertTrue(actual & subprocess.CREATE_NO_WINDOW)
            self.assertEqual(
                bool(actual & subprocess.CREATE_BREAKAWAY_FROM_JOB),
                breakaway,
                "a jobbed launcher must make its windowless supervisor break "
                "away from the launcher job",
            )

    def test_a_detached_resume_names_the_directory_that_already_exists(self):
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "run_id_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        out = self.tmp / "runs"
        existing = out / "r-20260916-115450"
        existing.mkdir(parents=True)
        (existing / "run-log.jsonl").write_text("", encoding="utf-8")

        captured = self._capture_argv()
        with quiet():
            code = cli.main(["run", "--workflow", str(workflow_file), "--out", str(out),
                             "--detach", "--resume", "r-20260916-115450",
                             "--args", f"repo={repo}"],
                            harness_executors=self.harness_executors)
        self.assertEqual(code, cli.EXIT_OK)
        argv = captured["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], "r-20260916-115450")
        self.assertEqual(argv[argv.index("--run-id") + 1], "r-20260916-115450",
                         "a resuming child without --run-id could land in a "
                         "different directory")

    def test_the_child_is_told_to_write_utf8(self):
        """The detached supervisor logs through a pipe, which picks the ANSI
        code page. Defect 1 lands here too, as an environment variable."""
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "run_id_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        captured = self._capture_argv()
        with quiet():
            cli.main(["run", "--workflow", str(workflow_file), "--out",
                      str(self.tmp / "runs"), "--run-id", "r-x", "--detach",
                      "--args", f"repo={repo}"])
        env = captured["kwargs"]["env"]
        self.assertEqual(env.get("PYTHONIOENCODING"), "utf-8:replace")
