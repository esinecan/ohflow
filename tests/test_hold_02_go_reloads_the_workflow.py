"""`go` reloads the workflow module before the agents start.

The hold exists so a person can read the plan and change it. A brief edited
while the run is held must be the brief the agents receive, so `go` loads the
workflow module again, validates it, rebuilds the engine and rewrites
`workflow.json`. A module that no longer builds ends the run as `crashed`,
with the message, and the `go` file stays as evidence of what was asked.
"""

from __future__ import annotations

import json
import textwrap
import threading
import time
from pathlib import Path

from ohflow import rundir, supervisor
from ohflow.supervisor import RunOptions, run_workflow
from ohflow.workflow import load_workflow, validate
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, stub_preflight)

HOLD_WAIT_S = 15.0

WORKFLOW = '''
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             Step, AgentSpec)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    step = Step(id="a", kind="agent",
                gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                                {"regex": "DONE"}),)),
                agent=AgentSpec(harness_executor="pi", role="a", brief="%s", model=MODEL,
                                max_iterations=3))
    return Workflow(name="reload", repo=Path(args["repo"]), base_branch="main",
                    max_parallel=1, transient_backoff_s=0,
                    phases=(Phase(name="Only", steps=(step,)),))
'''

BROKEN = "def build(args):\n    return None\n"


def wait_for(path: Path, timeout: float = HOLD_WAIT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return path.exists()


def recorded_brief(run_dir: Path) -> str:
    workflow = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
    return workflow["phases"][0]["steps"][0]["agent"]["brief"]


class GoReloadsTheWorkflow(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        original = supervisor.HOLD_POLL_S
        supervisor.HOLD_POLL_S = 0.02
        self.addCleanup(setattr, supervisor, "HOLD_POLL_S", original)
        self.module = self.tmp / "workflow.py"
        self.module.write_text(textwrap.dedent(WORKFLOW) % "FIRST BRIEF",
                               encoding="utf-8")
        self.args = {"repo": str(self.repo)}

    def start_held(self, run_dir: Path):
        workflow = validate(load_workflow(self.module, self.args))
        result: dict = {}

        def target():
            with quiet():
                result["outcome"] = run_workflow(workflow, run_dir, RunOptions(
                    hold=True, dashboard=False,
                    harness_executors=self.harness_executors,
                    workflow_path=str(self.module), workflow_args=self.args,
                    say=lambda _line: None))

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self.assertTrue(wait_for(run_dir / rundir.HOLD_FILE))
        return thread, result

    def test_an_edit_made_while_held_reaches_workflow_json_and_the_agent(self):
        run_dir = self.tmp / "runs" / "r-edit"
        thread, result = self.start_held(run_dir)
        self.assertEqual(recorded_brief(run_dir), "FIRST BRIEF")
        self.module.write_text(textwrap.dedent(WORKFLOW) % "SECOND BRIEF",
                               encoding="utf-8")
        (run_dir / rundir.GO_FILE).write_text("now", encoding="utf-8")
        thread.join(HOLD_WAIT_S)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["outcome"].status, "finished")
        self.assertEqual(recorded_brief(run_dir), "SECOND BRIEF",
                         "go rewrites workflow.json from the reloaded module")
        brief = (run_dir / "phases" / "01.only" / "01.a" / "attempts" / "01"
                 / "brief.md")
        self.assertTrue(brief.exists(), "the agent was launched")
        self.assertIn("SECOND BRIEF", brief.read_text(encoding="utf-8"))

    def test_a_module_that_no_longer_builds_ends_the_run_as_crashed(self):
        run_dir = self.tmp / "runs" / "r-broken"
        thread, result = self.start_held(run_dir)
        self.module.write_text(BROKEN, encoding="utf-8")
        (run_dir / rundir.GO_FILE).write_text("now", encoding="utf-8")
        thread.join(HOLD_WAIT_S)
        self.assertFalse(thread.is_alive())
        outcome = result["outcome"]
        self.assertEqual(outcome.status, "crashed")
        self.assertIn("build() returned", outcome.problem)
        self.assertFalse((run_dir / "run-log.jsonl").exists(),
                         "the run stays unstarted")
        self.assertTrue((run_dir / rundir.GO_FILE).exists(),
                        "the go file is left in place as evidence")
        record = json.loads((run_dir / "exit.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "crashed")
        self.assertEqual(recorded_brief(run_dir), "FIRST BRIEF",
                         "a module that does not build rewrites nothing")


if __name__ == "__main__":
    import unittest
    unittest.main()
