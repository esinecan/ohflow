"""The pi-cloud Worker's event stream on stdout, reconnected in one process.

Run by path from `ohflow.pi_cloud_runner`; no ohflow import, standard library
only. `python pi_cloud_client.py events --url <url> --name <name>
--operation <op>` opens `GET <url>/attempts/<name>/events?operationId=<op>`,
copies each NDJSON line to stdout flushed per line, and keeps the stream's
own rules:

- a beat never reaches stdout, and neither does a line this process already
  printed: `message_end` and `tool_execution_end` by their `entryId`,
  `tool_execution_start` by its `toolCallId`. Every request replays from the
  start, so a reconnection would otherwise duplicate half a transcript in the
  event log.
- `pi_cloud_end` exits 0; `pi_cloud_error` exits 1. A stream that ends without
  either line - the client dropped, the Worker restarted - is retried inside
  this same process, because the Durable Object holds the conversation and a
  fresh connection replays it.
- HTTP 408, 429 and 5xx are retried like a dropped stream. Any other 4xx is a
  verdict: the client prints one `pi_cloud_error` line naming the status and
  the body, and exits 1.
- the lost-Worker clock counts from the last contact: a response opening
  resets it, and so does every line read from the stream, beats included.
  When neither a line nor an opened response has arrived for
  `OHFLOW_PI_CLOUD_LOST_S` seconds (default 900), the Worker is gone for
  good: a reason goes to stderr and the process exits 3, which the runner
  records as `host_lost` and the engine answers with a reattach of the same
  attempt. A stream that stayed quiet-but-healthy - beats arriving - for
  longer than the bound and then dropped is therefore an ordinary drop: its
  clock is fresh, and the first reconnect proceeds.

The token is read from `PI_CLOUD_TOKEN` and travels only in the
`Authorization` header: never in an argv, a log line or an error message.
Cloudflare answers error 1010 with HTTP 403 to Python's default `User-Agent`,
so every request sets the Worker's own.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

EXIT_END = 0
EXIT_FAULT = 1
EXIT_NO_TOKEN = 2
EXIT_LOST = 3

TOKEN_ENV = "PI_CLOUD_TOKEN"
RETRY_ENV = "OHFLOW_PI_CLOUD_RETRY_S"
LOST_ENV = "OHFLOW_PI_CLOUD_LOST_S"
#: The same string is defined as `USER_AGENT` in `ohflow/pi_cloud_runner.py`,
#: and the two cannot share one definition: this module is run by path and
#: imports nothing from ohflow by design. Change both together.
USER_AGENT = "ohflow-pi-cloud/1"

READ_TIMEOUT_S = 60.0
DEFAULT_RETRY_S = 5.0
DEFAULT_LOST_S = 900.0
END = "pi_cloud_end"
FAULT = "pi_cloud_error"
BEAT = "pi_cloud_beat"


def read_token() -> str:
    """The Worker's bearer token from `PI_CLOUD_TOKEN`, without a leading byte
    order mark and without the whitespace around it. A token copied from a
    file a Windows editor wrote carries the mark, and the header cannot encode
    it."""
    return (os.environ.get(TOKEN_ENV) or "").lstrip("\ufeff").strip()


def _env_seconds(name: str, default: float) -> float:
    """One tunable from the environment, or its default when unset or odd."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def events_url(base: str, name: str, operation: str) -> str:
    """The events route; the attempt's name is percent-encoded, `/` included."""
    return (f"{base.rstrip('/')}/attempts/"
            f"{urllib.parse.quote(name, safe='')}/events"
            f"?operationId={urllib.parse.quote(operation, safe='')}")


class StreamDropped(Exception):
    """The connection ended or failed before `pi_cloud_end` or a fault line."""


class _Printed:
    """What this process already put on stdout, so a replay duplicates nothing.

    The Worker replays the whole transcript on every connection, live turns
    and replayed turns carrying the same `entryId`; a tool-call start built
    from a stored entry carries the same `toolCallId` as its end. One set per
    process lifetime, not per connection, is what makes a reconnect seamless.
    """

    def __init__(self) -> None:
        self.entries: set = set()
        self.starts: set = set()

    def keep(self, event: dict) -> bool:
        kind = event.get("type")
        if kind == BEAT:
            return False
        if kind in ("message_end", "tool_execution_end"):
            entry = event.get("entryId")
            if entry is not None:
                if entry in self.entries:
                    return False
                self.entries.add(entry)
            return True
        if kind == "tool_execution_start":
            call = event.get("toolCallId")
            if call is not None:
                if call in self.starts:
                    return False
                self.starts.add(call)
            return True
        return True


def _emit(line: str) -> None:
    sys.stdout.write(line.rstrip("\n") + "\n")
    sys.stdout.flush()


def _stream_once(url: str, token: str, printed: _Printed,
                 on_success) -> str:
    """One connection. `"end"` or `"fault"` when the operation settled.

    Raises `StreamDropped` when the stream ended without either line, or the
    connection failed: the caller reconnects. `on_success` runs once the HTTP
    response opened and again on every line read from the stream, beats
    included, and each run is what resets the lost-Worker clock: contact, not
    connection age, is what the clock measures.
    """
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "User-Agent": USER_AGENT})
    try:
        response = urllib.request.urlopen(request, timeout=READ_TIMEOUT_S)
    except urllib.error.HTTPError as error:
        if error.code in (408, 429) or error.code >= 500:
            raise StreamDropped(f"HTTP {error.code} from the events route") from None
        # A verdict the Worker will not change on a retry: one fault line.
        try:
            body = error.read(4096).decode("utf-8", "replace")
        except (OSError, ValueError):
            body = ""
        _emit(json.dumps({"type": FAULT, "name": "HTTPError",
                          "message": f"HTTP {error.code}: {body[:300]}"}))
        return "fault"
    except (urllib.error.URLError, OSError, TimeoutError,
            http.client.HTTPException) as error:
        raise StreamDropped(f"{type(error).__name__}: {error}") from None
    with response:
        on_success()
        try:
            for raw in response:
                on_success()
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = None
                kind = event.get("type") if isinstance(event, dict) else None
                if kind == END or kind == FAULT:
                    _emit(line)
                    return "end" if kind == END else "fault"
                if event is None or printed.keep(event):
                    _emit(line)
        except (urllib.error.URLError, OSError, TimeoutError,
                http.client.HTTPException) as error:
            raise StreamDropped(f"{type(error).__name__}: {error}") from None
    raise StreamDropped("the event stream ended without " + END)


def follow(url: str, token: str, retry_s: float, lost_s: float) -> int:
    """Stream until the operation settles, reconnecting inside this process."""
    printed = _Printed()
    last_success = time.monotonic()

    def mark_success() -> None:
        nonlocal last_success
        last_success = time.monotonic()

    while True:
        try:
            settled = _stream_once(url, token, printed, mark_success)
        except StreamDropped as dropped:
            quiet_for = time.monotonic() - last_success
            if quiet_for >= lost_s:
                sys.stderr.write(
                    f"pi_cloud_client: no line and no opened response from "
                    f"{url} for {round(quiet_for)} s ({dropped}); the "
                    f"attempt continues as a reattach\n")
                return EXIT_LOST
            time.sleep(retry_s)
            continue
        return EXIT_END if settled == "end" else EXIT_FAULT


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pi_cloud_client.py",
        description="copy one pi-cloud attempt's event stream to stdout")
    verbs = parser.add_subparsers(dest="verb", required=True)
    events = verbs.add_parser(
        "events", help="stream one attempt's events until the operation settles")
    events.add_argument("--url", required=True, help="the Worker's base URL")
    events.add_argument("--name", required=True,
                        help="the Durable Object's name, the attempt key")
    events.add_argument("--operation", required=True, help="the operation id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = read_token()
    if not token:
        sys.stderr.write(f"{TOKEN_ENV} is empty or unset; the pi-cloud client "
                         f"reads the Worker's bearer token from it\n")
        return EXIT_NO_TOKEN
    url = events_url(args.url, args.name, args.operation)
    return follow(url, token,
                  _env_seconds(RETRY_ENV, DEFAULT_RETRY_S),
                  _env_seconds(LOST_ENV, DEFAULT_LOST_S))


if __name__ == "__main__":
    raise SystemExit(main())
