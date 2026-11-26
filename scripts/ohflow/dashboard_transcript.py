"""Bounded, source-bound primitives for dashboard transcript paging.

The data adapters live in :mod:`ohflow.dashboard_data`; this module owns the
part that must be format-independent: opaque cursor integrity, source/prefix
signatures, and lossless continuation envelopes for unusually large logical
records.  It performs no writes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

CURSOR_VERSION = 2
MAX_CURSOR_CHARS = 4096

# A normal record is returned in its structured form.  Larger records are
# encoded as JSON continuation chunks so the original normalized record can
# be reconstructed byte-for-byte at the JSON value level without an unbounded
# response or DOM node.
INLINE_RECORD_CHARS = 32_768
CONTINUATION_CHARS = 16_384
PAGE_CONTENT_CHARS = 131_072

# A cursor must detect a change at every byte it claims to have consumed.
# Validation therefore streams the complete consumed prefix through SHA-256.
# This is linear in the cursor offset on every poll, but
# it avoids parsing/normalizing any record outside the requested page and uses
# constant memory.  Sampling or metadata alone cannot provide this guarantee.
HASH_CHUNK_BYTES = 64 * 1024


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _checksum(payload: dict) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()[:24]


def encode_cursor(state: dict) -> str:
    """Encode one cursor with a corruption/tamper checksum."""
    payload = dict(state)
    payload["v"] = CURSOR_VERSION
    wrapped = {"p": payload, "h": _checksum(payload)}
    return base64.urlsafe_b64encode(_json_bytes(wrapped)).decode(
        "ascii").rstrip("=")


def decode_cursor(text: str | None) -> tuple[dict | None, str | None]:
    """Decode a cursor, returning a diagnostic instead of trusting bad data."""
    if text is None or text == "":
        return None, None
    if not isinstance(text, str) or len(text) > MAX_CURSOR_CHARS:
        return None, "cursor is invalid or too large; restarted at the beginning"
    try:
        pad = "=" * (-len(text) % 4)
        wrapped = json.loads(base64.b64decode(
            (text + pad).encode("ascii"), altchars=b"-_", validate=True))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None, "cursor is invalid or tampered; restarted at the beginning"
    if not isinstance(wrapped, dict) or not isinstance(wrapped.get("p"), dict):
        return None, "cursor is invalid or tampered; restarted at the beginning"
    payload = wrapped["p"]
    if wrapped.get("h") != _checksum(payload) \
            or payload.get("v") != CURSOR_VERSION:
        return None, "cursor is invalid, stale, or tampered; restarted at the beginning"
    ints = (payload.get("o"), payload.get("l"), payload.get("f"),
            payload.get("q"), payload.get("n"))
    if not all(isinstance(value, int) and value >= 0 for value in ints):
        return None, "cursor contains out-of-range positions; restarted at the beginning"
    for key in ("b", "s", "i", "g"):
        if not isinstance(payload.get(key), str) or len(payload[key]) > 256:
            return None, "cursor has an invalid source binding; restarted at the beginning"
    record_hash = payload.get("r")
    if record_hash is not None and (not isinstance(record_hash, str)
                                    or len(record_hash) > 128):
        return None, "cursor has an invalid continuation; restarted at the beginning"
    return payload, None


def source_binding(root: Path, coord: str, attempt: int, fmt: str,
                   source_name: str) -> str:
    """Stable binding to the selected run, coordinate, attempt and source."""
    raw = "\0".join((str(Path(root).resolve()), coord, str(attempt), fmt,
                     source_name)).encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:24]


def file_identity(path: Path) -> str:
    """Filesystem identity that survives append but changes on replacement."""
    stat = path.stat()
    raw = f"{stat.st_dev}:{stat.st_ino}".encode("ascii", "replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def _prefix_hasher(binding: str, length: int):
    """Seed a prefix digest with its source/run/coord/attempt binding."""
    digest = hashlib.sha256()
    digest.update(_json_bytes(["ohflow-prefix-sha256/1", binding, length]))
    return digest


def bytes_prefix_signature(data: bytes, length: int, binding: str) -> str:
    """SHA-256 of every byte before ``length``, bound to its source."""
    length = max(0, min(int(length), len(data)))
    digest = _prefix_hasher(binding, length)
    view = memoryview(data)
    for pos in range(0, length, HASH_CHUNK_BYTES):
        digest.update(view[pos:min(length, pos + HASH_CHUNK_BYTES)])
    return digest.hexdigest()


def file_prefix_signature(path: Path, length: int, binding: str) -> str:
    """Stream SHA-256 over the complete consumed file prefix."""
    size = path.stat().st_size
    length = max(0, min(int(length), size))
    digest = _prefix_hasher(binding, length)
    remaining = length
    with path.open("rb") as fh:
        while remaining:
            chunk = fh.read(min(HASH_CHUNK_BYTES, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    if remaining:
        digest.update(b"!short-prefix")
    return digest.hexdigest()


def record_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:24]





def normalized_json(record: dict) -> str:
    """Canonical lossless JSON text used by the continuation contract."""
    return json.dumps(record, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def continuation(record: dict, offset: int = 0) -> tuple[dict, int | None]:
    """Return one bounded continuation envelope and its next character offset.

    The caller only uses this for records larger than ``INLINE_RECORD_CHARS``.
    Concatenating ``continuation.data`` for the same ``id`` and JSON-decoding
    the result yields the complete normalized record.
    """
    encoded = normalized_json(record)
    offset = max(0, min(int(offset), len(encoded)))
    end = min(len(encoded), offset + CONTINUATION_CHARS)
    envelope = {
        "id": record.get("id"),
        "source": record.get("source"),
        "ts": record.get("ts"),
        "type": record.get("type"),
        "role": record.get("role"),
        "blocks": [],
        "record_complete": False,
        "continuation": {
            "schema": "ohflow.record-json/1",
            "record_id": record.get("id"),
            "offset": offset,
            "next_offset": end,
            "total_chars": len(encoded),
            "data": encoded[offset:end],
            "complete": end == len(encoded),
        },
    }
    return envelope, (None if end == len(encoded) else end)
