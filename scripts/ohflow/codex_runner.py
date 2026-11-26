"""Run one Codex agent and translate its events to ohflow records.

The agent runs over `codex app-server` through `ohflow.codex_appserver`, which
prints the `codex exec --json` event shapes plus `item.output_delta`: the output
of a running command, which `exec --json` never carried (measured 2026-10-10,
ohflow M0 spike S3). Every event reader below reads those exec shapes.

The sandbox is `danger-full-access`, the same no-sandbox posture as the pi
and claude harness executors: the worktree and the `ownership` gate are the isolation.
Measured 2026-09-30 (codex-cli 0.157.1): under `workspace-write` every write
under `.git` is denied, `--add-dir <repo>/.git` does not lift it, and a worktree
keeps its index and HEAD in `<repo>/.git/worktrees/<name>`. A roll-call agent
then spent 300 s and 1.1 M input tokens committing one file through git
plumbing.

Codex announces no tool list. The harness executor records the MCP server names from the
config the agent runs with.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Mapping

from . import activity as act
from .attempt_record import TOKEN_KEYS, empty_record, settings_record
from .cli_harness_executor import (CliEventAction, CliPreparedProcess, CliRunOutcome,
                                   recover_cli_result)
from .signed_in import (SignedInRules, bootstrap_prompt, executable_argv, read_schema,
                        runner_main, signed_in_activity, signed_in_env, signed_in_transcript,
                        signed_in_agent_errors, version_of)
from .structured import parse_structured
from .tool_output import CallEvent
from . import IMPORT_ROOT

EVENT_LOG = "codex-events.jsonl"
TOOL_CALL_ITEMS = frozenset({"command_execution", "file_change", "mcp_tool_call", "web_search"})
# Servers Codex adds itself in the usual setup; no config.toml names them.
CODEX_BUILTIN_SERVERS = ("codex_apps",)
REAL_CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def codex_argv() -> list[str]:
    return executable_argv("OHFLOW_CODEX_EXE", "codex")


def preflight() -> list[str]:
    try:
        argv = codex_argv()
    except FileNotFoundError as e:
        return [str(e)]
    if len(argv) == 2 and argv[1].lower().endswith(".py"):
        return []
    if not (REAL_CODEX_HOME / "auth.json").is_file():
        return [f"codex harness executor: {REAL_CODEX_HOME / 'auth.json'} is missing; run `codex login`"]
    return []


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, Mapping):
        return "{ " + ", ".join(f"{json.dumps(str(k))} = {_toml_value(v)}"
                                for k, v in value.items()) + " }"
    return json.dumps(str(value))


def write_hermetic_home(spec: Mapping[str, Any], out_dir: Path) -> Path:
    """A CODEX_HOME with only the workflow's MCP servers and no hooks.

    `auth.json` is a hard link to the real one, so a token refresh inside the
    agent writes the one real file (risk C2).
    """
    home = out_dir / "codex-home"
    home.mkdir(parents=True, exist_ok=True)
    lines = ['approval_policy = "never"', 'sandbox_mode = "danger-full-access"', ""]
    for name, server in (spec.get("mcp_config") or {}).items():
        lines.append(f"[mcp_servers.{json.dumps(str(name))}]")
        for key, value in server.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append('default_tools_approval_mode = "approve"')
        lines.append("")
    (home / "config.toml").write_text("\n".join(lines), encoding="utf-8")
    auth = home / "auth.json"
    if not auth.exists():
        os.link(REAL_CODEX_HOME / "auth.json", auth)
    return home


def configured_servers(home: Path) -> list[str]:
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    servers = config.get("mcp_servers") or {}
    return [str(n) for n, s in servers.items()
            if not (isinstance(s, Mapping) and s.get("enabled") is False)]


def plugin_servers(home: Path) -> list[str]:
    """Servers the installed plugins define, in `plugins/cache/<market>/<plugin>/
    <version>/.mcp.json`. Measured 2026-09-30: `cua_repl` comes from the bundled
    unified-computer-use plugin, and no config.toml names it. A plugin's
    enabled flag and its cache folder do not map one to one, so every
    installed plugin counts."""
    servers: list[str] = []
    for path in sorted(home.glob("plugins/cache/*/*/*/.mcp.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for name, server in (data.get("mcpServers") or {}).items():
            if isinstance(server, Mapping) and server.get("enabled") is False:
                continue
            if name not in servers:
                servers.append(str(name))
    return servers


def build_command(spec: Mapping[str, Any], out_dir: Path) -> list[str]:
    """`python -m ohflow.codex_appserver ...`: one app-server turn as exec events."""
    model = spec.get("model") or {}
    command = [sys.executable, "-m", "ohflow.codex_appserver",
               "--codex", json.dumps(codex_argv()), "--cwd", str(spec["workspace"]),
               "--final", str(out_dir / "final.md")]
    if model.get("model"):
        command.extend(["--model", str(model["model"])])
    effort = (model.get("params") or {}).get("reasoning_effort")
    if effort:
        command.extend(["--effort", str(effort)])
    if spec.get("schema_path"):
        command.extend(["--schema", str((out_dir / str(spec["schema_path"])).resolve())])
    command.extend(["--prompt", bootstrap_prompt(out_dir)])
    return command


def _call_events(event: Mapping[str, Any]) -> tuple[CallEvent, ...]:
    """Tool items and command output as tool-output calls."""
    kind = event.get("type")
    if kind == "item.output_delta" and event.get("item_id"):
        return (CallEvent("output", str(event["item_id"]), text=str(event.get("delta") or "")),)
    item = event.get("item") if isinstance(event.get("item"), Mapping) else {}
    if item.get("type") not in TOOL_CALL_ITEMS or not item.get("id"):
        return ()
    name = {"command_execution": "shell", "file_change": "apply_patch",
            "web_search": "web_search"}.get(item["type"],
                                            f"{item.get('server')}.{item.get('tool')}")
    command = item.get("command") or item.get("arguments") or item.get("changes")
    if not isinstance(command, str):
        command = json.dumps(command, separators=(",", ":"))[:400] if command else None
    if kind == "item.started":
        return (CallEvent("start", str(item["id"]), tool=name, command=command),)
    if kind == "item.completed":
        exit_code = item.get("exit_code")
        return (CallEvent("start", str(item["id"]), tool=name, command=command),
                CallEvent("end", str(item["id"]), ok=not _failed(item),
                          exit=exit_code if isinstance(exit_code, int) else None,
                          text=str(item.get("aggregated_output") or "") or None))
    return ()


def _items(events, kinds=None) -> list[Mapping[str, Any]]:
    out = []
    for e in events:
        if e.get("type") != "item.completed":
            continue
        item = e.get("item") or {}
        if kinds is None or item.get("type") in kinds:
            out.append(item)
    return out


def _failed(item: Mapping[str, Any]) -> bool:
    if item.get("type") == "command_execution":
        return item.get("exit_code") not in (0, None)
    return item.get("status") == "failed" or bool(item.get("error"))


def _tokens(events) -> dict[str, int]:
    total = {key: 0 for key in TOKEN_KEYS}
    for e in events:
        if e.get("type") != "turn.completed":
            continue
        u = e.get("usage") or {}
        total["prompt_tokens"] += int(u.get("input_tokens") or 0)
        total["completion_tokens"] += int(u.get("output_tokens") or 0)
        total["cache_read_tokens"] += int(u.get("cached_input_tokens") or 0)
        total["cache_write_tokens"] += int(u.get("cache_write_input_tokens") or 0)
        total["reasoning_tokens"] += int(u.get("reasoning_output_tokens") or 0)
    return total


def _error(events) -> str | None:
    for e in reversed(events):
        if e.get("type") == "turn.failed":
            return str((e.get("error") or {}).get("message") or "turn failed")
    for e in reversed(events):
        if e.get("type") == "turn.completed":
            return None
        if e.get("type") == "error":
            return str(e.get("message") or "codex error")
    return None


def _record(spec, out_dir: Path, events, *, error: str | None, wall: float,
            home: Path, version: str) -> tuple[dict[str, Any], str | None]:
    error = error or _error(events)
    final_path = out_dir / "final.md"
    final = final_path.read_text(encoding="utf-8") if final_path.is_file() else ""
    if not final:
        messages = _items(events, {"agent_message"})
        final = str(messages[-1].get("text") or "") if messages else ""
    if not error and not any(e.get("type") == "turn.completed" for e in events):
        error = "codex ended without turn.completed"
    tool_calls = _items(events, TOOL_CALL_ITEMS)
    thread = next((e.get("thread_id") for e in events if e.get("type") == "thread.started"), None)
    schema = read_schema(spec, out_dir)
    structured, schema_error = parse_structured(final, schema, bare_ok=True)
    servers = configured_servers(home)
    if home == REAL_CODEX_HOME:
        extra = [*CODEX_BUILTIN_SERVERS, *plugin_servers(home)]
        servers += [s for s in dict.fromkeys(extra) if s not in servers]
    result = {
        **empty_record(spec, error or ""),
        "conversation_id": thread,
        "transcript_dir": str(out_dir / "logs"),
        "execution_status": "error" if error else "finished",
        "tools": [], "mcp_servers": servers,
        "tool_calls": len(tool_calls),
        "observation_errors": sum(_failed(a) for a in tool_calls),
        "llm_calls": sum(int(e.get("model_calls") or 1) for e in events
                         if e.get("type") == "turn.completed"),
        "wall_seconds": wall, "tokens": _tokens(events), "cost": 0.0,
        "cost_source": "subscription", "final_text_path": "final.md" if final else None,
        "structured": structured, "schema_error": schema_error, "error": error,
        "codex_version": version,
        "settings": settings_record(spec, {"model": (spec.get("model") or {}).get("model"),
                                           "agent_profile": spec.get("agent_profile"),
                                           "sandbox": "danger-full-access",
                                           "codex_home": str(home)}),
    }
    return result, final or None


def usage(attempt_dir: Path) -> tuple[dict[str, int] | None, str | None]:
    """The usage the event log records."""
    from .cli_harness_executor import read_cli_events
    path = Path(attempt_dir) / "logs" / EVENT_LOG
    if not path.is_file():
        return None, f"codex event log is missing ({path})"
    return _tokens(read_cli_events(path, json.loads)), None


RULES = SignedInRules("codex", {"reasoning_effort": frozenset(
    {"minimal", "low", "medium", "high", "xhigh"})})


def agent_errors(where: str, agent: Any) -> list[str]:
    return signed_in_agent_errors(RULES, where, agent)


def resume_target(prior_result: Mapping[str, Any], attempt_dir: Path) -> str | None:
    """A codex retry starts a fresh conversation."""
    return None


def transcript(attempt_dir: Path, result: Mapping[str, Any],
               output: Path | None = None) -> tuple[Path | None, str | None]:
    """The runner's copy of the event stream, in `codex exec --json` shapes."""
    return signed_in_transcript(attempt_dir, EVENT_LOG)


def _entry(model: act.Activity, e: dict, at: float) -> None:
    kind = e.get("type")
    item = e.get("item") if isinstance(e.get("item"), dict) else {}
    itype = item.get("type")
    if kind == "turn.completed":
        usage = e.get("usage") or {}
        model.llm_calls += int(e.get("model_calls") or 1)
        model.tokens["input"] += act.int_of(usage.get("input_tokens"))
        model.tokens["output"] += act.int_of(usage.get("output_tokens"))
        model.tokens["cache_read"] += act.int_of(usage.get("cached_input_tokens"))
        model.tokens["reasoning"] += act.int_of(usage.get("reasoning_output_tokens"))
    elif kind in ("turn.failed", "error"):
        model.last_error = act.first_line((e.get("error") or {}).get("message")
                                          if kind == "turn.failed" else e.get("message"))
    elif itype == "agent_message" and kind == "item.completed":
        model.replied = True
        model.said(item.get("text"), at, "text")
    elif itype == "reasoning" and kind == "item.completed":
        model.replied = True
        model.said(item.get("text"), at, "thinking")
    elif itype in TOOL_CALL_ITEMS:
        model.replied = True
        name = {"command_execution": "shell", "file_change": "apply_patch",
                "web_search": "web_search"}.get(
                    itype, f"{item.get('server')}.{item.get('tool')}")
        if kind in ("item.started", "item.completed"):
            model.add_call(item.get("id"), at, name,
                           item.get("command") or item.get("arguments") or item.get("changes"))
        if kind == "item.completed":
            ok = (item.get("exit_code") in (0, None) if itype == "command_execution"
                  else item.get("status") != "failed")
            model.add_result(item.get("id"), at, ok,
                             item.get("aggregated_output") or item.get("status") or "")


def activity(attempt_dir: Path, *, now: float | None = None, running: bool = True,
             limit: int = act.DEFAULT_TOOL_CALLS) -> dict:
    return signed_in_activity(attempt_dir, "codex", EVENT_LOG, _entry, now=now,
                              running=running, limit=limit)


def _home_for(spec: Mapping[str, Any], out_dir: Path) -> Path:
    return out_dir / "codex-home" if spec.get("agent_profile") == "hermetic" else REAL_CODEX_HOME


def _recover(spec, out_dir, events, fallback):
    out_dir = Path(out_dir)
    return _record(spec, out_dir, events, error=fallback, wall=0.0,
                   home=_home_for(spec, out_dir), version="unknown")


def recover_result(spec_path: Path, out_dir: Path, fallback_error: str) -> dict[str, Any]:
    return recover_cli_result(spec_path, out_dir, fallback_error,
                              event_log_name=EVENT_LOG, parser=json.loads,
                              builder=_recover)


class CodexAdapter:
    name = "codex"
    event_log_name = EVENT_LOG
    stderr_log_name = "codex-stderr.log"

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
        extra = {}
        if spec.get("agent_profile") == "hermetic":
            extra["CODEX_HOME"] = str(write_hermetic_home(spec, out_dir))
        extra["PYTHONPATH"] = str(IMPORT_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
        return CliPreparedProcess(argv=tuple(build_command(spec, out_dir)),
                                  cwd=Path(str(spec["workspace"])), env=signed_in_env(extra),
                                  context={"home": _home_for(spec, out_dir)})

    def parse_event(self, line: str) -> Mapping[str, Any]:
        return json.loads(line)

    def on_event(self, spec, event, events) -> CliEventAction:
        calls = _call_events(event)
        if event.get("type") == "item.completed" and \
                (event.get("item") or {}).get("type") in TOOL_CALL_ITEMS:
            count = len(_items(events, TOOL_CALL_ITEMS))
            cap = int(spec.get("max_iterations") or 150)
            if count > cap:
                return CliEventAction(stop_error=f"max iterations {cap} exceeded", calls=calls)
            return CliEventAction(heartbeat={"tool_calls": count}, calls=calls)
        return CliEventAction(calls=calls)

    def build_result(self, outcome: CliRunOutcome):
        error = outcome.stop_error
        if not error and outcome.returncode and _error(outcome.events) is None:
            error = f"codex exited {outcome.returncode}"
        return _record(outcome.spec, outcome.out_dir, outcome.events, error=error,
                       wall=round(outcome.finished_at - outcome.started_at, 1),
                       home=outcome.prepared.context["home"],
                       version=version_of(codex_argv()))


def make_harness_executor():
    from .cli_harness_executor import CliHarnessExecutor
    return CliHarnessExecutor(name="codex", runner_module="ohflow.codex_runner",
                              recovery=recover_result,
                              checks=preflight)


def main(argv: list[str] | None = None) -> int:
    return runner_main(CodexAdapter, argv)


if __name__ == "__main__":
    raise SystemExit(main())
