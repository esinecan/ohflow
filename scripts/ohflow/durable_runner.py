"""Run one agent step through the durable host that ships in `ohflow/host`.

The host opens a pi-durable `Harness` over the step's `session.sqlite`, so the
step survives the death of the process that drives it. `AgentSpec.box` names
where it runs: `local` is this machine, and any other name is the ssh host
alias of an ssh box. `durable_host.py` installs the host on that machine on first
use. This module is ohflow's half:

- On an ssh box, `DurableHarnessExecutor.launch` pushes the step's start commit to
  the project's own remote on `ohflow/durable/<key>` and records the transport
  in `remote.json` (`remote_git.py` owns the git). `DurableAdapter.prepare`
  waits for the box on a reattach, installs the host there, asks it to make the
  step's folder, sends the spec and the brief with the paths rewritten to the
  box's own, and returns the `ssh ... run <key>` argv the runtime spawns.
- On `local`, the agent works in the step's worktree itself. The step folder is
  `<attempt dir>/durable`, and the argv is `node .../ohflow-step.mjs local
  <folder>`; no git leaves this machine.
- The host prints pi's `--mode json` event shapes on stdout, so the events,
  the usage, the activity and the tool-output contract are pi's, read through
  `pi_runner`'s helpers. Its own log lines carry `ev` instead of `type`.
- `build_result` fetches the answer back into the worktree and copies the
  transcript, the usage and the handover down with `scp`, or, on `local`, out
  of the step folder.

A supervisor death or a host reboot reattaches the attempt: the host holds the
conversation in `<dir>/session.sqlite` and replays it, so the engine restarts
the same attempt in the same directory with `spec.reattach` set. A host that
ends with no `durable_end`, such as one behind a dropped ssh connection, ends
the runner with `host_lost`, which the engine answers with a reattach rather
than a fresh attempt. The rule itself lives in `engine.py` and
`attempts.py`; `reattach_target` below answers where an attempt directory
continues.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from . import activity as act
from . import attempt_record, durable_host, pi_runner, proc, remote_git, settings
from .cli_harness_executor import (CliEventAction, CliPreparedProcess,
                                   CliRunOutcome, CliHarnessExecutor,
                                   recover_cli_result)
from .harness_executor import AgentLaunchError
from .paths import bash_exe, posix, win
from .remote_git import attempt_key
from .signed_in import read_schema, runner_main
from .structured import parse_structured
from .workflow import effective_command_time_cap

__all__ = ["EVENT_LOG", "LOCAL_BOX", "default_box", "durable_providers", "DurableAdapter", "DurableHarnessExecutor",
           "attempt_key", "branch_for", "offered_tools", "agent_errors", "usage",
           "activity", "resume_target", "reattach_target", "transcript",
           "preflight", "make_harness_executor", "main"]

EVENT_LOG = "durable-events.jsonl"
STDERR_LOG = "durable-stderr.log"


DEFAULT_SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
DEFAULT_SCP = r"C:\Windows\System32\OpenSSH\scp.exe"
#: `-T` gives no remote tty, BatchMode never prompts for a password, and the
#: alive interval notices a dropped connection within a few keepalives.
SSH_OPTIONS = ("-T", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=15")

#: Seconds a reattach waits for the box to come back before giving up.
BOX_WAIT_S = 900
BOX_POLL_S = 15
PREPARE_TIMEOUT_S = 180
SCP_TIMEOUT_S = 300


LOCAL_BOX = durable_host.LOCAL_BOX
NODE_MIN = (22, 19)


def default_box() -> str | None:
    """The box for the preflight and the routes that name none."""
    return os.environ.get("OHFLOW_DURABLE_BOX") or settings.get("durable.box")


def durable_providers() -> frozenset[str]:
    """The providers the host's pi holds keys for on its own box."""
    return frozenset(settings.get("durable.providers", []))

#: `tools.only` names the host maps. Empty means all four tools.
TOOL_MAP = {"terminal": ("bash",), "file_editor": ("read", "write", "edit")}
ALL_TOOLS = ("read", "write", "edit", "bash")
#: The shared tool policy names the spec may narrow to; `task_tracker` has no
#: equivalent on the host and is dropped with a warning, as on pi.
DURABLE_SHARED_TOOLS = frozenset({"terminal", "file_editor", "task_tracker"})

#: Every branch this executor exchanges with the box sits under this prefix;
#: `remote_git.push_start` checks the wider `ohflow/` rule for every executor.
BRANCH_PREFIX = "ohflow/durable"


# ------------------------------------------------------------------ programs


def _program(env_var: str, default: str) -> list[str]:
    """The argv prefix of one OpenSSH program. A `.py` override runs under this
    interpreter, which is how the test fakes run."""
    override = os.environ.get(env_var)
    if override:
        if override.lower().endswith(".py"):
            return [sys.executable, override]
        return [override]
    return [default]


def _default_program(name: str, windows_path: str) -> str:
    """The OpenSSH program this platform has: the System32 copy on Windows,
    the first PATH hit elsewhere, or the bare name when PATH has none."""
    if os.name == "nt":
        return windows_path
    return shutil.which(name) or name


def ssh_argv() -> list[str]:
    prefix = _program("OHFLOW_DURABLE_SSH",
                      _default_program("ssh", DEFAULT_SSH))
    if prefix[0] != sys.executable and not Path(prefix[0]).is_file():
        raise FileNotFoundError(
            f"ssh executable not found at {prefix[0]}; set OHFLOW_DURABLE_SSH")
    return [*prefix, *SSH_OPTIONS]


def scp_argv() -> list[str]:
    prefix = _program("OHFLOW_DURABLE_SCP",
                      _default_program("scp", DEFAULT_SCP))
    if prefix[0] != sys.executable and not Path(prefix[0]).is_file():
        raise FileNotFoundError(
            f"scp executable not found at {prefix[0]}; set OHFLOW_DURABLE_SCP")
    return [*prefix, "-o", "BatchMode=yes"]


def _remote(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    """Run one ssh/scp line against the box, windowless, with the agent env."""
    return proc.run_managed(argv, env=proc.agent_env(), timeout=timeout)


# --------------------------------------------------------------- the key

# `attempt_key` lives in `remote_git.py`, which every harness executor that runs
# its step on another machine shares; this module keeps exporting the name.


def branch_for(key: str) -> str:
    return f"{BRANCH_PREFIX}/{key}"


def offered_tools(spec: Mapping[str, Any]) -> list[str]:
    """The tools the host offers: the mapped `tools.only`, else all four."""
    only = ((spec.get("tools") or {}).get("only")) or []
    out: list[str] = []
    for name in only:
        for tool in TOOL_MAP.get(name, ()):
            if tool not in out:
                out.append(tool)
    return out or list(ALL_TOOLS)


# ------------------------------------------------------------------ the box


def _wait_for_box(box: str) -> None:
    """Poll `ssh <box> exit` until the box answers, within the wait bound."""
    limit = float(os.environ.get("OHFLOW_DURABLE_BOX_WAIT_S") or BOX_WAIT_S)
    deadline = time.monotonic() + limit
    while True:
        try:
            done = _remote([*ssh_argv(), box, "exit"], timeout=45)
        except subprocess.TimeoutExpired:
            done = None
        if done is not None and done.returncode == 0:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"the box {box} did not answer ssh within {round(limit)} s; "
                f"a reattach cannot start until it is back")
        time.sleep(BOX_POLL_S)


def _box_host(box: str) -> str:
    """The host's folder on the box, installed there on first use."""
    return durable_host.install([*ssh_argv(), box, "node"], box).replace("\\", "/")


def _host_argv(host: str, box: str, mode: str, key: str) -> list[str]:
    return [*ssh_argv(), box, "node", f"{host}/ohflow-step.mjs", mode, key]


def _run_prepare(host: str, box: str, key: str) -> Mapping[str, Any]:
    """Ask the host to make the step's folder and read its one line."""
    try:
        done = _remote(_host_argv(host, box, "prepare", key), timeout=PREPARE_TIMEOUT_S)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"prepare on {box} timed out after {PREPARE_TIMEOUT_S} s") from error
    for line in (done.stdout or "").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("type") == "durable_prepared":
            return record
    tail = ((done.stdout or "") + (done.stderr or ""))[-400:]
    raise RuntimeError(f"prepare on {box} printed no durable_prepared line: {tail!r}")


def _scp_to(box: str, files: list[str], remote_dir: str) -> None:
    done = _remote([*scp_argv(), *files, f"{box}:{remote_dir}"],
                   timeout=SCP_TIMEOUT_S)
    if done.returncode != 0:
        raise RuntimeError(
            f"scp to {box}:{remote_dir} exited {done.returncode}: "
            f"{(done.stderr or '')[-300:]}")


def _scp_from(box: str, remote_file: str, target: Path) -> bool:
    """One file off the box. False when the copy failed; a missing handover is
    no error, so the caller decides what a failure means."""
    try:
        done = _remote([*scp_argv(), f"{box}:{remote_file}", str(target)],
                       timeout=SCP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def _rewrite_brief(text: str, workspace: str, out_dir: str, box_dir: Path, *,
                   branch: str = "", start_sha: str = "") -> str:
    """Point the brief's absolute paths at the box's own folders.

    The agent on the box must not see this machine's worktree or run directory:
    it could not open them, and a path it could open would be the wrong file.
    Both renderings of each path are replaced - by the shared rule in
    `remote_git.rewrite_paths`, which the pi-cloud executor's own rewrite also
    uses - because the position block and the brief mix `paths.win` and
    forward-slash text.

    `box_dir` is a path on the box, which is a Windows machine, so it is
    spelled the Windows way on any host. `paths.win` renders for this host
    and would join `work` with a forward slash on a Mac.
    """
    box = PureWindowsPath(str(box_dir))
    text = remote_git.rewrite_paths(text, (
        (workspace, str(box / "work")),
        (out_dir, str(box)),
    ))
    return remote_git.transport_position(text, branch, start_sha)


# ---------------------------------------------------------------- the adapter


def _fleet_names(fleet: Mapping[str, Any]) -> list[str]:
    """The server names in the host's `mcp_fleet` line.

    The line carries one object per server - `tools`, `offered`, `source`,
    `status` - so the record keeps each object's `server` field, the name,
    and not a stringified object.
    """
    names: list[str] = []
    for entry in (fleet.get("servers") or []):
        name = entry.get("server") if isinstance(entry, Mapping) else entry
        if name:
            names.append(str(name))
    return names


class DurableAdapter:
    """The durable host's argv, event and result semantics for the CLI runtime."""

    name = "durable"
    event_log_name = EVENT_LOG
    stderr_log_name = STDERR_LOG

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
        box = str(spec.get("box") or "")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", box):
            raise RuntimeError(
                f"the durable spec's box must name the box's ssh host "
                f"alias or local, got {spec.get('box')!r}")
        out_dir = Path(out_dir)
        try:
            remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"{win(out_dir / 'remote.json')} is missing or unreadable "
                f"({error}); the launch writes it before the runner starts") from error
        key = str(remote.get("key") or "")
        if not key:
            raise RuntimeError(f"{win(out_dir / 'remote.json')} names no key")
        command_time_cap = effective_command_time_cap(
            int(spec.get("execution_timeout_s") or 5400), spec.get("command_time_cap_s"))
        if box == LOCAL_BOX:
            return self._prepare_local(spec, out_dir, remote, key, command_time_cap)
        if spec.get("reattach"):
            # A reattach only happens after this machine lost the host, so the
            # box may itself be rebooting. Wait for it rather than fail.
            _wait_for_box(box)
        host = _box_host(box)
        prepared = _run_prepare(host, box, key)
        box_dir = Path(str(prepared.get("dir") or ""))
        if not str(box_dir):
            raise RuntimeError(f"prepare on {box} named no dir: {dict(prepared)!r}")
        # The box's dir is durable state: a resume reads it back for the
        # reattach target without asking the box again.
        remote["dir"] = str(box_dir)
        (out_dir / "remote.json").write_text(json.dumps(remote, indent=2),
                                             encoding="utf-8")

        durable = {"box": box, "remote_url": remote.get("remote_url"),
                   "branch": remote.get("branch"), "start_sha": remote.get("start_sha"),
                   "command_cap_s": command_time_cap}
        staged = out_dir / "remote"
        staged.mkdir(parents=True, exist_ok=True)
        (staged / "spec.json").write_text(
            json.dumps({**spec, "durable": durable}, indent=2), encoding="utf-8")
        brief = (out_dir / "brief.md").read_text(encoding="utf-8")
        (staged / "brief.md").write_text(
            _rewrite_brief(brief, str(spec.get("workspace") or ""),
                           str(out_dir.resolve()), box_dir,
                           branch=str(remote.get("branch") or ""),
                           start_sha=str(remote.get("start_sha") or "")),
            encoding="utf-8")
        files = [str(staged / "spec.json"), str(staged / "brief.md")]
        if (out_dir / "schema.json").is_file():
            shutil.copyfile(out_dir / "schema.json", staged / "schema.json")
            files.append(str(staged / "schema.json"))
        _scp_to(box, files, f".pi-durable/ohflow/{key}/")
        return CliPreparedProcess(
            argv=tuple(_host_argv(host, box, "run", key)),
            cwd=out_dir,
            env=proc.agent_env(),
            context={"box": box, "key": key, "remote": remote,
                     "dir": str(box_dir), "durable": durable, "host": host},
        )

    def _prepare_local(self, spec: dict[str, Any], out_dir: Path,
                       remote: dict[str, Any], key: str,
                       command_time_cap: int) -> CliPreparedProcess:
        host = durable_host.ensure_local()
        step_dir = (out_dir / "durable").resolve()
        step_dir.mkdir(parents=True, exist_ok=True)
        work = str(Path(str(spec.get("workspace") or ".")).resolve())
        durable = {"box": LOCAL_BOX, "key": key, "work": work,
                   "command_cap_s": command_time_cap}
        (step_dir / "spec.json").write_text(
            json.dumps({**spec, "durable": durable}, indent=2), encoding="utf-8")
        shutil.copyfile(out_dir / "brief.md", step_dir / "brief.md")
        env = proc.agent_env()
        if "OHFLOW_BASH" not in env:
            try:
                env["OHFLOW_BASH"] = bash_exe()
            except FileNotFoundError:
                pass
        return CliPreparedProcess(
            argv=(*durable_host.node_argv(), str(Path(host) / "ohflow-step.mjs"),
                  "local", str(step_dir)),
            cwd=out_dir,
            env=env,
            context={"box": LOCAL_BOX, "key": key, "remote": remote,
                     "dir": str(step_dir), "durable": durable, "host": host},
        )

    def parse_event(self, line: str) -> Mapping[str, Any]:
        return json.loads(line)

    def on_event(self, spec: dict[str, Any], event: Mapping[str, Any],
                 events: list[Mapping[str, Any]]) -> CliEventAction:
        # The host prints pi's own event shapes, so pi's rules read them.
        return pi_runner.pi_event_action(spec, event, events)

    def _copy_back(self, box: str, box_dir: str, out_dir: Path) -> None:
        for name in ("transcript.md", "usage.json", "handover.md"):
            if box == LOCAL_BOX:
                source = Path(box_dir) / name
                if source.is_file():
                    shutil.copyfile(source, out_dir / name)
                continue
            # A missing handover is no error, and the run itself already
            # succeeded, so a failed copy leaves the attempt passing.
            _scp_from(box, f"{posix(Path(box_dir))}/{name}", out_dir)

    def build_result(self, outcome: CliRunOutcome) -> tuple[dict[str, Any], str | None]:
        spec = outcome.spec
        out_dir = Path(outcome.out_dir)
        events = outcome.events
        context = outcome.prepared.context
        box = str(context["box"])
        remote = context["remote"]

        # Replayed message_end events carry their usage too, so a reattached
        # attempt counts everything its conversation ever spent.
        messages = pi_runner.pi_messages(events)
        final = pi_runner.assistant_text(messages[-1]) if messages else ""
        tokens, cost, provider_error = pi_runner.pi_usage(messages)
        tool_ends = [e for e in events if e.get("type") == "tool_execution_end"]
        end = next((e for e in reversed(events)
                    if e.get("type") == "durable_end"), None)
        fault = next((e for e in reversed(events)
                      if e.get("type") == "durable_error"), None)
        fleet = next((e for e in reversed(events)
                      if e.get("ev") == "mcp_fleet"), None)

        error = outcome.stop_error
        if not error and fault is not None:
            error = f"{fault.get('name')}: {fault.get('message')}"
        if not error and end is None and fault is None:
            via = "node" if box == LOCAL_BOX else "ssh"
            error = (f"host_lost: {via} exited {outcome.returncode}; the host on "
                     f"{box} ended without durable_end")
        if not error:
            error = provider_error

        durable_block = {"box": box, "key": context["key"], "dir": context["dir"],
                         "branch": remote.get("branch"),
                         "start_sha": remote.get("start_sha"),
                         "head": None, "dirty": None, "pushed": False,
                         "session": None, "branch_deleted": False}
        if end is not None and box == LOCAL_BOX:
            durable_block.update(start_sha=end.get("start"), head=end.get("head"),
                                 dirty=end.get("dirty"), session=end.get("session"))
            self._copy_back(box, context["dir"], out_dir)
        elif end is not None:
            durable_block.update(head=end.get("head"), dirty=end.get("dirty"),
                                 pushed=bool(end.get("pushed")),
                                 session=end.get("session"))
            try:
                remote_git.fetch_result(Path(str(spec.get("workspace") or ".")),
                                        str(remote.get("branch") or ""),
                                        str(remote.get("start_sha") or ""))
            except (ValueError, RuntimeError) as fault_back:
                if not error:
                    error = f"fetch_back: {fault_back}"
            else:
                # The fetched commit is in the run's worktree now, so the
                # transport branch has served its purpose; a reattach after
                # this point pushes it again. A refused delete only lingers.
                durable_block["branch_deleted"] = remote_git.delete_branch(
                    Path(str(spec.get("workspace") or ".")),
                    str(remote.get("branch") or ""))
            self._copy_back(box, context["dir"], out_dir)

        structured, schema_error = parse_structured(final, read_schema(spec, out_dir))
        tools = offered_tools(spec)
        model = spec.get("model") or {}
        result = {
            **attempt_record.empty_record(spec, error or "", cost_source="durable-host"),
            "conversation_id": context["key"],
            "transcript_dir": None,
            "execution_status": "error" if error else "finished",
            "tools": tools, "skills": list(spec.get("skills") or []),
            "mcp_servers": (_fleet_names(fleet) if fleet is not None else []),
            "tool_calls": len(tool_ends),
            "observation_errors": sum(
                bool(e.get("isError") or (e.get("result") or {}).get("isError"))
                for e in tool_ends),
            "llm_calls": len(messages),
            "wall_seconds": round(outcome.finished_at - outcome.started_at, 1),
            "tokens": tokens, "cost": cost,
            "final_text_path": "final.md", "structured": structured,
            "schema_error": schema_error, "error": error,
            "settings": attempt_record.settings_record(spec, {
                "model": model.get("model"),
                "thinking": (model.get("params") or {}).get("thinking", "low"),
                "box": box, "tools": tools}),
            "durable": durable_block,
        }
        return result, final if final else None


# ------------------------------------------------------------ agent rules


def agent_errors(where: str, agent: Any) -> list[str]:
    """The faults in an agent spec for the durable harness executor."""
    errs: list[str] = []
    box = agent.box
    if not isinstance(box, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", box or ""):
        errs.append(
            f"{where}: durable agent.box must name the ssh host alias "
            f"of the box, such as 'buildbox', or local for this machine, "
            f"got {box!r}")
    if agent.agent_profile is not None:
        errs.append(
            f"{where}: durable refuses agent.agent_profile; agent.box names "
            f"the box, got {agent.agent_profile!r}")
    model = agent.model
    errs.extend(pi_runner.model_errors(where, model, "durable",
                                      durable_providers()))

    tools = agent.tools
    if tools.preset != "default":
        errs.append(
            f"{where}: durable supports only tools.preset='default', got "
            f"{tools.preset!r}")
    if tools.enable_browser:
        errs.append(f"{where}: durable refuses enable_browser=True; the box has no browser")
    if tools.enable_sub_agents:
        errs.append(f"{where}: durable refuses enable_sub_agents=True")
    if tools.allow or tools.block:
        errs.append(
            f"{where}: durable refuses tools.allow and tools.block; the box has no "
            "MCP servers to narrow")
    unknown = sorted(repr(name) for name in tools.only
                     if not isinstance(name, str) or name not in DURABLE_SHARED_TOOLS)
    if unknown:
        errs.append(
            f"{where}: durable tools.only has unsupported names {unknown}; "
            f"known: {sorted(DURABLE_SHARED_TOOLS)}")
    if "task_tracker" in tools.only:
        warnings.warn(
            f"{where}: durable has no task_tracker equivalent; it will be dropped",
            UserWarning, stacklevel=3)
    if agent.mcp_config:
        errs.append(
            f"{where}: durable refuses mcp_config; the box has no MCP servers")
    # The box resolves each name as ~/.agents/skills/<name>/SKILL.md in its own
    # copy of the skills tree, so a name must be one safe path segment there.
    bad_skills = sorted(repr(name) for name in agent.skills
                        if not isinstance(name, str)
                        or not re.fullmatch(r"[A-Za-z0-9._-]+", name))
    if bad_skills:
        errs.append(
            f"{where}: durable resolves each skill name on the box as "
            f"~/.agents/skills/<name>/SKILL.md, so it must match "
            f"[A-Za-z0-9._-]+; refused {bad_skills}")
    if agent.skills_dir:
        errs.append(
            f"{where}: durable refuses skills_dir; the box reads skills from "
            "its own ~/.agents/skills")
    return errs


# ------------------------------------------------------------------- usage


def usage(attempt_dir: Path) -> tuple[dict[str, int] | None, str | None]:
    """The usage the runner's event log records, replayed turns included."""
    event_log = Path(attempt_dir) / "logs" / EVENT_LOG
    if not event_log.is_file():
        return None, f"durable event log is missing ({event_log})"
    return pi_runner.event_log_usage(event_log, "durable")


# ---------------------------------------------------------------- activity


def activity(attempt_dir: Path, *, now: float | None = None, running: bool = True,
             limit: int = act.DEFAULT_TOOL_CALLS) -> dict:
    """The step as the box ran it, read from the runner's copy of its events.

    The events are pi's own shapes with the host's `t` stamps, so the one
    event reader in `pi_runner` serves both remote harness executors.
    """
    attempt_dir = Path(attempt_dir)
    now = time.time() if now is None else float(now)
    model = act.model_for(attempt_dir)
    with model.lock:
        path = attempt_dir / "logs" / EVENT_LOG
        lines, reset = model.tail.read(path)
        if reset:
            model.reset()
            lines, _ = model.tail.read(path)
        for raw in lines:
            try:
                event = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(event, dict):
                pi_runner.apply_pi_event(model, event)
        beat = act.read_json(attempt_dir / "logs" / "heartbeat.json")
        beat_at = act.epoch(beat.get("at")) if isinstance(beat, dict) else None
        note = act.STARTING_NOTE if not model.replied else None
        return act.activity_out(model, harness_executor="durable",
                                root=act.worktree_root(attempt_dir), now=now,
                                running=running, limit=limit,
                                fallback_at=beat_at, note=note)


# --------------------------------------------- resume, reattach, transcript


def resume_target(prior_result: Mapping[str, Any], attempt_dir: Path) -> str | None:
    """A durable retry starts a fresh conversation; a reattach is not a retry."""
    return None


def reattach_target(attempt_dir: Path) -> str | None:
    """`<box>:<dir>` where this attempt directory continues, or None.

    The engine asks this before restarting a step whose execution is still
    open in the run log: a supervisor death. `remote.json` is the evidence the
    launch reached the box, and its `dir` is the folder the host made.
    """
    try:
        remote = json.loads(
            (Path(attempt_dir) / "remote.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(remote, dict):
        return None
    box = remote.get("box")
    key = remote.get("key")
    if not box or not key:
        return None
    where = remote.get("dir") or f".pi-durable/ohflow/{key}"
    return f"{box}:{where}"


def transcript(attempt_dir: Path, result: Mapping[str, Any],
               output: Path | None = None) -> tuple[Path | None, str | None]:
    """The transcript the host wrote on the box and the runner copied down."""
    path = Path(attempt_dir) / "transcript.md"
    if path.is_file():
        return path, None
    return None, "no durable transcript"


# ---------------------------------------------------------------- preflight


def preflight() -> list[str]:
    try:
        ssh_argv()
    except FileNotFoundError as e:
        return [str(e)]
    return []


def _node_fault(argv: list[str], where: str) -> str | None:
    """Why `argv` (a node, maybe behind ssh) cannot run the host, or None."""
    try:
        done = _remote([*argv, "--version"], timeout=60)
    except subprocess.TimeoutExpired:
        return f"node --version on {where} timed out after 60 s"
    except OSError as error:
        return f"node on {where} did not start: {error}"
    found = re.search(r"v(\d+)\.(\d+)", done.stdout or "")
    if done.returncode != 0 or not found:
        detail = ((done.stderr or done.stdout or "").strip())[:200]
        return f"node on {where} exited {done.returncode}: {detail}"
    if (int(found.group(1)), int(found.group(2))) < NODE_MIN:
        return (f"node {found.group(0)} on {where} is below "
                f"v{NODE_MIN[0]}.{NODE_MIN[1]}, which the durable host needs")
    return None


def box_preflight() -> list[str]:
    """The default box runs Node 22.19 or newer: this machine for `local`,
    else a box that answers ssh. ohflow installs the host there on launch.

    A workflow may name another box in `agent.box`; this check covers the
    one the roll call and the default routes use, because a preflight cannot
    see a workflow's agents.
    """
    box = default_box()
    if not box:
        return ["no durable box: set durable.box in ohflow.settings.local.json "
                "or OHFLOW_DURABLE_BOX, to an ssh host alias or local"]
    if box == LOCAL_BOX:
        fault = _node_fault(durable_host.node_argv(), "this machine")
        return [fault] if fault else []
    faults = preflight()
    if faults:
        return faults
    try:
        done = _remote([*ssh_argv(), box, "exit"], timeout=45)
    except subprocess.TimeoutExpired:
        return [f"ssh {box} timed out after 45 s"]
    if done.returncode != 0:
        detail = ((done.stderr or done.stdout or "").strip())[:200]
        return [f"ssh {box} exited {done.returncode}: {detail}"]
    fault = _node_fault([*ssh_argv(), box, "node"], box)
    return [fault] if fault else []


# ---------------------------------------------------------------- the harness executor


class DurableHarnessExecutor(CliHarnessExecutor):
    """The CLI harness executor whose runner drives the host over ssh."""

    def __init__(self, python: Path | None = None):
        super().__init__(name="durable", runner_module="ohflow.durable_runner",
                         python=python,
                         recovery=recover_result,
                         checks=box_preflight)

    def launch(self, spec: dict, out_dir: Path):
        out_dir = Path(out_dir)
        try:
            if spec.get("reattach"):
                # The transport of the attempt being reattached is already on
                # disk; pushing a new start commit would answer a new question.
                if not (out_dir / "remote.json").is_file():
                    raise ValueError(
                        f"{win(out_dir)} holds no remote.json to reattach")
            elif spec.get("box") == LOCAL_BOX:
                key = attempt_key(str(spec["coord"]),
                                  int(spec.get("attempt") or 1), out_dir)
                (out_dir / "remote.json").write_text(json.dumps({
                    "box": LOCAL_BOX, "key": key,
                    "dir": str((out_dir / "durable").resolve())}, indent=2),
                    encoding="utf-8")
            else:
                workspace = Path(str(spec["workspace"]))
                url = remote_git.remote_url(workspace)
                key = attempt_key(str(spec["coord"]),
                                  int(spec.get("attempt") or 1), out_dir)
                branch = branch_for(key)
                start_sha = remote_git.push_start(workspace, branch)
                (out_dir / "remote.json").write_text(json.dumps({
                    "box": spec.get("box"), "key": key,
                    "branch": branch, "remote_url": url,
                    "start_sha": start_sha}, indent=2), encoding="utf-8")
        except (ValueError, RuntimeError) as e:
            raise AgentLaunchError(f"durable launch failed: {e}") from e
        return super().launch(spec, out_dir)


def _recover(spec: dict[str, Any], out_dir: Path,
             events: list[Mapping[str, Any]],
             fallback_error: str) -> tuple[dict[str, Any], str | None]:
    """Rebuild the record from the event log after the runner itself died."""
    messages = pi_runner.pi_messages(events)
    tokens, cost, _ = pi_runner.pi_usage(messages)
    tool_ends = [e for e in events if e.get("type") == "tool_execution_end"]
    final = pi_runner.assistant_text(messages[-1]) if messages else ""
    try:
        remote = json.loads(
            (Path(out_dir) / "remote.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        remote = {}
    result = {
        **attempt_record.empty_record(spec, fallback_error, tokens=tokens,
                                      cost=cost, cost_source="durable-host"),
        "conversation_id": remote.get("key"),
        "execution_status": "error",
        "tool_calls": len(tool_ends), "llm_calls": len(messages),
        "final_text_path": "final.md" if final else None,
        "error": fallback_error,
        "durable": {"box": remote.get("box"), "key": remote.get("key"),
                    "dir": remote.get("dir"), "branch": remote.get("branch"),
                    "start_sha": remote.get("start_sha"), "head": None,
                    "dirty": None, "pushed": False, "session": None,
                    "branch_deleted": False},
    }
    return result, final if final else None


def recover_result(spec_path: Path, out_dir: Path, fallback_error: str) -> dict[str, Any]:
    return recover_cli_result(spec_path, out_dir, fallback_error,
                              event_log_name=EVENT_LOG, parser=json.loads,
                              builder=_recover)


def make_harness_executor():
    return DurableHarnessExecutor()


def main(argv: list[str] | None = None) -> int:
    return runner_main(DurableAdapter, argv)


if __name__ == "__main__":
    raise SystemExit(main())
