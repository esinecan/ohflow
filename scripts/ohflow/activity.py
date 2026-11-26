"""What one attempt did, read from its files and shaped for a card.

Each harness executor module owns the parser for its own attempt directory and calls the
shared model here: `Activity` collects the reasoning, tool calls, tokens and
the idle clock, `activity_out` renders them in the one shape the dashboard
reads. Nothing in this module names a harness executor.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

#: Tool calls a card shows by default. The page can ask for more.
DEFAULT_TOOL_CALLS = 8
#: A tool-call summary and an objective fit one line of a card.
SUMMARY_MAX = 120
#: Latest reasoning is a statement of intent, not a transcript.
REASONING_MAX = 200
#: A harness executor that has not yet answered shows this note.
STARTING_NOTE = "starting: no model reply yet"

_ACTIVITY_LOCK = threading.Lock()
_ACTIVITY: dict[str, "Activity"] = {}

# --------------------------------------------------------------------- time


def epoch(value: Any) -> float | None:
    """ISO text, epoch seconds or epoch milliseconds, as epoch seconds.

    pi stamps its session lines in UTC with a `Z`. A naive stamp is read as
    local time.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e11 else v
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def hms(epoch: float | None) -> str | None:
    """`HH:MM:SS` in local time. The viewer sits on the same machine."""
    if epoch is None:
        return None
    return time.strftime("%H:%M:%S", time.localtime(epoch))


def age(now: float, epoch: float | None) -> int | None:
    if epoch is None:
        return None
    return max(0, int(round(now - epoch)))


# ------------------------------------------------------------------ caching


class FileCache:
    """Parsed files keyed on `(mtime, size)`. Safe to share between threads.

    A file caught half-written parses to None under its current key. Its key
    changes when the writer finishes, so the next poll parses it again.
    """

    def __init__(self, limit: int = 4096):
        self._lock = threading.Lock()
        self._items: dict[str, tuple[tuple[int, int], Any]] = {}
        self._limit = limit

    def load(self, path: Path, parse: Callable[[Path], Any]) -> Any:
        try:
            st = path.stat()
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        name = str(path)
        with self._lock:
            hit = self._items.get(name)
        if hit is not None and hit[0] == key:
            return hit[1]
        try:
            value = parse(path)
        except (OSError, ValueError, UnicodeDecodeError):
            value = None
        with self._lock:
            if len(self._items) >= self._limit:
                self._items.clear()
            self._items[name] = (key, value)
        return value


FILES = FileCache()


def read_json(path: Path) -> Any:
    return FILES.load(path, lambda p: json.loads(p.read_text(encoding="utf-8")))


class Tail:
    """The complete lines of one append-only file, from the last byte offset.

    A final line without its newline is left for the next read, because the
    writer may be half-way through it. A file that shrank was truncated or
    replaced, and the reader starts again from the top.
    """

    def __init__(self) -> None:
        self.offset = 0

    def read(self, path: Path) -> tuple[list[bytes], bool]:
        """(new complete lines, whether the file was reset since last time)."""
        try:
            size = path.stat().st_size
        except OSError:
            reset = self.offset > 0
            self.offset = 0
            return [], reset
        reset = False
        if size < self.offset:
            self.offset, reset = 0, True
        if size == self.offset:
            return [], reset
        try:
            with path.open("rb") as fh:
                fh.seek(self.offset)
                data = fh.read(size - self.offset)
        except OSError:
            return [], reset
        end = data.rfind(b"\n")
        if end < 0:
            return [], reset
        self.offset += end + 1
        return [ln for ln in data[:end + 1].splitlines() if ln.strip()], reset


# ------------------------------------------------------------ text shaping


def one_line(text: Any, limit: int = SUMMARY_MAX) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "\u2026"


def first_line(text: Any, limit: int = 200) -> str | None:
    for line in str(text or "").splitlines():
        if line.strip():
            return one_line(line, limit)
    return None


_SENTENCE_END = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"')\]]))\s")


def first_sentence(text: str, limit: int = REASONING_MAX) -> str | None:
    """The first sentence of a paragraph, markdown emphasis dropped."""
    s = re.sub(r"[*_`]{2,}", "", str(text or "")).strip()
    if not s:
        return None
    para = re.split(r"\n\s*\n", s, maxsplit=1)[0]
    para = re.sub(r"\s+", " ", para).strip()
    m = _SENTENCE_END.search(para)
    sentence = para[:m.start()].strip() if m else para
    return one_line(sentence, limit)


def content_text(content: Any) -> str:
    """The text of a message `content` list, or of a plain string."""
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)



def _slashed(p: str) -> str:
    """Forward slashes, no trailing slash, Git Bash `/c/x` read as `c:/x`."""
    s = str(p).replace("\\", "/").rstrip("/")
    m = re.match(r"^/([a-zA-Z])(/|$)", s)
    if m:
        s = f"{m.group(1)}:{s[2:]}"
    return s


def _norm_path(p: str) -> str:
    return _slashed(p).lower()


def _rel(path: str, root: str | None) -> str:
    """A path relative to the worktree root, when it sits inside it."""
    plain = str(path).replace("\\", "/")
    if not root:
        return plain
    shown = _slashed(path)
    r = _norm_path(root)
    if shown.lower() == r:
        return "."
    if shown.lower().startswith(r + "/"):
        return shown[len(r) + 1:]
    return plain


_CD_PREFIX = re.compile(
    r"""^\s*cd\s+(?:"([^"]*)"|'([^']*)'|(\S+))\s*(?:&&|;)\s*""")


def _strip_cd(command: str, root: str | None) -> str:
    """Drop a leading `cd "<worktree>" &&`: it says nothing on a card."""
    m = _CD_PREFIX.match(command or "")
    if m and root:
        target = m.group(1) or m.group(2) or m.group(3) or ""
        if _norm_path(target) == _norm_path(root):
            return command[m.end():]
    return command or ""


def _compact(value: Any, limit: int = 600) -> str:
    try:
        s = json.dumps(value, separators=(",", ":"), ensure_ascii=False,
                       default=str)
    except (TypeError, ValueError):
        s = str(value)
    return s if len(s) <= limit else s[:limit]


def _trim_args(args: Any) -> Any:
    """Keep what a summary needs and drop file bodies a session may carry."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (TypeError, ValueError):
            return args[:600]
    if not isinstance(args, dict):
        return args
    out = {}
    for k, v in args.items():
        if k == "kind":
            continue
        if isinstance(v, str):
            out[k] = v[:600]
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = _compact(v, 200)
    return out


_SHELL_TOOLS = frozenset({"bash", "terminal", "powershell"})
_PATH_TOOLS = frozenset({"read", "ls", "edit", "write", "grep", "find"})


def _summarize(call: dict, root: str | None) -> str:
    """One line per spec §7.4. A recorded `hint` wins when it is not empty."""
    name = call.get("name") or "?"
    args = call.get("args")
    hint = call.get("hint")
    if isinstance(hint, str) and hint.strip():
        text = hint
    elif not isinstance(args, dict):
        text = _compact(args)
    elif name in _SHELL_TOOLS and isinstance(args.get("command"), str):
        text = _strip_cd(args["command"], root)
    elif name in _PATH_TOOLS and isinstance(args.get("path"), str):
        text = _rel(args["path"], root)
    elif name == "file_editor" and isinstance(args.get("path"), str):
        text = f"{args.get('command') or ''} {_rel(args['path'], root)}"
    elif name == "finish" and isinstance(args.get("message"), str):
        text = args["message"]
    else:
        text = _compact(args)
    return one_line(text)




TOKEN_FIELDS = ("input", "output", "cache_read", "reasoning")


def int_of(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


class Activity:
    """What one attempt did, built up incrementally from its files."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._clear()

    def _clear(self) -> None:
        self.calls: dict[str, dict] = {}
        self.order: list[str] = []
        self.reasoning: dict | None = None
        self.tokens = {k: 0 for k in TOKEN_FIELDS}
        self.llm_calls = 0
        self.last_at: float | None = None
        self.replied = False
        self.last_error: str | None = None
        # The one file a harness executor tails, and where it stopped reading.
        self.session: Path | None = None
        self.tail = Tail()
        # Files a harness executor parses once each.
        self.seen: set[str] = set()
        # Anything else a harness executor parser keeps between polls.
        self.scratch: dict[str, Any] = {}

    def reset(self) -> None:
        """Forget everything but the lock, which a caller may be holding."""
        self._clear()

    def touch(self, at: float | None) -> None:
        if at is not None and (self.last_at is None or at > self.last_at):
            self.last_at = at

    def said(self, text: str | None, at: float | None, source: str) -> None:
        sentence = first_sentence(text or "")
        if sentence:
            self.reasoning = {"text": sentence, "at": at, "source": source}

    def add_call(self, cid: str | None, at: float | None, name: str,
                 args: Any, hint: str | None = None) -> None:
        cid = cid or f"call-{len(self.order)}"
        if cid in self.calls:
            return
        self.calls[cid] = {"id": cid, "at": at, "name": name,
                           "args": _trim_args(args), "hint": hint}
        self.order.append(cid)

    def add_result(self, cid: str | None, at: float | None, ok: bool,
                   text: str) -> None:
        call = self.calls.get(cid or "")
        if call is None or call.get("result") is not None:
            return
        call["result"] = {"at": at, "ok": ok, "first_line": first_line(text)}


def model_for(attempt_dir: Path) -> Activity:
    key = str(attempt_dir)
    with _ACTIVITY_LOCK:
        model = _ACTIVITY.get(key)
        if model is None:
            if len(_ACTIVITY) > 1024:
                _ACTIVITY.clear()
            model = _ACTIVITY[key] = Activity()
        return model


def worktree_root(attempt_dir: Path) -> str | None:
    spec = read_json(attempt_dir / "spec.json")
    if isinstance(spec, dict) and isinstance(spec.get("workspace"), str):
        return spec["workspace"]
    return None


def _render_call(call: dict, root: str | None) -> dict:
    res = call.get("result")
    start = call.get("at")
    duration = None
    if res and res.get("at") is not None and start is not None:
        duration = round(max(0.0, res["at"] - start), 1)
    return {
        "id": call["id"],
        "at": hms(start),
        "name": call.get("name"),
        "summary": _summarize(call, root),
        "duration_s": duration,
        "ok": res.get("ok") if res else None,
        "first_line": res.get("first_line") if res else None,
        "pending": res is None,
    }


def activity_out(model: Activity, *, harness_executor: str, root: str | None,
                 now: float, running: bool, limit: int,
                 fallback_at: float | None, note: str | None = None) -> dict:
    calls = [model.calls[cid] for cid in model.order]
    rendered = [_render_call(c, root) for c in reversed(calls)]
    running_tool = None
    if running:
        for item, call in zip(rendered, reversed(calls)):
            if item["pending"]:
                running_tool = {"name": item["name"], "summary": item["summary"],
                                "since_s": age(now, call.get("at")),
                                "id": item["id"]}
                break
    listed = [r for r in rendered
              if running_tool is None or r["id"] != running_tool["id"]]
    last = model.last_at if model.last_at is not None else fallback_at
    reasoning = None
    if model.reasoning:
        reasoning = {"text": model.reasoning["text"],
                     "at": iso(model.reasoning["at"]),
                     "age_s": age(now, model.reasoning["at"]),
                     "source": model.reasoning["source"]}
    return {
        "harness_executor": harness_executor,
        "running_tool": running_tool,
        "tool_calls": listed[:max(0, limit)],
        "tool_calls_total": len(calls),
        "latest_reasoning": reasoning,
        "idle_s": age(now, last),
        "tokens": dict(model.tokens),
        "llm_calls": model.llm_calls,
        "note": note,
        "last_error": model.last_error,
    }
