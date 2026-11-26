"""A fake pi-cloud Worker: one Durable Object per attempt key, in-process.

An importable `FakeWorker` (unlike the fake CLIs, which run as child
processes) because the Worker serves HTTP: a `ThreadingHTTPServer` on
`127.0.0.1:0` that a test starts, points `OHFLOW_PI_CLOUD_URL` at and stops
in its cleanup. It replays the recordings taken from the real Worker on
2026-10-26 (`tests/fixtures/pi_cloud`), rewriting each `pi_cloud_start` and
`pi_cloud_end` line with the attempt's own key, branch, start commit and
pushed head.

Routes, all needing `Authorization: Bearer <token>` and `User-Agent:
ohflow-pi-cloud/1`:

- `POST /attempts/<name>/step`  the first post answers `accepted: true`, a
  repeat with the same operation id `accepted: false, reattach: true`, and
  another operation id on the same object 409.
- `GET /attempts/<name>/events?operationId=<op>`  the NDJSON stream, chosen
  by the per-key plan below.
- `POST /attempts/<name>/abort`  `{"operationId", "aborted": true, "container",
  "last_look"}`, where `last_look` is `worker.last_look` (None is a container
  that was not running; `worker.sends_last_look = False` is a Worker from
  before the look, whose answer has no such field). Under `/claude` and
  `/codex` the answer also carries `usage`, the tokens the object had counted
  (`worker.abort_usage`, None for an object that counted none).
  `worker.abort_fails = True` answers 500.
- `GET /attempts/<name>/transcript`, `GET /attempts/<name>/out/handover.md`
  the two text routes; every other `out/<file>` 404.
- `GET /`  404 with both headers, 401 without them.

The events answer comes from a per-key plan. `worker.plan(key, post,
behaviours)` names the behaviours of the connections that follow the `post`-th
`step` post of `key`, one entry per connection, the last repeating; a key and
post with no plan takes `worker.default_plan` (`["success"]`). A behaviour
is a name from the list below, or a dict
`{"hold_s": 3, "beat_s": 0.5, "prefix": "cut-first", "then": "single"}`:
serve the `prefix` recording's lines (the start line alone when no `prefix`
is named), then beats every `beat_s` (default `BEAT_S`) for `hold_s` seconds,
then close the stream - or serve the `then` recording's lines on the same
stream instead of closing. Every beat written is logged in `worker.beats` as
`{"key", "at"}`, because a beat is a line the client reads but never prints,
and this behaviour is how a test serves a stream that stays quiet-but-healthy
longer than the client's lost bound, in seconds. The behaviours:

- `success`   `single-events.ndjson` rewritten; before its end line, clone the
  step's branch from the test's bare origin, commit one file, push it and
  name that sha as the end's `head` (the commit is cached per key, so a
  reattach answers the same head).
- `cut-first` / `cut-second`  the dropped first connection (six lines, close)
  and the reconnected second (the replay with `"replayed": true`, the live
  continuation, `done`), `cut-second` with the same commit as `success`.
  `worker.CUT` is the pair.
- `settled`   `replay-events.ndjson` rewritten: a request after the operation
  settled, everything replayed, the end at once.
- `refuse`    close the events connection at once, before any HTTP response:
  what a dropped Worker looks like to the client.
- `silent`    the start line and the replay, then only beats until the client
  goes away: what a stalled agent looks like. Under `/claude` and `/codex`
  the replay holds the tool calls and no `message_end`, because a Claude Code
  or Codex object sends its messages and their token usage only when the
  operation settles.
- `aborted`   `aborted-events.ndjson`: the operation settles `unanswered`.
- `unauthorized`  answer 401.
- `pushfail`  the end line with `pushed: false` and a `push_error`.
- `clonefail` the end line with `pushed: false` and a `push_error` that names
  `clone_failed`: what a box that could not clone the start commit sends.
- `loop`      an agent that calls a tool every turn. With `worker.enforces_limit`
  (the default, the deployed Worker) the step answer echoes the posted
  `max_iterations`, and the stream ends `unanswered`, `turn_limit` after that
  many rounds. Without it the answer names no limit, and the stream serves
  `worker.loop_rounds` rounds and then only beats.

The worker records every request as `(method, path, body, auth, user agent)`.
`auth` is whether the headers matched, never the token value, which stays in
the `Authorization` header and out of every artifact a test can read. It also
records, for each `step` post, whether the transport branch was already at
the posted `start_sha` on the test's origin at that moment (R1: the push
precedes the post) and every `abort` it was asked for.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pi_cloud"
WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
USER_AGENT = "ohflow-pi-cloud/1"

#: Seconds between the beats of a `silent` stream. The real Worker beats every
#: 15 s; the client never prints a beat, so a faster fake only shortens tests.
BEAT_S = 0.5

#: The dropped-then-reconnected stream of one step, as one plan.
CUT = ["cut-first", "cut-second"]


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=fake pi-cloud worker",
         "-c", "user.email=worker@pi-cloud.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=WINDOW)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} exited {done.returncode}: "
                           f"{(done.stderr or done.stdout)[-300:]}")
    return done.stdout.strip()


def _fixture_lines(name: str) -> list[dict]:
    out = []
    for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


class FakeWorker:
    """The Worker's routes over one test's bare origin."""

    def __init__(self, origin: Path, root: Path, token: str = "pi-cloud-test-token"):
        self.origin = Path(origin)
        self.root = Path(root)
        self.token = token
        self.default_plan = ["success"]
        self.enforces_limit = True
        self.loop_rounds = 12
        #: (key, post) -> behaviour names or hold dicts, one per connection,
        #: last repeating.
        self.plans: dict[tuple[str, int], list] = {}
        #: Every request as (method, path, body, auth ok, user agent).
        self.requests: list[dict] = []
        #: Every beat written, as {"key", "at"}: the lines the client reads
        #: but never prints.
        self.beats: list[dict] = []
        #: key -> the answer of each step post, in order.
        self.step_answers: dict[str, list[dict]] = {}
        #: key -> {branch, on_origin} observed when the step post arrived.
        self.transport_at_step: dict[str, dict] = {}
        #: The keys `POST abort` named, in order.
        self.aborted: list[str] = []
        self.last_look: dict | None = dict(LAST_LOOK)
        self.sends_last_look = True
        self.abort_usage: dict | None = dict(ABORT_USAGE)
        self.abort_fails = False
        #: (key, post) -> connections served; post counts the step posts.
        self._conns: dict[tuple[str, int], int] = {}
        self._steps: dict[str, list[dict]] = {}
        self._head: dict[str, str] = {}
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    # ------------------------------------------------------------- the plan

    def plan(self, key: str, post: int, behaviours: list) -> None:
        self.plans[(key, post)] = list(behaviours)

    # ------------------------------------------------------------- lifecycle

    def start(self) -> "FakeWorker":
        worker = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                pass

            def _authorized(self) -> bool:
                return (self.headers.get("Authorization")
                        == f"Bearer {worker.token}"
                        and self.headers.get("User-Agent") == USER_AGENT)

            def _record(self, method: str, body=None) -> bool:
                ok = self._authorized()
                worker.requests.append({
                    "method": method, "path": self.path,
                    "body": body, "auth": ok,
                    "user_agent": self.headers.get("User-Agent")})
                return ok

            def _reply(self, code: int, payload) -> None:
                data = (payload if isinstance(payload, bytes)
                        else json.dumps(payload).encode("utf-8"))
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                try:
                    self._post()
                except (OSError, ValueError):
                    # The client went away mid-answer; the response ends where
                    # the test's plan cut it, which is what was asked for.
                    pass

            def _post(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    body = {"raw": raw.decode("utf-8", "replace")}
                key, action = worker.split_path(self.path)
                if not self._record("POST", body):
                    self._reply(401, {"error": "unauthorized"})
                    return
                if action == "step":
                    self._step(key, body)
                elif action == "abort":
                    with worker._lock:
                        worker.aborted.append(key)
                    if worker.abort_fails:
                        self._reply(500, {"error": "the object is gone"})
                        return
                    answer = {"operationId": body.get("operationId"),
                              "aborted": True,
                              "container": fake_container(key, ABORT_SECONDS)}
                    if worker.sends_last_look:
                        answer["last_look"] = (dict(worker.last_look)
                                               if worker.last_look else None)
                    if re.match(r"^/(claude|codex)/", self.path):
                        answer["usage"] = (dict(worker.abort_usage)
                                           if worker.abort_usage else None)
                    self._reply(200, answer)
                else:
                    self._reply(404, {"error": "no such route"})

            def _step(self, key, body):
                if not key:
                    self._reply(400, {"error": "no attempt name"})
                    return
                if not isinstance(body, dict) or not body.get("operationId"):
                    self._reply(400, {"error": "no operationId"})
                    return
                with worker._lock:
                    prior = worker._steps.get(key) or []
                    if any(p.get("operationId") != body.get("operationId")
                           for p in prior):
                        self._reply(409, {"error": "another operation runs on "
                                                   "this attempt"})
                        return
                    repeat = bool(prior)
                    prior.append(dict(body))
                    worker._steps[key] = prior
                # R1's evidence: the branch the runner names must already sit
                # at the posted start commit when the post arrives.
                branch = str(body.get("branch") or "")
                on_origin = ""
                if branch:
                    listed = git("ls-remote", str(worker.origin),
                                 f"refs/heads/{branch}")
                    on_origin = listed.split()[0] if listed else ""
                with worker._lock:
                    worker.transport_at_step[key] = {
                        "branch": branch, "on_origin": on_origin,
                        "start_sha": str(body.get("start_sha") or "")}
                fixture = ("step-reattach-answer.json" if repeat
                           else "step-answer.json")
                answer = json.loads((FIXTURES / fixture).read_text(
                    encoding="utf-8"))
                answer.update(operationId=body.get("operationId"),
                              branch=branch,
                              start_sha=body.get("start_sha"))
                if body.get("model"):
                    answer["model"] = body["model"]
                if "thinking" in body:
                    answer["thinking"] = body["thinking"]
                if worker.enforces_limit:
                    answer["max_iterations"] = prior[0].get("max_iterations")
                with worker._lock:
                    worker.step_answers.setdefault(key, []).append(answer)
                self._reply(200, answer)

            def do_GET(self):
                try:
                    self._get()
                except (OSError, ValueError):
                    pass

            def _get(self):
                path = urlparse(self.path).path
                key, action = worker.split_path(self.path)
                if not key and path.rstrip("/") == "":
                    if not self._record("GET"):
                        self._reply(401, {"error": "unauthorized"})
                        return
                    # The Worker's own root route: 404 with both headers.
                    self._reply(404, {"error": "no such route"})
                    return
                if not self._record("GET"):
                    self._reply(401, {"error": "unauthorized"})
                    return
                if action == "events":
                    self._events(key, parse_qs(urlparse(self.path).query))
                    return
                if action == "transcript":
                    self._text(200, (FIXTURES / "transcript.md").read_text(
                        encoding="utf-8"))
                    return
                if action == "out/handover.md":
                    self._text(200, (FIXTURES / "handover.md").read_text(
                        encoding="utf-8"))
                    return
                self._reply(404, {"error": "no such route"})

            def _text(self, code: int, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            # ------------------------------------------------------- events

            def _events(self, key, query):
                behaviour = worker.behaviour_for(key, query)
                if isinstance(behaviour, dict):
                    self._hold(key, behaviour)
                    return
                if behaviour == "refuse":
                    # No HTTP response at all: the connection drops before
                    # one, so the client counts no successful connection.
                    self.connection.close()
                    return
                if behaviour == "unauthorized":
                    self._reply(401, {"error": "unauthorized"})
                    return
                if behaviour == "silent":
                    step = worker.step_body(key)
                    lines = _rewritten("single-events.ndjson", step, worker,
                                       stop_before_end=True, replayed=True)
                    if re.match(r"^/(claude|codex)/", self.path):
                        lines = [record for record in lines
                                 if record.get("type") != "message_end"]
                    self._stream(lines, beats=True)
                    return
                if behaviour == "aborted":
                    step = worker.step_body(key)
                    self._stream(_rewritten("aborted-events.ndjson", step,
                                            worker))
                    return
                if behaviour == "loop":
                    step = worker.step_body(key)
                    limit = step.get("max_iterations") if worker.enforces_limit else None
                    rounds = limit or worker.loop_rounds
                    lines = _loop_lines(step, worker, rounds,
                                        ended=bool(limit))
                    self._stream(lines, beats=not limit)
                    return
                if behaviour in ("pushfail", "clonefail"):
                    step = worker.step_body(key)
                    lines = _rewritten("single-events.ndjson", step, worker,
                                       push=False)
                    for record in lines:
                        if record.get("type") == "pi_cloud_end":
                            record.update(
                                pushed=False,
                                push_error=("origin refused the push"
                                            if behaviour == "pushfail" else
                                            "clone_failed: repository not found"))
                    self._stream(lines)
                    return
                if behaviour == "cut-first":
                    step = worker.step_body(key)
                    self._stream(_rewritten("cut-first.ndjson", step, worker))
                    return
                if behaviour in ("cut-second", "success", "settled"):
                    step = worker.step_body(key)
                    if step:
                        worker.head_for(key, step)
                    name = {"cut-second": "cut-second.ndjson",
                            "settled": "replay-events.ndjson",
                            "success": "single-events.ndjson"}[behaviour]
                    self._stream(_rewritten(name, step, worker))
                    return
                self._reply(500, {"error": f"unknown behaviour {behaviour!r}"})

            def _hold(self, key, plan):
                """One response: a prefix, then beats for a while, then a
                close (or a named recording served on, on the same stream)."""
                step = worker.step_body(key)
                prefix = plan.get("prefix")
                lines = (_rewritten(f"{prefix}.ndjson", step, worker) if prefix
                         else _rewritten("single-events.ndjson", step,
                                         worker)[:1])
                self._stream_open()
                for record in lines:
                    self._send_line(record)
                self._beats(float(plan.get("hold_s") or 0),
                            float(plan.get("beat_s") or BEAT_S), key=key)
                then = plan.get("then")
                if then:
                    for record in _rewritten(f"{then}.ndjson", step, worker):
                        self._send_line(record)

            def _stream(self, lines: list[dict], beats: bool = False) -> None:
                self._stream_open()
                for record in lines:
                    self._send_line(record)
                if beats:
                    self._beats(None, BEAT_S)

            def _stream_open(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

            def _send_line(self, record) -> None:
                self.wfile.write(
                    (json.dumps(record, separators=(",", ":")) + "\n")
                    .encode("utf-8"))
                self.wfile.flush()

            def _beats(self, seconds: float | None, beat_s: float,
                       key: str | None = None) -> None:
                """A beat every `beat_s` until `seconds` passes (None: until
                the client goes away), each logged when a key is named."""
                deadline = (None if seconds is None
                            else time.monotonic() + seconds)
                try:
                    while deadline is None or time.monotonic() < deadline:
                        self._send_line({"type": "pi_cloud_beat",
                                         "t": int(time.time() * 1000)})
                        if key is not None:
                            with worker._lock:
                                worker.beats.append({"key": key,
                                                     "at": time.time()})
                        time.sleep(beat_s)
                except OSError:
                    # The runtime killed the client (a stall); the stream it
                    # was reading is allowed to end right there.
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)

        def quiet_errors(*args):
            # A client that vanished mid-stream, or the socket `refuse`
            # closed under the handler, is the normal end of a cut stream.
            pass

        server.handle_error = quiet_errors
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=10)
            self._server = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    # ------------------------------------------------------------- routing

    @staticmethod
    def split_path(path: str) -> tuple[str, str]:
        """/attempts/<name>/<action> as (name, action), both percent-decoded."""
        rest = re.sub(r"^/(claude|codex)(?=/attempts/)", "", urlparse(path).path)
        if not rest.startswith("/attempts/"):
            return "", ""
        tail = rest[len("/attempts/"):]
        encoded, _, action = tail.partition("/")
        return unquote(encoded), unquote(action)

    def step_body(self, key: str) -> dict:
        """The newest step post recorded for `key`, or the empty body."""
        with self._lock:
            posts = self._steps.get(key) or []
        return dict(posts[-1]) if posts else {}

    def behaviour_for(self, key: str, query: dict):
        """The behaviour of this events connection, from the per-key plan."""
        with self._lock:
            posts = len(self._steps.get(key) or [])
            served = self._conns.get((key, posts), 0)
            self._conns[(key, posts)] = served + 1
            plan = self.plans.get((key, posts), self.default_plan)
        return plan[min(served, len(plan) - 1)]

    def head_for(self, key: str, step: dict) -> str:
        """The sha the fake Worker pushed for `key`, committing once.

        Clones the step's branch from the test's bare origin, checks out the
        posted start commit, commits one file and pushes it back without
        force - the same move the real Worker makes on its own branch.
        """
        with self._lock:
            cached = self._head.get(key)
        if cached:
            return cached
        branch = str(step.get("branch") or "")
        start = str(step.get("start_sha") or "")
        work = self.root / "work" / key.replace("/", "-")
        if not (work / ".git").exists():
            git("clone", str(self.origin), str(work))
        git("fetch", "origin", f"refs/heads/{branch}", cwd=work)
        git("checkout", "--detach", start or "FETCH_HEAD", cwd=work)
        (work / "rollcall").mkdir(exist_ok=True)
        (work / "rollcall" / f"{key}.md").write_text(
            f"# {key}\nfake pi-cloud work\n", encoding="utf-8")
        git("add", "-A", cwd=work)
        git("commit", "-m", "rollcall: pi-cloud fake", cwd=work)
        git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=work)
        head = git("rev-parse", "HEAD", cwd=work)
        with self._lock:
            self._head[key] = head
        return head


END_SECONDS = 42.0
ABORT_SECONDS = 7.5
ABORT_USAGE = {"input": 1200, "output": 300, "notional_cost_usd": 0.0}
LAST_LOOK = {
    "at": 1794769303000, "took_ms": 1180, "exit": 0, "truncated": False,
    "text": ("box: up 2710.4 s, load 1.92 1.80 1.71, cores 1, first process: /usr/local/bin/computerd\n"
             "machine cpu, since boot: user 2% system 1% idle 97% iowait 0% steal 0%\n"
             "machine cpu, last 1 s: user 1% system 1% idle 98% iowait 0% steal 0%\n"
             "container cpu (cgroup), since boot: used 71.0 s, throttled 0.0 s in 0 of 0 periods; "
             "last 1 s: used 20 ms, throttled 0 ms\n"
             "container cpu limit (cpu.max, quota and period in usec): max 100000\n"
             "container memory: 812000000 of 4294967296 bytes\n"
             "processes: 2 live (1 running, 0 blocked in the kernel), 1 zombies, 0 kernel threads left out\n"
             "zombies (dead, and not yet collected by their parent): 1 under parent 1; the first 1:\n"
             "    PID    PPID    PGID STAT     ELAPSED     TIME COMMAND\n"
             "   1517       1    1517 Zs         26:34 00:00:00 [python3] <defunct>\n"
             "live processes, oldest first (STAT R runs, S sleeps, D is blocked in the kernel, T is stopped):\n"
             "    PID    PPID    PGID STAT     ELAPSED     TIME COMMAND\n"
             "    423     419     423 S          35:00 00:01:10 python3 ohflow/tests/run_tests.py --shard 1/3\n"
             "   4757     423    4757 R          00:03 00:00:01 git -C /tmp/t/abort-repo switch -c merge-tail")}


def object_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def fake_container(key: str, seconds: float) -> dict:
    return {"durable_object_id": object_id(key), "instance": "standard-1",
            "seconds": seconds, "launches": 1, "stopped": True}


def _loop_lines(step: dict, worker: FakeWorker, rounds: int, *,
                ended: bool) -> list[dict]:
    """An agent that calls a tool in every turn and never answers.

    `ended` is the Worker that enforces the posted `max_iterations`: after
    `rounds` tool rounds the operation settles `unanswered` with the reason
    `turn_limit`, as pi-durable's `maxTurns` ends a run, and the work so far
    is pushed. Without it the stream stops after `rounds` rounds and beats on.
    """
    lines = _rewritten("single-events.ndjson", step, worker)[:1]
    for turn in range(1, rounds + 1):
        call = f"call_loop_{turn}"
        lines.append({"type": "message_end", "entryId": 100 + 2 * turn, "message": {
            "role": "assistant", "stopReason": "toolUse",
            "content": [{"type": "toolCall", "id": call, "name": "exec",
                         "arguments": {"command": f"echo turn {turn}"}}],
            "usage": {"input": 100, "output": 10, "cacheRead": 0, "cacheWrite": 0,
                      "reasoning": 0, "totalTokens": 110,
                      "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0,
                               "cacheWrite": 0.0, "total": 0.0}}}})
        lines.append({"type": "tool_execution_start", "toolCallId": call,
                      "toolName": "exec", "args": {"command": f"echo turn {turn}"}})
        lines.append({"type": "tool_execution_end", "toolCallId": call,
                      "toolName": "exec", "entryId": 101 + 2 * turn, "isError": False,
                      "result": {"content": [{"type": "text", "text": f"turn {turn}"}]}})
    if ended:
        key = str(step.get("operationId") or "")
        lines.append({"type": "pi_cloud_end", "operationId": key,
                      "status": "unanswered", "reason": "turn_limit",
                      "start": step.get("start_sha"), "branch": step.get("branch"),
                      "head": worker.head_for(key, step), "dirty": [],
                      "pushed": True, "usage": {},
                      "container": fake_container(key, END_SECONDS)})
    return lines


def _rewritten(fixture: str, step: dict, worker: FakeWorker, *,
               stop_before_end: bool = False, replayed: bool = False,
               push: bool = True) -> list[dict]:
    """One fixture's lines with this attempt's own key, branch and commits.

    `stop_before_end` drops the end line (the `silent` behaviour); `replayed`
    marks every non-start line as replayed, which is how the Worker serves a
    transcript it already holds; `push=False` leaves the end's head at the
    start commit and commits nothing, which is what a refused push means.
    """
    lines: list[dict] = []
    for record in _fixture_lines(fixture):
        kind = record.get("type")
        if kind == "pi_cloud_start":
            record.update(operationId=step.get("operationId") or "",
                          branch=step.get("branch") or "",
                          durable_object_id=object_id(step.get("operationId") or ""),
                          instance="standard-1")
            if step.get("start_sha"):
                record["start"] = step["start_sha"]
            if step.get("model"):
                record["model"] = step["model"]
            if "thinking" in step:
                record["thinking"] = step["thinking"]
        elif kind == "pi_cloud_end":
            if stop_before_end:
                continue
            record.update(operationId=step.get("operationId") or "",
                          branch=step.get("branch") or "",
                          container=fake_container(step.get("operationId") or "",
                                                   END_SECONDS))
            if step.get("start_sha"):
                record["start"] = step["start_sha"]
                if not push:
                    record["head"] = step["start_sha"]
            if push and record.get("pushed") and step.get("branch"):
                record["head"] = worker.head_for(
                    str(step.get("operationId") or ""), step)
        elif replayed:
            record["replayed"] = True
        lines.append(record)
    return lines
