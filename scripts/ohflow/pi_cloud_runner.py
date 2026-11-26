"""Run one agent step in the pi-cloud Worker's Durable Object.

The step's worktree sits on this machine and the agent works in a Cloudflare
Durable Object of the operator's own pi-cloud Worker, whose URL the ohflow
settings name (`pi_cloud.url`). One object runs one attempt; this module is
ohflow's half:

- `PiCloudHarnessExecutor.launch` pushes the step's start commit to the
  project's own remote on `ohflow/pi-cloud/<key>` and records the transport
  in `remote.json` (`remote_git.py` owns the git and the key, which the
  durable executor shares). A reattach keeps the file and pushes nothing.
- `PiCloudAdapter.prepare` rewrites the brief to the Worker's own folders
  (`/workspace/repo`, `/workspace/out`), posts `step` with the operation id
  and the object name both the attempt key, and returns the
  `pi_cloud_client.py events ...` argv the runtime spawns. The client reads
  the NDJSON stream, reconnects inside one process and deduplicates replays,
  so the events, the usage and the tool-output contract are pi's own shapes,
  read through `pi_runner`'s helpers.
- `build_result` fetches the answer back into the worktree when the Worker
  pushed its branch, deletes the branch, copies the transcript, the usage and
  the handover down over HTTP, and stops the object with `abort` when the
  runtime itself stopped the attempt (a stall or the command time cap).
- Until that copy lands, and on a killed attempt that never makes one, the
  runner's event log `logs/pi-cloud-events.jsonl` is the transcript:
  `transcript` names it, and `ohflow actions` and the dashboard read it.
  `Replays` keeps the client's deduplication rule, so a replayed event reads
  once there too.
- `PiCloudHarnessExecutor.kill` stops the object with `abort` too, because
  the engine kills the runner past `execution_timeout_s` and when a phase
  aborts, and a killed runner never reaches its own abort. The retry starts
  a new object, so the old container would run on, billed, for no step. The
  answer lands in `kill-abort.json`. A supervisor death never calls `kill`,
  so its reattach still finds the object.

A dropped Worker - the client exits 3 after `OHFLOW_PI_CLOUD_LOST_S`
seconds with no line and no opened response - ends the runner with
`host_lost`, which the engine
answers with a reattach of the same attempt in the same directory: the object
holds the conversation, a repeat `step` post with the same operation id
changes nothing, and the replayed `message_end` events carry their usage, so
the reattached attempt counts all its turns once. The rule itself lives in
`engine.py` and `attempts.py`; `reattach_target` below answers where an
attempt directory continues. A stall, the command time cap, an `unanswered` end or
an HTTP fault is an ordinary failure under the usual retry rules, and the
retry is a fresh attempt with its own key, object and branch.

The token travels only in the `Authorization` header: never in an argv, a
spec, a log, an event line or an error message.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from . import activity as act
from . import attempt_record, cloud_spend, pi_runner, proc, remote_git, settings
from .cli_harness_executor import (CliPreparedProcess, CliRunOutcome,
                                   CliHarnessExecutor, recover_cli_result)
from .harness_executor import AgentLaunchError
from .paths import win
from .signed_in import read_schema, runner_main
from .structured import parse_structured

__all__ = ["EVENT_LOG", "pi_cloud_providers", "PiCloudAdapter", "PiCloudHarnessExecutor",
           "worker_url", "attempt_route", "agent_errors", "usage", "activity",
           "resume_target", "reattach_target", "transcript", "Replays",
           "replay_key", "replayed_lines", "preflight", "make_harness_executor",
           "main"]

EVENT_LOG = "pi-cloud-events.jsonl"
STDERR_LOG = "pi-cloud-stderr.log"

#: Every branch this executor exchanges with the Worker sits under this
#: prefix; `remote_git.push_start` checks the wider `ohflow/` rule.
BRANCH_PREFIX = "ohflow/pi-cloud"
#: Cloudflare answers error 1010 with HTTP 403 to Python's default
#: `User-Agent`, so every request this module makes sets the Worker's own.
#: The same string is defined as `USER_AGENT` in `pi_cloud_client.py`, which
#: imports nothing from ohflow by design and runs by path, so the two cannot
#: share one definition. Change both together.
USER_AGENT = "ohflow-pi-cloud/1"
TOKEN_ENV = "PI_CLOUD_TOKEN"
URL_ENV = "OHFLOW_PI_CLOUD_URL"
TURN_LIMIT = "turn_limit"


def requested_limit(spec: Mapping[str, Any]) -> int:
    """The step's `max_iterations`, as every runner reads it."""
    return int(spec.get("max_iterations") or 150)


def read_token() -> str:
    """The Worker's bearer token from `PI_CLOUD_TOKEN`, without a leading byte
    order mark and without the whitespace around it. A token copied from a
    file a Windows editor wrote carries the mark, and the header cannot encode
    it."""
    return (os.environ.get(TOKEN_ENV) or "").lstrip("\ufeff").strip()


def pi_cloud_providers() -> frozenset[str]:
    """The providers the Worker holds keys for."""
    return frozenset(settings.get("pi_cloud.providers", []))

#: The client script this package ships, run by path with this interpreter.
CLIENT_SCRIPT = Path(__file__).with_name("pi_cloud_client.py")

STEP_TIMEOUT_S = 300.0
ABORT_TIMEOUT_S = 60.0
TEXT_TIMEOUT_S = 60.0
PREFLIGHT_TIMEOUT_S = 15.0


#: What the executor's `kill` got back from its `abort` post.
KILL_ABORT = "kill-abort.json"
RUNNER_ABORT = "runner-abort.json"
LAST_LOOK_LOG = "box-last-look.txt"


def abort_operation(url: str, key: str) -> dict[str, Any] | None:
    """Tell the Worker to stop the operation and its container; a fault
    is only recorded.

    The attempt is already ending on its own verdict, so a refused abort must
    not mask that verdict. The retry is a fresh attempt with a new object,
    and the branch this attempt pushed lingers until the next launch
    force-pushes over it. The answer carries the container's meter, None
    when the abort failed.
    """
    try:
        answer = _request("POST", attempt_route(url, key, "abort"),
                          {"operationId": key}, route="POST abort",
                          timeout=ABORT_TIMEOUT_S)
        return answer if isinstance(answer, dict) else {}
    except RuntimeError as fault:
        sys.stderr.write(f"pi-cloud abort of {key} failed: {fault}\n")
        return None


def abort_killed_attempt(out_dir: Path) -> dict[str, Any] | None:
    try:
        remote = json.loads((Path(out_dir) / "remote.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(remote, dict) or not remote.get("key") or not remote.get("url"):
        return None
    answer = abort_operation(str(remote["url"]), str(remote["key"]))
    _keep_abort(out_dir, KILL_ABORT, answer)
    return answer


def _keep_abort(out_dir: Path, name: str, answer: dict[str, Any] | None) -> None:
    (Path(out_dir) / name).write_text(json.dumps(
        {"aborted": answer is not None, "answer": answer}, indent=2), encoding="utf-8")


def _kill_abort(out_dir: Path) -> dict[str, Any] | None:
    try:
        record = json.loads((Path(out_dir) / KILL_ABORT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def _abort_records(out_dir: Path) -> list[dict[str, Any]]:
    """The abort posts this attempt kept, the runner's own first, then the
    executor's after a kill. Each holds `aborted` and the Worker's `answer`,
    None when the post failed."""
    records: list[dict[str, Any]] = []
    for name in (RUNNER_ABORT, KILL_ABORT):
        try:
            record = json.loads((Path(out_dir) / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _abort_answers(out_dir: Path) -> list[dict[str, Any]]:
    return [record["answer"] for record in _abort_records(out_dir)
            if isinstance(record.get("answer"), dict)]


def abort_tokens(out_dir: Path) -> dict[str, int] | None:
    """The tokens the Worker had counted when it answered `abort`.

    None when no abort answer carries a count: the tokens are then unknown,
    which is not the same as a counted zero.
    """
    for answer in reversed(_abort_answers(out_dir)):
        usage = answer.get("usage")
        if not isinstance(usage, dict):
            continue
        counts = {"prompt_tokens": usage.get("input"),
                  "completion_tokens": usage.get("output")}
        if all(attempt_record.is_count(value) for value in counts.values()):
            return {**attempt_record.zero_tokens(), **counts}
    return None


def tokens_with_abort(tokens: Mapping[str, int], out_dir: Path) -> dict[str, int]:
    """The attempt's tokens, from the abort answer when the stream carried none.

    A Claude Code or Codex object reports its tokens on the stream only when
    the operation settles, and it answers `abort` with the count so far. The
    record and `usage` both read the tokens through this function, so the
    token reconcile compares like with like.
    """
    if any(tokens.values()):
        return dict(tokens)
    return abort_tokens(out_dir) or dict(tokens)


LOOK_NOT_RUNNING = "the container was not running at the abort"
LOOK_ABORT_FAILED = "the abort post failed, so the Worker took no look"
LOOK_NOT_SENT = "the Worker's abort answer carries no last look"


def keep_last_look(out_dir: Path) -> dict[str, Any] | None:
    """Write the box's last look to `logs/box-last-look.txt`; the record's pointer.

    The Worker takes the look just before it stops the container: the load,
    the CPU rates, the memory, and the live processes apart from the zombies.
    None when the attempt posted no abort. `absent` says why an abort left no
    look: the post failed, the container was not running, or the Worker sent
    none. `error` is the Worker's own fault text, as for a look that passed
    its time limit.
    """
    out_dir = Path(out_dir)
    records = _abort_records(out_dir)
    if not records:
        return None
    kept = {"at": None, "took_ms": None, "exit": None, "error": None,
            "truncated": False, "file": None, "absent": LOOK_ABORT_FAILED}
    for record in reversed(records):
        answer = record.get("answer")
        if not isinstance(answer, dict):
            continue
        if "last_look" not in answer:
            kept["absent"] = LOOK_NOT_SENT
            continue
        look = answer["last_look"]
        if not isinstance(look, dict):
            kept["absent"] = LOOK_NOT_RUNNING
            continue
        kept.update(at=look.get("at"), took_ms=look.get("took_ms"),
                    exit=look.get("exit"), error=look.get("error"),
                    truncated=bool(look.get("truncated")), absent=None)
        if isinstance(look.get("text"), str):
            logs = out_dir / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / LAST_LOOK_LOG).write_text(look["text"] + "\n", encoding="utf-8")
            kept["file"] = f"logs/{LAST_LOOK_LOG}"
        return kept
    return kept


def worker_url() -> str:
    """The Worker's base URL: `OHFLOW_PI_CLOUD_URL`, else `pi_cloud.url`."""
    url = os.environ.get(URL_ENV) or settings.get("pi_cloud.url")
    if not url:
        raise AgentLaunchError(
            "pi_cloud.url is not set; name your pi-cloud Worker in "
            "ohflow.settings.local.json or OHFLOW_PI_CLOUD_URL")
    return str(url).rstrip("/")


def attempt_route(url: str, key: str, action: str) -> str:
    """One route of one attempt's Durable Object; the name is percent-encoded."""
    return f"{url.rstrip('/')}/attempts/{urllib.parse.quote(key, safe='')}/{action}"


def _headers(token: str, data: bytes | None = None) -> dict[str, str]:
    """The headers of every request this module makes to the Worker.

    `Authorization` and `User-Agent` always - a request that misses either
    reads as an unauthorized client on the Worker - and `Content-Type` when a
    body rides along. Built here in one place, because `_send` and the
    preflight are the same client of the same Worker and must not drift
    apart; neither the headers nor the token they carry may reach a log.
    """
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    return headers


def _send(method: str, url: str, body: Mapping[str, Any] | None, *,
          route: str, timeout: float) -> str:
    """One HTTP call to the Worker with both headers; the body text back.

    An `HTTPError` becomes a `RuntimeError` naming the route, the status and
    the body's `error` field. A transport fault names the unreachable Worker.
    Neither message can carry a header, because the only interesting one holds
    the token.
    """
    token = read_token()
    if not token:
        raise RuntimeError(f"{TOKEN_ENV} is empty or unset; the pi-cloud "
                           f"Worker needs its bearer token")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers=_headers(token, data))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            parsed = json.loads(error.read(4096).decode("utf-8", "replace"))
        except (OSError, ValueError):
            parsed = None
        if isinstance(parsed, dict) and parsed.get("error"):
            detail = str(parsed["error"])
        raise RuntimeError(
            f"the pi-cloud Worker answered HTTP {error.code} on {route}"
            + (f": {detail}" if detail else "")) from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise RuntimeError(f"the pi-cloud Worker at {worker_url()} did not "
                           f"answer {route}: {error}") from None


def _request(method: str, url: str, body: Mapping[str, Any] | None, *,
             route: str, timeout: float) -> Any:
    """`_send` with the answer parsed as JSON (None on an empty body)."""
    text = _send(method, url, body, route=route, timeout=timeout)
    return json.loads(text) if text.strip() else None


def _rewrite_brief(text: str, workspace: str, out_dir: str, *,
                   branch: str = "", start_sha: str = "") -> str:
    """Point the brief at the Worker's own folders, `/workspace/repo` and
    `/workspace/out`.

    The agent in the Durable Object must not see this machine's worktree or
    run directory: it could not open them, and a path it could open would be
    the wrong file. Both renderings of each path are replaced - by the shared
    rule in `remote_git.rewrite_paths`, which the durable executor's own
    rewrite also uses - because the position block and the brief mix
    `paths.win` and forward-slash text.
    """
    text = remote_git.rewrite_paths(text, (
        (workspace, "/workspace/repo"),
        (out_dir, "/workspace/out"),
    ))
    return remote_git.transport_position(text, branch, start_sha)


def _announced(events, out_dir: Path, field: str) -> list[str]:
    """A list the Worker announced, `tools` or `mcp_servers`: the last
    `pi_cloud_start` line, else the answer the `step` post saved."""
    for event in reversed(events):
        if event.get("type") == "pi_cloud_start":
            names = event.get(field)
            if isinstance(names, list):
                return [str(name) for name in names]
    try:
        answer = json.loads(
            (Path(out_dir) / "pi-cloud-step.json").read_text(encoding="utf-8"))
        names = answer.get(field)
        if isinstance(names, list):
            return [str(name) for name in names]
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return []


# ---------------------------------------------------------------- the adapter


class PiCloudAdapter:
    """The pi-cloud Worker's argv, event and result semantics for the runtime."""

    name = "pi-cloud"
    event_log_name = EVENT_LOG
    stderr_log_name = STDERR_LOG
    local_limit = True
    worker_limit: int | None = None

    def prepare(self, spec: dict[str, Any], out_dir: Path) -> CliPreparedProcess:
        out_dir = Path(out_dir)
        try:
            remote = json.loads(
                (out_dir / "remote.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"{win(out_dir / 'remote.json')} is missing or unreadable "
                f"({error}); the launch writes it before the runner starts") from error
        if not isinstance(remote, dict):
            raise RuntimeError(f"{win(out_dir / 'remote.json')} is not an object")
        key = str(remote.get("key") or "")
        if not key:
            raise RuntimeError(f"{win(out_dir / 'remote.json')} names no key")
        url = str(remote.get("url") or worker_url()).rstrip("/")
        # The object's own copy of the brief, with the paths it can open.
        brief = _rewrite_brief((out_dir / "brief.md").read_text(encoding="utf-8"),
                               str(spec.get("workspace") or ""),
                               str(out_dir.resolve()),
                               branch=str(remote.get("branch") or ""),
                               start_sha=str(remote.get("start_sha") or ""))
        staged = out_dir / "remote"
        staged.mkdir(parents=True, exist_ok=True)
        (staged / "brief.md").write_text(brief, encoding="utf-8")
        model = spec.get("model") or {}
        params = model.get("params") or {}
        body: dict[str, Any] = {
            "operationId": key,
            "brief": brief,
            "model": model.get("model"),
            "remote_url": remote.get("remote_url"),
            "branch": remote.get("branch"),
            "start_sha": remote.get("start_sha"),
            "ohflow": {"coord": spec.get("coord"),
                       "attempt": spec.get("attempt"), "key": key},
        }
        if "thinking" in params:
            body["thinking"] = params["thinking"]
        tools = spec.get("tools") or {}
        body["tools"] = {"allow": list(tools.get("allow") or ()),
                         "block": list(tools.get("block") or ())}
        body["skills"] = list(spec.get("skills") or ())
        body["max_iterations"] = requested_limit(spec)
        answer = _request("POST", attempt_route(url, key, "step"), body,
                          route="POST step", timeout=STEP_TIMEOUT_S)
        (out_dir / "pi-cloud-step.json").write_text(
            json.dumps(answer, indent=2), encoding="utf-8")
        acknowledged = (answer or {}).get("max_iterations")
        self.worker_limit = (acknowledged if isinstance(acknowledged, int)
                             and not isinstance(acknowledged, bool) else None)
        return CliPreparedProcess(
            argv=tuple([sys.executable, str(CLIENT_SCRIPT), "events",
                        "--url", url, "--name", key, "--operation", key]),
            cwd=out_dir,
            env=proc.agent_env(),
            context={"url": url, "key": key, "remote": remote},
        )

    def parse_event(self, line: str) -> Mapping[str, Any]:
        return json.loads(line)

    def on_event(self, spec: dict[str, Any], event: Mapping[str, Any],
                 events: list[Mapping[str, Any]]):
        return pi_runner.pi_event_action(
            spec, event, events,
            enforce_limit=self.local_limit and self.worker_limit is None)

    def limit_record(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """The iteration limit this attempt ran under, and who enforced it."""
        if self.worker_limit is not None:
            return {"max_iterations": self.worker_limit,
                    "max_iterations_enforced_by": "worker"}
        if self.local_limit:
            return {"max_iterations": requested_limit(spec),
                    "max_iterations_enforced_by": "ohflow"}
        return {"max_iterations": None, "max_iterations_enforced_by": None}

    def _abort(self, url: str, key: str) -> dict[str, Any] | None:
        return abort_operation(url, key)

    def _copy_text(self, url: str, key: str, action: str, target: Path) -> None:
        """One text route copied into the attempt directory.

        A failed copy is no error: the run itself already settled, and a
        missing handover or transcript must not turn a passed step failed.
        """
        try:
            text = _send("GET", attempt_route(url, key, action), None,
                         route=f"GET {action}", timeout=TEXT_TIMEOUT_S)
        except RuntimeError:
            return
        target.write_text(text, encoding="utf-8")

    def build_result(self, outcome: CliRunOutcome) -> tuple[dict[str, Any], str | None]:
        spec = outcome.spec
        out_dir = Path(outcome.out_dir)
        events = outcome.events
        context = outcome.prepared.context
        url = str(context["url"])
        key = str(context["key"])
        remote = context["remote"]
        workspace = Path(str(spec.get("workspace") or "."))

        # Replayed message_end events carry their usage too, so a reattached
        # attempt counts everything its conversation ever spent, once.
        messages = pi_runner.pi_messages(events)
        final = pi_runner.assistant_text(messages[-1]) if messages else ""
        tokens, cost, provider_error = pi_runner.pi_usage(messages)
        tool_ends = [e for e in events if e.get("type") == "tool_execution_end"]
        end = next((e for e in reversed(events)
                    if e.get("type") == "pi_cloud_end"), None)
        fault = next((e for e in reversed(events)
                      if e.get("type") == "pi_cloud_error"), None)

        error = outcome.stop_error
        abort_answer = self._abort(url, key) if error else None
        aborted = abort_answer is not None
        if error:
            _keep_abort(out_dir, RUNNER_ABORT, abort_answer)
            tokens = tokens_with_abort(tokens, out_dir)
        if not error and fault is not None:
            error = f"{fault.get('name')}: {fault.get('message')}"
        if not error and end is None:
            error = (f"host_lost: the event stream of "
                     f"{url}/attempts/{key} ended without pi_cloud_end "
                     f"(client exited {outcome.returncode})")
        if not error and end is not None and end.get("status") != "done":
            if end.get("reason") == TURN_LIMIT and self.worker_limit:
                error = f"max iterations {self.worker_limit} exceeded"
            else:
                error = f"unanswered: {end.get('reason')}"
        if not error and end is not None and not end.get("pushed"):
            prefix, _, text = str(end.get("push_error") or "").partition(": ")
            if prefix == "clone_failed":
                error = f"clone_failed: {text}"
            elif prefix == "skills_failed":
                error = f"skills_failed: {text}"
            else:
                error = f"push_failed: {end.get('push_error')}"
        if not error:
            error = provider_error

        cloud = {"url": url, "key": key, "branch": remote.get("branch"),
                 "start_sha": remote.get("start_sha"),
                 "head": None, "dirty": None, "pushed": False,
                 "status": None, "reason": None, "aborted": aborted,
                 "branch_deleted": False, "last_look": keep_last_look(out_dir)}
        if end is not None:
            cloud.update(head=end.get("head"), dirty=end.get("dirty"),
                         pushed=bool(end.get("pushed")),
                         status=end.get("status"), reason=end.get("reason"))
            if end.get("pushed"):
                try:
                    remote_git.fetch_result(
                        workspace, str(remote.get("branch") or ""),
                        str(remote.get("start_sha") or ""))
                except (ValueError, RuntimeError) as fault_back:
                    if not error:
                        error = f"fetch_back: {fault_back}"
                else:
                    # The fetched commit is in the run's worktree now, so the
                    # transport branch has served its purpose. A refused
                    # delete only lingers until the next launch force-pushes.
                    cloud["branch_deleted"] = remote_git.delete_branch(
                        workspace, str(remote.get("branch") or ""))
            self._copy_text(url, key, "transcript", out_dir / "transcript.md")
            (out_dir / "usage.json").write_text(
                json.dumps(end.get("usage") or {}, indent=2), encoding="utf-8")
            self._copy_text(url, key, "out/handover.md", out_dir / "handover.md")

        start = next((e for e in events if e.get("type") == "pi_cloud_start"), None)
        container = (end or {}).get("container") or (abort_answer or {}).get("container")
        infra, infra_cost = cloud_spend.attempt_infra(start, container)
        cloud["durable_object_id"] = (infra or {}).get("durable_object_id")

        structured, schema_error = parse_structured(final, read_schema(spec, out_dir))
        tools = _announced(events, out_dir, "tools")
        model = spec.get("model") or {}
        result = {
            **attempt_record.empty_record(spec, error or "",
                                          cost_source="pi-cloud-worker"),
            "conversation_id": key,
            "transcript_dir": None,
            "execution_status": "error" if error else "finished",
            "tools": tools, "skills": list(spec.get("skills") or []),
            "mcp_servers": _announced(events, out_dir, "mcp_servers"),
            "tool_calls": len(tool_ends),
            "observation_errors": sum(
                bool(e.get("isError") or (e.get("result") or {}).get("isError"))
                for e in tool_ends),
            "llm_calls": len(messages),
            "wall_seconds": round(outcome.finished_at - outcome.started_at, 1),
            "tokens": tokens, "cost": cost,
            "infra": infra, "infra_cost": infra_cost,
            "final_text_path": "final.md", "structured": structured,
            "schema_error": schema_error, "error": error,
            "settings": attempt_record.settings_record(spec, {
                "model": model.get("model"),
                "thinking": (model.get("params") or {}).get("thinking", "low"),
                "tools": tools, **self.limit_record(spec)}),
            "pi_cloud": cloud,
        }
        return result, final if final else None


# ------------------------------------------------------------ agent rules


def agent_errors(where: str, agent: Any) -> list[str]:
    """The faults in an agent spec for the pi-cloud harness executor.

    The Worker offers one fixed tool set in one fixed container, plus the
    MCP servers of the box's gateway, which `tools.allow` and `tools.block`
    narrow, plus the skills the step names, which the Worker mounts from its
    mirror of the operator's skills repository. No workflow MCP servers, no skills folder
    of this machine, no browser, no second machine to pick: everything that
    would configure one of those is refused, each naming the reason.
    """
    errs: list[str] = []
    if agent.agent_profile:
        errs.append(
            f"{where}: pi-cloud agent.agent_profile must be empty; the Worker "
            f"is the only machine, got {agent.agent_profile!r}")
    model = agent.model
    errs.extend(pi_runner.model_errors(where, model, "pi-cloud",
                                      pi_cloud_providers()))

    tools = agent.tools
    if tools.preset != "default":
        errs.append(
            f"{where}: pi-cloud supports only tools.preset='default', got "
            f"{tools.preset!r}")
    if tools.enable_browser:
        errs.append(f"{where}: pi-cloud refuses enable_browser=True; the "
                    "Worker has no browser")
    if tools.enable_sub_agents:
        errs.append(f"{where}: pi-cloud refuses enable_sub_agents=True; the "
                    "Worker runs one agent per object")
    if tools.only:
        errs.append(f"{where}: pi-cloud refuses tools.only; the Worker offers "
                    "one fixed tool set")
    if agent.mcp_config:
        errs.append(f"{where}: pi-cloud refuses mcp_config; the box serves "
                    "its own MCP servers, which tools.allow and tools.block "
                    "narrow")
    if agent.skills_dir:
        errs.append(f"{where}: pi-cloud refuses skills_dir; the Worker mounts "
                    "the named skills from its mirror of the skills repository")
    return errs


# ------------------------------------------------------------------- usage


def usage(attempt_dir: Path) -> tuple[dict[str, int] | None, str | None]:
    """The usage the runner's event log records, replayed turns included."""
    event_log = Path(attempt_dir) / "logs" / EVENT_LOG
    if not event_log.is_file():
        return None, f"pi-cloud event log is missing ({event_log})"
    return usage_with_abort(pi_runner.event_log_usage(event_log, "pi-cloud"), attempt_dir)


def usage_with_abort(read: tuple[dict[str, int] | None, str | None],
                     attempt_dir: Path) -> tuple[dict[str, int] | None, str | None]:
    counted, problem = read
    if counted is None:
        aborted = abort_tokens(Path(attempt_dir))
        if aborted is not None and str(problem).endswith(pi_runner.NO_USAGE_RECORDS):
            return aborted, None
        return counted, problem
    return tokens_with_abort(counted, Path(attempt_dir)), problem


# ---------------------------------------------------------------- activity


def activity(attempt_dir: Path, *, now: float | None = None, running: bool = True,
             limit: int = act.DEFAULT_TOOL_CALLS) -> dict:
    """The step as the Worker ran it, read from the runner's copy of its events."""
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
            replays = model.scratch.setdefault("replays", Replays())
            if isinstance(event, dict) and replays.first(event):
                pi_runner.apply_pi_event(model, event)
        beat = act.read_json(attempt_dir / "logs" / "heartbeat.json")
        beat_at = act.epoch(beat.get("at")) if isinstance(beat, dict) else None
        note = act.STARTING_NOTE if not model.replied else None
        return act.activity_out(model, harness_executor="pi-cloud",
                                root=act.worktree_root(attempt_dir), now=now,
                                running=running, limit=limit,
                                fallback_at=beat_at, note=note)


# --------------------------------------------- resume, reattach, transcript


def resume_target(prior_result: Mapping[str, Any], attempt_dir: Path) -> str | None:
    """A pi-cloud retry starts a fresh conversation; a reattach is not a retry."""
    return None


def reattach_target(attempt_dir: Path) -> str | None:
    """`<url>/attempts/<key>` where this attempt directory continues, or None.

    The engine asks this before restarting a step whose execution is still
    open in the run log: a supervisor death. `remote.json` is the evidence
    the launch reached the transport, and its `key` is the Durable Object's
    name, so the object the attempt started in is the object it continues in.
    """
    try:
        remote = json.loads(
            (Path(attempt_dir) / "remote.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(remote, dict):
        return None
    key = remote.get("key")
    if not key:
        return None
    url = str(remote.get("url") or worker_url()).rstrip("/")
    return f"{url}/attempts/{urllib.parse.quote(str(key), safe='')}"


def transcript(attempt_dir: Path, result: Mapping[str, Any],
               output: Path | None = None) -> tuple[Path | None, str | None]:
    """The transcript the Worker served and the runner copied down, else the
    runner's event log: a running attempt has no copy yet, and a killed
    runner never makes one."""
    for path in (Path(attempt_dir) / "transcript.md",
                 Path(attempt_dir) / "logs" / EVENT_LOG):
        if path.is_file():
            return path, None
    return None, f"no pi-cloud transcript and no logs/{EVENT_LOG}"


def replay_key(event: Mapping[str, Any]) -> tuple[str, Any] | None:
    """What a replayed copy of this event shares with its first copy.

    The rule is `pi_cloud_client._Printed`'s: `message_end` and
    `tool_execution_end` by their `entryId`, `tool_execution_start` by its
    `toolCallId`. A live start carries no `entryId` and its replayed copy
    does, so a start is never keyed by its entry.
    """
    kind = event.get("type")
    if kind in ("message_end", "tool_execution_end"):
        ident = event.get("entryId")
    elif kind == "tool_execution_start":
        ident = event.get("toolCallId")
    else:
        return None
    return None if ident is None else (str(kind), ident)


class Replays:
    """The events of one event log read so far, so a replay reads once."""

    def __init__(self) -> None:
        self.seen: set[tuple[str, Any]] = set()

    def first(self, event: Mapping[str, Any]) -> bool:
        key = replay_key(event)
        if key is None:
            return True
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


_SCANS: dict[str, dict[str, Any]] = {}
_SCANS_LOCK = threading.Lock()


def replayed_lines(path: Path) -> frozenset[int]:
    """The line numbers of an event log that repeat an earlier event.

    The dashboard pages the log by byte offset, so it skips these lines by
    number instead of carrying a seen set from page to page. Each call reads
    on from where the last one stopped; a log that shrank, or whose first
    line changed as when a reattach's runner rewrites it, is read again.
    """
    path = Path(path)
    with _SCANS_LOCK:
        try:
            with path.open("rb") as fh:
                head = fh.readline()
                size = fh.seek(0, os.SEEK_END)
                scan = _SCANS.get(str(path))
                if scan is None or scan["head"] != head or size < scan["offset"]:
                    if len(_SCANS) > 256:
                        _SCANS.clear()
                    scan = _SCANS[str(path)] = {
                        "head": head, "offset": 0, "line": 0,
                        "replays": Replays(), "lines": set()}
                fh.seek(scan["offset"])
                for raw in fh:
                    if not raw.endswith(b"\n"):
                        break
                    scan["offset"] += len(raw)
                    scan["line"] += 1
                    try:
                        event = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(event, dict) and not scan["replays"].first(event):
                        scan["lines"].add(scan["line"])
        except OSError:
            return frozenset()
        return frozenset(scan["lines"])


# ---------------------------------------------------------------- preflight


def preflight() -> list[str]:
    """`PI_CLOUD_TOKEN` is set, and the Worker answers its root route 404.

    `GET <url>/` answers 404 with both headers and 401 with a wrong token,
    so the one request tells the three faults apart: unset, refused,
    unreachable. The URL is named in each, because `OHFLOW_PI_CLOUD_URL`
    may point somewhere else.
    """
    token = read_token()
    try:
        url = worker_url()
    except AgentLaunchError as error:
        return [str(error)]
    if not token:
        return [f"PI_CLOUD_TOKEN is empty or unset; the pi-cloud Worker at "
                f"{url} needs its bearer token"]
    request = urllib.request.Request(url + "/",
                                     headers=_headers(token))
    try:
        with urllib.request.urlopen(request, timeout=PREFLIGHT_TIMEOUT_S) as response:
            code = response.status
    except urllib.error.HTTPError as error:
        if error.code == 404:
            # The Worker's own root route: 404 with both headers is the
            # healthy answer, and it arrives as an HTTPError here.
            return []
        if error.code == 401:
            return [f"the pi-cloud Worker at {url} refused PI_CLOUD_TOKEN "
                    f"(HTTP 401); check the token"]
        return [f"the pi-cloud Worker at {url} answered HTTP {error.code} on "
                f"its root route, expected 404"]
    except (urllib.error.URLError, OSError) as error:
        return [f"the pi-cloud Worker at {url} is unreachable: {error}"]
    if code != 404:
        return [f"the pi-cloud Worker at {url} answered HTTP {code} on its "
                f"root route, expected 404"]
    return []


# ---------------------------------------------------------------- the harness executor


class PiCloudHarnessExecutor(CliHarnessExecutor):
    """The CLI harness executor whose runner streams the Worker over HTTP."""

    def __init__(self, python: Path | None = None):
        super().__init__(name="pi-cloud", runner_module="ohflow.pi_cloud_runner",
                         python=python,
                         recovery=recover_result,
                         checks=preflight)

    def launch(self, spec: dict, out_dir: Path):
        out_dir = Path(out_dir)
        try:
            if spec.get("reattach"):
                # The transport of the attempt being reattached is already on
                # disk; pushing a new start commit would answer a new question
                # on an object that holds half a conversation.
                if not (out_dir / "remote.json").is_file():
                    raise ValueError(
                        f"{win(out_dir)} holds no remote.json to reattach")
            else:
                workspace = Path(str(spec["workspace"]))
                url = remote_git.remote_url(workspace)
                key = remote_git.attempt_key(str(spec["coord"]),
                                             int(spec.get("attempt") or 1), out_dir)
                branch = f"{BRANCH_PREFIX}/{key}"
                start_sha = remote_git.push_start(workspace, branch)
                (out_dir / "remote.json").write_text(json.dumps({
                    "url": worker_url(), "key": key, "branch": branch,
                    "remote_url": url, "start_sha": start_sha}, indent=2),
                    encoding="utf-8")
        except (ValueError, RuntimeError) as e:
            raise AgentLaunchError(f"pi-cloud launch failed: {e}") from e
        return super().launch(spec, out_dir)

    def kill(self, handle) -> None:
        super().kill(handle)
        abort_killed_attempt(handle.out_dir)


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
    start = next((e for e in events if e.get("type") == "pi_cloud_start"), None)
    killed = _kill_abort(out_dir) or {}
    container = next((answer["container"] for answer in reversed(_abort_answers(out_dir))
                      if answer.get("container")), None)
    infra, infra_cost = cloud_spend.attempt_infra(start, container)
    tokens_from = ("event_log" if messages
                   else "abort_answer" if abort_tokens(out_dir) is not None
                   else "unknown")
    tokens = tokens_with_abort(tokens, out_dir)
    result = {
        **attempt_record.empty_record(spec, fallback_error, tokens=tokens,
                                      cost=cost, cost_source="pi-cloud-worker"),
        "recovery": {"tokens": tokens_from},
        "infra": infra, "infra_cost": infra_cost,
        "conversation_id": remote.get("key"),
        "execution_status": "error",
        "tool_calls": len(tool_ends), "llm_calls": len(messages),
        "final_text_path": "final.md" if final else None,
        "error": fallback_error,
        "pi_cloud": {"url": remote.get("url"), "key": remote.get("key"),
                     "branch": remote.get("branch"),
                     "start_sha": remote.get("start_sha"), "head": None,
                     "dirty": None, "pushed": False, "status": None,
                     "reason": None, "aborted": bool(killed.get("aborted")),
                     "branch_deleted": False, "last_look": keep_last_look(out_dir),
                     "durable_object_id": (infra or {}).get("durable_object_id")},
    }
    return result, final if final else None


def recover_result(spec_path: Path, out_dir: Path, fallback_error: str) -> dict[str, Any]:
    return recover_cli_result(spec_path, out_dir, fallback_error,
                              event_log_name=EVENT_LOG, parser=json.loads,
                              builder=_recover)


def make_harness_executor():
    return PiCloudHarnessExecutor()


def main(argv: list[str] | None = None) -> int:
    return runner_main(PiCloudAdapter, argv)


if __name__ == "__main__":
    raise SystemExit(main())
