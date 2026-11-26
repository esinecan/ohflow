"""A cloud step's brief names the branch the Worker actually cloned.

Observed 19.11.2026 in the source-analysis run: the position block said the
agent worked on the worktree's branch `ohflow/sabine-20261119c-v2`, while
the cloud checkout was on `ohflow/pi-cloud/<attempt-key>`, and the worker
flagged the mismatch. The paths in the brief were rewritten; the branch claim
was not.

The posted brief now names two branches: the current branch, which is the
transport branch the Worker cloned at the start commit, and the worktree's
branch, which the fetched commits reach. The pi-cloud,
claude-cloud and codex-cloud executors share one adapter, and the durable
executor rewrites its brief by the same rule.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from ohflow import durable_runner, harness_executors, remote_git
from ohflow.coords import render_position
from ohflow.run_log import RunState
from ohflow.workflow import WorktreeSpec
from pi_cloud_support import PiCloudCase, git
from support import agent_step, simple_workflow

LOCAL_BRANCH = "ohflow/sabine-20261119c-v2"
MODELS = {"pi-cloud": "zai/glm-5.3-flash",
          "claude-cloud": "claude-haiku-4-5-20251001",
          "codex-cloud": "gpt-5.6-luna"}


def _current_branch(brief: str) -> str:
    found = re.search(r"^\s+current branch (\S+), the transport checkout", brief,
                      re.MULTILINE)
    return found.group(1) if found else ""


class TheCloudBriefNamesTheClonedBranch(PiCloudCase):

    def _position(self, start_sha: str) -> str:
        workflow = simple_workflow(self.repo, steps=[agent_step("s1")])
        workflow = dataclasses.replace(
            workflow,
            worktrees=(WorktreeSpec(name="wt", path=self.repo, branch=LOCAL_BRANCH,
                                    base="main"),),
            phases=(dataclasses.replace(
                workflow.phases[0],
                steps=(dataclasses.replace(workflow.phases[0].steps[0],
                                           worktree="wt"),)),))
        state = RunState(meta={"worktrees": {"wt": {
            "path": str(self.repo), "branch": LOCAL_BRANCH, "base": "main",
            "base_sha": start_sha}}})
        return render_position(workflow, state, workflow.phases[0].steps[0])

    def _attempt(self, executor: str) -> tuple[str, dict, dict]:
        self.executor = harness_executors.harness_executor_for(executor)
        name = executor.replace("-", "_")
        key = self.key_of(self.tmp / name)
        self.worker.plan(key, 1, ["success"])
        position = self._position(git(self.repo, "rev-parse", "HEAD"))
        self.assertIn(f"branch {LOCAL_BRANCH}, created from main", position)
        out_dir, result = self.run_attempt(
            name, brief=position + "\n---\n\nDo the trivial thing.\n",
            harness_executor=executor,
            model={"model": MODELS[executor], "base_url": "", "api_key_env": "",
                   "params": {}, "extra_body": {}})
        self.assertIsNone(result["error"], result["error"])
        posted = next(r["body"] for r in self.worker.requests
                      if r["path"].endswith(f"/{key}/step"))
        cloned = self.worker.transport_at_step[key]
        remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        return posted["brief"], cloned, remote

    def test_every_cloud_executor_names_the_cloned_branch_as_current(self):
        for executor in MODELS:
            with self.subTest(executor=executor):
                brief, cloned, remote = self._attempt(executor)
                self.assertTrue(cloned["branch"].startswith(f"ohflow/{executor}/"),
                                cloned)
                self.assertEqual(cloned["on_origin"], cloned["start_sha"])
                self.assertEqual(_current_branch(brief), cloned["branch"], brief)
                self.assertEqual(remote["branch"], cloned["branch"])
                self.assertIn(f"the transport checkout cloned at "
                              f"{cloned['start_sha'][:7]}", brief)
                self.assertIn(f"after the step, ohflow fetches this branch's commits "
                              f"onto the worktree's branch "
                              f"{LOCAL_BRANCH}, created from main", brief)
                self.assertNotRegex(brief, rf"(?m)^\s+branch {re.escape(LOCAL_BRANCH)},")

    def test_the_durable_brief_follows_the_same_rule(self):
        position = self._position("a" * 40)
        brief = durable_runner._rewrite_brief(
            position, str(self.repo), str(self.tmp / "out"), Path("C:\\box\\pi\\k1"),
            branch="ohflow/durable/k1", start_sha="a" * 40)
        self.assertEqual(_current_branch(brief), "ohflow/durable/k1")
        self.assertIn(f"onto the worktree's branch {LOCAL_BRANCH}", brief)

    def test_a_brief_without_a_worktree_line_is_left_alone(self):
        text = "# Task\n\nThe branch ohflow/x, created from main is not a position line.\n"
        self.assertEqual(remote_git.transport_position(text, "ohflow/pi-cloud/k", "b" * 40),
                         text)


if __name__ == "__main__":
    import unittest
    unittest.main()
