"""Run one Claude Code agent and translate its stream-json events to ohflow records.

Launch: `claude.exe -p --output-format stream-json --verbose`, in the signed-in harness's
usual setup unless the step names `agent_profile="hermetic"`. A hermetic agent loads
no instruction file and no user settings, and keeps its login. The first `system`
`init` event announces the tools, the MCP servers and the model. The last
`result` event carries the final text, the usage and the cost.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from . import activity as act
from .attempt_record import (TOKEN_KEYS, empty_record, mcp_servers_of,
                             settings_record)
from .cli_harness_executor import (CliEventAction, CliPreparedProcess, CliRunOutcome,
                                   recover_cli_result)
from .signed_in import (SignedInRules, bootstrap_prompt, executable_argv, read_schema,
                        run_quiet, runner_main, signed_in_activity, signed_in_env,
                        signed_in_transcript, signed_in_agent_errors, version_of)
from .structured import parse_structured
from .tool_output import CallEvent, out_dir_of
from .paths import posix

#: The CLAUDE_CODE_SHELL_PREFIX wrapper that copies Bash output while it runs.
SHELL_TEE = Path(__file__).resolve().parent / "shell_tee.sh"


def ensure_executable(path: Path) -> bool:
    """True when Claude can run `path` as a program. Off Windows that needs
    the executable bit, which a zip or a plain copy drops; this sets it back.
    Git Bash on Windows ignores the bit."""
    path = Path(path)
    if os.name == "nt":
        return True
    if not path.is_file():
        return False
    if os.access(path, os.X_OK):
        return True
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        return False
    return os.access(path, os.X_OK)


def shell_capture_env(out_dir: Path) -> dict[str, str]:
    """The variables that route every Bash command through `shell_tee.sh`.

    Claude splices the prefix into `bash -c "<prefix> '<line>'"` unquoted, so a
    path with a space would break every command: then nothing is routed and
    Bash output arrives only with each `tool_result`. The PowerShell tool is
    never wrapped (measured 2026-10-10); its output also arrives at the end.
    The same holds off Windows for a wrapper that is not executable and cannot
    be made so: a prefix that cannot run fails every Bash command with 126.
    """
    tee = posix(SHELL_TEE)
    target = posix(out_dir_of(out_dir))
    if " " in tee or " " in target:
        return {}
    if not ensure_executable(SHELL_TEE):
        return {}
    return {"CLAUDE_CODE_SHELL_PREFIX": tee, "OHFLOW_TOOL_OUTPUT_DIR": target}


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(str(p.get("text") or "") for p in content or ()
                   if isinstance(p, Mapping) and p.get("type") == "text")


def _call_events(event: Mapping[str, Any]) -> tuple[CallEvent, ...]:
    """Claude's tool_use and tool_result blocks as tool-output calls."""
    kind = event.get("type")
    if kind not in ("assistant", "user"):
        return ()
    out = []
    for part in (event.get("message") or {}).get("content") or ():
        if not isinstance(part, Mapping):
            continue
        if kind == "assistant" and part.get("type") == "tool_use" and part.get("id"):
            inp = part.get("input") if isinstance(part.get("input"), Mapping) else {}
            command = inp.get("command") if isinstance(inp.get("command"), str) \
                else json.dumps(inp, separators=(",", ":"))[:400]
            out.append(CallEvent("start", str(part["id"]), tool=part.get("name"),
                                 command=command))
        elif kind == "user" and part.get("type") == "tool_result" and part.get("tool_use_id"):
            out.append(CallEvent("end", str(part["tool_use_id"]),
                                 ok=not part.get("is_error"),
                                 text=_result_text(part.get("content"))))
    return tuple(out)

EVENT_LOG = "claude-events.jsonl"

# Shared tool policy names to Claude built-ins, for a hermetic agent.
HERMETIC_TOOLS = {
    "terminal": ("Bash",),
    "file_editor": ("Read", "Edit", "Write", "Glob", "Grep"),
    "task_tracker": ("TodoWrite",),
}
HERMETIC_DEFAULT = ("terminal", "file_editor")

# `--setting-sources project,local` drops the user's settings but not the
# instruction files (CLAUDE.md). This variable drops every one, the user's and
# the project's, and keeps the `--mcp-config` servers and the login. `--safe-mode` drops the servers too;
# `--bare` needs an API key. Measured 2026-10-01 (2.1.281).
HERMETIC_ENV = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}

# The init event names some tools by their internal name; the model sees
# another. Measured 2026-09-30 (2.1.281): init says `Task`, the model calls
# it `Agent`.
TOOL_ALIASES = {"Task": ("Agent",)}


def claude_argv() -> list[str]:
    return executable_argv("OHFLOW_CLAUDE_EXE", "claude")


def preflight() -> list[str]:
    """The harness must be signed in; a logged-out CLI fails every attempt."""
    try:
        argv = claude_argv()
    except FileNotFoundError as e:
        return [str(e)]
    try:
        out = run_quiet([*argv, "auth", "status"], timeout=30).stdout
        status = json.loads(out)
    except Exception as e:  # noqa: BLE001 - any failure is a preflight finding
        return [f"claude harness executor: `claude auth status` failed: {e}"]
    if not status.get("loggedIn"):
        return ["claude harness executor: the Claude CLI is not logged in; run `claude auth login`"]
    return []


def build_command(spec: Mapping[str, Any], out_dir: Path, session_id: str) -> list[str]:
    model = spec.get("model") or {}
    command = [*claude_argv(), "-p", "--output-format", "stream-json", "--verbose",
               "--permission-mode", "bypassPermissions"]
    if model.get("model"):
        command.extend(["--model", str(model["model"])])
    effort = (model.get("params") or {}).get("effort")
    if effort:
        command.extend(["--effort", str(effort)])
    fork = spec.get("fork_session")
    if fork:
        command.extend(["--resume", str(fork), "--fork-session", "--session-id", session_id])
    else:
        command.extend(["--session-id", session_id])
    if spec.get("schema_path"):
        schema = read_schema(spec, out_dir)
        command.extend(["--json-schema", json.dumps(schema, separators=(",", ":"))])
    if spec.get("agent_profile") == "hermetic":
        only = list((spec.get("tools") or {}).get("only") or HERMETIC_DEFAULT)
        tools = [t for name in only for t in HERMETIC_TOOLS.get(name, ())]
        mcp_path = out_dir / "claude-mcp.json"
        mcp_path.write_text(json.dumps({"mcpServers": spec.get("mcp_config") or {}},
                                       indent=2), encoding="utf-8")
        command.extend(["--tools", ",".join(tools), "--strict-mcp-config",
                        "--mcp-config", str(mcp_path), "--setting-sources", "project,local"])
    command.append(bootstrap_prompt(out_dir))
    return command


def _init(events) -> Mapping[str, Any]:
    for e in events:
        if e.get("type") == "system" and e.get("subtype") == "init":
            return e
    return {}


def _result_event(events) -> Mapping[str, Any] | None:
    for e in reversed(events):
        if e.get("type") == "result":
            return e
    return None


def _assistant_messages(events) -> dict[str, list[Mapping[str, Any]]]:
    """Assistant events grouped by API message id. One API reply arrives as
    one event per content block, all carrying the same id and usage."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        if msg.get("model") == "<synthetic>":
            continue
        grouped.setdefault(str(msg.get("id") or len(grouped)), []).append(msg)
    return grouped


def _tokens(usage: Mapping[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    inp = int(usage.get("input_tokens") or 0)
    write = int(usage.get("cache_creation_input_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)
    details = usage.get("output_tokens_details") or {}
    return {"prompt_tokens": inp + write + read,
            "completion_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": read, "cache_write_tokens": write,
            "reasoning_tokens": int(details.get("thinking_tokens") or 0)}


def _summed_tokens(events) -> dict[str, int]:
    total = {key: 0 for key in TOKEN_KEYS}
    for messages in _assistant_messages(events).values():
        for key, value in _tokens(messages[-1].get("usage")).items():
            total[key] += value
    return total


def _tool_results(events) -> list[Mapping[str, Any]]:
    results = []
    for e in events:
        if e.get("type") != "user":
            continue
        for part in (e.get("message") or {}).get("content") or []:
            if isinstance(part, Mapping) and part.get("type") == "tool_result":
                results.append(part)
    return results


def _last_text(events) -> str:
    for messages in reversed(list(_assistant_messages(events).values())):
        texts = [str(p.get("text") or "") for m in messages
                 for p in (m.get("content") or []) if isinstance(p, Mapping)
                 and p.get("type") == "text"]
        if any(t.strip() for t in texts):
            return "".join(texts)
    return ""


STRUCTURED_TOOL = "StructuredOutput"


def _last_structured_call(events) -> tuple[bool, Any]:
    for e in reversed(events):
        if e.get("type") != "assistant" or e.get("parent_tool_use_id"):
            continue
        for part in reversed((e.get("message") or {}).get("content") or []):
            if (isinstance(part, Mapping) and part.get("type") == "tool_use"
                    and part.get("name") == STRUCTURED_TOOL):
                return True, part.get("input")
    return False, None


def _synthetic_error(events) -> str | None:
    """Claude reports a failed login or API call as a `<synthetic>` reply."""
    for e in events:
        msg = e.get("message") or {}
        if e.get("type") == "assistant" and msg.get("model") == "<synthetic>":
            return "".join(str(p.get("text") or "") for p in msg.get("content") or []
                           if isinstance(p, Mapping)) or "synthetic error"
    return None


def _record(spec: Mapping[str, Any], out_dir: Path, events, *, error: str | None,
            wall: float, version: str) -> tuple[dict[str, Any], str | None]:
    init = _init(events)
    final_event = _result_event(events)
    # A failed login or API call arrives as a `<synthetic>` reply, and the
    # result event then says only `success` with terminal_reason `api_error`.
    synthetic = _synthetic_error(events)
    if synthetic and not error:
        error = synthetic
    if final_event is not None:
        final = str(final_event.get("result") or "")
        tokens = _tokens(final_event.get("usage"))
        cost = float(final_event.get("total_cost_usd") or 0.0)
        if final_event.get("is_error") and not error:
            error = final_event.get("subtype") or "claude result is_error"
            if final_event.get("terminal_reason"):
                error = f"{error}: {final_event['terminal_reason']}"
    else:
        final = _last_text(events)
        tokens = _summed_tokens(events)
        cost = 0.0
    schema = read_schema(spec, out_dir)
    structured, schema_error = None, None
    called, call_input = _last_structured_call(events)
    if called or (final_event is not None
                  and final_event.get("structured_output") is not None):
        structured = call_input if called else final_event.get("structured_output")
        # `--json-schema` may leave the result text empty; the report is the text.
        if not final.strip():
            final = json.dumps(structured, indent=2)
    else:
        structured, schema_error = parse_structured(final, schema, bare_ok=True)
    tools = [str(t) for t in init.get("tools") or []]
    tools += [a for t in list(tools) for a in TOOL_ALIASES.get(t, ()) if a not in tools]
    # Every server init names, whatever its status: a `pending` server
    # finishes connecting after init and the agent then sees it.
    listed = [s for s in init.get("mcp_servers") or [] if isinstance(s, Mapping)]
    servers = [str(s.get("name")) for s in listed]
    # The model sees a server by the name in its tool names, which differs for
    # a claude.ai connector: init says `claude.ai Gmail`, the tools say
    # `mcp__claude_ai_Gmail__*`. Measured 2026-09-30.
    servers += [s for s in mcp_servers_of(tools) if s not in servers]
    results = _tool_results(events)
    result = {
        **empty_record(spec, error or ""),
        "conversation_id": init.get("session_id") or (final_event or {}).get("session_id"),
        "transcript_dir": str(out_dir / "logs"),
        "execution_status": "error" if error else "finished",
        "tools": tools, "mcp_servers": servers,
        "tool_calls": len(results),
        "observation_errors": sum(bool(r.get("is_error")) for r in results),
        "llm_calls": len(_assistant_messages(events)),
        "wall_seconds": wall, "tokens": tokens, "cost": cost,
        "cost_source": "claude-cli" if final_event is not None else "unpriced",
        "final_text_path": "final.md" if final else None,
        "structured": structured, "schema_error": schema_error,
        "error": error, "claude_version": init.get("claude_code_version") or version,
        "num_turns": (final_event or {}).get("num_turns"),
        "mcp_status": {str(s.get("name")): s.get("status") for s in listed},
        "settings": settings_record(spec, {"model": init.get("model"),
                                           "agent_profile": spec.get("agent_profile"),
                                           "permission_mode": init.get("permissionMode"),
                                           "tools": tools}),
    }
    return result, final or None


def usage(attempt_dir: Path) -> tuple[dict[str, int] | None, str | None]:
    """The usage the event log records."""
    from .cli_harness_executor import read_cli_events
    path = Path(attempt_dir) / "logs" / EVENT_LOG
    if not path.is_file():
        return None, f"claude event log is missing ({path})"
    events = read_cli_events(path, json.loads)
    final_event = _result_event(events)
    return (_tokens(final_event.get("usage")) if final_event is not None
            else _summed_tokens(events)), None


RULES = SignedInRules("claude", {"effort": frozenset({"low", "medium", "high", "xhigh", "max"})})


def agent_errors(where: str, agent: Any) -> list[str]:
    return signed_in_agent_errors(RULES, where, agent)


def resume_target(prior_result: Mapping[str, Any], attempt_dir: Path) -> str | None:
    """A retry resumes the prior attempt's conversation."""
    return prior_result.get("conversation_id") or None


def transcript(attempt_dir: Path, result: Mapping[str, Any],
               output: Path | None = None) -> tuple[Path | None, str | None]:
    """The runner's copy of the claude stream-json stream; a human reads it as it is."""
    return signed_in_transcript(attempt_dir, EVENT_LOG)

def _entry(model: act.Activity, e: dict, at: float) -> None:
    kind = e.get("type")
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    content = msg.get("content") if isinstance(msg.get("content"), list) else []
    if kind == "assistant":
        if msg.get("model") == "<synthetic>":
            model.last_error = act.first_line(act.content_text(content))
            return
        seen = model.scratch.setdefault("message_ids", set())
        if msg.get("id") not in seen:
            seen.add(msg.get("id"))
            model.llm_calls += 1
            usage = msg.get("usage") or {}
            model.tokens["input"] += (act.int_of(usage.get("input_tokens")) +
                                      act.int_of(usage.get("cache_creation_input_tokens")) +
                                      act.int_of(usage.get("cache_read_input_tokens")))
            model.tokens["output"] += act.int_of(usage.get("output_tokens"))
            model.tokens["cache_read"] += act.int_of(usage.get("cache_read_input_tokens"))
        model.replied = True
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and str(c.get("text") or "").strip():
                model.said(c["text"], at, "text")
            elif c.get("type") == "thinking" and str(c.get("thinking") or "").strip():
                model.said(c["thinking"], at, "thinking")
            elif c.get("type") == "tool_use":
                model.add_call(c.get("id"), at, str(c.get("name") or "?"), c.get("input"))
    elif kind == "user":
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                model.add_result(c.get("tool_use_id"), at, not c.get("is_error"),
                                 act.content_text(c.get("content")))
    elif kind == "result" and e.get("is_error"):
        model.last_error = act.first_line(e.get("result") or e.get("subtype"))


def activity(attempt_dir: Path, *, now: float | None = None, running: bool = True,
             limit: int = act.DEFAULT_TOOL_CALLS) -> dict:
    return signed_in_activity(attempt_dir, "claude", EVENT_LOG, _entry, now=now,
                              running=running, limit=limit)


def _recover(spec: dict[str, Any], out_dir: Path, events, fallback: str):
    return _record(spec, Path(out_dir), events, error=fallback, wall=0.0,
                   version="unknown")


def recover_result(spec_path: Path, out_dir: Path, fallback_error: str) -> dict[str, Any]:
    return recover_cli_result(spec_path, out_dir, fallback_error,
                              event_log_name=EVENT_LOG, parser=json.loads,
                              builder=_recover)


class ClaudeAdapter:
    name = "claude"
    event_log_name = EVENT_LOG
    stderr_log_name = "claude-stderr.log"

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
        session_id = str(uuid.uuid4())
        hermetic = spec.get("agent_profile") == "hermetic"
        return CliPreparedProcess(
            argv=tuple(build_command(spec, out_dir, session_id)),
            cwd=Path(str(spec["workspace"])),
            env=signed_in_env({**(HERMETIC_ENV if hermetic else {}),
                               **shell_capture_env(out_dir)}),
            context={"session_id": session_id})

    def parse_event(self, line: str) -> Mapping[str, Any]:
        return json.loads(line)

    def on_event(self, spec, event, events) -> CliEventAction:
        calls = _call_events(event)
        if event.get("type") == "assistant":
            content = (event.get("message") or {}).get("content") or []
            if any(isinstance(p, Mapping) and p.get("type") == "tool_use" for p in content):
                cap = int(spec.get("max_iterations") or 150)
                if len(_assistant_messages(events)) > cap:
                    return CliEventAction(stop_error=f"max iterations {cap} exceeded",
                                          calls=calls)
        if event.get("type") == "user":
            return CliEventAction(heartbeat={"tool_calls": len(_tool_results(events))},
                                  calls=calls)
        return CliEventAction(calls=calls)

    def build_result(self, outcome: CliRunOutcome):
        error = outcome.stop_error
        if not error and outcome.returncode and _result_event(outcome.events) is None:
            error = f"claude exited {outcome.returncode}"
        return _record(outcome.spec, outcome.out_dir, outcome.events, error=error,
                       wall=round(outcome.finished_at - outcome.started_at, 1),
                       version=version_of(claude_argv()))


def make_harness_executor():
    from .cli_harness_executor import CliHarnessExecutor
    return CliHarnessExecutor(name="claude", runner_module="ohflow.claude_runner",
                              recovery=recover_result,
                              checks=preflight)


def main(argv: list[str] | None = None) -> int:
    return runner_main(ClaudeAdapter, argv)


if __name__ == "__main__":
    raise SystemExit(main())
