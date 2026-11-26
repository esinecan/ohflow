"""The durable harness executor module answers the harness executor questions over a real attempt.

The fake `ssh`/`scp` in `tests/fakes/fake_durable.py` replay the three
recordings taken on a durable box on 2026-10-25: a whole step, a step whose ssh
client was killed during a 40 s command, and the same step reattached. The
attempt runs against a real repository with a bare `origin`, so the transport -
`push_start`, the box clone, `fetch_result` - is the real git path. Usage
equals the result's tokens (the recordings carry real usage), the fetched
commit is the worktree HEAD after the attempt, the brief on the box carries
the box's paths and no worktree path, and a reattached attempt counts the
usage its replayed turns spent.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path, PureWindowsPath

from contract_support import (assert_usage_matches_result, last_tool_call,
                              recorded_result)
from ohflow import harness_executors
from ohflow.harness_executor import FINISHED, RUNNING
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


class DurableContract(TempCase):

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
        # Both renderings of both paths, as the position block and the brief mix them.
        (out_dir / "brief.md").write_text(
            f"# Task\n\nWork in {self.repo} and in {self.repo.as_posix()}. "
            f"Your evidence is at {out_dir} and at {out_dir.as_posix()}.\n",
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

    def test_the_recorded_step_fetches_back_its_commit(self):
        out_dir, result = self._run("success", "success")
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["execution_status"], "finished")
        self.assertEqual(result["durable"]["box"], "fakebox")
        self.assertTrue(result["durable"]["pushed"])
        self.assertEqual(result["durable"]["head"],
                         git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(result["tools"], ["read", "write", "edit", "bash"])
        # The fleet line carries one object per server; the record holds names.
        self.assertEqual(result["mcp_servers"], ["forum", "search"])
        self.assertEqual(result["llm_calls"], 3)
        self.assertEqual(result["durable"]["start_sha"],
                         json.loads((out_dir / "remote.json").read_text())["start_sha"])
        # The transport branch served its purpose once its commit is fetched.
        self.assertTrue(result["durable"]["branch_deleted"])
        branch = json.loads((out_dir / "remote.json").read_text())["branch"]
        self.assertEqual(git(self.tmp, "ls-remote", self.origin.as_posix(),
                             f"refs/heads/{branch}"), "")
        self.assertTrue((out_dir / "transcript.md").is_file())
        self.assertTrue((out_dir / "handover.md").is_file())

    def test_the_wire_spec_carries_the_local_tools_unchanged(self):
        out_dir, _ = self._run("tools-wire", "success")
        local = json.loads((out_dir / "spec.json").read_text(encoding="utf-8"))
        wire = json.loads((out_dir / "remote" / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(wire["tools"], local["tools"])
        self.assertNotIn("mcp_profile", wire["tools"])

    def test_a_refused_branch_delete_is_recorded_and_is_no_error(self):
        git(self.origin, "config", "receive.denyDeletes", "true")
        out_dir, result = self._run("refused-delete", "success")
        self.assertIsNone(result["error"], result["error"])
        self.assertFalse(result["durable"]["branch_deleted"])
        branch = json.loads((out_dir / "remote.json").read_text())["branch"]
        listed = git(self.tmp, "ls-remote", self.origin.as_posix(),
                     f"refs/heads/{branch}")
        self.assertIn(branch, listed)

    def test_harness_executor_contract_usage_equals_the_result_tokens(self):
        _out_dir, result = self._run("usage", "success")
        tokens = assert_usage_matches_result(self, self.module, self.tmp / "usage")
        # The three recorded assistant turns: 929, then 91 + 896 cached, then
        # 135 + 960 cached. The recording's own durable_end agrees.
        self.assertEqual(tokens["prompt_tokens"], 3011)
        self.assertEqual(tokens["completion_tokens"], 111)
        self.assertEqual(tokens, result["tokens"])

    def test_harness_executor_contract_activity_returns_the_last_tool_call(self):
        self._run("activity", "success")
        call = last_tool_call(self.module, self.tmp / "activity", now=time.time())
        self.assertEqual(call["name"], "bash")
        self.assertIn("rollcall: handtest", call["summary"])

    def test_harness_executor_contract_the_brief_on_the_box_names_box_paths(self):
        out_dir, _result = self._run("brief", "success")
        box_dir = self._box_dir(out_dir)
        brief = (box_dir / "brief.md").read_text(encoding="utf-8")
        spec = json.loads((box_dir / "spec.json").read_text(encoding="utf-8"))
        self.assertNotIn(str(self.repo), brief)
        self.assertNotIn(self.repo.as_posix(), brief)
        self.assertNotIn(str(out_dir), brief)
        self.assertNotIn(out_dir.as_posix(), brief)
        self.assertEqual(spec["durable"]["box"], "fakebox")
        self.assertEqual(spec["durable"]["remote_url"], self.origin.as_posix())
        from ohflow.workflow import effective_command_time_cap
        self.assertEqual(spec["durable"]["command_cap_s"],
                         effective_command_time_cap(60, None))
        # The box is a Windows machine: its paths are spelled the Windows way
        # on any host that supervises it.
        box = PureWindowsPath(str(box_dir))
        self.assertIn(str(box / "work"), brief)
        self.assertIn(str(box), brief)

    def test_harness_executor_contract_a_dropped_connection_is_host_lost(self):
        out_dir, result = self._run("killed", "killed")
        self.assertEqual(
            result["error"],
            "host_lost: ssh exited 255; the host on fakebox ended without durable_end")
        self.assertFalse(result["durable"]["pushed"])
        # Nothing was fetched back, and the interrupted bash call is recorded open.
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"),
                         json.loads((out_dir / "remote.json").read_text())["start_sha"])
        self.assertEqual(result["open_tool_call"]["tool"], "bash")
        # No durable_end, no fetch: the transport branch is left alone.
        self.assertFalse(result["durable"]["branch_deleted"])

    def test_a_reattached_attempt_replays_and_counts_all_its_usage(self):
        _first_dir, first = self._run("reattach", "killed")
        self.assertIn("host_lost", first["error"])
        before = (self.tmp / "reattach" / "remote.json").read_text(encoding="utf-8")
        out_dir, second = self._run("reattach", "reattach", reattach=True)
        # The reattach continues the same transport: no second push, no new key.
        self.assertEqual(before,
                         (out_dir / "remote.json").read_text(encoding="utf-8"))
        self.assertIsNone(second["error"], second["error"])
        # One replayed assistant turn plus the four the rerun spent.
        self.assertEqual(second["llm_calls"], 5)
        self.assertGreater(second["tokens"]["prompt_tokens"],
                           first["tokens"]["prompt_tokens"])
        tokens, why = self.module.usage(out_dir)
        self.assertIsNone(why)
        self.assertEqual(tokens, second["tokens"])
        self.assertEqual(second["durable"]["head"],
                         git(self.repo, "rev-parse", "HEAD"))

    def test_harness_executor_contract_resume_target_is_none_and_reattach_target_names_the_box(self):
        out_dir, _result = self._run("questions", "success")
        self.assertIsNone(self.module.resume_target(
            recorded_result(out_dir), out_dir))
        remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        self.assertEqual(self.module.reattach_target(out_dir),
                         f"fakebox:{remote['dir']}")

    def test_harness_executor_contract_transcript_is_the_copied_transcript(self):
        out_dir, _result = self._run("transcript", "success")
        path, why = self.module.transcript(out_dir, recorded_result(out_dir))
        self.assertIsNone(why)
        self.assertEqual(path, out_dir / "transcript.md")
        path, why = self.module.transcript(self.tmp / "empty", {})
        self.assertEqual((path, why), (None, "no durable transcript"))

    def test_a_refused_launch_names_the_dirty_worktree(self):
        from ohflow.harness_executor import AgentLaunchError
        (self.repo / "stray.txt").write_text("uncommitted\n", encoding="utf-8")
        os.environ["OHFLOW_FAKE_DURABLE_SCENARIO"] = "success"
        out_dir = self.tmp / "dirty"
        out_dir.mkdir()
        (out_dir / "brief.md").write_text("x\n", encoding="utf-8")
        with self.assertRaises(AgentLaunchError) as caught:
            self.harness_executor.launch(self._spec(), out_dir)
        self.assertIn("stray.txt", str(caught.exception))
