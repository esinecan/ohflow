"""Stand-in for `claude -p --output-format stream-json --verbose`.

`logged-out` replays the real 2026-09-30 stream of a logged-out CLI verbatim.
The other scenarios are built on the real init event from that stream.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import FIXTURES, SCENARIO, arg, emit, replay, spawn_grandchild  # noqa: E402

args = sys.argv[1:]
if "auth" in args and "status" in args:
    print(json.dumps({"loggedIn": SCENARIO != "logged-out", "authMethod": "claude.ai"}))
    raise SystemExit(0)
if "--version" in args:
    print("2.1.281 (Claude Code)")
    raise SystemExit(0)
state = os.environ.get("OHFLOW_FAKE_SIGNED_IN_STATE")
if state:
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "argv.json"), "w", encoding="utf-8") as fh:
        json.dump(args, fh)
    with open(os.path.join(state, "argv-history.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args) + "\n")
    with open(os.path.join(state, "env.json"), "w", encoding="utf-8") as fh:
        json.dump(sorted(k for k in os.environ if k.startswith(("CLAUDE", "ANTHROPIC_BASE"))), fh)

session = arg(args, "--session-id", "fake-session")
real = FIXTURES / "claude" / "l0-logged-out.jsonl"
init = json.loads(real.read_text(encoding="utf-8").splitlines()[0])
init["session_id"] = session
init["tools"] = ["Bash", "Read", "Edit", "Write", "mcp__forum__post", "mcp__forum__poll"]
init["mcp_servers"] = [{"name": "forum", "status": "connected"},
                       {"name": "cortex", "status": "pending"}]


def assistant(mid, content):
    emit({"type": "assistant", "session_id": session,
          "message": {"id": mid, "model": "claude-haiku-4-5-20251001", "role": "assistant",
                      "content": content,
                      "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
                                "cache_read_input_tokens": 20, "output_tokens": 7}}})


def tool_round(n):
    assistant(f"msg_{n}", [{"type": "tool_use", "id": f"tu_{n}", "name": "Bash",
                            "input": {"command": "git status"}}])
    emit({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"tu_{n}", "content": "clean",
         "is_error": n == 1 and SCENARIO == "schema"}]}})


def result(text, structured=None):
    event = {"type": "result", "subtype": "success", "is_error": False, "result": text,
             "session_id": session, "num_turns": 2, "total_cost_usd": 0.0042,
             "usage": {"input_tokens": 20, "cache_creation_input_tokens": 10,
                       "cache_read_input_tokens": 40, "output_tokens": 14,
                       "output_tokens_details": {"thinking_tokens": 3}}}
    if structured is not None:
        event["structured_output"] = structured
    emit(event)


if SCENARIO == "logged-out":
    replay(real)
    raise SystemExit(1)
emit(init)
if SCENARIO == "success":
    tool_round(1)
    assistant("msg_2", [{"type": "text", "text": "DONE"}])
    result("DONE")
elif SCENARIO == "schema":
    tool_round(1)
    assistant("msg_2", [{"type": "text", "text": '{"answer":"ok","count":2}'}])
    result('{"answer":"ok","count":2}', structured={"answer": "ok", "count": 2})
elif SCENARIO in ("structured-then-prose", "structured-invalid-later"):
    tool_round(1)
    valid = {"answer": "ok", "count": 2}
    calls = [valid, {"answer": "ok", "count": "two"}] \
        if SCENARIO == "structured-invalid-later" else [valid]
    for n, value in enumerate(calls, start=2):
        assistant(f"msg_{n}", [{"type": "tool_use", "id": f"so_{n}",
                                "name": "StructuredOutput", "input": value}])
        failed = value is not valid
        emit({"type": "user", "parent_tool_use_id": None, "message": {
            "role": "user", "content": [{
                "type": "tool_result", "tool_use_id": f"so_{n}", "is_error": failed,
                "content": "Output does not match required schema: /count must be integer"
                if failed else "Structured output provided successfully"}]}})
    result(json.dumps(valid), structured=valid)
    emit({"type": "assistant", "session_id": session, "parent_tool_use_id": "tu_sub",
          "message": {"id": "msg_sub", "model": "claude-haiku-4-5-20251001",
                      "role": "assistant",
                      "content": [{"type": "tool_use", "id": "so_sub",
                                   "name": "StructuredOutput",
                                   "input": {"answer": "subagent", "count": 9}}],
                      "usage": {"input_tokens": 1, "output_tokens": 1}}})
    assistant("msg_9", [{"type": "text", "text": "All readers reported. The report stands."}])
    result("All readers reported. The report stands.")
elif SCENARIO == "tool-loop":
    for n in range(1, 50):
        tool_round(n)
        time.sleep(0.02)
    result("never")
elif SCENARIO == "slow":
    time.sleep(60)
elif SCENARIO == "torn-tail":
    tool_round(1)
    sys.stdout.write('{"type":"assistant","message":')
    sys.stdout.flush()
    time.sleep(60)
elif SCENARIO == "grandchild":
    spawn_grandchild()
