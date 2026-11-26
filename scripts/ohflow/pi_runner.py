"""Run one hermetic pi agent and translate its JSON stream to ohflow records."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Mapping

from . import activity as act
from . import attempt_record
from . import proc
from .cli_harness_executor import (CliEventAction, CliPreparedProcess, CliRunOutcome,
                                   recover_cli_result)
from .workflow import effective_command_time_cap
from .signed_in import executable_argv, read_schema, runner_main, version_of
from .structured import parse_structured
from .tool_output import CallEvent


def _content_text(value: Any) -> str:
    parts = (value or {}).get("content") if isinstance(value, Mapping) else None
    return "".join(str(p.get("text") or "") for p in parts or ()
                   if isinstance(p, Mapping) and p.get("type") == "text")


def _call_events(event: Mapping[str, Any]) -> tuple[CallEvent, ...]:
    """pi's tool events as tool-output calls.

    Measured 2026-10-10 (pi 0.84, glm-5.3-flash): `tool_execution_update`
    carries all output so far, stderr merged, 1-3 ms after the command prints;
    one `toolCallId` links start, updates and end. A silent command sends
    nothing until it ends.
    """
    kind = event.get("type")
    cid = event.get("toolCallId")
    if not cid or kind not in ("tool_execution_start", "tool_execution_update",
                               "tool_execution_end"):
        return ()
    if kind == "tool_execution_start":
        args = event.get("args") if isinstance(event.get("args"), Mapping) else {}
        command = args.get("command") if isinstance(args.get("command"), str) \
            else json.dumps(args, separators=(",", ":"))[:400]
        return (CallEvent("start", str(cid), tool=event.get("toolName"), command=command),)
    if kind == "tool_execution_update":
        return (CallEvent("output", str(cid), text=_content_text(event.get("partialResult")),
                          cumulative=True),)
    return (CallEvent("end", str(cid), ok=not event.get("isError"),
                      text=_content_text(event.get("result"))),)

EVENT_LOG = "pi-events.jsonl"

# Names pi accepts directly in --tools. The three shared tool policy names below
# are translated by pi_tool_policy; task_tracker is deliberately warning-only
# because pi has no equivalent and drops it.
PI_NATIVE_TOOLS = frozenset({
    "read", "bash", "edit", "write", "grep", "find", "ls", "powershell",
})
PI_SHARED_TOOLS = frozenset({"terminal", "file_editor", "task_tracker"})
PI_MODEL_PARAMS = frozenset({"thinking"})
PI_THINKING_LEVELS = frozenset({"off", "minimal", "low", "medium", "high", "xhigh", "max"})

#: How each remote harness executor words who holds the model keys, in its
#: `api_key_env` refusal. Both executors refuse the field for the same
#: reason and say it in their own words; an unknown executor gets a plain one.
KEY_HOLDERS = {"pi-cloud": "the Worker holds its keys",
               "durable": "the host holds its keys on its own box"}


def pi_argv() -> list[str]:
    return executable_argv("OHFLOW_PI_EXE", "pi", path_fallback=True)


def build_command(spec: Mapping[str, Any], out_dir: Path, tool_policy: Any) -> list[str]:
    model = str((spec.get("model") or {}).get("model") or "")
    thinking = str(((spec.get("model") or {}).get("params") or {}).get("thinking") or "low")
    session_dir = out_dir / "session"
    command = [*pi_argv(), "--mode", "json", "-p", "--model", model,
               "--thinking", thinking, "--no-extensions", "--no-skills",
               "--no-prompt-templates", "--no-context-files", "--no-themes",
               "--offline", "--session-dir", str(session_dir)]
    for extension in (*tool_policy.extension_paths, *tool_policy.builtin_extensions):
        command.extend(["-e", str(extension)])
    for path in tool_policy.skill_paths:
        command.extend(["--skill", str(path)])
    command.extend(["--tools", ",".join(tool_policy.tools)])
    if tool_policy.exclude_tools:
        command.extend(["--exclude-tools", ",".join(tool_policy.exclude_tools)])
    fork = spec.get("fork_session")
    if fork:
        command.extend(["--fork", str(fork)])
    command.extend(["--", "@" + str((out_dir / "brief.md").resolve())])
    return command


def _cost_source(out_dir: Path) -> str:
    """Read the attempt-local route policy without claiming a catalog price."""
    marker = Path(out_dir) / "pi-agent" / "ohflow-model.json"
    if not marker.exists():
        return "pi-catalog"
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unpriced"
    source = metadata.get("cost_source") if isinstance(metadata, Mapping) else None
    return str(source) if source else "unpriced"


def assistant_text(message: Mapping[str, Any]) -> str:
    content = message.get("content") or []
    if isinstance(content, str):
        return content
    return "".join(str(part.get("text") or "") for part in content
                   if isinstance(part, Mapping) and part.get("type") == "text")


def pi_messages(events: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]
               ) -> list[Mapping[str, Any]]:
    messages = [e.get("message") or {} for e in events
                if e.get("type") == "message_end" and
                (e.get("message") or {}).get("role") == "assistant"]
    return messages


def _message_tokens(usage: Mapping[str, Any]) -> dict[str, int]:
    """The five token fields of one assistant message's usage.

    pi's `input` excludes cache traffic, so `prompt_tokens` adds both cache
    counts. Omitted or null fields count as zero.
    """
    values = {key: int(usage.get(key) or 0)
              for key in ("input", "output", "cacheRead", "cacheWrite", "reasoning")}
    return {"prompt_tokens": values["input"] + values["cacheRead"] + values["cacheWrite"],
            "completion_tokens": values["output"],
            "cache_read_tokens": values["cacheRead"],
            "cache_write_tokens": values["cacheWrite"],
            "reasoning_tokens": values["reasoning"]}


def pi_usage(messages: list[Mapping[str, Any]]) -> tuple[dict[str, int], float, str | None]:
    tokens = attempt_record.zero_tokens()
    cost = 0.0
    error = None
    for message in messages:
        usage = message.get("usage") or {}
        for key, value in _message_tokens(usage).items():
            tokens[key] += value
        cost += float((usage.get("cost") or {}).get("total") or 0.0)
        if message.get("stopReason") == "error":
            error = str(message.get("errorMessage") or "provider error")
    return tokens, cost, error


def _recover_pi(spec: dict[str, Any], out_dir: Path,
                events: list[Mapping[str, Any]],
                fallback_error: str) -> tuple[dict[str, Any], str | None]:
    messages = pi_messages(events)
    tokens, cost, error = pi_usage(messages)
    session_files = sorted((Path(out_dir) / "session").glob("*.jsonl"))
    tool_calls = [e for e in events if e.get("type") == "tool_execution_end"]
    final = assistant_text(messages[-1]) if messages else ""
    result = {**attempt_record.empty_record(spec, error or fallback_error,
                                            cost_source=_cost_source(out_dir)),
              "conversation_id": session_files[-1].stem if session_files else None,
              "transcript_dir": str(Path(out_dir) / "session"), "tokens": tokens,
              "cost": cost, "llm_calls": len(messages), "tool_calls": len(tool_calls),
              "observation_errors": sum(bool(e.get("isError") or (e.get("result") or {}).get("isError")) for e in tool_calls),
              "final_text_path": "final.md" if final else None,
              "error": error or fallback_error}
    return result, final if final else None


def recover_result(spec_path: Path, out_dir: Path, fallback_error: str) -> dict[str, Any]:
    """Recover the last complete pi events after the runner was killed."""
    return recover_cli_result(
        spec_path, out_dir, fallback_error,
        event_log_name=EVENT_LOG, parser=json.loads, builder=_recover_pi,
    )


class PiAdapter:
    """Pi argv, event, usage and result semantics for the shared CLI runtime."""

    name = "pi"
    event_log_name = EVENT_LOG
    stderr_log_name = "pi-stderr.log"

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
        from .pi_tool_policy import discover_mcp, prepare_pi_tool_policy, write_pi_agent_dir

        (out_dir / "session").mkdir(parents=True, exist_ok=True)
        tool_policy = prepare_pi_tool_policy(spec, out_dir)
        agent_dir = write_pi_agent_dir(spec, out_dir)
        env = proc.agent_env()
        env["PI_CODING_AGENT_DIR"] = str(agent_dir)
        env["PI_OFFLINE"] = "1"
        env["OHFLOW_BASH"] = os.environ.get(
            "OHFLOW_BASH", r"C:\Program Files\Git\bin\bash.exe")
        env["OHFLOW_WRITE_SCOPE"] = json.dumps(list(spec.get("write_scope") or []))
        env["OHFLOW_WORKSPACE"] = str(spec.get("workspace") or "")
        env["OHFLOW_ATTEMPT_DIR"] = str(out_dir.resolve())
        command_time_cap = effective_command_time_cap(
            int(spec.get("execution_timeout_s") or 5400), spec.get("command_time_cap_s"))
        env["OHFLOW_BASH_TIMEOUT_S"] = str(command_time_cap)
        env["OHFLOW_COMMAND_TIME_CAP_LOG"] = str(
            out_dir / "logs" / "command_time_caps.jsonl")
        env["OHFLOW_COMMAND_TIME_CAP_CONTEXT"] = json.dumps(
            {"coord": spec.get("coord"), "attempt": spec.get("attempt")})
        key_name = str((spec.get("model") or {}).get("api_key_env") or "")
        if key_name and not env.get(key_name):
            raise RuntimeError(f"{key_name} is empty or unset")
        provider = str((spec.get("model") or {}).get("model") or "").split("/", 1)[0]
        canonical_key = {"zai": "ZAI_API_KEY"}.get(provider)
        if canonical_key and key_name:
            env[canonical_key] = env[key_name]
        tool_policy = discover_mcp(tool_policy, env, out_dir)
        return CliPreparedProcess(
            argv=tuple(build_command(spec, out_dir, tool_policy)),
            cwd=Path(str(spec["workspace"])),
            env=env,
            context={"tool_policy": tool_policy, "agent_dir": agent_dir},
        )

    def parse_event(self, line: str) -> Mapping[str, Any]:
        return json.loads(line)

    def on_event(self, spec: dict[str, Any], event: Mapping[str, Any],
                 events: list[Mapping[str, Any]]) -> CliEventAction:
        return pi_event_action(spec, event, events)

    def build_result(self, outcome: CliRunOutcome) -> tuple[dict[str, Any], str | None]:
        spec = outcome.spec
        out_dir = outcome.out_dir
        events = outcome.events
        tool_policy = outcome.prepared.context["tool_policy"]
        messages = pi_messages(events)
        final = assistant_text(messages[-1]) if messages else ""
        structured, schema_error = parse_structured(final, read_schema(spec, out_dir))
        cost_source = _cost_source(out_dir)
        tokens, cost, provider_error = pi_usage(messages)
        tool_calls = [e for e in events if e.get("type") == "tool_execution_end"]
        session_files = sorted((out_dir / "session").glob("*.jsonl"))
        error = outcome.stop_error or provider_error
        if not error and outcome.returncode:
            error = f"pi exited {outcome.returncode}"
        model = spec.get("model") or {}
        result = {
            **attempt_record.empty_record(spec, error or "", cost_source=cost_source),
            "conversation_id": session_files[-1].stem if session_files else None,
            "transcript_dir": str(out_dir / "session"),
            "execution_status": "error" if error else "finished",
            "tools": list(tool_policy.offered_tools), "skills": list(spec.get("skills") or []),
            "mcp_servers": sorted((spec.get("mcp_config") or {}).keys()),
            "tool_calls": len(tool_calls),
            "observation_errors": sum(bool(e.get("isError") or
                                           (e.get("result") or {}).get("isError"))
                                      for e in tool_calls),
            "llm_calls": len(messages),
            "wall_seconds": round(outcome.finished_at - outcome.started_at, 1),
            "tokens": tokens, "cost": cost,
            "final_text_path": "final.md", "structured": structured,
            "schema_error": schema_error, "error": error,
            "pi_version": version_of(pi_argv()),
            "settings": attempt_record.settings_record(spec, {
                "model": model.get("model"),
                "thinking": (model.get("params") or {}).get("thinking", "low"),
                "tools": list(tool_policy.offered_tools)}),
        }
        return result, final


def pi_event_action(spec: dict[str, Any], event: Mapping[str, Any],
                    events: list[Mapping[str, Any]], *,
                    enforce_limit: bool = True) -> CliEventAction:
    """What one pi-shaped event line asks the runtime to do.

    A module-level function and not a method, because the rule is stateless:
    the durable host prints pi's own event shapes, so its adapter reads them
    here without building a `PiAdapter` per event line. `enforce_limit=False`
    leaves `max_iterations` to a host that enforces it itself.
    """
    if (enforce_limit and event.get("type") == "message_end" and
            (event.get("message") or {}).get("role") == "assistant" and
            len(pi_messages(events)) >= int(spec.get("max_iterations") or 150) and
            (event.get("message") or {}).get("stopReason") in ("toolUse", "tool_use")):
        return CliEventAction(
            stop_error=f"max iterations {int(spec.get('max_iterations') or 150)} exceeded")
    calls = _call_events(event)
    if event.get("type") == "tool_execution_end":
        tool_calls = sum(e.get("type") == "tool_execution_end" for e in events)
        return CliEventAction(heartbeat={"tool_calls": tool_calls}, calls=calls)
    return CliEventAction(calls=calls)


# ------------------------------------------------------------ agent rules

def _model_errors(where: str, model: Any) -> list[str]:
    """Pi consumes provider/id plus its own small, explicit option set."""
    errs: list[str] = []
    if not isinstance(model.model, str) or not re.fullmatch(
            r"[^/\s]+/[^/\s]+", model.model):
        errs.append(
            f"{where}: pi model must be provider/id, got {model.model!r}")

    params = model.params if isinstance(model.params, Mapping) else {}
    unknown = sorted((repr(key) for key in params
                      if not isinstance(key, str) or key not in PI_MODEL_PARAMS))
    if unknown:
        errs.append(
            f"{where}: pi model params are closed; unsupported {unknown}. "
            f"Known: {sorted(PI_MODEL_PARAMS)}")
    if "thinking" in params and params["thinking"] not in PI_THINKING_LEVELS:
        errs.append(
            f"{where}: pi model param 'thinking' must be one of "
            f"{sorted(PI_THINKING_LEVELS)}, got {params['thinking']!r}")
    if model.extra_body:
        errs.append(
            f"{where}: pi refuses ModelConfig.extra_body; use a supported pi "
            "model param or provider configuration")
    if not isinstance(model.api_key_env, str) or not model.api_key_env.strip():
        errs.append(f"{where}: pi model api_key_env must name a variable")
    return errs


def _tool_policy_errors(where: str, agent: Any) -> list[str]:
    """Harness executor-specific tool policy and skill rules proved by the Part 2 probes."""
    errs: list[str] = []
    tool_policy = agent.tools
    if tool_policy.preset != "default":
        errs.append(
            f"{where}: pi supports only tools.preset='default', got "
            f"{tool_policy.preset!r}")
    if tool_policy.enable_browser:
        errs.append(f"{where}: pi harness executor refuses enable_browser=True")
    if tool_policy.enable_sub_agents:
        errs.append(f"{where}: pi harness executor refuses enable_sub_agents=True")

    allowed = PI_SHARED_TOOLS | PI_NATIVE_TOOLS
    unknown = sorted((repr(name) for name in tool_policy.only
                      if not isinstance(name, str) or name not in allowed))
    if unknown:
        errs.append(
            f"{where}: pi tools.only has unsupported names {unknown}; known: "
            f"{sorted(allowed)}")
    if "task_tracker" in tool_policy.only:
        warnings.warn(
            f"{where}: pi has no task_tracker equivalent; it will be dropped",
            UserWarning, stacklevel=3)

    if agent.skills:
        if not agent.skills_dir:
            errs.append(f"{where}: pi named skills require skills_dir")
        else:
            root = Path(agent.skills_dir)
            if not root.is_dir():
                errs.append(f"{where}: pi skills_dir is not a directory: {root}")
            for name in agent.skills:
                if not isinstance(name, str) or not name:
                    errs.append(f"{where}: pi skill names must be non-empty strings")
                elif not (root / name / "SKILL.md").is_file():
                    errs.append(
                        f"{where}: pi skill {name!r} has no {root / name / 'SKILL.md'}")

    config = agent.mcp_config
    if isinstance(config, Mapping) and len(config) > 3:
        warnings.warn(
            f"{where}: pi configures more than three MCP servers "
            f"({len(config)}); startup and tool discovery may dominate the run",
            UserWarning, stacklevel=3)
    return errs


def model_errors(where: str, model: Any, executor: str,
                 providers) -> list[str]:
    """The model faults a remote harness executor's host refuses.

    The durable host and the pi-cloud Worker run pi against providers whose
    keys they hold themselves, so both judge the model the same way: a
    `provider/id` whose provider is one of `providers`, the closed param set,
    the thinking levels, no `extra_body`, no `api_key_env`. Each message names
    `executor`, so the two executors word the one rule in their own name.
    """
    errs: list[str] = []
    model_id = model.model if isinstance(model.model, str) else ""
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", model_id) \
            or model_id.split("/", 1)[0] not in providers:
        errs.append(
            f"{where}: {executor} model must be provider/id with the provider "
            f"one of {sorted(providers)}, got {model.model!r}")
    params = model.params if isinstance(model.params, Mapping) else {}
    unknown = sorted(repr(key) for key in params
                     if not isinstance(key, str)
                     or key not in PI_MODEL_PARAMS)
    if unknown:
        errs.append(
            f"{where}: {executor} model params are closed; unsupported {unknown}. "
            f"Known: {sorted(PI_MODEL_PARAMS)}")
    if "thinking" in params and params["thinking"] not in PI_THINKING_LEVELS:
        errs.append(
            f"{where}: {executor} model param 'thinking' must be one of "
            f"{sorted(PI_THINKING_LEVELS)}, got {params['thinking']!r}")
    if model.extra_body:
        errs.append(
            f"{where}: {executor} refuses ModelConfig.extra_body; use a "
            "supported model param")
    if model.api_key_env:
        holder = KEY_HOLDERS.get(executor, f"{executor} holds its keys")
        errs.append(
            f"{where}: {executor} model api_key_env must be empty; {holder}")
    return errs


def agent_errors(where: str, agent: Any) -> list[str]:
    return _model_errors(where, agent.model) + _tool_policy_errors(where, agent)


# ------------------------------------------------------------------- usage

def usage(attempt_dir: Path) -> tuple[dict[str, int] | None, str | None]:
    """The usage the runner's event log records.

    Only completed assistant `message_end` events count. The session file may
    carry forked history in another shape, so it is not the authority.
    """
    event_log = Path(attempt_dir) / "logs" / EVENT_LOG
    if not event_log.is_file():
        return None, f"pi event log is missing ({event_log})"
    return event_log_usage(event_log, "pi")


NO_USAGE_RECORDS = "no assistant message_end usage records"


def event_log_usage(event_log: Path, name: str) -> tuple[dict[str, int] | None, str | None]:
    """The usage one pi-shape event log records.

    The durable host replays pi's event shapes, so its runner reads the same
    log through this function; `name` labels the fault text. Only completed
    assistant `message_end` events count, and a malformed record is a fault
    rather than a zero, because the attempt's tokens are reconciled against
    this count.
    """
    event_log = Path(event_log)
    total = attempt_record.zero_tokens()
    assistants = 0
    try:
        lines = event_log.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return None, f"{event_log}: cannot read the {name} event log ({error})"
    for line_number, line in enumerate(lines, start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            return None, f"{event_log}:{line_number}: malformed JSON ({error})"
        if not isinstance(event, dict) or event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        assistants += 1
        raw = message.get("usage")
        if not isinstance(raw, dict):
            return None, f"{event_log}:{line_number}: assistant usage is missing"
        required = ("input", "output", "cacheRead", "cacheWrite")
        if any(key not in raw or raw[key] is None or
               not attempt_record.is_count(raw[key]) for key in required):
            return None, f"{event_log}:{line_number}: assistant usage is malformed"
        if ("reasoning" in raw and raw["reasoning"] is not None and
                not attempt_record.is_count(raw["reasoning"])):
            return None, f"{event_log}:{line_number}: assistant usage is malformed"
        for key, value in _message_tokens(raw).items():
            total[key] += value
    if not assistants:
        return None, f"{event_log}: {NO_USAGE_RECORDS}"
    return total, None


# --------------------------------------------------- resume and transcript

def _session_in(result: Mapping[str, Any], attempt_dir: Path) -> Path | None:
    """The session file an attempt left: its own conversation, else the newest."""
    attempt_dir = Path(attempt_dir)
    transcript_dir = attempt_dir / "session"
    recorded = result.get("transcript_dir")
    if recorded:
        path = Path(str(recorded))
        # Result files record absolute paths. An archived run can move, and
        # its attempt-local session stays authoritative.
        candidate = path if path.is_absolute() else attempt_dir / path
        if candidate.is_dir():
            transcript_dir = candidate
    if not transcript_dir.is_dir():
        return None
    conversation_id = result.get("conversation_id")
    if conversation_id:
        named = transcript_dir / f"{conversation_id}.jsonl"
        if named.is_file():
            return named
    sessions = list(transcript_dir.glob("*.jsonl"))
    if not sessions:
        return None

    def freshness(path: Path) -> tuple[int, str]:
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        return stamp, path.name

    return max(sessions, key=freshness)


def resume_target(prior_result: Mapping[str, Any], attempt_dir: Path) -> str | None:
    """A pi retry forks the prior attempt's session file."""
    session = _session_in(prior_result, attempt_dir)
    return str(session) if session else None


def transcript(attempt_dir: Path, result: Mapping[str, Any],
               output: Path | None = None) -> tuple[Path | None, str | None]:
    """Export the session as an HTML file a human can read."""
    session = _session_in(result, attempt_dir)
    if session is None:
        return None, "no pi session"
    if output is None:
        return session, None
    try:
        command = pi_argv()
    except FileNotFoundError as error:
        return None, str(error)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    kwargs = ({"creationflags": subprocess.CREATE_NO_WINDOW}
              if sys.platform == "win32" else {})
    try:
        completed = proc.run([*command, "--export", str(session), str(output)],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120, **kwargs)
    except subprocess.TimeoutExpired:
        return None, "pi export timed out after 120 seconds"
    except OSError as error:
        return None, f"cannot start pi export: {error}"
    if completed.returncode:
        return None, completed.stderr.strip() or completed.stdout.strip()
    if not output.is_file():
        return None, f"pi export did not write {output}"
    return output, None


# ---------------------------------------------------------------- activity

def apply_assistant_message(model: act.Activity, message: Mapping[str, Any],
                            at: float | None) -> None:
    """Read one pi assistant message into an activity model.

    The message shape is pi's own wherever it arrives from: a session file
    this machine tails or the durable host's event log replayed over ssh.
    What a message spent, what it said and which calls it opened is one
    interpretation, so it lives here once and every harness executor that
    sees pi's shapes calls it.
    """
    model.replied = True
    model.llm_calls += 1
    raw = message.get("usage") or {}
    model.tokens["input"] += (act.int_of(raw.get("input"))
                              + act.int_of(raw.get("cacheRead"))
                              + act.int_of(raw.get("cacheWrite")))
    model.tokens["output"] += act.int_of(raw.get("output"))
    model.tokens["cache_read"] += act.int_of(raw.get("cacheRead"))
    model.tokens["reasoning"] += act.int_of(raw.get("reasoning"))
    content = message.get("content") if isinstance(message.get("content"), list) else []
    texts = [c.get("text") for c in content if isinstance(c, dict)
             and c.get("type") == "text"
             and str(c.get("text") or "").strip()]
    thoughts = [c.get("thinking") for c in content if isinstance(c, dict)
                and c.get("type") == "thinking"
                and str(c.get("thinking") or "").strip()]
    if texts:
        model.said(texts[0], at, "text")
    elif thoughts:
        model.said(thoughts[0], at, "thinking")
    for c in content:
        if isinstance(c, dict) and c.get("type") == "toolCall":
            model.add_call(c.get("id"), at, str(c.get("name") or "?"),
                           c.get("arguments"))


def pi_event_time(event: Mapping[str, Any]) -> float | None:
    """A `t`-stamped pi event's own clock: the `t` field, else the message's.

    The durable host and the pi-cloud Worker both print pi's own event shapes
    with a `t` of their own, in epoch milliseconds, so the one clock reader
    serves both.
    """
    at = act.epoch(event.get("t"))
    if at is None:
        at = act.epoch((event.get("message") or {}).get("timestamp"))
    return at


def apply_pi_event(model: act.Activity, event: Mapping[str, Any]) -> None:
    """Read one pi-shaped event line into an activity model.

    `pi_event_action` is what a runtime does with an event; this is what an
    activity reader reads from a stored one. Both remote harness executors
    (durable, pi-cloud) replay the same shapes, so the reader lives here once.
    """
    at = pi_event_time(event)
    model.touch(at)
    kind = event.get("type")
    if kind == "message_end":
        message = event.get("message") or {}
        if message.get("role") == "assistant":
            apply_assistant_message(model, message, at)
    elif kind == "tool_execution_start":
        args = event.get("args") if isinstance(event.get("args"), Mapping) else {}
        model.add_call(event.get("toolCallId"), at,
                       str(event.get("toolName") or "?"), args)
    elif kind == "tool_execution_end":
        model.add_result(event.get("toolCallId"), at, not event.get("isError"),
                         act.content_text((event.get("result") or {}).get("content")))


def _entry(model: act.Activity, entry: dict) -> None:
    at = act.epoch(entry.get("timestamp"))
    model.touch(at)
    msg = entry.get("message")
    if entry.get("type") != "message" or not isinstance(msg, dict):
        return
    role = msg.get("role")
    content = msg.get("content") if isinstance(msg.get("content"), list) else []
    if role == "assistant":
        apply_assistant_message(model, msg, at)
        if msg.get("errorMessage"):
            model.last_error = act.first_line(msg["errorMessage"])
    elif role == "toolResult":
        model.add_result(msg.get("toolCallId"), at, not msg.get("isError"),
                         act.content_text(content))


def _refresh(model: act.Activity, attempt_dir: Path) -> None:
    sessions = sorted((attempt_dir / "session").glob("*.jsonl"))
    if not sessions:
        return
    newest = sessions[-1]
    if model.session != newest:
        # A forked or restarted session: read the newest one from the top.
        model.reset()
        model.session = newest
    lines, reset = model.tail.read(newest)
    if reset:
        model.reset()
        model.session = newest
        lines, _ = model.tail.read(newest)
    for raw in lines:
        try:
            entry = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(entry, dict):
            _entry(model, entry)


def activity(attempt_dir: Path, *, now: float | None = None, running: bool = True,
             limit: int = act.DEFAULT_TOOL_CALLS) -> dict:
    """The pi session file, with the heartbeat as a fallback clock.

    pi holds entries in memory until its first assistant message exists, so an
    empty session is normal for the first seconds of an attempt. The heartbeat
    then says when the process last moved.
    """
    attempt_dir = Path(attempt_dir)
    now = time.time() if now is None else float(now)
    model = act.model_for(attempt_dir)
    with model.lock:
        _refresh(model, attempt_dir)
        beat = act.read_json(attempt_dir / "logs" / "heartbeat.json")
        beat_at = act.epoch(beat.get("at")) if isinstance(beat, dict) else None
        note = act.STARTING_NOTE if not model.replied else None
        return act.activity_out(model, harness_executor="pi",
                                root=act.worktree_root(attempt_dir), now=now,
                                running=running, limit=limit,
                                fallback_at=beat_at, note=note)


def preflight() -> list[str]:
    try:
        pi_argv()
    except FileNotFoundError as e:
        return [str(e)]
    return []


def make_harness_executor():
    from .cli_harness_executor import PiHarnessExecutor
    return PiHarnessExecutor()


def main(argv: list[str] | None = None) -> int:
    return runner_main(PiAdapter, argv)


if __name__ == "__main__":
    raise SystemExit(main())
