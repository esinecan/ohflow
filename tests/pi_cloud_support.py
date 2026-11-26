"""Shared machinery for the pi-cloud tests: a bare origin, a repo, the fake Worker.

Every pi-cloud test needs the same three things: a bare `origin` the fake
Worker clones from and pushes to, a clean repository pointing at it (the
transport is real git, so faking it would fake the subject), and the
in-process fake Worker of `tests/fakes/fake_pi_cloud.py` with
`OHFLOW_PI_CLOUD_URL` pointed at it. `PiCloudCase` builds all three and hands
each test the executors, the deterministic attempt key and the two ways to
drive the system under test:

- `run_client` starts the real `pi_cloud_client.py` against the fake Worker,
- `run_attempt` launches the real `PiCloudHarnessExecutor` on one attempt
  directory and collects its result, as `test_harness_executor_contract_*`
  does for the other harness executors.

`PI_CLOUD_TOKEN` is set to the fake's own token for the duration of each
test and restored afterwards; its value is a test constant, so no run ever
reads a real token, and R9's assertions can name it safely.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fakes.fake_pi_cloud import FakeWorker
from ohflow import harness_executors, remote_git
from ohflow.harness_executor import FINISHED, RUNNING
from support import TempCase, git_repo

CLIENT = (Path(__file__).resolve().parents[1] / "scripts" / "ohflow"
          / "pi_cloud_client.py")
WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TOKEN = "pi-cloud-test-token"
COORD = "01.report/01.s1"


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=ohflow tests",
         "-c", "user.email=tests@localhost", "-c", "commit.gpgsign=false",
         *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", creationflags=WINDOW)
    assert done.returncode == 0, (args, done.stderr, done.stdout)
    return done.stdout.strip()


@contextlib.contextmanager
def override_env(name: str, value: str):
    """One variable for one block, restored to what it was before."""
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def spec(workspace: Path, **changes) -> dict:
    """One pi-cloud agent spec, as the engine writes it into `spec.json`."""
    record = {"coord": COORD, "attempt": 1, "role": "rollcall",
              "harness_executor": "pi-cloud",
              "workspace": str(workspace),
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
    record.update(changes)
    return record


class PiCloudCase(TempCase):
    """A bare origin, a clean repo on it, and the fake Worker over both."""

    def setUp(self):
        super().setUp()
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.origin)],
                       check=True, capture_output=True, creationflags=WINDOW)
        self.repo = git_repo(self.tmp / "repo")
        git(self.repo, "remote", "add", "origin", self.origin.as_posix())
        git(self.repo, "push", "origin", "main")
        self.worker = FakeWorker(self.origin, self.tmp / "worker",
                                 token=TOKEN).start()
        self.addCleanup(self.worker.stop)
        self._set_env("PI_CLOUD_TOKEN", TOKEN)
        self._set_env("OHFLOW_PI_CLOUD_URL", self.worker.url)
        self.executor = harness_executors.harness_executor_for("pi-cloud")
        self.module = harness_executors.harness_executor_module("pi-cloud")

    def _set_env(self, name: str, value: str) -> None:
        old = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(lambda: os.environ.pop(name, None) if old is None
                        else os.environ.__setitem__(name, old))

    def key_of(self, out_dir: Path, *, attempt: int = 1,
               coord: str = COORD) -> str:
        """The deterministic attempt key the launch mints for `out_dir`."""
        return remote_git.attempt_key(coord, attempt, out_dir)

    def branch_for(self, key: str) -> str:
        return f"ohflow/pi-cloud/{key}"

    def post_step(self, key: str, branch: str, start_sha: str) -> dict:
        """One `step` post, as the runner's adapter makes it."""
        url = (f"{self.worker.url}/attempts/"
               f"{urllib.parse.quote(key, safe='')}/step")
        request = urllib.request.Request(url, data=json.dumps({
            "operationId": key, "brief": "# Task\n", "model": "zai/glm-5.3-flash",
            "thinking": "low", "remote_url": self.origin.as_posix(),
            "branch": branch, "start_sha": start_sha,
            "ohflow": {"coord": COORD, "attempt": 1, "key": key},
        }).encode("utf-8"), method="POST", headers={
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "ohflow-pi-cloud/1",
            "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def run_client(self, name: str, *, operation: str | None = None,
                   timeout: float = 60.0,
                   env: dict | None = None) -> subprocess.CompletedProcess:
        """The real client against the fake Worker, captured."""
        return subprocess.run(
            [sys.executable, str(CLIENT), "events", "--url", self.worker.url,
             "--name", name, "--operation", operation or name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
            env={**os.environ, **(env or {})}, creationflags=WINDOW)

    def run_attempt(self, name: str, *, timeout: float = 120.0,
                    brief: str | None = None, **spec_changes) -> tuple[Path, dict]:
        """One pi-cloud attempt through the real executor, launched and collected."""
        out_dir = self.tmp / name
        out_dir.mkdir(parents=True, exist_ok=True)
        # Both renderings of both paths, as the position block and the brief
        # mix them; the posted brief must carry none of them.
        (out_dir / "brief.md").write_text(
            brief if brief is not None else
            f"# Task\n\nWork in {self.repo} and in {self.repo.as_posix()}. "
            f"Your evidence is at {out_dir} and at {out_dir.as_posix()}.\n",
            encoding="utf-8")
        handle = self.executor.launch(spec(self.repo, **spec_changes), out_dir)
        deadline = time.monotonic() + timeout
        state = RUNNING
        while state == RUNNING and time.monotonic() < deadline:
            state = self.executor.poll(handle)
            time.sleep(0.05)
        if state == RUNNING:
            self.executor.kill(handle)
            self.fail(f"pi-cloud runner did not finish in {timeout}s")
        self.assertEqual(state, FINISHED,
                         sorted(p.name for p in (out_dir / "logs").iterdir()))
        return out_dir, self.executor.collect(handle)
