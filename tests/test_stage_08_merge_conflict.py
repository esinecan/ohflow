"""Stage 8: merge steps restore conflicts and need no agent."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ohflow.engine import Engine
from ohflow.run_log import RunLog
from ohflow.workflow import Phase, Workflow, Step, WorktreeSpec
from support import TempCase, git_repo


class MergeConflict(TempCase):

    def _git(self, repo: Path, *args: str) -> str:
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_GLOBAL": str(repo / ".gitconfig-none"),
            "GIT_CONFIG_SYSTEM": str(repo / ".gitconfig-none"),
        })
        completed = subprocess.run(
            ["git", "-C", str(repo), *args], check=True,
            capture_output=True, text=True, env=env,
        )
        return completed.stdout.strip()

    def _commit(self, repo: Path, branch: str,
                changes: dict[str, str]) -> None:
        self._git(repo, "switch", "-c", branch)
        for relative, content in changes.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self._git(repo, "add", *changes)
        self._git(repo, "-c", "user.name=ohflow tests",
                  "-c", "user.email=tests@localhost",
                  "commit", "-m", f"build {branch}")
        self._git(repo, "switch", "main")

    def _workflow(self, repo: Path, integration: Path,
                  first: str, second: str, *, policy: str) -> Workflow:
        return Workflow(
            name="stage-8-merge",
            repo=repo,
            base_branch="main",
            baseline_cmd=None,
            max_parallel=1,
            transient_backoff_s=0,
            worktrees=(WorktreeSpec(
                name="integration", path=integration,
                branch="integration", base="main",
                node_modules_mode="none"),),
            phases=(
                Phase(
                    name="Merge first",
                    on_step_failure="abort",
                    steps=(Step(
                        id="merge-first", kind="merge",
                        worktree="integration", merge_branch=first),),
                ),
                Phase(
                    name="Merge second",
                    on_step_failure=policy,
                    steps=(Step(
                        id="merge-second", kind="merge",
                        worktree="integration", merge_branch=second,
                        depends_on=("merge-first",)),),
                ),
            ),
        )

    def _forbid_agents(self):
        def forbidden(_name: str):
            raise AssertionError("a mechanical merge must not launch an agent")

        self.harness_executors = forbidden

    def test_conflict_is_aborted_recorded_and_quarantined(self):
        repo = git_repo(self.tmp / "conflict-repo")
        self._commit(repo, "change-left", {"README.md": "left\n"})
        self._commit(repo, "change-right", {"README.md": "right\n"})
        integration = self.tmp / "conflict-integration"
        workflow = self._workflow(repo, integration, "change-left", "change-right",
                                  policy="quarantine")
        self._forbid_agents()

        run_dir = self.run_dir("r-stage-8-conflict")
        summary = Engine(
            workflow, run_dir, run_id=run_dir.name, verbose=False,
            harness_executors=self.harness_executors,
        ).run()

        state = RunLog.replay(run_dir)
        first = state.steps["01.merge-first/01.merge-first"]
        second = state.steps["02.merge-second/01.merge-second"]
        second_dir = run_dir / "phases" / "02.merge-second" / "01.merge-second"
        result = json.loads((second_dir / "result.json").read_text(
            encoding="utf-8"))
        gate = json.loads((second_dir / "gate.json").read_text(
            encoding="utf-8"))

        self.assertEqual(first.status, "passed")
        self.assertEqual(second.status, "quarantined")
        self.assertEqual(state.phases["02.merge-second"]["policy"],
                         "quarantine")
        self.assertEqual(state.phases["02.merge-second"]["status"], "failed")
        self.assertEqual(summary["status"], "finished")
        self.assertNotEqual(result["exit"], 0)
        self.assertEqual(result["conflicts"], ["README.md"])
        self.assertTrue(result["restored"])
        self.assertEqual(self._git(integration, "rev-parse", "HEAD"),
                         result["before_sha"])
        merge_head = Path(self._git(
            integration, "rev-parse", "--git-path", "MERGE_HEAD"))
        if not merge_head.is_absolute():
            merge_head = integration / merge_head
        self.assertFalse(merge_head.exists(), merge_head)
        self.assertFalse(gate["passed"])
        self.assertIn("README.md", json.dumps(gate))

    def test_disjoint_branches_merge_cleanly_without_an_agent(self):
        repo = git_repo(self.tmp / "clean-repo")
        self._commit(repo, "add-left", {"left.txt": "left\n"})
        self._commit(repo, "add-right", {"right.txt": "right\n"})
        integration = self.tmp / "clean-integration"
        workflow = self._workflow(repo, integration, "add-left", "add-right",
                                  policy="abort")
        self._forbid_agents()

        run_dir = self.run_dir("r-stage-8-clean")
        summary = Engine(
            workflow, run_dir, run_id=run_dir.name, verbose=False,
            harness_executors=self.harness_executors,
        ).run()

        state = RunLog.replay(run_dir)
        self.assertEqual(summary["status"], "finished")
        self.assertEqual(state.steps["01.merge-first/01.merge-first"].status,
                         "passed")
        self.assertEqual(state.steps["02.merge-second/01.merge-second"].status,
                         "passed")
        for result_path in sorted(run_dir.glob("phases/*/*/result.json")):
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["exit"], 0, result)
        self.assertEqual((integration / "left.txt").read_text(encoding="utf-8"),
                         "left\n")
        self.assertEqual((integration / "right.txt").read_text(encoding="utf-8"),
                         "right\n")

    def test_abort_stops_later_merges_in_the_same_phase(self):
        repo = git_repo(self.tmp / "abort-repo")
        self._commit(repo, "change-left", {"README.md": "left\n"})
        self._commit(repo, "change-right", {"README.md": "right\n"})
        self._commit(repo, "merge-tail", {"tail.txt": "must not merge\n"})
        integration = self.tmp / "abort-integration"
        workflow = Workflow(
            name="stage-8-abort",
            repo=repo,
            base_branch="main",
            baseline_cmd=None,
            max_parallel=1,
            transient_backoff_s=0,
            worktrees=(WorktreeSpec(
                name="integration", path=integration,
                branch="integration", base="main",
                node_modules_mode="none"),),
            phases=(Phase(
                name="Merge in order",
                on_step_failure="abort",
                steps=(
                    Step(id="merge-left", kind="merge",
                         worktree="integration", merge_branch="change-left"),
                    Step(id="merge-right", kind="merge",
                         worktree="integration", merge_branch="change-right"),
                    Step(id="merge-tail", kind="merge",
                         worktree="integration", merge_branch="merge-tail"),
                ),
            ),),
        )
        self._forbid_agents()

        run_dir = self.run_dir("r-stage-8-abort")
        summary = Engine(
            workflow, run_dir, run_id=run_dir.name, verbose=False,
            harness_executors=self.harness_executors,
        ).run()

        state = RunLog.replay(run_dir)
        right_dir = run_dir / "phases" / "01.merge-in-order" / "02.merge-right"
        right_result = json.loads((right_dir / "result.json").read_text(
            encoding="utf-8"))
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(state.steps["01.merge-in-order/01.merge-left"].status,
                         "passed")
        self.assertEqual(state.steps["01.merge-in-order/02.merge-right"].status,
                         "failed")
        self.assertEqual(state.steps["01.merge-in-order/03.merge-tail"].status,
                         "deferred")
        self.assertEqual(self._git(integration, "rev-parse", "HEAD"),
                         right_result["before_sha"])
        self.assertFalse((integration / "tail.txt").exists())

    def test_non_conflict_merge_failure_is_not_labeled_as_a_conflict(self):
        repo = git_repo(self.tmp / "missing-branch-repo")
        self._commit(repo, "add-left", {"left.txt": "left\n"})
        integration = self.tmp / "missing-branch-integration"
        workflow = self._workflow(repo, integration, "add-left", "does-not-exist",
                                  policy="quarantine")
        self._forbid_agents()

        run_dir = self.run_dir("r-stage-8-missing-branch")
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
               harness_executors=self.harness_executors).run()

        state = RunLog.replay(run_dir)
        second_dir = run_dir / "phases" / "02.merge-second" / "01.merge-second"
        result = json.loads((second_dir / "result.json").read_text(
            encoding="utf-8"))
        gate = json.loads((second_dir / "gate.json").read_text(
            encoding="utf-8"))
        check_names = [check["name"] for check in gate["checks"]]
        self.assertEqual(state.steps["02.merge-second/01.merge-second"].status,
                         "quarantined")
        self.assertNotEqual(result["exit"], 0)
        self.assertEqual(result["conflicts"], [])
        self.assertNotIn("merge_conflict", check_names)
        self.assertIn("merge_failed", check_names)
