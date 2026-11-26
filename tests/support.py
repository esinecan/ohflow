"""Shared test machinery: fake agents, a throwaway repository, tiny workflows.

Three rules hold for everything in here.

1. **Nothing writes outside a temporary directory.** `TempCase` makes one per
   test with `tempfile.mkdtemp` and removes it afterwards. A test that needs a
   path asks `self.tmp` for it.
2. **No provider is called.** `FakeHarnessExecutor` replaces the real harness executor
   entirely. It never starts a process and never opens a socket. What it returns
   is scripted by the test.
3. **No wall clock is waited on.** Workflows built here set `transient_backoff_s=0`,
   so the engine's cooldown is skipped, and the fake harness executor finishes on the
   engine's first poll so the two-second poll sleep is never reached.

The one exception is git. A few engine paths shell out to `git rev-parse`, and
faking git would be faking the thing under test. `git_repo` therefore creates a
real repository with one real commit, inside the temporary directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from ohflow import harness_executor as ohexecutor
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             AgentSpec)

__all__ = [
    "TempCase", "FakeHarnessExecutor", "FakeHandle", "AgentScript", "git_repo",
    "simple_workflow", "agent_step", "install_fake_harness_executor", "read_run_log",
    "step_statuses", "stub_preflight", "quiet", "FAKE_MODEL",
    "fake_pi_executable", "scrub_attempt_environment",
    "real_process", "is_real_process", "use_settings",
]

#: Settings an operator chooses for a box. Every other `OHFLOW_*` name is a
#: coordinate of a running attempt (log path, run directory, write scope).
OPERATOR_SETTINGS = frozenset({
    "OHFLOW_E2E", "OHFLOW_BASH", "OHFLOW_PI_EXE", "OHFLOW_CLAUDE_EXE",
    "OHFLOW_CODEX_EXE",
    "OHFLOW_PI_CATALOG", "OHFLOW_RUN_HIDDEN"})


def scrub_attempt_environment(env=None) -> None:
    """Drop the coordinates of a running attempt from `env` (default: os.environ).

    An agent that runs this suite carries `OHFLOW_*` variables that name its
    own evidence. Each child the suite starts would inherit them.
    """
    env = os.environ if env is None else env
    for name in [n for n in env if n.startswith("OHFLOW_")
                 and n not in OPERATOR_SETTINGS
                 and not n.startswith("OHFLOW_TEST_")]:
        del env[name]


scrub_attempt_environment()

#: The suite reads `operator.settings.json` beside this file over the shipped
#: base settings, so the real operator's local file never changes a result. It
#: names a durable box and a pi-cloud Worker and leaves every house rule at its
#: base value. `OHFLOW_TEST_SETTINGS` names another file, such as the
#: operator's own for a real-model run.
TEST_OPERATOR_SETTINGS = Path(__file__).resolve().with_name("operator.settings.json")
os.environ["OHFLOW_SETTINGS"] = os.environ.get("OHFLOW_TEST_SETTINGS",
                                               str(TEST_OPERATOR_SETTINGS))


def use_settings(case: unittest.TestCase, values: dict) -> Path:
    """Run `case` with `values` as the operator's local settings file."""
    import json
    folder = Path(tempfile.mkdtemp(prefix="ohflow-settings-"))
    path = folder / "ohflow.settings.local.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    patcher = mock.patch.dict(os.environ, {"OHFLOW_SETTINGS": str(path)})
    patcher.start()
    case.addCleanup(patcher.stop)
    case.addCleanup(shutil.rmtree, folder, True)
    return path

REAL_PROCESS_ATTR = "ohflow_real_process"


def real_process(target):
    setattr(target, REAL_PROCESS_ATTR, True)
    return target


def is_real_process(test) -> bool:
    method = getattr(test, getattr(test, "_testMethodName", ""), None)
    return bool(getattr(test, REAL_PROCESS_ATTR, False)
                or getattr(method, REAL_PROCESS_ATTR, False))

#: A model that names an environment variable the tests set themselves. No key
#: value ever appears here, and no request is ever built from it.
FAKE_MODEL = ModelConfig(model="fake/deterministic",
                         base_url="http://127.0.0.1:0/never-called",
                         api_key_env="OHFLOW_TEST_FAKE_KEY")


# --------------------------------------------------------------- the fake harness executor


class AgentScript:
    """What a fake agent does when the engine asks.

    `final_text` is written to `final.md`, `error` becomes the collected error,
    and `exit_status` is what `poll` returns once the agent has "finished".
    `on_poll` is called with the engine before every poll, which is how a test
    makes something happen while a step is in flight - setting the abort event,
    for example.
    """

    def __init__(self, *, final_text: str = "DONE\n", error: str | None = None,
                 exit_status: str = ohexecutor.FINISHED,
                 structured: Any = None,
                 on_poll: Callable[[], str | None] | None = None,
                 tokens: dict | None = None,
                 sequence: list[dict] | None = None,
                 files: dict[str, str] | None = None):
        self.final_text = final_text
        self.error = error
        self.exit_status = exit_status
        self.structured = structured
        self.on_poll = on_poll
        self.tokens = tokens or {"prompt": 10, "completion": 5}
        self.files = files or {}
        # One entry per launch, for an agent that must answer differently the
        # second time. Each entry may carry `final_text`, `error`, `structured`
        # and `tokens`; anything it leaves out falls back to the values above.
        # The last entry answers every launch past the end of the list.
        self.sequence = sequence
        self.launches = 0
        self.kills = 0

    def answer(self, launch_index: int) -> dict:
        """What this agent says on its `launch_index`-th launch, 1-based."""
        base = {"final_text": self.final_text, "error": self.error,
                "structured": self.structured, "tokens": dict(self.tokens), "files": self.files}
        if not self.sequence:
            return base
        entry = self.sequence[min(launch_index, len(self.sequence)) - 1]
        base.update(entry)
        return base


class FakeHandle:
    def __init__(self, coord: str, out_dir: Path, script: AgentScript,
                 attempt: int | None = None):
        self.coord = coord
        self.harness_executor = "pi"
        self.out_dir = Path(out_dir)
        self.spec_path = self.out_dir / "spec.json"
        self.script = script
        self.killed = False
        self.error: str | None = None
        # `collect` runs more than once for a killed agent, and the live count
        # must fall exactly once per launch.
        self.collected = False
        # Which launch of this script this handle is, 1-based. A scripted
        # agent answers differently on its second launch, and that is what a
        # retry test needs.
        self.launch_index = 1
        self.attempt = attempt


class FakeHarnessExecutor:
    """An agent harness executor that runs no process.

    One instance is shared by every step in a run, because the registry builds
    a harness executor per call and the test needs one object to inspect afterwards.
    `install_fake_harness_executor` hands the test a resolver that returns it.
    """

    name = "pi"

    def __init__(self, scripts: dict[str, AgentScript] | None = None,
                 default: AgentScript | None = None,
                 gate_at: int | None = None, gate_timeout: float = 0.25):
        self.scripts = scripts or {}
        self.default = default or AgentScript()
        self.launched: list[str] = []
        self.killed: list[str] = []
        self._lock = threading.Lock()
        # How many agents were in flight at once, and the most there ever were.
        # A step holds its slot for as long as `launch` has not returned, so the
        # peak is measured where the semaphore actually binds.
        self._live = 0
        self.peak = 0
        # `gate_at` holds each launch until this many agents are in flight, or
        # until `gate_timeout` elapses. A concurrency test can then observe a
        # real overlap without any test waiting on a wall clock it cannot bound:
        # a limit below `gate_at` releases on the timeout and the peak says so.
        self.gate_at = gate_at
        self.gate_timeout = gate_timeout
        self._arrived = threading.Condition(self._lock)

    def script_for(self, coord: str) -> AgentScript:
        for key, script in self.scripts.items():
            if coord.endswith(key) or key == coord:
                return script
        return self.default

    # ---- the HarnessExecutor protocol

    def preflight(self) -> list[str]:
        return []

    def launch(self, spec: dict, out_dir: Path) -> FakeHandle:
        coord = spec["coord"]
        script = self.script_for(coord)
        with self._lock:
            self.launched.append(coord)
            script.launches += 1
            launch_index = script.launches
            self._live += 1
            if self._live > self.peak:
                self.peak = self._live
            if self.gate_at is not None:
                self._arrived.notify_all()
                self._arrived.wait_for(lambda: self._live >= self.gate_at,
                                       timeout=self.gate_timeout)
        handle = FakeHandle(coord, out_dir, script, spec.get("attempt"))
        handle.launch_index = launch_index
        return handle

    def poll(self, handle: FakeHandle) -> str:
        if handle.killed:
            handle.error = "fake child was killed"
            return ohexecutor.ERROR
        if handle.script.on_poll is not None:
            override = handle.script.on_poll()
            if override is not None:
                if handle.killed:
                    handle.error = "fake child was killed"
                    return ohexecutor.ERROR
                return override
        return handle.script.exit_status

    def collect(self, handle: FakeHandle) -> dict:
        script = handle.script
        with self._lock:
            if not handle.collected:
                handle.collected = True
                self._live -= 1
                if self.gate_at is not None:
                    self._arrived.notify_all()
        said = script.answer(handle.launch_index)
        for name, text in said.get("files", {}).items():
            target = handle.out_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        (handle.out_dir).mkdir(parents=True, exist_ok=True)
        (handle.out_dir / "final.md").write_text(said["final_text"],
                                                 encoding="utf-8")
        result = {
            "coord": handle.coord,
            "attempt": handle.attempt,
            "conversation_id": "fake-" + handle.coord.replace("/", "-"),
            "execution_status": "finished" if said["error"] is None else "error",
            "tool_calls": 1, "observation_errors": 0, "llm_calls": 1,
            "wall_seconds": 0.0, "tokens": dict(said["tokens"]),
            "cost": 0.0, "cost_source": "unpriced",
            "final_text_path": "final.md",
            "structured": said["structured"],
            "error": said["error"],
        }
        (handle.out_dir / "result.json").write_text(
            __import__("json").dumps(result, indent=2), encoding="utf-8")
        return result

    def kill(self, handle: FakeHandle) -> None:
        handle.killed = True
        handle.error = "fake child was killed"
        with self._lock:
            self.killed.append(handle.coord)
            handle.script.kills += 1


def fake_harness_executors(harness_executor: FakeHarnessExecutor) -> Callable[[str], FakeHarnessExecutor]:
    """A harness executor resolver that answers every harness executor name with `harness_executor`."""
    return lambda name: harness_executor


def install_fake_harness_executor(case: unittest.TestCase, harness_executor: FakeHarnessExecutor) -> FakeHarnessExecutor:
    """Give `case` a resolver that returns `harness_executor`, as `case.harness_executors`.

    The test passes `harness_executors=self.harness_executors` to the `Engine`, or `harness_executors=` in the run
    options. One shared instance answers every harness executor name, because the registry
    builds a new harness executor per call and the test needs one object to inspect.
    """
    case.harness_executors = fake_harness_executors(harness_executor)
    return harness_executor


# ----------------------------------------------------------------- temp cases


class TempCase(unittest.TestCase):
    """A test case with one temporary directory, removed afterwards.

    Everything a test writes goes under `self.tmp`. Nothing in this suite takes
    a path from the environment, from a scratchpad or from a home directory.
    """

    #: The harness executor resolver a test passes to the `Engine`. None means the registry.
    harness_executors: Callable[[str], Any] | None = None

    def setUp(self) -> None:
        super().setUp()
        # Resolved: on macOS the temp dir sits behind the /var symlink, and
        # the engine resolves the paths it records.
        self.tmp = Path(tempfile.mkdtemp(prefix="ohflow-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # An agent model names this variable. Preflight only checks that it is
        # non-empty, and no fake harness executor ever reads it.
        os.environ.setdefault("OHFLOW_TEST_FAKE_KEY", "not-a-key")
        # A detached run waits for its dashboard URL. A test's launcher is a
        # fake that never serves one, so the wait would only cost 20 s.
        from ohflow import cli as ohcli
        patch = mock.patch.object(ohcli, "DASHBOARD_WAIT_S", 0.0)
        patch.start()
        self.addCleanup(patch.stop)

    def run_dir(self, run_id: str = "r-test-0001") -> Path:
        return self.tmp / "runs" / run_id


# ---------------------------------------------------------- a fake pi process


def fake_pi_executable(root: Path) -> Path:
    """Write a deterministic stand-in for pi's ``--mode json`` process.

    ``OHFLOW_FAKE_PI_SCENARIO`` selects a recorded stream shape.  The fixture
    deliberately runs as a real descendant process: these tests exercise the
    harness executor's process, event-file, stall and job-object behaviour, not a mocked
    call boundary.
    """
    path = Path(root) / "fake-pi.py"
    path.write_text(
        r'''from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


ERRORS = {
    "429": '429: {"message":"Rate limit reached for requests","type":"rate_limit_error","param":null,"code":"rate_limit_exceeded"}',
    "401": '401: {"message":"Phase 0 unauthorized","type":"authentication_error","param":null,"code":"invalid_api_key"}',
    "400": '400: {"message":"Phase 0 bad request","type":"invalid_request_error","param":null,"code":"bad_request"}',
}


def emit(event):
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def assistant(text="", *, error=None, stop_reason=None):
    message = {
        "role": "assistant",
        "content": [] if error else [{"type": "text", "text": text}],
        "provider": "phase0-stub",
        "model": "glm-5.3-flash",
        "usage": {
            "input": 11, "output": 3, "cacheRead": 2, "cacheWrite": 1,
            "reasoning": 1, "cost": {"total": 0.00125},
        },
        "stopReason": stop_reason or ("error" if error else "stop"),
    }
    if error:
        message["errorMessage"] = error
    emit({"type": "message_end", "message": message})


args = sys.argv[1:]
scenario = os.environ.get("OHFLOW_FAKE_PI_SCENARIO", "success")
if "--session-dir" in args:
    session_dir = Path(args[args.index("--session-dir") + 1])
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "fake-session.jsonl").write_text(
        '{"type":"session","id":"fake-session"}\n', encoding="utf-8")

if scenario == "success":
    emit({"type": "tool_execution_end", "toolName": "read", "isError": False})
    assistant("DONE\n")
elif scenario == "schema":
    assistant('DONE\n```json\n{"answer":"ok","count":2}\n```\n')
elif scenario in ERRORS:
    assistant(error=ERRORS[scenario])
elif scenario == "slow":
    time.sleep(60)
elif scenario == "torn-tail":
    assistant(error=ERRORS["429"])
    sys.stdout.write('{"type":"message_end","message":')
    sys.stdout.flush()
    time.sleep(60)
elif scenario == "immediate-grandchild":
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=flags,
    )
    state = Path(os.environ["OHFLOW_FAKE_PI_STATE"])
    state.mkdir(parents=True, exist_ok=True)
    (state / "grandchild.pid").write_text(str(child.pid), encoding="ascii")
    time.sleep(60)
elif scenario == "iterations":
    assistant("calling tool", stop_reason="toolUse")
    time.sleep(60)
else:
    raise SystemExit("unknown OHFLOW_FAKE_PI_SCENARIO=" + scenario)
''',
        encoding="utf-8",
    )
    return path


# ----------------------------------------------------------------- a real repo


def git_repo(root: Path, branch: str = "main") -> Path:
    """A real git repository with one commit, inside `root`.

    Real because `Engine.preflight` and `rundir.Run.write_summary` shell out to git,
    and a fake git would be faking the subject. It is one `git init` and one
    commit, which costs well under a second.

    The repository's own config names `user.name` and `user.email`. A merge
    step and a campaign revision commit through ohflow's own git calls, which
    carry no identity, and a machine with no global identity refuses them.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "ohflow tests",
        "GIT_AUTHOR_EMAIL": "tests@localhost",
        "GIT_COMMITTER_NAME": "ohflow tests",
        "GIT_COMMITTER_EMAIL": "tests@localhost",
        "GIT_CONFIG_GLOBAL": str(root / ".gitconfig-none"),
        "GIT_CONFIG_SYSTEM": str(root / ".gitconfig-none"),
    })

    def g(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       capture_output=True, env=env,
                       creationflags=getattr(subprocess,
                                             "CREATE_NO_WINDOW", 0))

    subprocess.run(["git", "init", "-b", branch, str(root)], check=True,
                   capture_output=True, env=env,
                   creationflags=getattr(subprocess,
                                         "CREATE_NO_WINDOW", 0))
    g("config", "user.name", "ohflow tests")
    g("config", "user.email", "tests@localhost")
    (root / "README.md").write_text("a throwaway repository\n", encoding="utf-8")
    g("add", "README.md")
    g("commit", "-m", "initial commit")
    return root


# ------------------------------------------------------------------- tiny workflows


def simple_workflow(repo: Path, *, steps: list[Step] | None = None,
                    on_step_failure: str = "quarantine",
                    min_success: Any = "all",
                    max_parallel: int = 3,
                    name: str = "test-workflow",
                    phases: tuple[Phase, ...] | None = None) -> Workflow:
    """One phase of agent steps, no worktrees, no backoff.

    No worktree on purpose: creating one costs several git calls per step and
    none of the defects under test live there. A step with `worktree=None` runs
    against `workflow.repo` directly.
    """
    if phases is None:
        if steps is None:
            steps = [agent_step("s1")]
        phases = (Phase(name="Only phase", steps=tuple(steps),
                        on_step_failure=on_step_failure,
                        min_success=min_success),)
    return Workflow(
        name=name,
        repo=Path(repo),
        base_branch="main",
        baseline_cmd=None,
        max_parallel=max_parallel,
        worktrees=(),
        phases=phases,
        transient_backoff_s=0,          # no test ever waits on a cooldown
    )


def agent_step(step_id: str, *, gate: GateSpec | None = None,
               schema: dict | None = None,
               execution_timeout_s: int = 5400,
               brief: str = "do the trivial thing",
               note: str | None = None) -> Step:
    if gate is None:
        gate = GateSpec(checks=(CheckSpec("final_message_matches",
                                          {"regex": r"DONE"}),))
    return Step(
        id=step_id,
        kind="agent",
        worktree=None,
        execution_timeout_s=execution_timeout_s,
        schema=schema,
        note=note,
        gate=gate,
        agent=AgentSpec(role=f"role-{step_id}", brief=brief,
                        model=FAKE_MODEL, max_iterations=5, harness_executor="pi"),
    )


# ------------------------------------------------------------------- readback


def read_run_log(run_dir: Path) -> list[dict]:
    import json
    p = Path(run_dir) / "run-log.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def step_statuses(run_dir: Path) -> dict[str, str]:
    """coord -> final status, replayed from the run log rather than from the
    engine's memory. The run log is what a resume will read."""
    from ohflow.run_log import RunLog
    state = RunLog.replay(Path(run_dir))
    return {c: r.status for c, r in state.steps.items()}


class quiet:
    """Swallow stdout and stderr for the duration of a block.

    The CLI writes a board and a status line on every run, and a suite that
    prints them is a suite nobody reads. What the CLI wrote is still available:
    `quiet().out` holds it after the block, for a test that wants to assert on
    it.
    """

    def __init__(self) -> None:
        self._buf = None
        self.out = ""

    def __enter__(self):
        import io
        import contextlib
        self._buf = io.StringIO()
        self._redirect_out = contextlib.redirect_stdout(self._buf)
        self._redirect_err = contextlib.redirect_stderr(self._buf)
        self._redirect_out.__enter__()
        self._redirect_err.__enter__()
        return self

    def __exit__(self, *exc):
        self._redirect_err.__exit__(*exc)
        self._redirect_out.__exit__(*exc)
        self.out = self._buf.getvalue()
        return False


def stub_preflight(case: unittest.TestCase) -> None:
    """Make `Engine.preflight` and `Engine.baseline` return nothing.

    Used only by tests about scheduling, where preflight is not the subject and
    each of its git calls costs about 350 ms through Git Bash. The preflight
    path has its own test that does not stub it.
    """
    from ohflow.engine import Engine
    original_p, original_b = Engine.preflight, Engine.baseline
    Engine.preflight = lambda self: []
    Engine.baseline = lambda self: {"command": None, "skipped": "stubbed in tests"}
    case.addCleanup(setattr, Engine, "preflight", original_p)
    case.addCleanup(setattr, Engine, "baseline", original_b)
