"""The tool-output contract: every tool call's output, on disk, while it runs.

One layout for every harness executor, so a reader never asks which harness
produced it:

    <attempt>/logs/tool-output/index.jsonl        start and end of each call
    <attempt>/logs/tool-output/shell-index.jsonl  the same, written by a shell
                                                  wrapper outside the runtime
    <attempt>/logs/tool-output/<seq>-<id>.log     the call's output so far

The runtime writes `index.jsonl` through `ToolOutputWriter`. A shell wrapper
(claude's `CLAUDE_CODE_SHELL_PREFIX`) writes `shell-index.jsonl` and its own
`.log` files, because it runs in another process and cannot know the tool
call's id. `calls()` merges both, and pairs a wrapper entry with the tool call
whose command it ran.

The capture is evidence, never input: nothing here enters a fingerprint.
Measured sources and their limits are in
`docs/history/silent-command-liveness.md`.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = ["DIR", "INDEX", "SHELL_INDEX", "CAP_BYTES", "HEAD_BYTES",
           "CallEvent", "ToolOutputWriter", "calls", "open_calls", "tail",
           "out_dir_of", "DETACH_GRACE_S", "summary", "current",
           "output_path"]

DIR = "tool-output"
INDEX = "index.jsonl"
SHELL_INDEX = "shell-index.jsonl"
#: One call's file never grows past this. The head and the tail are kept.
CAP_BYTES = 5 * 1024 * 1024
HEAD_BYTES = 1024 * 1024
TRUNCATION_MARK = "\n[... ohflow kept the head and the tail of this output ...]\n"
#: Output written this long after its call ended marks the call detached: the
#: harness gave control back while the command kept running.
DETACH_GRACE_S = 2.0

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def out_dir_of(attempt_dir: Path) -> Path:
    return Path(attempt_dir) / "logs" / DIR


@dataclass(frozen=True)
class CallEvent:
    """One thing an adapter saw about a tool call.

    kind: "start", "output" or "end". `text` on "output" is new text unless
    `cumulative`, in which case it is all output so far. `text` on "end" is the
    full result, written only when the live capture holds less.
    """

    kind: str
    id: str
    tool: str | None = None
    command: str | None = None
    text: str | None = None
    cumulative: bool = False
    ok: bool | None = None
    exit: int | None = None
    at: float | None = None


@dataclass
class _Open:
    seq: int
    path: Path
    tool: str | None
    command: str | None
    started: float
    size: int = 0
    truncated: bool = False
    last: bytes = b""          # the file's last 64 bytes, for cumulative appends


def _last_bytes(o: "_Open") -> bytes:
    if o.size == 0:
        return b""
    try:
        with o.path.open("rb") as fh:
            fh.seek(max(0, o.size - 64))
            return fh.read(64)
    except OSError:
        return b""


class ToolOutputWriter:
    """The runtime's side of the contract. Not thread-safe; one per attempt."""

    def __init__(self, attempt_dir: Path):
        self.dir = out_dir_of(attempt_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._open: dict[str, _Open] = {}
        self._ended: dict[str, _Open] = {}
        self._seq = 0

    # -------------------------------------------------------------- state

    @property
    def open(self) -> dict[str, dict[str, Any]]:
        """The calls that started and have not ended: id -> tool, command, started."""
        return {cid: {"id": cid, "tool": o.tool, "command": o.command,
                      "started": o.started, "file": o.path.name}
                for cid, o in self._open.items()}

    def oldest_open(self) -> dict[str, Any] | None:
        if not self._open:
            return None
        cid, o = min(self._open.items(), key=lambda kv: kv[1].started)
        return {"id": cid, "tool": o.tool, "command": o.command,
                "started": o.started, "file": o.path.name}

    # -------------------------------------------------------------- events

    def apply(self, event: CallEvent) -> None:
        if event.kind == "start":
            self.start(event.id, event.tool, event.command, at=event.at)
        elif event.kind == "output":
            self.write(event.id, event.text or "", cumulative=event.cumulative)
        elif event.kind == "end":
            self.end(event.id, ok=event.ok, exit=event.exit, text=event.text,
                     at=event.at)

    def start(self, call_id: str, tool: str | None, command: str | None,
              *, at: float | None = None) -> None:
        call_id = str(call_id)
        if call_id in self._open or call_id in self._ended:
            return
        self._seq += 1
        name = f"{self._seq:03d}-{_SAFE.sub('_', call_id)[:60]}.log"
        path = self.dir / name
        path.write_bytes(b"")
        started = time.time() if at is None else float(at)
        self._open[call_id] = _Open(self._seq, path, tool, command, started)
        self._index({"event": "start", "seq": self._seq, "id": call_id,
                     "tool": tool, "command": command, "at": round(started, 3),
                     "file": name})

    def write(self, call_id: str, text: str, *, cumulative: bool = False) -> None:
        o = self._open.get(str(call_id)) or self._ended.get(str(call_id))
        if o is None or not text and not cumulative:
            return
        data = text.encode("utf-8", "replace")
        if cumulative:
            if len(data) == o.size and not o.truncated:
                return
            # Output so far usually extends what is on disk; append the new
            # part then, so a chatty command costs its bytes once, not once
            # per update. A harness that trims its own buffer breaks the
            # prefix, and the file is rewritten whole.
            if (not o.truncated and len(data) > o.size
                    and data[max(0, o.size - 64):o.size] == o.last):
                _write_capped(o, data[o.size:], replace=False)
            else:
                _write_capped(o, data, replace=True)
        else:
            _write_capped(o, data, replace=False)
        o.last = _last_bytes(o)

    def end(self, call_id: str, *, ok: bool | None = None, exit: int | None = None,
            text: str | None = None, at: float | None = None) -> None:
        call_id = str(call_id)
        o = self._open.pop(call_id, None)
        if o is None:
            return
        if text:
            data = text.encode("utf-8", "replace")
            if len(data) > o.size and not o.truncated:
                _write_capped(o, data, replace=True)
        self._ended[call_id] = o
        ended = time.time() if at is None else float(at)
        self._index({"event": "end", "id": call_id, "at": round(ended, 3),
                     "ok": ok, "exit": exit, "bytes": o.size,
                     "truncated": o.truncated})

    def _index(self, record: Mapping[str, Any]) -> None:
        with (self.dir / INDEX).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def _write_capped(o: _Open, data: bytes, *, replace: bool) -> None:
    """Write within CAP_BYTES, keeping the first HEAD_BYTES and the latest tail."""
    if replace:
        if len(data) > CAP_BYTES:
            data = _cap(data)
            o.truncated = True
        o.path.write_bytes(data)
        o.size = len(data)
        return
    if o.size + len(data) <= CAP_BYTES and not o.truncated:
        with o.path.open("ab") as fh:
            fh.write(data)
        o.size += len(data)
        return
    whole = o.path.read_bytes() + data
    if o.truncated:
        mark = TRUNCATION_MARK.encode()
        head, _, rest = whole.partition(mark)
        whole = head + mark + rest[-(CAP_BYTES - len(head) - len(mark)):]
    else:
        whole = _cap(whole)
    o.truncated = True
    o.path.write_bytes(whole)
    o.size = len(whole)


def _cap(data: bytes) -> bytes:
    mark = TRUNCATION_MARK.encode()
    keep = CAP_BYTES - HEAD_BYTES - len(mark)
    return data[:HEAD_BYTES] + mark + data[-keep:]


# ------------------------------------------------------------------ readers


def _records(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _fold(records: Iterable[Mapping[str, Any]], d: Path, source: str) -> list[dict]:
    by_id: dict[str, dict[str, Any]] = {}
    for rec in records:
        cid = str(rec.get("id") or "")
        if not cid:
            continue
        if rec.get("event") == "start":
            by_id.setdefault(cid, {
                "id": cid, "seq": rec.get("seq"), "tool": rec.get("tool"),
                "command": rec.get("command"), "started": rec.get("at"),
                "ended": None, "ok": None, "exit": None,
                "file": rec.get("file"), "truncated": False, "source": source,
            })
        elif rec.get("event") == "end" and cid in by_id:
            by_id[cid].update(ended=rec.get("at"), ok=rec.get("ok"),
                              exit=rec.get("exit"),
                              truncated=bool(rec.get("truncated")))
    out = list(by_id.values())
    for c in out:
        path = d / str(c["file"]) if c.get("file") else None
        if source == "shell" and c.get("command") is None and path is not None:
            cmd = path.with_suffix(".cmd")
            try:
                c["command"] = _shell_command(cmd.read_text(encoding="utf-8",
                                                            errors="replace"))
            except OSError:
                pass
        _stat(c, path)
    return out


def _stat(c: dict[str, Any], path: Path | None) -> None:
    try:
        st = path.stat() if path is not None else None
    except OSError:
        st = None
    c["bytes"] = st.st_size if st else 0
    c["written"] = st.st_mtime if st else None


def _shell_word(text: str, i: int) -> str:
    """The shell word that starts at `text[i]`, with its quoting removed.

    A word is adjacent pieces: '...' (literal), "..." (backslash escapes
    `\\ " $ backquote`) and bare characters, up to unquoted whitespace.
    """
    out = []
    n = len(text)
    while i < n and not text[i].isspace():
        ch = text[i]
        if ch == "'":
            end = text.find("'", i + 1)
            end = n if end < 0 else end
            out.append(text[i + 1:end])
            i = end + 1
        elif ch == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n and text[i + 1] in '\\"$`':
                    i += 1
                out.append(text[i])
                i += 1
            i += 1
        elif ch == "\\" and i + 1 < n:
            out.append(text[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _shell_command(wrapped: str) -> str:
    """The model's command inside claude's wrapped shell line.

    claude runs `source <snapshot> && ... && eval '<cmd>' < /dev/null && pwd -P
    >| <f>`, quoting `<cmd>` with adjacent '...' and "..." pieces (measured
    2026-10-10, 2.1.295: a quote inside the command became `'"'"'`).
    """
    at = wrapped.find("eval ")
    if at < 0:
        return wrapped.strip()
    return _shell_word(wrapped, at + len("eval "))


def calls(attempt_dir: Path) -> list[dict[str, Any]]:
    """Every recorded tool call, oldest first.

    A call the runtime recorded and a shell-wrapper entry for the same command
    are one call: the wrapper's file is the live output, recorded as `live_file`.
    """
    d = out_dir_of(attempt_dir)
    if not d.is_dir():
        return []
    events = _fold(_records(d / INDEX), d, "events")
    shell = _fold(_records(d / SHELL_INDEX), d, "shell")
    _pair(events, shell)
    paired = {c.get("live_of") for c in shell if c.get("live_of")}
    merged = events + [c for c in shell if c["id"] not in paired
                       and not c.get("live_of")]
    merged = [c for c in merged if not c.get("internal")]
    now = time.time()
    for c in merged:
        c["detached"] = _detached(c, now)
    merged.sort(key=lambda c: (c.get("started") or 0.0, c.get("seq") or 0))
    return merged


def _pair(events: list[dict], shell: list[dict]) -> None:
    free = sorted(shell, key=lambda c: c.get("started") or 0.0)
    for c in sorted(events, key=lambda c: c.get("started") or 0.0):
        cmd = (c.get("command") or "").strip()
        if not cmd:
            continue
        for s in free:
            if s.get("live_of"):
                continue
            if (s.get("started") or 0.0) + 1.0 < (c.get("started") or 0.0):
                continue
            if (s.get("command") or "").strip() == cmd:
                s["live_of"] = c["id"]
                c["live_file"] = s["file"]
                c["live_bytes"] = s.get("bytes", 0)
                c["live_written"] = s.get("written")
                c["live_ended"] = s.get("ended")
                break
    # Wrapper entries that no tool call claims are the harness's own shell
    # work (claude snapshots its shell through the same prefix).
    for s in shell:
        if not s.get("live_of"):
            s["internal"] = bool(events)


def _detached(c: Mapping[str, Any], now: float) -> bool:
    ended = c.get("ended")
    if ended is None:
        return False
    if c.get("live_file"):
        live_end = c.get("live_ended")
        written = c.get("live_written")
        if live_end is None:
            return True
        return bool(written and written > float(ended) + DETACH_GRACE_S)
    written = c.get("written")
    return bool(written and written > float(ended) + DETACH_GRACE_S)


def open_calls(attempt_dir: Path) -> list[dict[str, Any]]:
    return [c for c in calls(attempt_dir) if c.get("ended") is None]


def output_path(attempt_dir: Path, call: Mapping[str, Any]) -> Path | None:
    name = call.get("live_file") or call.get("file")
    return out_dir_of(attempt_dir) / str(name) if name else None


def tail(path: Path | None, lines: int = 20, max_bytes: int = 8192) -> list[str]:
    """The last `lines` lines of a capture file, reading at most `max_bytes`."""
    if path is None:
        return []
    try:
        with Path(path).open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read()
    except OSError:
        return []
    out = data.decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
    if size > max_bytes and out:
        out = out[1:]
    while out and not out[-1].strip():
        out.pop()
    return out[-lines:]


def summary(attempt_dir: Path, *, lines: int = 20, max_calls: int = 30) -> dict[str, Any]:
    """What a reader shows: the newest calls, each with its output tail.

    `file` is relative to the attempt directory. The text is not redacted here;
    the dashboard redacts every payload it serves.
    """
    every = calls(attempt_dir)
    shown = every[-max_calls:]
    out = []
    for c in shown:
        path = output_path(attempt_dir, c)
        rel = f"logs/{DIR}/{path.name}" if path is not None else None
        out.append({
            "id": c["id"], "tool": c.get("tool"), "command": c.get("command"),
            "started": c.get("started"), "ended": c.get("ended"),
            "ok": c.get("ok"), "exit": c.get("exit"),
            "open": c.get("ended") is None, "detached": bool(c.get("detached")),
            "truncated": bool(c.get("truncated")),
            "bytes": c.get("live_bytes") if c.get("live_file") else c.get("bytes"),
            "file": rel, "tail": tail(path, lines),
        })
    return {"total": len(every), "shown": len(out), "calls": out}


def current(attempt_dir: Path, *, lines: int = 20,
            now: float | None = None,
            ended_at: float | None = None) -> dict[str, Any] | None:
    """The call a live view shows: the oldest open one, else the newest.

    `since_s` runs to `now`, or to `ended_at` when the attempt has ended: a
    call a killed attempt left open stops where the attempt stopped.
    """
    every = calls(attempt_dir)
    if not every:
        return None
    now = time.time() if now is None else now
    until = now if ended_at is None else min(now, float(ended_at))
    open_ = [c for c in every if c.get("ended") is None]
    c = open_[0] if open_ else every[-1]
    started = c.get("started")
    return {"id": c["id"], "tool": c.get("tool"), "command": c.get("command"),
            "open": c.get("ended") is None, "detached": bool(c.get("detached")),
            "since_s": round(until - float(started), 1) if started else None,
            "ok": c.get("ok"), "exit": c.get("exit"),
            "lines": tail(output_path(attempt_dir, c), lines)}
