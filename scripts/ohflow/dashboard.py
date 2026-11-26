"""The live dashboard: one small HTTP server per run, inside the supervisor.

`start(run_dir)` binds `127.0.0.1` on a port the OS picks, serves the page and
its data from a daemon thread, and writes `dashboard.json` so a person or an
agent can find the URL again. `Handle.stop()` closes it.

Why it looks like this:

* **A thread, not a process.** The windowless rule on this box audits every
  process a run starts. A daemon thread inside the supervisor starts none, and
  it dies with the supervisor, so a dashboard can never outlive its run.
* **Port 0 by default.** The OS hands out a free port, so two runs started at
  the same moment never collide. An explicit port is refused when taken,
  rather than shared: Windows lets `SO_REUSEADDR` bind a listening port twice.
* **Fixed GET routes and nothing else.** The server never maps a request
  path to a file, so no request can reach `attempts/NN/pi-agent/auth.json` or
  a `.env`. It accepts no POST: pause, kill and resume would change engine
  state, and the dashboard stays an observer. The live page answers on `/`,
  `/api/read-out` and `/api/agent`; the graph layer in `dashboard_data`
  answers on `/api/workflow`, `/api/plan`, `/api/transcript` and
  `/api/evidence`, and it can also serve a `docs/dashboard-basis` evidence
  packet, which it never writes to. `/api/plan` is the declared plan, read
  once by the page and never polled; a packet has none and answers 404.
* **No token.** Any local process can already read the run directory. What a
  token would not cover is a web page in the viewer's browser reaching the port
  through DNS rebinding, so the `Host` header must name a loopback address.
* **It reads files only.** Every answer comes from `live`, which never touches
  `Engine.state` or the engine lock. A slow page therefore cannot stall a
  transition, and the same server shows a finished or an orphaned run.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import dashboard_data
from . import live
from .proc import pid_alive

__all__ = ["start", "Handle", "HOST", "RECORD", "record_is_live",
           "live_record"]

HOST = "127.0.0.1"
#: Written into the run directory: `url`, `port`, `pid`, `started`.
RECORD = "dashboard.json"
ASSET_ROOT = Path(__file__).resolve().parent
TEMPLATE = ASSET_ROOT / "dashboard.html"
STATIC_ASSETS = {
    "/dashboard.css": (ASSET_ROOT / "dashboard.css", "text/css; charset=utf-8"),
    "/dashboard.js": (ASSET_ROOT / "dashboard.js",
                      "text/javascript; charset=utf-8"),
    "/dashboard_records.js": (ASSET_ROOT / "dashboard_records.js",
                              "text/javascript; charset=utf-8"),
    "/assets/lexend-variable.ttf": (
        ASSET_ROOT / "assets" / "lexend-variable.ttf", "font/ttf"),
}
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "[::1]"})
#: A page that polled this recently is watching the run.
WATCHED_WITHIN_S = 10.0
#: How long `stop` waits for a watching page's next poll. The page polls
#: every 2 s, so one poll always fits.
LINGER_S = 3.0
_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "font-src 'self' data:; img-src data:; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

_page_lock = threading.Lock()
_page_cache: tuple[int, bytes] | None = None


def _page() -> bytes:
    """The template, read again only when it changes on disk."""
    global _page_cache
    stamp = TEMPLATE.stat().st_mtime_ns
    with _page_lock:
        if _page_cache is None or _page_cache[0] != stamp:
            _page_cache = (stamp, TEMPLATE.read_bytes())
        return _page_cache[1]


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    allow_reuse_port = False

    def __init__(self, address, handler, run_dir: Path,
                 supervisor_pid: int | None):
        self.run_dir = run_dir
        self.supervisor_pid = supervisor_pid
        # Set by `Handle.stop`: the exit path's verdict, for a crash or an
        # interrupt the run log cannot name, and the instant stopping began.
        self.final_status: str | None = None
        self.stopping_since: float | None = None
        self.stop_requested = False
        self.last_poll = 0.0
        self.final_served = threading.Event()
        super().__init__(address, handler)

    def handle_error(self, request, client_address) -> None:
        # A browser that drops a connection mid-response is routine. A
        # traceback on the supervisor's console for it is noise in the run log.
        return


class _Handler(BaseHTTPRequestHandler):
    server_version = "ohflow-dashboard"
    sys_version = ""

    def log_message(self, format, *args) -> None:        # noqa: A002
        return                                            # the run log is not an access log

    # ---- responses

    def _send(self, code: int, body: bytes, ctype: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", _CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                          default=str).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _text(self, code: int, text: str, extra=None) -> None:
        self._send(code, (text + "\n").encode("utf-8"),
                   "text/plain; charset=utf-8", extra)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            name = host.split("]", 1)[0] + "]"
        else:
            name = host.rsplit(":", 1)[0]
        return name in _LOOPBACK

    # ---- methods

    def do_GET(self) -> None:                             # noqa: N802
        if not self._host_ok():
            return self._text(403, "this dashboard answers loopback names only")
        parts = urlsplit(self.path)
        run_dir, pid = self.server.run_dir, self.server.supervisor_pid
        try:
            if parts.path == "/":
                return self._send(200, _page(), "text/html; charset=utf-8")
            if parts.path in STATIC_ASSETS:
                path, content_type = STATIC_ASSETS[parts.path]
                try:
                    body = path.read_bytes()
                except OSError:
                    return self._text(404, "not found")
                return self._send(200, body, content_type)
            if parts.path == "/api/read-out":
                began = time.monotonic()
                server = self.server
                final = (server.final_status if server.final_status in (
                    "crashed", "interrupted") else None)
                self._json(200, live.read_out(run_dir, supervisor_pid=pid,
                                              final_status=final))
                server.last_poll = time.monotonic()
                if server.stopping_since is not None \
                        and began >= server.stopping_since:
                    server.final_served.set()
                return None
            if parts.path == "/api/workflow":
                began = time.monotonic()
                server = self.server
                payload = dashboard_data.workflow_data(run_dir)
                # The page polls this route, not `/api/read-out`, so the same
                # watching signal the read-out handler feeds is fed here: a
                # recent poll keeps the server lingering through `stop`, and
                # the poll that began after the stop carries the exit verdict
                # for a run whose run log cannot name it (crash/interrupt).
                final = (server.final_status if server.final_status in (
                    "crashed", "interrupted") else None)
                run = payload.get("run")
                if final and isinstance(run, dict) and run.get("status") in (
                        "running", "starting", "held", "not started",
                        "orphaned"):
                    run["status"] = final
                    run["mode"] = "final"
                self._json(200, payload)
                server.last_poll = time.monotonic()
                if server.stopping_since is not None \
                        and began >= server.stopping_since:
                    server.final_served.set()
                return None
            if parts.path == "/api/plan":
                payload = dashboard_data.plan_data(run_dir)
                if payload is None:
                    return self._text(404, "not found")
                return self._json(200, payload)
            if parts.path == "/api/transcript":
                query = parse_qs(parts.query, keep_blank_values=True)
                coord = (query.get("coord") or [""])[0]
                cursor = (query.get("cursor") or [None])[0]
                try:
                    attempt = int((query.get("attempt") or [""])[0])
                    limit = int((query.get("limit") or [""])[0]) \
                        if (query.get("limit") or [""])[0] else None
                    # `tail=N`: the last N records and a cursor that continues
                    # from the end, for the peek panel's first look.
                    tail = int((query.get("tail") or [""])[0]) \
                        if (query.get("tail") or [""])[0] else None
                except ValueError:
                    return self._text(404, "not found")
                payload = dashboard_data.transcript_data(
                    run_dir, coord, attempt, cursor=cursor, limit=limit,
                    tail=tail)
                if payload is None:
                    return self._text(404, "not found")
                return self._json(200, payload)
            if parts.path == "/api/evidence":
                query = parse_qs(parts.query, keep_blank_values=True)
                coord = (query.get("coord") or [""])[0]
                artifact = (query.get("id") or [None])[0]
                try:
                    attempt = int((query.get("attempt") or [""])[0])
                except ValueError:
                    return self._text(404, "not found")
                payload = dashboard_data.evidence_data(
                    run_dir, coord, attempt, artifact_id=artifact)
                if payload is None:
                    return self._text(404, "not found")
                return self._json(200, payload)
            if parts.path == "/api/agent":
                query = parse_qs(parts.query, keep_blank_values=True)
                coord = (query.get("coord") or [""])[0]
                try:
                    attempt = int((query.get("attempt") or [""])[0])
                    limit = int((query.get("limit") or ["20"])[0])
                except ValueError:
                    return self._text(404, "not found")
                block = live.activity(run_dir, coord, attempt, limit=limit)
                if block is None:
                    return self._text(404, "not found")
                return self._json(200, block)
        except Exception as e:                             # never kill the thread
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        return self._text(404, "not found")

    def _refuse(self) -> None:
        self._text(405, "this dashboard only reads; it accepts GET only",
                   {"Allow": "GET"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _refuse


class Handle:
    """A running dashboard. `url` is what a person opens; `stop()` ends it."""

    def __init__(self, server: _Server, thread: threading.Thread,
                 run_dir: Path):
        self._server = server
        self._thread = thread
        self._stopped = False
        self.run_dir = run_dir
        self.port: int = server.server_address[1]
        self.url = f"http://{HOST}:{self.port}/"
        self.record: Path | None = None

    def stop(self, timeout: float = 5.0, *, final_status: str | None = None,
             linger: float = LINGER_S) -> None:
        """Stop serving, after one last answer to a page that is watching.

        The supervisor stops the server a moment after `run_finished`, and a
        page polling every two seconds would otherwise keep a read-out that
        says `running` and call the end of the run a lost contact. When a page
        asked for a read-out or the workflow graph recently, the server waits
        up to `linger` seconds for its next poll, and that poll sees the final
        state. With no page watching, it stops at once.
        """
        if self._stopped:
            return
        self._stopped = True
        server = self._server
        server.final_status = final_status
        if linger > 0 and server.last_poll and \
                time.monotonic() - server.last_poll < WATCHED_WITHIN_S:
            server.stopping_since = time.monotonic()
            server.final_served.wait(linger)
        server.stop_requested = True
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive() and not self._stopped

    def __enter__(self) -> "Handle":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


def _write_record(run_dir: Path, handle: Handle,
                  supervisor: bool) -> Path:
    record = {
        "url": handle.url, "port": handle.port, "pid": os.getpid(),
        "started": _dt.datetime.now(_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "supervisor": supervisor,
    }
    path = run_dir / RECORD
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def live_record(run_dir: Path) -> dict | None:
    """The `dashboard.json` record when it names a supervisor's dashboard
    still serving, else None.

    `ohflow dashboard` starts nothing for such a run and prints the recorded
    URL instead: a second server would give one run two addresses, and
    overwriting the record would hide the run's own URL behind a viewer that
    stops first.
    """
    try:
        record = json.loads((Path(run_dir) / RECORD).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or not record.get("supervisor"):
        return None
    pid = record.get("pid")
    if not isinstance(pid, int) or pid == os.getpid():
        return None
    return record if pid_alive(pid) else None


def record_is_live(run_dir: Path) -> bool:
    """Whether `dashboard.json` names a supervisor's dashboard still serving."""
    return live_record(run_dir) is not None


def _serve(server: _Server) -> None:
    while not server.stop_requested:
        try:
            server.serve_forever(poll_interval=0.1)
            return
        except OSError:
            if server.stop_requested:
                return
            time.sleep(1.0)


def start(run_dir: Path, port: int = 0, *, supervisor_pid: int | None = None,
          write_record: bool = True) -> Handle:
    """Serve one run directory. Raises OSError when the port cannot be bound.

    `supervisor_pid` says the serving process is the run's supervisor, which
    the page needs before the engine has written `supervisor.pid`.
    """
    run_dir = Path(run_dir).resolve()
    server = _Server((HOST, int(port)), _Handler, run_dir, supervisor_pid)
    thread = threading.Thread(target=_serve, args=(server,),
                              name=f"ohflow-dashboard-{server.server_address[1]}",
                              daemon=True)
    thread.start()
    handle = Handle(server, thread, run_dir)
    # A dashboard-case packet is recorded evidence: no file is added to it,
    # so a reader can hash it before and after a session and match the
    # bytes. A run directory still gets its `dashboard.json`.
    if write_record and dashboard_data.is_packet(run_dir):
        write_record = False
    if write_record and run_dir.is_dir():
        try:
            handle.record = _write_record(run_dir, handle,
                                          supervisor=supervisor_pid is not None)
        except OSError:
            handle.record = None
    return handle
