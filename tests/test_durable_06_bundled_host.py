"""The durable host ships inside ohflow and serves box `local` and a box over ssh.

`ohflow/host/` is the host. `durable_host.py` installs it on the machine
that runs the step by feeding `install.cjs`, with the host's files embedded,
to that machine's `node`. The fakes play both machines: `fake_durable.py` is
`ssh` and `scp` to a box, `fake_durable_node.py` is this machine's `node`.

What is proved:

- the bundle holds the host's own files and no installed ones, and its version
  follows their content;
- the preflight for a box checks its ssh and its node;
- a step on `local` needs no remote: it works in the worktree, ends with the
  worktree's commit, and copies the transcript out of `<attempt dir>/durable`;
- on `local`, a host that ends with no `durable_end` is `host_lost`, and the
  reattach continues the same step folder and session;
- the preflight for `local` checks this machine's node version;
- `agent.box` accepts `local`;
- with a real node: the host's modules parse, and the installer answers at
  once for a version it already holds, or refuses a node below 22.19.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import unittest
from dataclasses import replace
from pathlib import Path

from ohflow import durable_host, durable_runner, harness_executors
from ohflow.harness_executor import FINISHED, RUNNING
from ohflow.workflow import AgentSpec, ModelConfig
from support import TempCase, git_repo

FAKES = Path(__file__).resolve().parent / "fakes"
WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NODE = shutil.which("node")


def node_below_minimum() -> bool:
    done = subprocess.run([NODE, "--version"], capture_output=True, text=True,
                          creationflags=WINDOW, timeout=60)
    major, minor = (int(part) for part in done.stdout.strip().lstrip("v").split(".")[:2])
    return (major, minor) < durable_runner.NODE_MIN


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=ohflow tests",
         "-c", "user.email=tests@localhost", *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=WINDOW)
    assert done.returncode == 0, (args, done.stderr, done.stdout)
    return done.stdout.strip()


class BundledHostCase(TempCase):

    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self._set_env("OHFLOW_DURABLE_SSH", str(FAKES / "fake_durable.py"))
        self._set_env("OHFLOW_DURABLE_SCP", str(FAKES / "fake_durable.py"))
        self._set_env("OHFLOW_DURABLE_NODE", str(FAKES / "fake_durable_node.py"))
        self._set_env("OHFLOW_FAKE_DURABLE_HOME", str(self.home))
        self.harness_executor = harness_executors.harness_executor_for("durable")

    def _set_env(self, name: str, value: str | None) -> None:
        old = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        self.addCleanup(lambda: os.environ.pop(name, None) if old is None
                        else os.environ.__setitem__(name, old))

    def _spec(self, repo: Path, box: str, **changes) -> dict:
        spec = {"coord": "01.report/01.durable", "attempt": 1, "role": "rollcall",
                "harness_executor": "durable", "box": box,
                "workspace": str(repo),
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

    def _run(self, repo: Path, box: str, name: str, scenario: str,
             **changes) -> tuple[Path, dict]:
        self._set_env("OHFLOW_FAKE_DURABLE_SCENARIO", scenario)
        out_dir = self.tmp / name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "brief.md").write_text(f"# Task\n\nWork in {repo}.\n",
                                          encoding="utf-8")
        handle = self.harness_executor.launch(self._spec(repo, box, **changes), out_dir)
        deadline = time.monotonic() + 90
        state = RUNNING
        while state == RUNNING and time.monotonic() < deadline:
            state = self.harness_executor.poll(handle)
            time.sleep(0.05)
        if state == RUNNING:
            self.harness_executor.kill(handle)
            self.fail("durable runner did not finish in 90 s")
        self.assertEqual(state, FINISHED)
        return out_dir, self.harness_executor.collect(handle)


class TheBundle(BundledHostCase):

    def test_the_bundle_holds_the_host_files_and_none_installed(self):
        files = durable_host.host_files()
        for name in ("ohflow-step.mjs", "install.cjs", "package.json",
                     "package-lock.json", "src/host.mjs", "native/winjob.cs"):
            self.assertIn(name, files)
        self.assertFalse([n for n in files
                          if n.startswith(("node_modules/", "bin/")) or "/." in n])
        first = durable_host.installer_program().split(b"\n", 1)[0].decode("utf-8")
        self.assertTrue(first.startswith("const BUNDLE = ") and first.endswith(";"))
        bundle = json.loads(first[len("const BUNDLE = "):-1])
        self.assertEqual(bundle["version"], durable_host.host_version())
        self.assertNotIn("install.cjs", bundle["files"])
        self.assertIn("ohflow-step.mjs", bundle["files"])

    def test_the_version_follows_the_content_and_ignores_line_endings(self):
        copy = self.tmp / "host"
        shutil.copytree(durable_host.HOST_DIR, copy,
                        ignore=shutil.ignore_patterns("node_modules", "bin"))
        version = durable_host.host_version(durable_host.host_files(copy))
        step = copy / "ohflow-step.mjs"
        text = step.read_bytes().replace(b"\r\n", b"\n")
        step.write_bytes(text.replace(b"\n", b"\r\n"))
        self.assertEqual(durable_host.host_version(durable_host.host_files(copy)), version)
        step.write_bytes(text + b"\n")
        self.assertNotEqual(durable_host.host_version(durable_host.host_files(copy)), version)

    def test_agent_box_accepts_local(self):
        model = ModelConfig(model="zai/glm-5.3-flash", base_url="", api_key_env="",
                            params={"thinking": "low"})
        agent = AgentSpec(role="implement", brief="x", model=model,
                          harness_executor="durable", box="local")
        self.assertEqual(durable_runner.agent_errors("01.p/01.s", agent), [])
        errs = durable_runner.agent_errors("01.p/01.s", replace(agent, box="no box"))
        self.assertIn("or local for this machine", errs[0])


class OnABox(BundledHostCase):

    def setUp(self):
        super().setUp()
        origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                       check=True, capture_output=True, creationflags=WINDOW)
        self.repo = git_repo(self.tmp / "repo")
        git(self.repo, "remote", "add", "origin", origin.as_posix())
        git(self.repo, "push", "origin", "main")

    def test_the_box_preflight_checks_ssh_and_node(self):
        self._set_env("OHFLOW_DURABLE_BOX", "fakebox")
        self.assertEqual(durable_runner.box_preflight(), [])
        self._set_env("OHFLOW_FAKE_DURABLE_NODE_VERSION", "v22.18.0")
        faults = durable_runner.box_preflight()
        self.assertEqual(len(faults), 1, faults)
        self.assertIn("node v22.18 on fakebox is below v22.19", faults[0])


class OnLocal(BundledHostCase):

    def setUp(self):
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")

    def test_a_local_step_works_in_the_worktree_with_no_remote(self):
        start = git(self.repo, "rev-parse", "HEAD")
        out_dir, result = self._run(self.repo, "local", "local", "success")
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["execution_status"], "finished")
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertNotEqual(head, start)
        self.assertEqual(result["durable"]["head"], head)
        self.assertEqual(result["durable"]["box"], "local")
        self.assertFalse(result["durable"]["pushed"])
        self.assertEqual(git(self.repo, "remote"), "")
        step_dir = (out_dir / "durable").resolve()
        remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        self.assertEqual(remote["box"], "local")
        self.assertEqual(remote["dir"], str(step_dir))
        wire = json.loads((step_dir / "spec.json").read_text(encoding="utf-8"))
        self.assertEqual(wire["durable"]["work"], str(self.repo.resolve()))
        self.assertEqual(wire["durable"]["key"], remote["key"])
        self.assertEqual((step_dir / "brief.md").read_text(encoding="utf-8"),
                         (out_dir / "brief.md").read_text(encoding="utf-8"))
        self.assertTrue((out_dir / "transcript.md").is_file())
        calls = [json.loads(line) for line in
                 (self.home / "node-calls.jsonl").read_text(encoding="utf-8").splitlines()]
        installed = self.home / ".pi-durable" / "ohflow-host" / durable_host.host_version()
        self.assertEqual(calls[0], [])
        self.assertEqual(calls[-1], [str(installed.resolve() / "ohflow-step.mjs"),
                                     "local", str(step_dir)])
        self.assertEqual(durable_runner.reattach_target(out_dir), f"local:{step_dir}")

    def test_a_local_host_that_dies_is_host_lost_and_reattaches_in_place(self):
        out_dir, first = self._run(self.repo, "local", "attempt", "killed")
        self.assertEqual(first["error"], "host_lost: node exited 255; the host on "
                         "local ended without durable_end")
        self.assertEqual(first["open_tool_call"]["tool"], "bash")
        session = out_dir / "durable" / "session.sqlite"
        self.assertTrue(session.is_file())
        before = (out_dir / "remote.json").read_text(encoding="utf-8")
        out_dir, second = self._run(self.repo, "local", "attempt", "reattach",
                                    reattach=True)
        self.assertEqual((out_dir / "remote.json").read_text(encoding="utf-8"), before)
        self.assertIsNone(second["error"], second["error"])
        self.assertEqual(second["llm_calls"], 5)
        self.assertEqual(second["durable"]["session"], str(session.resolve()))
        self.assertEqual(second["durable"]["head"], git(self.repo, "rev-parse", "HEAD"))

    def test_the_local_preflight_checks_this_machines_node(self):
        self._set_env("OHFLOW_DURABLE_BOX", "local")
        self.assertEqual(durable_runner.box_preflight(), [])
        self._set_env("OHFLOW_FAKE_DURABLE_NODE_VERSION", "v20.11.0")
        faults = durable_runner.box_preflight()
        self.assertEqual(len(faults), 1, faults)
        self.assertIn("node v20.11 on this machine is below v22.19", faults[0])


@unittest.skipUnless(NODE, "node is not on PATH")
class WithRealNode(TempCase):

    def test_every_host_module_parses(self):
        for path in sorted(durable_host.HOST_DIR.rglob("*.mjs")) + [
                durable_host.HOST_DIR / "install.cjs"]:
            if "node_modules" in path.parts:
                continue
            with self.subTest(path=path.name):
                done = subprocess.run([NODE, "--check", str(path)], capture_output=True,
                                      text=True, creationflags=WINDOW)
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_installer_answers_at_once_for_a_version_it_holds(self):
        version = durable_host.host_version()
        held = self.tmp / "hosts" / version
        held.mkdir(parents=True)
        (held / ".version").write_text(version + "\n", encoding="utf-8")
        env = {**os.environ, "OHFLOW_DURABLE_HOST_HOME": str(self.tmp / "hosts")}
        done = subprocess.run([NODE], input=durable_host.installer_program(),
                              capture_output=True, env=env, creationflags=WINDOW,
                              timeout=60)
        line = json.loads(done.stdout.decode("utf-8").splitlines()[0])
        if node_below_minimum():
            self.assertEqual(done.returncode, 1, done.stderr)
            self.assertEqual(line["type"], "durable_error")
            self.assertIn("is below 22.19", line["message"])
            return
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(line["type"], "durable_host")
        self.assertEqual(line["version"], version)
        self.assertFalse(line["installed"])
        self.assertEqual(Path(line["dir"]), held)
        self.assertEqual(sorted(p.name for p in held.iterdir()), [".version"])


if __name__ == "__main__":
    unittest.main()
