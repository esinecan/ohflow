"""D-14: a completed dry run exits zero through the real CLI path."""

from __future__ import annotations

from ohflow import cli
from support import TempCase, git_repo, quiet, stub_preflight


WORKFLOW_MODULE = '''
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             AgentSpec)

def build(args):
    return Workflow(
        name="dry-run-exit",
        repo=Path(args["repo"]),
        base_branch="main",
        baseline_cmd=None,
        phases=(
            Phase(name="Scout", steps=(Step(
                id="scout", kind="agent",
                gate=GateSpec(checks=(CheckSpec(
                    "final_message_matches", {"regex": "DONE"}),)),
                agent=AgentSpec(harness_executor="pi", 
                    role="scout", brief="inspect the repo",
                    model=ModelConfig(
                        model="fake/deterministic",
                        base_url="http://127.0.0.1:0/never-called",
                        api_key_env="OHFLOW_TEST_FAKE_KEY"),
                ),
            ),)),
            Phase(name="Synthesize", steps=(Step(
                id="synth", kind="agent", depends_on=("scout",),
                gate=GateSpec(checks=(CheckSpec(
                    "final_message_matches", {"regex": "DONE"}),)),
                agent=AgentSpec(harness_executor="pi", 
                    role="synth", brief="use the scout result",
                    model=ModelConfig(
                        model="fake/deterministic",
                        base_url="http://127.0.0.1:0/never-called",
                        api_key_env="OHFLOW_TEST_FAKE_KEY"),
                ),
            ),)),
        ),
    )
'''


class DryRunExit(TempCase):

    def test_cmd_run_returns_zero_after_writing_dry_artifacts(self):
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "dry_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        stub_preflight(self)
        out = self.tmp / "runs"

        with quiet():
            code = cli.main([
                "run", "--workflow", str(workflow_file), "--out", str(out),
                "--run-id", "r-dry", "--dry-run", "--args", f"repo={repo}",
            ])

        self.assertEqual(code, cli.EXIT_OK)
        self.assertTrue((out / "r-dry" / "summary.json").exists())
        for path in (
            out / "r-dry" / "phases" / "01.scout" / "01.scout",
            out / "r-dry" / "phases" / "02.synthesize" / "01.synth",
        ):
            attempt = path / "attempts" / "01"
            self.assertTrue((attempt / "brief.md").exists(), path)
            self.assertTrue((attempt / "spec.json").exists(), path)

    def test_dry_run_with_resume_is_refused_and_writes_nothing(self):
        repo = git_repo(self.tmp / "repo")
        workflow_file = self.tmp / "dry_workflow.py"
        workflow_file.write_text(WORKFLOW_MODULE, encoding="utf-8")
        run_dir = self.tmp / "runs" / "r-old"
        run_dir.mkdir(parents=True)
        log = run_dir / "run-log.jsonl"
        log.write_text('{"event": "run_finished"}\n', encoding="utf-8")

        with quiet():
            code = cli.main([
                "run", "--workflow", str(workflow_file), "--out", str(self.tmp / "runs"),
                "--resume", "r-old", "--dry-run", "--args", f"repo={repo}",
            ])

        self.assertEqual(code, cli.EXIT_WORKFLOW)
        self.assertEqual(log.read_text(encoding="utf-8"), '{"event": "run_finished"}\n')
