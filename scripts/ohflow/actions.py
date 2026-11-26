"""`ohflow actions`: one attempt's model calls and the actions under them.

One call lists what an agent did: each model call with its tokens and latency,
and under it each action that call launched, with its duration and the first
line of its result. The rows let the orchestrating agent find the layer of a
failure; this module names no layer itself.

Rules this module keeps, and why:

* **Tokens attach to the model call, never to each action.** One response can
  launch several actions; copying its tokens onto each one counts them twice.
* **A figure a format does not record stays empty.** claude's stream records a
  message's output tokens as of its first block, so its per-call output count
  is wrong; the attempt total comes from the `result` record instead. codex
  records tokens once per turn and no time at all. A cloud CLI's messages
  arrive when its session settles, with the subscription's zero usage on
  claude-cloud, so a call keeps no tokens it was not told and the attempt
  total comes from the `pi_cloud_end` record.
* **Every call and action carries its evidence**: a path relative to the run
  directory, with a line number for a JSONL file.
* **The text is bounded.** Each line is at most `LINE_CAP` characters and the
  whole text at most `TEXT_CAP`; a cut keeps the newest calls.

The spec is `docs/history/orchestrator-visibility.md`, "Utility 3".
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Iterator

from . import activity as act
from . import dashboard_data as ohdata
from . import live, rundir
from .explain import _fit, resolve_step

__all__ = ["SCHEMA", "LINE_CAP", "TEXT_CAP", "actions_data", "render"]

SCHEMA = "ohflow.actions/1"
LINE_CAP = 300
TEXT_CAP = 8000

JOINS = {
    "pi": "assistant message.responseId; tool results by toolCallId",
    "claude": "assistant message.id; output tokens only in the result record",
    "codex": "none; codex records tokens once per turn",
    "pi-cloud": "message_end message.responseId; tool ends by toolCallId; "
                "a replayed event counts once",
    "codex-cloud": "message_end toolCall ids onto the tool executions that "
                   "ran first; a replayed event counts once",
    "claude-cloud": "message_end toolCall ids onto the tool executions that "
                    "ran first; tokens only in pi_cloud_end; a replayed event "
                    "counts once",
}
_SHELLS = frozenset({"bash", "shell", "terminal", "powershell"})


def actions_data(run_dir: Path, step: str, attempt: int | None = None,
                 now: float | None = None) -> dict | None:
    """The actions view of one attempt. None for a directory that is not a run.

    Raises `LookupError` with a one-line message when the step is missing or
    ambiguous, has no such attempt, is not an agent step, or left no transcript.
    """
    now = time.time() if now is None else float(now)
    run_dir = Path(run_dir)
    source = ohdata.open_source(run_dir)
    if source is None or source.kind != "run":
        return None
    coord = resolve_step(source, step)
    mine = [i for i in source.invocations(now) if i["coord"] == coord]
    if attempt is None:
        inv = max(mine, key=lambda i: i["attempt"]) if mine else None
    else:
        inv = next((i for i in mine if i["attempt"] == int(attempt)), None)
    if inv is None:
        tail = f" {int(attempt)}" if attempt is not None else ""
        raise LookupError(f"step {coord} has no recorded attempt{tail}")
    row = next(s for s in source.steps(now) if s["coord"] == coord)
    if row.get("kind") != "agent":
        raise LookupError(f"step {coord} is a {row.get('kind')} step; "
                          "it has no agent actions")
    harness = row.get("harness_executor")
    src = source.transcript_source(coord, inv["attempt"])
    if src.get("error"):
        raise LookupError(f"step {coord} attempt {inv['attempt']}: "
                          f"{src['error']}")
    reader = _READERS.get(harness)
    if reader is None:
        raise LookupError(f"step {coord}: no actions reader for harness "
                          f"executor {harness!r}")
    calls, unjoined, override, path = reader(run_dir, src)
    adir = rundir.attempt_dir(run_dir, coord, inv["attempt"])
    _finish(calls, act.worktree_root(adir), run_dir)
    view = {
        "schema": SCHEMA,
        "run": {"dir": str(run_dir), "status": source.run.status},
        "step": {"coord": coord, "id": row.get("id"),
                 "harness_executor": harness},
        "attempt": {"attempt": inv["attempt"], "status": inv["status"]},
        "source": {"path": path, "join": JOINS[harness],
                   "attempt_dir": ohdata._rel(run_dir, adir),
                   "unit": ("turn" if harness in ("codex", "codex-cloud")
                            else "model call")},
        "calls": calls,
        "totals": _totals(calls, override),
        "unjoined": unjoined,
    }
    return live._redact_tree(ohdata._cap_tree(view, ohdata.STRING_CAP))


# ------------------------------------------------------------ shared shapes


def _call(key: str | None, at: float | None, evidence: dict | None) -> dict:
    return {"n": 0, "key": key, "at": at, "latency_s": None, "tokens": None,
            "text": None, "error": None, "evidence": evidence, "actions": []}


def _action(tool: str, args: Any, at: float | None, evidence: dict,
            hint: str | None = None) -> dict:
    """An action row. `_finish` writes its summary once the root is known."""
    return {"tool": tool, "summary": None, "at": at, "duration_s": None,
            "ok": None, "first_line": None, "evidence": evidence,
            "result_evidence": None, "_args": act._trim_args(args),
            "_hint": hint}


_WRAPPED = re.compile(r"""^\s*(?:"[^"]*?(?:pwsh|powershell)(?:\.exe)?"|"""
                      r"\S*?(?:pwsh|powershell)(?:\.exe)?)\s+"
                      r"(?:-\w+\s+)*?-Command\s+(.*)$", re.I | re.S)


def _summary(tool: str, args: Any, hint: str | None, root: str | None,
             roots: list[tuple[str, str]]) -> str:
    """The dashboard's summary, with the shell command or file path first.

    A codex command arrives wrapped as `"...pwsh.exe" -Command "<command>"`
    with its backslashes doubled; the wrapper says nothing, so the inner
    command is shown. Paths are shortened before the summary is cut.
    """
    if hint:
        hint = _short(hint, roots)
    elif isinstance(args, dict):
        command = args.get("command")
        path = next((args[k] for k in ("file_path", "path", "notebook_path")
                     if isinstance(args.get(k), str)), None)
        if isinstance(command, str) and (str(tool).lower() in _SHELLS
                                         or path is None):
            m = _WRAPPED.match(command)
            if m:
                command = m.group(1).strip()
                if len(command) > 1 and command[0] == command[-1] == '"':
                    command = command[1:-1]
                command = command.replace("\\\\", "\\")
            hint = _short(act._strip_cd(command, root), roots)
        elif path is not None and str(tool) != "file_editor":
            hint = _short(act._rel(path, root), roots)
        else:
            args = {k: _short(v, roots) if isinstance(v, str) else v
                    for k, v in args.items()}
    return act._summarize({"name": tool, "args": args, "hint": hint}, root)


def _short(text: str | None, roots: list[tuple[str, str]]) -> str | None:
    """A path under the worktree or the run directory, written short."""
    if not text:
        return text
    for root, name in roots:
        back = root.replace("/", "\\")
        for form in {root, back, root.replace("\\", "/"),
                     back.replace("\\", "\\\\")}:
            text = re.sub(re.escape(form) + r"[\\/]?", name,
                          text, flags=re.I)
    return text


def _finish(calls: list[dict], root: str | None, run_dir: Path) -> None:
    roots = [(str(run_dir), "<run>/")]
    if root:
        roots.insert(0, (str(root), "./"))
    for c in calls:
        c["text"] = _short(c["text"], roots)
        for a in c["actions"]:
            a["summary"] = _summary(a["tool"], a.pop("_args"), a.pop("_hint"),
                                    root, roots)
            a["first_line"] = _short(a["first_line"], roots)


def _result(action: dict, at: float | None, ok: bool, text: Any,
            evidence: dict) -> None:
    if action["ok"] is not None:
        return
    action["ok"] = bool(ok)
    action["first_line"] = act.first_line(_text_of(text))
    action["result_evidence"] = evidence
    if at is not None and action["at"] is not None:
        action["duration_s"] = round(max(0.0, at - action["at"]), 1)


def _text_of(content: Any) -> str:
    if isinstance(content, list):
        return "\n".join(_text_of(c) for c in content)
    if isinstance(content, dict):
        inner = content.get("text", content.get("content"))
        return _text_of(inner) if inner is not None else ""
    return "" if content is None else str(content)


def _tokens(prompt: int | None, output: int | None, cache_read: int = 0,
            cache_write: int = 0, reasoning: int = 0) -> dict:
    return {"prompt": prompt, "output": output, "cache_read": cache_read,
            "cache_write": cache_write, "reasoning": reasoning}


def _said(call: dict, text: Any) -> None:
    if call["text"] is None:
        call["text"] = act.first_sentence(str(text or "")) or None


def _lines(path: Path, data: bytes | None = None) -> Iterator[tuple[int, dict]]:
    raw = data if data is not None else path.read_bytes()
    for n, line in enumerate(raw.splitlines(), 1):
        try:
            rec = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict):
            yield n, rec


def _number(calls: list[dict]) -> list[dict]:
    for n, c in enumerate(calls, 1):
        c["n"] = n
    return calls


def _totals(calls: list[dict], override: dict | None) -> dict:
    acts = [a for c in calls for a in c["actions"]]
    tokens, source = override, "the transcript's own total"
    if tokens is None:
        source = "the sum of the calls"
        known = [c["tokens"] for c in calls if c["tokens"]]
        tokens = None
        if known:
            tokens = {k: sum(t.get(k) or 0 for t in known)
                      for k in ("prompt", "output", "cache_read",
                                "cache_write", "reasoning")}
            if any(t.get("output") is None for t in known):
                tokens["output"] = None
    return {"calls": len(calls), "actions": len(acts),
            "failed": sum(1 for a in acts if a["ok"] is False),
            "pending": sum(1 for a in acts if a["ok"] is None),
            "tokens": tokens, "tokens_source": source}


def _ref(run_dir: Path, path: Path, line: int | None = None) -> dict:
    out = {"path": ohdata._rel(run_dir, path)}
    if line is not None:
        out["line"] = line
    return out


# -------------------------------------------------------------------- pi


def _read_pi(run_dir: Path, src: dict):
    path: Path = src["path"]
    calls: list[dict] = []
    pending: dict[str, dict] = {}
    for n, rec in _lines(path):
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        if rec.get("type") != "message":
            continue
        written = act.epoch(rec.get("timestamp"))
        where = _ref(run_dir, path, n)
        role = msg.get("role")
        if role == "assistant":
            began = act.epoch(msg.get("timestamp"))
            c = _call(msg.get("responseId"), began or written, where)
            if began is not None and written is not None:
                c["latency_s"] = round(max(0.0, written - began), 1)
            u = msg.get("usage")
            if isinstance(u, dict):
                read, write = act.int_of(u.get("cacheRead")), \
                    act.int_of(u.get("cacheWrite"))
                c["tokens"] = _tokens(act.int_of(u.get("input")) + read + write,
                                      act.int_of(u.get("output")), read, write,
                                      act.int_of(u.get("reasoning")))
            if msg.get("errorMessage"):
                c["error"] = str(msg["errorMessage"])
            for part in msg.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    _said(c, part.get("text"))
                elif part.get("type") == "toolCall":
                    a = _action(str(part.get("name") or "?"),
                                part.get("arguments"), written, where)
                    c["actions"].append(a)
                    pending[str(part.get("id"))] = a
            calls.append(c)
        elif role == "toolResult":
            a = pending.get(str(msg.get("toolCallId")))
            if a is not None:
                _result(a, written, not msg.get("isError"), msg.get("content"),
                        where)
    return _number(calls), [], None, ohdata._rel(run_dir, path)


# ---------------------------------------------------------------- claude


def _read_claude(run_dir: Path, src: dict):
    path: Path = src["path"]
    calls: dict[str, dict] = {}
    pending: dict[str, dict] = {}
    override = None
    for n, rec in _lines(path):
        kind = rec.get("type")
        at = act.epoch(rec.get("timestamp"))
        where = _ref(run_dir, path, n)
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        content = msg.get("content") if isinstance(msg.get("content"),
                                                   list) else []
        if kind == "assistant":
            if msg.get("model") == "<synthetic>":
                continue
            mid = str(msg.get("id") or f"no-id-{n}")
            c = calls.get(mid)
            if c is None:
                c = calls[mid] = _call(mid, at, where)
                u = msg.get("usage") or {}
                read = act.int_of(u.get("cache_read_input_tokens"))
                write = act.int_of(u.get("cache_creation_input_tokens"))
                c["tokens"] = _tokens(act.int_of(u.get("input_tokens"))
                                      + read + write, None, read, write)
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    _said(c, part.get("text"))
                elif part.get("type") == "tool_use":
                    a = _action(str(part.get("name") or "?"), part.get("input"),
                                at, where)
                    c["actions"].append(a)
                    pending[str(part.get("id"))] = a
        elif kind == "user":
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    a = pending.get(str(part.get("tool_use_id")))
                    if a is not None:
                        _result(a, at, not part.get("is_error"),
                                part.get("content"), where)
        elif kind == "result" and isinstance(rec.get("usage"), dict):
            u = rec["usage"]
            read = act.int_of(u.get("cache_read_input_tokens"))
            write = act.int_of(u.get("cache_creation_input_tokens"))
            override = _tokens(act.int_of(u.get("input_tokens")) + read + write,
                               act.int_of(u.get("output_tokens")), read, write)
    return _number(list(calls.values())), [], override, \
        ohdata._rel(run_dir, path)


# ----------------------------------------------------------------- codex


_CODEX_TOOLS = {"command_execution": "shell", "file_change": "apply_patch",
                "web_search": "web_search"}


def _read_codex(run_dir: Path, src: dict):
    path: Path = src["path"]
    turns: list[dict] = []
    pending: dict[str, dict] = {}

    def turn(where) -> dict:
        if not turns:
            turns.append(_call("turn 1", None, where))
        return turns[-1]

    for n, rec in _lines(path):
        kind = rec.get("type")
        item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
        itype = item.get("type")
        at = act.epoch(rec.get("timestamp"))
        where = _ref(run_dir, path, n)
        if kind == "turn.started":
            turns.append(_call(f"turn {len(turns) + 1}", at, where))
        elif kind == "turn.completed":
            t = turn(where)
            t["evidence"] = where
            u = rec.get("usage") or {}
            t["tokens"] = _tokens(act.int_of(u.get("input_tokens")),
                                  act.int_of(u.get("output_tokens")),
                                  act.int_of(u.get("cached_input_tokens")),
                                  act.int_of(u.get("cache_write_input_tokens")),
                                  act.int_of(u.get("reasoning_output_tokens")))
        elif kind in ("turn.failed", "error") and turns:
            err = rec.get("error") if isinstance(rec.get("error"), dict) else {}
            turns[-1]["error"] = str(err.get("message") or rec.get("message")
                                     or kind)
        elif not turns:
            # Configuration warnings before the first turn are not the agent's.
            continue
        elif kind == "item.completed" and itype == "agent_message":
            _said(turn(where), item.get("text"))
        elif itype in (None, "agent_message", "reasoning", "error"):
            continue
        elif kind == "item.started":
            name = _CODEX_TOOLS.get(itype, str(item.get("server") or itype))
            args = {"command": item["command"]} if item.get("command") else \
                (item.get("arguments") or item.get("changes") or {})
            a = _action(name, args, at, where)
            turn(where)["actions"].append(a)
            pending[str(item.get("id"))] = a
        elif kind == "item.completed":
            a = pending.get(str(item.get("id")))
            if a is None:
                name = _CODEX_TOOLS.get(itype, str(item.get("server") or itype))
                a = _action(name, {"command": item.get("command")}
                            if item.get("command") else {}, at, where)
                turn(where)["actions"].append(a)
            ok = (item.get("exit_code") in (0, None)
                  if itype == "command_execution"
                  else item.get("status") != "failed")
            _result(a, at, ok, item.get("aggregated_output")
                    or item.get("status"), where)
    return _number(turns), [], None, ohdata._rel(run_dir, path)


# -------------------------------------------------------------- pi-cloud


def _read_pi_cloud(run_dir: Path, src: dict):
    """The runner's copy of the Worker's event stream.

    A replayed event's `t` is the replay's clock, not the event's, so a
    replayed call takes its time from the message and a replayed action has
    no duration. The `pi_cloud_end` usage is the Worker's own total.
    """
    from . import pi_cloud_runner

    path: Path = src["path"]
    calls: list[dict] = []
    pending: dict[str, dict] = {}
    replays = pi_cloud_runner.Replays()
    override = None
    for n, rec in _lines(path):
        if not replays.first(rec):
            continue
        kind = rec.get("type")
        where = _ref(run_dir, path, n)
        at = None if rec.get("replayed") else act.epoch(rec.get("t"))
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        if kind == "message_end" and msg.get("role") == "assistant":
            began = act.epoch(msg.get("timestamp"))
            c = _call(msg.get("responseId"), began or at, where)
            if isinstance(msg.get("durationMs"), (int, float)):
                c["latency_s"] = round(max(0.0, msg["durationMs"] / 1000), 1)
            elif began is not None and at is not None:
                c["latency_s"] = round(max(0.0, at - began), 1)
            u = msg.get("usage")
            if isinstance(u, dict):
                read, write = act.int_of(u.get("cacheRead")), \
                    act.int_of(u.get("cacheWrite"))
                c["tokens"] = _tokens(act.int_of(u.get("input")) + read + write,
                                      act.int_of(u.get("output")), read, write,
                                      act.int_of(u.get("reasoning")))
            if msg.get("errorMessage"):
                c["error"] = str(msg["errorMessage"])
            for part in msg.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    _said(c, part.get("text"))
                elif part.get("type") == "toolCall":
                    a = _action(str(part.get("name") or "?"),
                                part.get("arguments"), None, where)
                    c["actions"].append(a)
                    pending[str(part.get("id"))] = a
            calls.append(c)
        elif kind == "tool_execution_start":
            cid = str(rec.get("toolCallId"))
            a = pending.get(cid)
            if a is None:
                if not calls:
                    calls.append(_call(None, at, where))
                a = _action(str(rec.get("toolName") or "?"), rec.get("args"),
                            at, where)
                calls[-1]["actions"].append(a)
                pending[cid] = a
            elif a["at"] is None:
                a["at"] = at
        elif kind == "tool_execution_end":
            a = pending.get(str(rec.get("toolCallId")))
            if a is not None:
                result = rec.get("result") if isinstance(rec.get("result"),
                                                         dict) else {}
                _result(a, at, not (rec.get("isError") or result.get("isError")),
                        result.get("content"), where)
        elif kind == "pi_cloud_error" and calls:
            calls[-1]["error"] = f"{rec.get('name')}: {rec.get('message')}"
        elif kind == "pi_cloud_end" and isinstance(rec.get("usage"), dict):
            models = rec["usage"].get("models")
            known = [u for u in (models or {}).values() if isinstance(u, dict)] \
                if isinstance(models, dict) else []
            if known:
                read = sum(act.int_of(u.get("cacheRead")) for u in known)
                write = sum(act.int_of(u.get("cacheWrite")) for u in known)
                override = _tokens(
                    sum(act.int_of(u.get("input")) for u in known) + read + write,
                    sum(act.int_of(u.get("output")) for u in known), read, write,
                    sum(act.int_of(u.get("reasoning")) for u in known))
    for c in calls:
        for a in c["actions"]:
            if a["at"] is None:
                a["at"] = c["at"]
    return _number(calls), [], override, ohdata._rel(run_dir, path)


# ------------------------------------------------------ the cloud CLIs


def _read_cli_cloud(run_dir: Path, src: dict):
    """The runner's copy of a cloud CLI's event stream.

    The stream is pi's event shapes in the CLI's own order: the tool
    executions arrive as they run, and the assistant messages arrive when
    the session settles, so a message claims the actions its toolCall ids
    already name and a tool no message claims keeps the call it started. A
    message's all-zero usage is the subscription's placeholder, so its call
    keeps empty tokens; the `pi_cloud_end` usage is the session's own total.
    """
    from . import pi_cloud_runner

    path: Path = src["path"]
    calls: list[dict] = []
    pending: dict[str, dict] = {}
    holder: dict[str, dict] = {}
    replays = pi_cloud_runner.Replays()
    override = None
    for n, rec in _lines(path):
        if not replays.first(rec):
            continue
        kind = rec.get("type")
        where = _ref(run_dir, path, n)
        at = None if rec.get("replayed") else act.epoch(rec.get("t"))
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        if kind == "message_end" and msg.get("role") == "assistant":
            began = act.epoch(msg.get("timestamp"))
            c = _call(msg.get("responseId"), began or at, where)
            if isinstance(msg.get("durationMs"), (int, float)):
                c["latency_s"] = round(max(0.0, msg["durationMs"] / 1000), 1)
            u = msg.get("usage")
            if isinstance(u, dict) and any(
                    act.int_of(u.get(k)) for k in
                    ("input", "output", "cacheRead", "cacheWrite",
                     "reasoning", "totalTokens")):
                read, write = act.int_of(u.get("cacheRead")), \
                    act.int_of(u.get("cacheWrite"))
                c["tokens"] = _tokens(act.int_of(u.get("input")) + read + write,
                                      act.int_of(u.get("output")), read, write,
                                      act.int_of(u.get("reasoning")))
            if msg.get("errorMessage"):
                c["error"] = str(msg["errorMessage"])
            for part in msg.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    _said(c, part.get("text"))
                elif part.get("type") == "toolCall":
                    cid = str(part.get("id"))
                    a = pending.get(cid)
                    if a is None:
                        a = _action(str(part.get("name") or "?"),
                                    part.get("arguments"), None, where)
                        pending[cid] = a
                    else:
                        home = holder.get(cid)
                        if home is not None and home is not c:
                            home["actions"].remove(a)
                    c["actions"].append(a)
                    holder[cid] = c
            calls.append(c)
        elif kind == "tool_execution_start":
            cid = str(rec.get("toolCallId"))
            a = pending.get(cid)
            if a is None:
                if not calls:
                    calls.append(_call(None, at, where))
                a = _action(str(rec.get("toolName") or "?"), rec.get("args"),
                            at, where)
                calls[-1]["actions"].append(a)
                pending[cid] = a
                holder[cid] = calls[-1]
            elif a["at"] is None:
                a["at"] = at
        elif kind == "tool_execution_end":
            a = pending.get(str(rec.get("toolCallId")))
            if a is not None:
                result = rec.get("result") if isinstance(rec.get("result"),
                                                         dict) else {}
                _result(a, at, not (rec.get("isError") or result.get("isError")),
                        result.get("content"), where)
        elif kind == "pi_cloud_error" and calls:
            calls[-1]["error"] = f"{rec.get('name')}: {rec.get('message')}"
        elif kind == "pi_cloud_end" and isinstance(rec.get("usage"), dict):
            u = rec["usage"]
            read, write = act.int_of(u.get("cacheRead")), \
                act.int_of(u.get("cacheWrite"))
            override = _tokens(act.int_of(u.get("input")) + read + write,
                               act.int_of(u.get("output")), read, write,
                               act.int_of(u.get("reasoning")))
    for c in calls:
        for a in c["actions"]:
            if a["at"] is None:
                a["at"] = c["at"]
    calls = [c for c in calls
             if c["actions"] or c["text"] or c["tokens"] or c["error"]]
    return _number(calls), [], override, ohdata._rel(run_dir, path)


_READERS = {"pi": _read_pi, "claude": _read_claude, "codex": _read_codex,
            "pi-cloud": _read_pi_cloud, "codex-cloud": _read_cli_cloud,
            "claude-cloud": _read_cli_cloud}


# ------------------------------------------------------------------ text


def _n(value) -> str:
    return "-" if value is None else str(value)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _head(view: dict) -> str:
    t = view["totals"]
    unit = view["source"]["unit"]
    tok = t.get("tokens")
    tokens = (f"tokens in {_n(tok.get('prompt'))} out {_n(tok.get('output'))}"
              if tok else "tokens not recorded")
    return _fit(f"ACTIONS {view['step']['coord']} attempt "
                f"{view['attempt']['attempt']}: {_plural(t['calls'], unit)}, "
                f"{_plural(t['actions'], 'action')}, {t['failed']} failed; "
                f"{tokens} ({view['step']['harness_executor']})")


def _in(text: str, suffix: str = "") -> str:
    """An indented line under a call; the evidence suffix is never cut."""
    tail = f" · {suffix}" if suffix else ""
    return "  " + act.one_line(str(text), max(20, LINE_CAP - 2 - len(tail)))         + tail


def _at(evidence: dict | None) -> str:
    """An evidence pointer in the file the source line names: `line N`, or the
    file name."""
    if not isinstance(evidence, dict) or not evidence.get("path"):
        return ""
    if evidence.get("line"):
        return f"line {evidence['line']}"
    return str(evidence["path"]).rsplit("/", 1)[-1]


def _call_lines(c: dict, label: str) -> list[str]:
    tok = c.get("tokens") or {}
    lat = "-" if c.get("latency_s") is None else f"{c['latency_s']:.1f}"
    lines = [_fit(f"{label} {c['n']} {act.hms(c.get('at')) or '-'} · "
                  f"in {_n(tok.get('prompt'))} out {_n(tok.get('output'))} · "
                  f"{lat} s · {_plural(len(c['actions']), 'action')}",
                  _at(c.get("evidence")))]
    if c.get("text"):
        lines.append(_in(f"said: {c['text']}"))
    if c.get("error"):
        lines.append(_in(f"error: {c['error']}"))
    for a in c["actions"]:
        state = ("pending" if a["ok"] is None else
                 "ok" if a["ok"] else "failed")
        dur = "-" if a.get("duration_s") is None else f"{a['duration_s']:.1f}"
        first = f": {a['first_line']}" if a.get("first_line") else ""
        lines.append(_in(f"{a['tool']} {a['summary']} -> {state} "
                         f"({dur} s){first}",
                         _at(a.get("result_evidence") or a.get("evidence"))))
    return lines


def render(view: dict) -> list[str]:
    """The text lines of one actions view, at most TEXT_CAP characters."""
    label = "turn" if view["source"]["unit"] == "turn" else "call"
    head = [_head(view),
            _fit(f"source: {view['source']['path']} · join: "
                 f"{view['source']['join']}")]
    blocks = [_call_lines(c, label) for c in view["calls"]]
    total = len("\n".join(head + [ln for b in blocks for ln in b]))
    if total <= TEXT_CAP:
        return head + [ln for b in blocks for ln in b]
    kept: list[list[str]] = []
    size = len("\n".join(head)) + 80
    for block in reversed(blocks):
        need = len("\n".join(block)) + 1
        if size + need > TEXT_CAP:
            break
        kept.insert(0, block)
        size += need
    cut = (f"... {len(blocks) - len(kept)} earlier {label}s not shown; "
           f"--json carries every {label}")
    return head + [cut] + [ln for b in kept for ln in b]
