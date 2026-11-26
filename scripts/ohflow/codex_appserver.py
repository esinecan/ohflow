"""Run one Codex turn over `codex app-server` and print it as `codex exec --json` lines.

The codex harness executor used `codex exec --json`, whose stream says nothing
while a command runs. `codex app-server` streams each command's output
(`item/commandExecution/outputDelta`). This shim speaks app-server JSON-RPC on
the server's stdin and prints the exec event shapes the runner already reads,
plus one new event:

    {"type": "item.output_delta", "item_id": "...", "delta": "..."}

so the process runtime, recovery, transcript and activity readers stay as they
were. It writes the final answer to `--final`, as `exec -o` did.

Measured 2026-10-10 (codex-cli 0.157.1, gpt-5.6-luna; ohflow M0 spike S3):

- `outputDelta` is new text only, about 0.4 s after the command prints.
- `turn/start` takes `outputSchema`. An early `phase: "commentary"` message can
  match the schema too, so the final answer is the `final_answer` message.
- No approval request arrived with `danger-full-access` and `never`. One that
  does arrive is accepted, as `exec` with those settings would.
- The shell yields to the model after 30 s while the command keeps running,
  and `turn/interrupt` leaves the command running. The runtime's tree kill
  ends such a command; this shim never relies on interrupt.

    python -m ohflow.codex_appserver --codex '<argv json>' --cwd <dir>
        --final <final.md> [--model M] [--effort E] [--schema F] --prompt TEXT
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

ITEM_TYPES = {"commandExecution": "command_execution", "fileChange": "file_change",
              "mcpToolCall": "mcp_tool_call", "webSearch": "web_search",
              "agentMessage": "agent_message", "reasoning": "reasoning",
              "userMessage": "user_message", "error": "error"}
FIELDS = {"aggregatedOutput": "aggregated_output", "exitCode": "exit_code",
          "durationMs": "duration_ms"}
USAGE = {"inputTokens": "input_tokens", "outputTokens": "output_tokens",
         "cachedInputTokens": "cached_input_tokens",
         "cacheWriteInputTokens": "cache_write_input_tokens",
         "reasoningOutputTokens": "reasoning_output_tokens"}
#: Seconds to wait for one JSON-RPC answer before the turn starts.
REQUEST_TIMEOUT_S = 120


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def exec_item(item: dict[str, Any]) -> dict[str, Any]:
    """An app-server item in the `codex exec --json` item shape."""
    out = {FIELDS.get(k, k): v for k, v in item.items()}
    out["type"] = ITEM_TYPES.get(str(item.get("type")), str(item.get("type")))
    if out["type"] == "reasoning" and "text" not in out:
        parts = [*(item.get("summary") or []), *(item.get("content") or [])]
        out["text"] = "\n".join(p if isinstance(p, str) else str((p or {}).get("text") or "")
                                for p in parts).strip()
    return out


class Server:
    """One `codex app-server` process and the JSON-RPC traffic with it."""

    def __init__(self, argv: list[str], cwd: str):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            [*argv, "app-server", "--listen", "stdio://"], cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=flags)
        self.next_id = 0
        self.pending: dict[int, queue.Queue] = {}
        self.events: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def send(self, msg: dict[str, Any]) -> None:
        with self.lock:
            assert self.proc.stdin is not None
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        rid = self.next_id
        answer: queue.Queue = queue.Queue()
        self.pending[rid] = answer
        self.send({"method": method, "id": rid, "params": params})
        msg = answer.get(timeout=REQUEST_TIMEOUT_S)
        if msg is None:
            raise RuntimeError(f"codex app-server exited during {method}")
        if msg.get("error"):
            raise RuntimeError(f"{method}: {json.dumps(msg['error'])}")
        return msg.get("result") or {}

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                answer = self.pending.pop(msg["id"], None)
                if answer is not None:
                    answer.put(msg)
            elif "id" in msg and "method" in msg:
                if "approval" in str(msg["method"]).lower():
                    self.send({"id": msg["id"], "result": {"decision": "accept"}})
                else:
                    self.send({"id": msg["id"], "error": {"code": -32601,
                                                          "message": "unsupported"}})
            else:
                self.events.put(msg)
        for answer in list(self.pending.values()):
            answer.put(None)
        self.events.put(None)

    def close(self) -> None:
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def run(args: argparse.Namespace) -> int:
    server = Server(json.loads(args.codex), args.cwd)
    try:
        return _turn(server, args)
    except Exception as exc:                     # noqa: BLE001 - reported as an event
        emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        return 1
    finally:
        server.close()


def _turn(server: Server, args: argparse.Namespace) -> int:
    server.request("initialize", {"clientInfo": {"name": "ohflow", "title": "ohflow",
                                                 "version": "1"}})
    server.send({"method": "initialized", "params": {}})
    thread_params: dict[str, Any] = {"cwd": args.cwd, "approvalPolicy": "never",
                                     "sandbox": "danger-full-access"}
    if args.model:
        thread_params["model"] = args.model
    thread = server.request("thread/start", thread_params)["thread"]["id"]
    emit({"type": "thread.started", "thread_id": thread})
    turn_params: dict[str, Any] = {
        "threadId": thread, "input": [{"type": "text", "text": args.prompt}],
        "cwd": args.cwd, "approvalPolicy": "never",
        "sandboxPolicy": {"type": "dangerFullAccess"}}
    if args.model:
        turn_params["model"] = args.model
    if args.effort:
        turn_params["effort"] = args.effort
    if args.schema:
        turn_params["outputSchema"] = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    server.request("turn/start", turn_params)

    usage: dict[str, Any] = {}
    model_calls = 0
    final: str | None = None
    last_message: str | None = None
    while True:
        msg = server.events.get()
        if msg is None:
            emit({"type": "error", "message": "codex app-server exited before turn/completed"})
            return 1
        method, params = msg.get("method"), msg.get("params") or {}
        if method == "turn/started":
            emit({"type": "turn.started"})
        elif method in ("item/started", "item/completed"):
            item = exec_item(params.get("item") or {})
            if item["type"] == "user_message":
                continue
            emit({"type": "item.started" if method == "item/started" else "item.completed",
                  "item": item})
            if method == "item/completed" and item["type"] == "agent_message":
                last_message = str(item.get("text") or "")
                if item.get("phase") == "final_answer":
                    final = last_message
        elif method == "item/commandExecution/outputDelta":
            emit({"type": "item.output_delta", "item_id": params.get("itemId"),
                  "delta": params.get("delta") or ""})
        elif method == "thread/tokenUsage/updated":
            model_calls += 1
            usage = (params.get("tokenUsage") or {}).get("total") or usage
        elif method == "error":
            err = params.get("error") or {}
            emit({"type": "error", "message": str(err.get("message") or json.dumps(params))})
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            for item in turn.get("items") or ():
                if item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
                    final = str(item.get("text") or "")
            text = final if final is not None else last_message
            if text and args.final:
                Path(args.final).write_text(text, encoding="utf-8")
            if turn.get("status") == "failed":
                message = str((turn.get("error") or {}).get("message") or "turn failed")
                emit({"type": "turn.failed", "error": {"message": message}})
                return 1
            emit({"type": "turn.completed", "model_calls": model_calls,
                  "status": turn.get("status"),
                  "usage": {USAGE[k]: int(v or 0) for k, v in usage.items() if k in USAGE}})
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ohflow.codex_appserver")
    parser.add_argument("--codex", required=True, help="JSON list: the codex argv prefix")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--final", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--schema", default="")
    parser.add_argument("--prompt", required=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
