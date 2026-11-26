"""Console and log writing that no character can crash.

A Windows console and a redirected pipe both default to the ANSI code page,
cp1252 on this box. Agent output carries box-drawing characters, em dashes and
arrows. `print` raises `UnicodeEncodeError` on those, and the exception kills
the thread that was writing, not just the line. A per-step thread that dies
there abandons the rest of its work.

Two defences, applied in order:

1. `use_utf8` reconfigures a stream to UTF-8 with `errors="replace"`. Every
   entry point calls it once, so the normal path encodes everything.
2. `say` catches an encoding failure anyway and rewrites the line through the
   stream's own encoding with `errors="replace"`. An unmappable character
   becomes `?`. The text is still written and the caller still returns.

Nothing here raises. A closed pipe, a broken stream or an exotic encoding all
end in a silent return, because a log line is never worth a lost run.
"""

from __future__ import annotations

import sys

__all__ = ["use_utf8", "say", "warn", "sanitize"]


def use_utf8(*streams) -> None:
    """Reconfigure the given streams (stdout and stderr by default) to UTF-8.

    Safe to call more than once and safe on a stream that cannot be
    reconfigured, such as one already replaced by a capture object.
    """
    targets = streams or (sys.stdout, sys.stderr)
    for s in targets:
        reconfigure = getattr(s, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def sanitize(text: str, encoding: str) -> str:
    """The text as it survives a round trip through `encoding`, with every
    unmappable character replaced. Used only after a write has already failed."""
    try:
        return text.encode(encoding, "replace").decode(encoding, "replace")
    except Exception:
        return text.encode("ascii", "replace").decode("ascii", "replace")


def say(*parts, file=None, sep: str = " ", end: str = "\n",
        flush: bool = True) -> None:
    """`print` that cannot raise. Same call shape, so it is a drop-in."""
    stream = file if file is not None else sys.stdout
    if stream is None:
        return
    text = sep.join("" if p is None else str(p) for p in parts) + end
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        replaced = sanitize(text, encoding)
        try:
            stream.write(replaced)
        except Exception:
            buffer = getattr(stream, "buffer", None)
            if buffer is None:
                return
            try:
                buffer.write(text.encode("utf-8", "replace"))
            except Exception:
                return
    except Exception:
        return
    if flush:
        try:
            stream.flush()
        except Exception:
            pass


def warn(*parts, **kw) -> None:
    """`say` to stderr."""
    kw.setdefault("file", sys.stderr)
    say(*parts, **kw)
