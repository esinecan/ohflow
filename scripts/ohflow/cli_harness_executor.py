"""Process-backed harness executor used by command-line coding agents."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import codecs
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from . import IMPORT_ROOT, attempt_record, tool_output as tool_output_files
from .tool_output import CallEvent, ToolOutputWriter
from .proc import spawn_managed, agent_env
from .harness_executor import ERROR, FINISHED, RUNNING, Handle, AgentLaunchError


@dataclass(frozen=True)
class CliPreparedProcess:
    """Agent-specific launch data consumed by the shared process runtime."""

    argv: Sequence[str]
    cwd: Path
    env: Mapping[str, str]
    context: Any = None


@dataclass(frozen=True)
class CliEventAction:
    """Agent interpretation of one event, expressed as generic runtime actions."""

    heartbeat: Mapping[str, Any] | None = None
    stop_error: str | None = None
    # What the event says about tool calls: starts, output, ends. The runtime
    # writes them to the tool-output contract and keeps the open set from them.
    calls: tuple[CallEvent, ...] = ()


@dataclass(frozen=True)
class CliRunOutcome:
    spec: Mapping[str, Any]
    out_dir: Path
    prepared: CliPreparedProcess
    events: tuple[Mapping[str, Any], ...]
    returncode: int
    started_at: float
    finished_at: float
    stop_error: str | None


class CliAgentAdapter(Protocol):
    """The agent-specific half of a command-line agent integration."""

    name: str
    event_log_name: str
    stderr_log_name: str

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess: ...

    def parse_event(self, line: str) -> Mapping[str, Any]: ...

    def on_event(self, spec: dict[str, Any], event: Mapping[str, Any],
                 events: list[Mapping[str, Any]]) -> CliEventAction: ...

    def build_result(self, outcome: CliRunOutcome) -> tuple[dict[str, Any], str | None]: ...

    # Optional. `liveness_at(prepared, out_dir) -> float | None` names the
    # newest moment the agent showed life outside stdout, for an agent whose
    # stdout is silent while it works. The stall deadline reads it.
    #
    # Optional. `answered_at(prepared, out_dir) -> float | None` names when the
    # agent finished its answer. An agent still running `exit_grace_s` after
    # that is killed, and `prepared.context["exit_grace_killed"]` is set.
    #
    # Optional. `poll_calls(prepared, out_dir) -> list[CallEvent]` names tool
    # calls the agent's stdout does not carry. The runtime asks every
    # `POLL_CALLS_S` seconds.


#: Seconds between `poll_calls` reads.
POLL_CALLS_S = 2.0
#: The runtime's own command time cap fires this long after the harness-native
#: one, so the harness's cap answers first where one exists.
COMMAND_TIME_CAP_GRACE_S = 60


def read_event_log(path: Path, parser: Callable[[str], Mapping[str, Any]]
                   ) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """Every complete event of an event log, and what the log was.

    The second value says `event_log`: `absent` (a runner killed before it
    opened its log left none), `unreadable` with the `error`, `empty` (no
    line parsed) or `read`, and `unparsed_lines`, the torn or foreign lines
    that were skipped.
    """
    path = Path(path)
    state: dict[str, Any] = {"event_log": EVENT_LOG_ABSENT, "unparsed_lines": 0,
                             "error": None}
    if not path.exists():
        return [], state
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return [], {**state, "event_log": EVENT_LOG_UNREADABLE,
                    "error": f"{type(error).__name__}: {error}"}
    events: list[Mapping[str, Any]] = []
    unparsed = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            events.append(parser(line))
        except (ValueError, TypeError, json.JSONDecodeError):
            unparsed += 1
    return events, {**state, "unparsed_lines": unparsed,
                    "event_log": EVENT_LOG_READ if events else EVENT_LOG_EMPTY}


def read_cli_events(path: Path,
                    parser: Callable[[str], Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Read every complete event, ignoring a final or intermediate torn line."""
    return read_event_log(path, parser)[0]


EVENT_LOG_ABSENT = "absent"
EVENT_LOG_UNREADABLE = "unreadable"
EVENT_LOG_EMPTY = "empty"
EVENT_LOG_READ = "read"

KILL_FILE = "kill.json"
ENDED_AT_KILL = "kill"
ENDED_AT_LAST_WRITE = "last_write"
ENDED_AT_RECOVERY = "recovery_time"


def recover_cli_result(spec_path: Path, out_dir: Path, fallback_error: str, *,
                       event_log_name: str,
                       parser: Callable[[str], Mapping[str, Any]],
                       builder: Callable[[dict[str, Any], Path,
                                          list[Mapping[str, Any]], str],
                                         tuple[dict[str, Any], str | None]]) -> dict[str, Any]:
    """Generic replay seam used when a runner died before writing result.json.

    The runner opens its event log only after its adapter prepared the
    process, and a cloud adapter posts the step to the Worker in that
    preparation. A kill in that window leaves no event log, and the attempt's
    other files (`remote.json`, `kill-abort.json`) still say what it held, so
    the builder runs on no events. The record then names what it was built
    from in `record_source` and `recovery`: what the event log was, when the
    attempt ended and how that moment is known, and what a builder adds.
    """
    out_dir = Path(out_dir)
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    ended_at, ended_basis = attempt_ended(out_dir)
    events, log_state = read_event_log(out_dir / "logs" / event_log_name, parser)
    result, final_text = builder(spec, out_dir, events, fallback_error)
    result.update(observed_at_recovery(
        out_dir, result, ended_at=ended_at,
        source=attempt_record.SOURCE_EVENT_LOG
        if log_state["event_log"] == EVENT_LOG_READ
        else attempt_record.SOURCE_ATTEMPT_FILES))
    result["recovery"] = {**log_state, "ended_at": round(ended_at, 3),
                          "ended_basis": ended_basis,
                          **(result.get("recovery") or {})}
    return attempt_record.write(out_dir, result, final_text)


def attempt_ended(out_dir: Path, now: float | None = None) -> tuple[float, str]:
    """When a runner that wrote no record stopped, and how that is known.

    `kill`: the executor killed it and wrote the moment. `last_write`: the
    newest write in the attempt directory; the runner lived at least that
    long, so the time is a lower bound. `recovery_time`: nothing dates the
    attempt, and the moment of this call is an upper bound.
    """
    out_dir = Path(out_dir)
    try:
        killed = json.loads((out_dir / KILL_FILE).read_text(encoding="utf-8"))
        return float(killed["at"]), ENDED_AT_KILL
    except (OSError, ValueError, TypeError, KeyError):
        pass
    newest = None
    for path in out_dir.rglob("*"):
        try:
            if path.is_file():
                newest = max(newest or 0.0, path.stat().st_mtime)
        except OSError:
            continue
    if newest is not None:
        return newest, ENDED_AT_LAST_WRITE
    return (time.time() if now is None else float(now)), ENDED_AT_RECOVERY


def observed_at_recovery(out_dir: Path, result: Mapping[str, Any], *, source: str,
                         ended_at: float) -> dict[str, Any]:
    """What the attempt directory still says about a runner that wrote no record.

    `agent.pid` is written when the runner starts, so the time from its
    write to `ended_at` is the attempt's wall time. The tool-output index
    holds a start without an end for every call the runner never saw finish;
    `since_s` is how long the oldest of them was open at `ended_at`.
    """
    out_dir = Path(out_dir)
    seen: dict[str, Any] = {"record_source": source}
    try:
        started = (out_dir / "agent.pid").stat().st_mtime
    except OSError:
        started = None
    if started is not None and not result.get("wall_seconds"):
        seen["wall_seconds"] = round(max(0.0, ended_at - started), 1)
    open_calls = [c for c in tool_output_files.open_calls(out_dir)
                  if c.get("started") is not None]
    if open_calls and not result.get("open_tool_call"):
        oldest = min(open_calls, key=lambda c: float(c["started"]))
        seen["open_tool_call"] = {
            "id": oldest["id"], "tool": oldest.get("tool"),
            "command": oldest.get("command"),
            "since_s": round(max(0.0, ended_at - float(oldest["started"])), 1),
            "file": (f"logs/{tool_output_files.DIR}/{oldest['file']}"
                     if oldest.get("file") else None)}
    return seen


class CliAgentRuntime:
    """Spawn one CLI agent and own its event stream, liveness and artifacts."""

    def __init__(self, adapter: CliAgentAdapter):
        self.adapter = adapter

    def run(self, spec: dict[str, Any], out_dir: Path) -> dict[str, Any]:
        out_dir = Path(out_dir)
        logs = out_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        prepared = self.adapter.prepare(spec, out_dir)
        event_path = logs / self.adapter.event_log_name
        stderr_path = logs / self.adapter.stderr_log_name
        heartbeat_path = logs / "heartbeat.json"
        events: list[Mapping[str, Any]] = []
        started = time.time()
        last_event = started
        stop_error: str | None = None
        liveness = getattr(self.adapter, "liveness_at", None)
        answered = getattr(self.adapter, "answered_at", None)
        poll_calls = getattr(self.adapter, "poll_calls", None)
        next_poll = 0.0
        tool_output = ToolOutputWriter(out_dir)
        command_time_cap = attempt_record.command_time_cap(spec) + COMMAND_TIME_CAP_GRACE_S
        open_at_stop: dict[str, Any] | None = None
        exit_grace = float(getattr(self.adapter, "exit_grace_s", 60))
        next_liveness = 0.0
        next_answered = 0.0
        answered_seen: float | None = None

        with stderr_path.open("w", encoding="utf-8") as stderr:
            managed = spawn_managed(
                prepared.argv, cwd=prepared.cwd, env=prepared.env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=stderr,
            )

            assert managed.process.stdout is not None
            stdout = managed.process.stdout
            fd = stdout.fileno()
            os.set_blocking(fd, False)
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            buffered = ""
            done = False
            try:
                with event_path.open("w", encoding="utf-8", newline="\n") as event_file:
                    exited_at: float | None = None
                    while not done:
                        produced: list[str] = []
                        eof = False
                        try:
                            chunk = os.read(fd, 65536)
                        except BlockingIOError:
                            chunk = None
                        if chunk == b"":
                            eof = True
                            buffered += decoder.decode(b"", final=True)
                            if buffered:
                                produced.append(buffered)
                                buffered = ""
                        elif chunk:
                            buffered += decoder.decode(chunk)
                            while "\n" in buffered:
                                line, buffered = buffered.split("\n", 1)
                                produced.append(line + "\n")

                        for line in produced:
                            event_file.write(line)
                            event_file.flush()
                            last_event = time.time()
                            try:
                                event = self.adapter.parse_event(line)
                            except (ValueError, TypeError, json.JSONDecodeError):
                                event = None
                            if event is None:
                                continue
                            events.append(event)
                            action = self.adapter.on_event(spec, event, events)
                            for call in action.calls:
                                tool_output.apply(call)
                            if action.heartbeat is not None:
                                heartbeat = {"at": time.time(), **dict(action.heartbeat)}
                                heartbeat_path.write_text(json.dumps(heartbeat), encoding="utf-8")
                            if action.stop_error is not None:
                                stop_error = action.stop_error
                                managed.kill_tree()
                                done = True
                                break
                        if eof:
                            done = True
                        if (poll_calls is not None and not done
                                and time.time() >= next_poll):
                            next_poll = time.time() + POLL_CALLS_S
                            for call in poll_calls(prepared, out_dir) or ():
                                tool_output.apply(call)
                        stall_timeout = int(spec.get("stall_timeout_s") or 0)
                        if (liveness is not None and not done and stall_timeout
                                and time.time() >= next_liveness):
                            next_liveness = time.time() + 1.0
                            seen = liveness(prepared, out_dir)
                            if seen is not None and seen > last_event:
                                last_event = seen
                        if answered is not None and not done and time.time() >= next_answered:
                            next_answered = time.time() + 1.0
                            at = answered(prepared, out_dir)
                            answered_seen = at if at is not None else answered_seen
                            if at is not None and time.time() - at > exit_grace:
                                if isinstance(prepared.context, dict):
                                    prepared.context["exit_grace_killed"] = round(time.time() - at, 1)
                                managed.kill_tree()
                                done = True
                        # An open tool call is the agent waiting on its own
                        # command, so the stall clock does not run; the
                        # command time cap does. An agent that has answered is
                        # shutting down, and the exit grace governs it.
                        # Otherwise silence is a stall.
                        oldest = tool_output.oldest_open()
                        if answered_seen is not None:
                            pass
                        elif oldest is not None:
                            if not done and time.time() - oldest["started"] > command_time_cap:
                                stop_error = (f"command_time_cap: {oldest.get('tool') or 'tool'} "
                                              f"call open longer than {command_time_cap} s")
                                open_at_stop = oldest
                                managed.kill_tree()
                                done = True
                        elif (not done and stall_timeout and
                                time.time() - last_event > stall_timeout):
                            stop_error = "stall"
                            managed.kill_tree()
                            done = True
                        if not done and managed.process.poll() is not None:
                            exited_at = exited_at or time.time()
                            if not produced and time.time() - exited_at > 0.5:
                                done = True
                        if not produced and not done:
                            time.sleep(0.05)
                returncode = managed.process.wait(timeout=30)
            finally:
                if managed.process.poll() is None:
                    managed.kill_tree()
                else:
                    managed.close()
                stdout.close()

        finished = time.time()
        if open_at_stop is None:
            open_at_stop = tool_output.oldest_open()
        for cid in list(tool_output.open):
            tool_output.end(cid, ok=None)
        outcome = CliRunOutcome(
            spec=spec, out_dir=out_dir, prepared=prepared, events=tuple(events),
            returncode=returncode, started_at=started, finished_at=finished,
            stop_error=stop_error,
        )
        result, final_text = self.adapter.build_result(outcome)
        result["record_source"] = attempt_record.SOURCE_RUNNER
        if open_at_stop is not None:
            result["open_tool_call"] = {
                "id": open_at_stop["id"], "tool": open_at_stop.get("tool"),
                "command": open_at_stop.get("command"),
                "since_s": round(finished - open_at_stop["started"], 1),
                "file": f"logs/tool-output/{open_at_stop['file']}"}
        return attempt_record.write(out_dir, result, final_text)


class CliHarnessExecutor:
    name = "cli"

    def __init__(self, *, name: str, runner_module: str, python: Path | None = None,
                 recovery: Callable[[Path, Path, str], dict[str, Any]] | None = None,
                 checks: Callable[[], list[str]] | None = None):
        self.name = name
        self.checks = checks
        self.runner_module = runner_module
        self.python = Path(python or sys.executable)
        self.recovery = recovery

    def preflight(self) -> list[str]:
        if not self.python.exists():
            return [f"{self.name} harness executor interpreter missing: {self.python}"]
        return list(self.checks()) if self.checks is not None else []

    def launch(self, spec: dict, out_dir: Path) -> Handle:
        out_dir = Path(out_dir)
        (out_dir / "logs").mkdir(parents=True, exist_ok=True)
        spec_path = out_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        if not self.python.exists():
            raise AgentLaunchError(f"{self.name} harness executor interpreter missing: {self.python}")
        env = agent_env()
        parent = str(IMPORT_ROOT)
        env["PYTHONPATH"] = parent + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        out = (out_dir / "logs" / f"{self.name}_runner.out.log").open("w", encoding="utf-8")
        err = (out_dir / "logs" / f"{self.name}_runner.err.log").open("w", encoding="utf-8")
        try:
            process = spawn_managed(
                [str(self.python), "-m", self.runner_module, str(spec_path)],
                cwd=Path(parent), env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err)
        finally:
            out.close()
            err.close()
        (out_dir / "agent.pid").write_text(f"{process.pid}\n", encoding="ascii")
        return Handle(coord=spec["coord"], harness_executor=self.name, out_dir=out_dir,
                      spec_path=spec_path, pid=process.pid, process=process)

    def poll(self, handle: Handle) -> str:
        rc = handle.process.poll()
        if rc is None:
            return RUNNING
        handle.process.close()
        if (handle.out_dir / "result.json").exists():
            return FINISHED
        handle.error = f"{self.name} runner exited {rc}"
        return ERROR

    def collect(self, handle: Handle) -> dict:
        path = handle.out_dir / "result.json"
        try:
            attempt = json.loads(handle.spec_path.read_text(encoding="utf-8")).get("attempt")
        except (OSError, json.JSONDecodeError):
            attempt = None
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return attempt_record.empty_record(
                    {"coord": handle.coord, "attempt": attempt},
                    f"result.json unreadable: {exc}")
        fault = None
        if self.recovery is not None:
            try:
                return self.recovery(handle.spec_path, handle.out_dir,
                                     handle.error or f"{self.name} runner was killed")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                fault = f"{type(exc).__name__}: {exc}"
        error = handle.error or "no result.json"
        if fault:
            error = f"{error}; the record could not be rebuilt ({fault})"
        return {**attempt_record.empty_record(
                    {"coord": handle.coord, "attempt": attempt}, error),
                "record_source": attempt_record.SOURCE_NONE,
                "recovery": {"error": fault}}

    def kill(self, handle: Handle) -> None:
        if handle.process is not None:
            try:
                (handle.out_dir / KILL_FILE).write_text(
                    json.dumps({"at": time.time()}), encoding="utf-8")
            except OSError:
                pass
            handle.process.kill_tree()


class PiHarnessExecutor(CliHarnessExecutor):
    def __init__(self, python: Path | None = None):
        from .pi_runner import preflight, recover_result
        super().__init__(name="pi", runner_module="ohflow.pi_runner", python=python,
                         recovery=recover_result,
                         checks=preflight)
