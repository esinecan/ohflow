"""The durable harness executor's named skills: validation, spec and record.

The host on the box resolves `spec.skills` itself (host commit 9673567), so
this machine's `agent_errors` judges only the names and the box keeps its own
copy of the skills tree. Four rules, one test each:

- R1: every skill name matching `[A-Za-z0-9._-]+` passes `agent_errors`, and a
  name outside that pattern - `../x`, which would escape
  `~/.agents/skills/<name>/SKILL.md` on the box - is refused, named.
- R2: `skills_dir` is refused; the box reads skills from its own
  `~/.agents/skills`.
- R3: the `spec.json` the fake host received and the result record both carry
  the step's skill names.
- R3 and R7: a step that names `codebase-design` survives a host loss and a
  reattach - the reattached attempt's `result.json` still lists it, and the
  `spec.json` the fake received on the second start still carries it, because
  the reattach is the same attempt.

The fake `ssh`/`scp` (`tests/fakes/fake_durable.py`) and the recordings
(`tests/fixtures/durable/`) are the ones `test_durable_03_reattach.py` and
the contract test use; the attempt runs against a real repository with a bare
`origin`, so the transport is the real git path.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from ohflow import harness_executors
from ohflow.harness_executor import FINISHED, RUNNING
from ohflow.workflow import AgentSpec, ModelConfig, ToolPolicy
from support import TempCase, git_repo

FAKES = Path(__file__).resolve().parent / "fakes"
WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=ohflow tests",
         "-c", "user.email=tests@localhost", *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=WINDOW)
    assert done.returncode == 0, (args, done.stderr, done.stdout)
    return done.stdout.strip()


class DurableSkills(TempCase):

    def setUp(self):
        super().setUp()
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.origin)],
                       check=True, capture_output=True, creationflags=WINDOW)
        self.repo = git_repo(self.tmp / "repo")
        git(self.repo, "remote", "add", "origin", self.origin.as_posix())
        git(self.repo, "push", "origin", "main")
        self._set_env("OHFLOW_DURABLE_SSH", str(FAKES / "fake_durable.py"))
        self._set_env("OHFLOW_DURABLE_SCP", str(FAKES / "fake_durable.py"))
        self._set_env("OHFLOW_FAKE_DURABLE_HOME", str(self.tmp / "box-home"))
        self.harness_executor = harness_executors.harness_executor_for("durable")
        self.module = harness_executors.harness_executor_module("durable")

    def _set_env(self, name: str, value: str) -> None:
        old = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(lambda: os.environ.pop(name, None) if old is None
                        else os.environ.__setitem__(name, old))

    def _agent(self, **changes) -> AgentSpec:
        agent = AgentSpec(
            role="implement", brief="x",
            model=ModelConfig(model="zai/glm-5.3-flash", base_url="",
                              api_key_env="", params={"thinking": "high"}),
            tools=ToolPolicy(), harness_executor="durable",
            box="buildbox")
        return replace(agent, **changes) if changes else agent

    def _spec(self, **changes) -> dict:
        spec = {"coord": "01.report/01.durable", "attempt": 1, "role": "rollcall",
                "harness_executor": "durable", "box": "fakebox",
                "workspace": str(self.repo),
                "model": {"model": "zai/glm-5.3-flash", "base_url": "",
                          "api_key_env": "", "params": {"thinking": "low"},
                          "extra_body": {}},
                "tools": {"preset": "default", "enable_browser": False,
                          "enable_sub_agents": False, "only": [], "allow": []},
                "skills": [], "skills_dir": None, "mcp_config": None,
                "max_iterations": 30, "command_time_cap_s": None,
                "execution_timeout_s": 60, "stall_timeout_s": 60,
                "write_scope": [], "fork_session": None,
                "brief_path": "brief.md", "schema_path": None, "out_dir": "."}
        spec.update(changes)
        return spec

    def _run(self, name: str, scenario: str, *, timeout: float = 90.0,
             **spec_changes) -> tuple[Path, dict]:
        os.environ["OHFLOW_FAKE_DURABLE_SCENARIO"] = scenario
        out_dir = self.tmp / name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "brief.md").write_text("# Task\n\nWork and report.\n",
                                          encoding="utf-8")
        handle = self.harness_executor.launch(self._spec(**spec_changes), out_dir)
        deadline = time.monotonic() + timeout
        state = RUNNING
        while state == RUNNING and time.monotonic() < deadline:
            state = self.harness_executor.poll(handle)
            time.sleep(0.05)
        if state == RUNNING:
            self.harness_executor.kill(handle)
            self.fail(f"durable runner did not finish in {timeout}s")
        self.assertEqual(state, FINISHED,
                         sorted(p.name for p in (out_dir / "logs").iterdir()))
        return out_dir, self.harness_executor.collect(handle)

    def _box_dir(self, out_dir: Path) -> Path:
        remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        return self.tmp / "box-home" / ".pi-durable" / "ohflow" / remote["key"]

    def test_r1_well_formed_skill_names_pass_and_one_bad_name_is_refused(self):
        self.assertEqual(
            self.module.agent_errors("01.p/01.s", self._agent(
                skills=("codebase-design", "a.second_one", "x-y_z.3"))), [])
        errs = self.module.agent_errors("01.p/01.s", self._agent(
            skills=("codebase-design", "../x")))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("01.p/01.s", errs[0])
        self.assertIn("[A-Za-z0-9._-]+", errs[0])
        # The bad name is named; the well-formed one is not accused.
        self.assertIn("'../x'", errs[0])
        self.assertNotIn("codebase-design", errs[0])

    def test_r2_skills_dir_is_refused(self):
        errs = self.module.agent_errors(
            "01.p/01.s", self._agent(skills_dir=Path("C:/skills/here")))
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual(
            errs[0],
            "01.p/01.s: durable refuses skills_dir; the box reads skills from "
            "its own ~/.agents/skills")

    def test_r3_the_spec_and_the_result_carry_the_skill_names(self):
        out_dir, result = self._run("skills", "success",
                                    skills=["codebase-design"])
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["skills"], ["codebase-design"])
        # The spec.json the fake received on the box carries them too.
        box_spec = json.loads(
            (self._box_dir(out_dir) / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(box_spec["skills"], ["codebase-design"])

    def test_r3_and_r7_a_reattach_keeps_the_skills_in_spec_and_result(self):
        _first_dir, first = self._run("reattach", "killed",
                                      skills=["codebase-design"])
        self.assertIn("host_lost", first["error"])
        out_dir, second = self._run("reattach", "reattach", reattach=True,
                                    skills=["codebase-design"])
        self.assertIsNone(second["error"], second["error"])
        # The reattach is the same attempt, and its result.json still names
        # the skill the first start asked for.
        recorded = json.loads(
            (out_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["skills"], ["codebase-design"])
        self.assertEqual(second["skills"], ["codebase-design"])
        # And the spec the fake received on the second start still carries it.
        box_spec = json.loads(
            (self._box_dir(out_dir) / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(box_spec["skills"], ["codebase-design"])
        self.assertTrue(box_spec["reattach"])


if __name__ == "__main__":
    import unittest
    unittest.main()
