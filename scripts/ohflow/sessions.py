"""The session controller: the orchestrator agent keeps up to three sessions open.

    ohflow session open NAME --dir D --cwd C (--brief FILE | --message TEXT)
    ohflow session send NAME --dir D (MESSAGE | --file FILE)
    ohflow session wait --dir D [--timeout S]
    ohflow session status [NAME] --dir D
    ohflow session interrupt NAME --dir D
    ohflow session close NAME --dir D [--force]

Each turn of a session is one process that continues the session's stored
conversation, so nothing stays alive between turns. A turn ends when its
process exits, and its reply is the last assistant message the process
printed. `D/events.jsonl` is the truth: every verb derives the state from it
and from the turn files, so a restarted orchestrator agent loses nothing.
Every verb prints one JSON object.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import IMPORT_ROOT, detach, pi_runner, proc, tiers
from .console import say

MAX_SESSIONS = 3
EVENTS = "events.jsonl"
LOCK = "lock"
POLL_S = 0.25
LOCK_WAIT_S = 30.0
EMPTY_LOCK_S = 5.0
INTERRUPT_GRACE_S = 30.0
NAME_RULE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
EXIT_OK, EXIT_FAIL, EXIT_REFUSED, EXIT_TIMEOUT, EXIT_IDLE = 0, 1, 2, 3, 4


class Refused(Exception):
    pass


@dataclass
class Turn:
    number: int
    pid: int
    sent_at: float


@dataclass
class Session:
    name: str
    dir: Path
    harness: str
    cwd: Path
    session_id: str
    model: str | None
    thinking: str | None
    opened_at: float
    closed: bool = False
    turns: list[Turn] = field(default_factory=list)
    delivered: set[int] = field(default_factory=set)
    queued: list[str] = field(default_factory=list)

    def file(self, number: int, suffix: str) -> Path:
        return self.dir / "turns" / f"{number}.{suffix}"

    @property
    def current(self) -> Turn | None:
        return self.turns[-1] if self.turns else None


class PiSessionHarness:
    name = "pi"

    def argv(self, session: Session, message: Path) -> list[str]:
        command = [*pi_runner.pi_argv(), "--mode", "json", "-p", "--no-mcp",
                   "--session-dir", str(session.dir / "session"),
                   "--session-id", session.session_id]
        if session.model:
            command += ["--model", session.model]
        if session.thinking:
            command += ["--thinking", session.thinking]
        return command + ["--", "@" + str(message.resolve())]

    def result(self, output: Path) -> dict[str, Any]:
        events = [event for event in (_json_line(line) for line in _lines(output))
                  if isinstance(event, dict)]
        messages = pi_runner.pi_messages(events)
        tokens, cost, error = pi_runner.pi_usage(messages)
        reply = pi_runner.assistant_text(messages[-1]) if messages else ""
        return {"reply": reply, "tokens": tokens, "cost": round(cost, 6), "error": error}


HARNESSES: dict[str, Any] = {"pi": PiSessionHarness()}


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []


def _json_line(line: str) -> Any:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temp, path)


class Record:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / EVENTS

    def append(self, event: str, **fields: Any) -> None:
        line = json.dumps({"at": round(time.time(), 3), "event": event, **fields})
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def sessions(self) -> dict[str, Session]:
        sessions: dict[str, Session] = {}
        for entry in (_json_line(line) for line in _lines(self.path)):
            if not isinstance(entry, dict):
                continue
            kind, name = entry.get("event"), str(entry.get("name") or "")
            if kind == "opened":
                sessions[name] = Session(
                    name=name, dir=self.root / name, harness=entry["harness"],
                    cwd=Path(entry["cwd"]), session_id=entry["session_id"],
                    model=entry.get("model"), thinking=entry.get("thinking"),
                    opened_at=float(entry["at"]))
                continue
            session = sessions.get(name)
            if session is None:
                continue
            if kind == "sent":
                session.turns.append(Turn(int(entry["turn"]), int(entry["pid"]),
                                          float(entry["at"])))
                if entry.get("message_id") in session.queued:
                    session.queued.remove(entry["message_id"])
            elif kind == "queued":
                session.queued.append(entry["message_id"])
            elif kind == "delivered":
                session.delivered.add(int(entry["turn"]))
            elif kind == "closed":
                session.closed = True
        return sessions

    def session(self, name: str) -> Session:
        session = self.sessions().get(name)
        if session is None:
            raise Refused(f"no session named {name} in {self.root}")
        if session.closed:
            raise Refused(f"the session {name} is closed")
        return session


@contextmanager
def locked(root: Path) -> Iterator[Record]:
    if not root.is_dir():
        raise Refused(f"no session record at {root}")
    path = root / LOCK
    deadline = time.time() + LOCK_WAIT_S
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                holder = int(path.read_text(encoding="utf-8") or 0)
                age = time.time() - path.stat().st_mtime
            except (OSError, ValueError):
                holder, age = 0, 0.0
            if (holder and not proc.pid_alive(holder)) or (not holder and age > EMPTY_LOCK_S):
                path.unlink(missing_ok=True)
                continue
            if time.time() > deadline:
                raise Refused(f"the record {root} stays locked by pid {holder or 'unknown'}")
            time.sleep(0.05)
            continue
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        break
    try:
        yield Record(root)
    finally:
        path.unlink(missing_ok=True)


def _exit_record(session: Session, number: int) -> dict[str, Any] | None:
    return _read_json(session.file(number, "exit.json"))


def _reaped(pid: int) -> bool:
    if os.name == "nt":
        return False
    try:
        return os.waitpid(pid, os.WNOHANG)[0] == pid
    except ChildProcessError:
        return False


def _alive(session: Session, turn: Turn) -> bool:
    if _reaped(turn.pid):
        return False
    pid_file = session.file(turn.number, "pid")
    try:
        own = int(pid_file.read_text(encoding="utf-8"))
        return proc.pid_alive(own, started_before=pid_file.stat().st_mtime)
    except (OSError, ValueError):
        return proc.pid_alive(turn.pid, started_before=turn.sent_at)


def _settle(session: Session) -> None:
    turn = session.current
    if turn is None or _exit_record(session, turn.number) is not None:
        return
    if not _alive(session, turn):
        _write_json(session.file(turn.number, "exit.json"),
                    {"exit_code": None, "interrupted": False, "lost": True,
                     "started_at": turn.sent_at, "finished_at": time.time(),
                     "error": "the turn process ended without writing its exit record"})


def _running(session: Session) -> bool:
    turn = session.current
    return turn is not None and _exit_record(session, turn.number) is None


def _state(session: Session) -> str:
    if session.closed:
        return "closed"
    return "running" if _running(session) else "idle"


def _launch(record: Record, session: Session, text: str, message_id: str | None = None) -> Turn:
    number = len(session.turns) + 1
    message = session.file(number, "md")
    message.write_text(text, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(IMPORT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8:replace"
    argv = [sys.executable, "-m", "ohflow.sessions", "turn", "--dir", str(record.root),
            session.name, str(number)]
    launched = detach.launch(argv, cwd=IMPORT_ROOT, env=env,
                             log_path=session.file(number, "log"))
    record.append("sent", name=session.name, turn=number, pid=launched.pid,
                  message_id=message_id)
    turn = Turn(number, launched.pid, time.time())
    session.turns.append(turn)
    return turn


def _start_queued(record: Record, sessions: dict[str, Session]) -> None:
    for session in sessions.values():
        if session.closed or not session.queued:
            continue
        _settle(session)
        if _running(session):
            continue
        message_id = session.queued.pop(0)
        queued = session.dir / "turns" / f"queued-{message_id}.md"
        _launch(record, session, queued.read_text(encoding="utf-8"), message_id)


def _refresh(record: Record) -> dict[str, Session]:
    sessions = record.sessions()
    for session in sessions.values():
        if not session.closed:
            _settle(session)
    _start_queued(record, sessions)
    return record.sessions()


def _report(session: Session, number: int) -> dict[str, Any]:
    exit_record = _exit_record(session, number) or {}
    result = HARNESSES[session.harness].result(session.file(number, "jsonl"))
    error = exit_record.get("error") or result["error"]
    code = exit_record.get("exit_code")
    if not error and code not in (0, None) and not exit_record.get("interrupted"):
        tail = _lines(session.file(number, "err"))[-1:]
        error = f"{session.harness} exited {code}" + (f": {tail[0]}" if tail else "")
    started, finished = exit_record.get("started_at"), exit_record.get("finished_at")
    return {"name": session.name, "turn": number, "reply": result["reply"], "error": error,
            "interrupted": bool(exit_record.get("interrupted")),
            "lost": bool(exit_record.get("lost")), "exit_code": code,
            "seconds": round(finished - started, 1) if started and finished else None,
            "tokens": result["tokens"], "cost": result["cost"]}


def _cost(session: Session) -> float:
    harness = HARNESSES[session.harness]
    return round(sum(harness.result(session.file(t.number, "jsonl"))["cost"]
                     for t in session.turns), 6)


def open_session(root: Path, name: str, *, cwd: Path, message: str,
                 harness: str = "pi", model: str | None = None,
                 thinking: str | None = None) -> dict[str, Any]:
    if not NAME_RULE.match(name):
        raise Refused(f"the name {name!r} must be 1 to 32 letters, digits, - or _")
    if not cwd.is_dir():
        raise Refused(f"the cwd {cwd} is not a directory")
    if harness not in HARNESSES:
        raise Refused(f"no harness {harness}; known: {', '.join(sorted(HARNESSES))}")
    if model and tiers.is_tier(model):
        model = tiers.model_for(model, harness)
    root.mkdir(parents=True, exist_ok=True)
    with locked(root) as record:
        sessions = record.sessions()
        if name in sessions:
            raise Refused(f"a session named {name} exists in {root}; a name is used once")
        open_names = [s.name for s in sessions.values() if not s.closed]
        if len(open_names) >= MAX_SESSIONS:
            raise Refused(f"{MAX_SESSIONS} sessions are open ({', '.join(open_names)}); "
                          "close one first")
        (root / name / "turns").mkdir(parents=True)
        (root / name / "session").mkdir()
        record.append("opened", name=name, harness=harness,
                      cwd=str(cwd.resolve()), session_id=str(uuid.uuid4()),
                      model=model, thinking=thinking)
        turn = _launch(record, record.session(name), message)
    return {"name": name, "turn": turn.number, "state": "running"}


def send(root: Path, name: str, message: str) -> dict[str, Any]:
    with locked(root) as record:
        _refresh(record)
        session = record.session(name)
        if _running(session) or session.queued:
            message_id = uuid.uuid4().hex[:12]
            (session.dir / "turns" / f"queued-{message_id}.md").write_text(
                message, encoding="utf-8")
            record.append("queued", name=name, message_id=message_id)
            return {"name": name, "state": "queued", "message_id": message_id,
                    "behind_turn": session.current.number if session.current else None}
        turn = _launch(record, session, message)
    return {"name": name, "turn": turn.number, "state": "running"}


def wait(root: Path, timeout: float | None = None) -> tuple[int, dict[str, Any]]:
    deadline = None if timeout is None else time.time() + timeout
    while True:
        with locked(root) as record:
            sessions = _refresh(record)
            ready = []
            for session in sessions.values():
                for turn in session.turns:
                    finished = _exit_record(session, turn.number)
                    if finished is not None and turn.number not in session.delivered:
                        ready.append((float(finished.get("finished_at") or 0), session, turn))
            if ready:
                _, session, turn = min(ready, key=lambda item: item[0])
                report = _report(session, turn.number)
                current = session.current
                report["next_turn"] = current.number if current and _running(session) else None
                record.append("delivered", name=session.name, turn=turn.number)
                return EXIT_OK, report
            running = [s.name for s in sessions.values() if not s.closed and _running(s)]
            if not running:
                return EXIT_IDLE, {"running": [], "note": "no session is running a turn, "
                                   "and every finished turn is delivered"}
        if deadline is not None and time.time() >= deadline:
            return EXIT_TIMEOUT, {"running": running, "note": f"no turn finished in {timeout} s"}
        time.sleep(POLL_S)


def status(root: Path, name: str | None = None) -> dict[str, Any]:
    with locked(root) as record:
        sessions = _refresh(record)
        if name is not None:
            session = sessions.get(name)
            if session is None:
                raise Refused(f"no session named {name} in {root}")
            finished = [t.number for t in session.turns if _exit_record(session, t.number)]
            last = _report(session, finished[-1]) if finished else None
            return {"name": name, "state": _state(session),
                    "turn": session.current.number if session.current else None,
                    "queued": len(session.queued), "last_finished": last}
        now = time.time()
        return {"sessions": [
            {"name": s.name, "state": _state(s),
             "turn": s.current.number if s.current else None,
             "undelivered": sum(1 for t in s.turns if t.number not in s.delivered
                                and _exit_record(w, t.number) is not None),
             "queued": len(s.queued), "age_s": round(now - s.opened_at),
             "cost": _cost(s), "harness": s.harness, "model": s.model}
            for s in sessions.values()]}


def interrupt(root: Path, name: str) -> dict[str, Any]:
    with locked(root) as record:
        _refresh(record)
        session = record.session(name)
        if not _running(session):
            raise Refused(f"the session {name} is not running a turn")
        number = session.current.number
        session.file(number, "interrupt").write_text(str(time.time()), encoding="utf-8")
    deadline = time.time() + INTERRUPT_GRACE_S
    while _exit_record(session, number) is None and time.time() < deadline:
        _settle(session)
        time.sleep(POLL_S)
    stopped = _exit_record(session, number) is not None
    with locked(root) as record:
        record.append("interrupted", name=name, turn=number, stopped=stopped)
    return {"name": name, "turn": number, "stopped": stopped}


def close(root: Path, name: str, force: bool = False) -> dict[str, Any]:
    with locked(root) as record:
        _refresh(record)
        session = record.session(name)
        running = _running(session)
    if running and not force:
        raise Refused(f"the session {name} is running turn {session.current.number}; "
                      "interrupt it first or pass --force")
    if running:
        try:
            interrupt(root, name)
        except Refused:
            pass
    with locked(root) as record:
        record.append("closed", name=name)
    return {"name": name, "state": "closed"}


def run_turn(root: Path, name: str, number: int) -> int:
    session = Record(root).sessions()[name]
    session.file(number, "pid").write_text(str(os.getpid()), encoding="utf-8")
    started = time.time()
    interrupted, code, error = False, None, None
    try:
        argv = HARNESSES[session.harness].argv(session, session.file(number, "md"))
        with session.file(number, "jsonl").open("w", encoding="utf-8") as out, \
                session.file(number, "err").open("w", encoding="utf-8") as err:
            managed = proc.spawn_managed(argv, cwd=session.cwd, env=proc.agent_env(),
                                         stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            try:
                while managed.poll() is None:
                    if session.file(number, "interrupt").exists():
                        managed.kill_tree()
                        interrupted = True
                        break
                    time.sleep(POLL_S)
                code = managed.poll()
            finally:
                managed.close()
    except (OSError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    _write_json(session.file(number, "exit.json"),
                {"exit_code": code, "interrupted": interrupted, "lost": False,
                 "started_at": started, "finished_at": time.time(), "error": error})
    return 0


def _message(ns: argparse.Namespace, text_attr: str) -> str:
    path = getattr(ns, "file", None) or getattr(ns, "brief", None)
    if path:
        return Path(path).read_text(encoding="utf-8")
    text = getattr(ns, text_attr, None)
    if not text:
        raise Refused("give the message as text or with --file")
    return text


def cmd(ns: argparse.Namespace) -> int:
    root = Path(ns.dir).resolve()
    code = EXIT_OK
    try:
        if ns.session_cmd == "open":
            out = open_session(root, ns.name, cwd=Path(ns.cwd),
                               message=_message(ns, "message"), harness=ns.harness,
                               model=ns.model, thinking=ns.thinking)
        elif ns.session_cmd == "send":
            out = send(root, ns.name, _message(ns, "text"))
        elif ns.session_cmd == "wait":
            code, out = wait(root, ns.timeout)
        elif ns.session_cmd == "status":
            out = status(root, ns.name)
        elif ns.session_cmd == "interrupt":
            out = interrupt(root, ns.name)
        else:
            out = close(root, ns.name, ns.force)
    except Refused as refusal:
        code, out = EXIT_REFUSED, {"refused": str(refusal)}
    say(json.dumps(out, ensure_ascii=False))
    return code


def add_verbs(parser: argparse.ArgumentParser) -> None:
    verbs = parser.add_subparsers(dest="session_cmd", required=True)
    p = verbs.add_parser("open", help="start a session and send it its first message")
    p.add_argument("name")
    p.add_argument("--cwd", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief")
    group.add_argument("--message")
    p.add_argument("--harness", default="pi", choices=sorted(HARNESSES))
    p.add_argument("--model", default=None, help="a model name, or the tier heavy or light")
    p.add_argument("--thinking", default=None)
    p = verbs.add_parser("send", help="send a follow-up; a busy session queues it")
    p.add_argument("name")
    p.add_argument("text", nargs="?")
    p.add_argument("--file")
    p = verbs.add_parser("wait", help="block until a session finishes a turn; print it once")
    p.add_argument("--timeout", type=float, default=None)
    p = verbs.add_parser("status", help="every session, or one session's last reply")
    p.add_argument("name", nargs="?")
    p = verbs.add_parser("interrupt", help="end a session's running turn")
    p.add_argument("name")
    p = verbs.add_parser("close", help="close a session for good")
    p.add_argument("name")
    p.add_argument("--force", action="store_true")
    for sub in verbs.choices.values():
        sub.add_argument("--dir", required=True, help="the orchestrator agent's session record")
        sub.set_defaults(fn=cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ohflow.sessions")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("turn")
    p.add_argument("--dir", required=True)
    p.add_argument("name")
    p.add_argument("number", type=int)
    ns = parser.parse_args(argv)
    return run_turn(Path(ns.dir), ns.name, ns.number)


if __name__ == "__main__":
    sys.exit(main())
