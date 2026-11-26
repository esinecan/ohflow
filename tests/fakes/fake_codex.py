"""Stand-in for `codex app-server --listen stdio://`.

It answers the JSON-RPC handshake, then plays each scenario's events as
app-server notifications. `success` and `refused` translate the real
`codex exec --json` streams of 2026-09-30 (codex-cli 0.157.1, gpt-5.6-luna)
into the app-server shapes measured on 2026-10-10 (ohflow M0 spike S3), so
`ohflow.codex_appserver` must turn them back into the same exec events.
`OHFLOW_FAKE_SIGNED_IN_STATE` receives `argv.json`, `codex_home.txt` and
`requests.jsonl` (every request the client sent).
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _common import FIXTURES, SCENARIO, emit, spawn_grandchild  # noqa: E402

args = sys.argv[1:]
if "--version" in args:
    print("codex-cli 0.157.1")
    raise SystemExit(0)
state = os.environ.get("OHFLOW_FAKE_SIGNED_IN_STATE")
if state:
    os.makedirs(state, exist_ok=True)
    Path(state, "argv.json").write_text(json.dumps(args), encoding="utf-8")
    Path(state, "codex_home.txt").write_text(os.environ.get("CODEX_HOME", ""), encoding="utf-8")

THREAD = "fake-thread"
CAMEL = {"command_execution": "commandExecution", "file_change": "fileChange",
         "mcp_tool_call": "mcpToolCall", "web_search": "webSearch",
         "agent_message": "agentMessage", "reasoning": "reasoning", "error": "error"}
FIELDS = {"aggregated_output": "aggregatedOutput", "exit_code": "exitCode"}
USAGE = {"input_tokens": "inputTokens", "output_tokens": "outputTokens",
         "cached_input_tokens": "cachedInputTokens",
         "cache_write_input_tokens": "cacheWriteInputTokens",
         "reasoning_output_tokens": "reasoningOutputTokens"}


def note(method, params):
    emit({"method": method, "params": params})


def item(e):
    raw = e.get("item") or {}
    out = {FIELDS.get(k, k): v for k, v in raw.items()}
    out["type"] = CAMEL.get(raw.get("type"), raw.get("type"))
    return out


def play(events):
    """Exec events as app-server notifications. The last agent message is final."""
    messages = [i for i, e in enumerate(events) if e.get("type") == "item.completed"
                and (e.get("item") or {}).get("type") == "agent_message"]
    for i, e in enumerate(events):
        kind = e.get("type")
        if kind == "turn.started":
            note("turn/started", {"threadId": THREAD, "turn": {"id": "t1"}})
        elif kind in ("item.started", "item.completed"):
            it = item(e)
            if it["type"] == "agentMessage":
                it["phase"] = "final_answer" if messages and i == messages[-1] else "commentary"
            note("item/started" if kind == "item.started" else "item/completed",
                 {"threadId": THREAD, "item": it})
        elif kind == "turn.completed":
            total = {USAGE[k]: v for k, v in (e.get("usage") or {}).items() if k in USAGE}
            note("thread/tokenUsage/updated", {"threadId": THREAD,
                                               "tokenUsage": {"total": total, "last": total}})
            note("turn/completed", {"threadId": THREAD,
                                    "turn": {"id": "t1", "status": "completed", "items": []}})
        elif kind == "turn.failed":
            note("turn/completed", {"threadId": THREAD, "turn": {
                "id": "t1", "status": "failed", "error": e.get("error") or {}}})
        elif kind == "error":
            note("error", {"error": {"message": e.get("message")}})


def exec_events(name):
    path = FIXTURES / "codex" / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def scenario_events():
    if SCENARIO == "success":
        return [e for e in exec_events("l0-rollcall.jsonl") if e.get("type") != "thread.started"]
    if SCENARIO == "refused":
        return [e for e in exec_events("l0-model-refused.jsonl")
                if e.get("type") != "thread.started"]
    if SCENARIO == "schema":
        text = '{"answer":"ok","count":2}'
        return [
            {"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                                "command": "git status", "exit_code": 1,
                                                "aggregated_output": "boom", "status": "failed"}},
            {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": text}},
            {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 60,
                                                "output_tokens": 9, "reasoning_output_tokens": 4}},
        ]
    return []


def respond(msg, result):
    emit({"id": msg["id"], "result": result})


for raw in sys.stdin:
    try:
        msg = json.loads(raw)
    except ValueError:
        continue
    if state:
        with Path(state, "requests.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg) + "\n")
    method = msg.get("method")
    if method == "initialize":
        if SCENARIO == "slow":
            time.sleep(60)
        respond(msg, {"userAgent": "fake"})
    elif method == "thread/start":
        fixture = {"success": "l0-rollcall.jsonl",
                   "refused": "l0-model-refused.jsonl"}.get(SCENARIO)
        started = [e for e in exec_events(fixture) if e.get("type") == "thread.started"] \
            if fixture else []
        THREAD = started[0]["thread_id"] if started else THREAD
        respond(msg, {"thread": {"id": THREAD}})
    elif method == "turn/start":
        respond(msg, {"turn": {"id": "t1"}})
        if SCENARIO == "tool-loop":
            for n in range(50):
                note("item/completed", {"threadId": THREAD, "item": {
                    "id": f"c{n}", "type": "commandExecution", "command": "ls", "exitCode": 0}})
                time.sleep(0.02)
        elif SCENARIO == "grandchild":
            spawn_grandchild()
        elif SCENARIO == "output":
            note("item/started", {"threadId": THREAD, "item": {
                "id": "x1", "type": "commandExecution", "command": "pytest"}})
            for n in range(3):
                note("item/commandExecution/outputDelta",
                     {"threadId": THREAD, "itemId": "x1", "delta": f"line {n}\n"})
            note("item/completed", {"threadId": THREAD, "item": {
                "id": "x1", "type": "commandExecution", "command": "pytest", "exitCode": 0,
                "aggregatedOutput": "line 0\nline 1\nline 2\n"}})
            note("item/completed", {"threadId": THREAD, "item": {
                "id": "m1", "type": "agentMessage", "text": "done", "phase": "final_answer"}})
            note("turn/completed", {"threadId": THREAD,
                                    "turn": {"id": "t1", "status": "completed", "items": []}})
        else:
            play(scenario_events())
            if SCENARIO == "refused":
                raise SystemExit(1)
