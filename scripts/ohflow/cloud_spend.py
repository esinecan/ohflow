"""What Cloudflare bills for cloud work.

A pi-cloud attempt runs in its own Durable Object, and the object runs one
container. The Worker reports the seconds its container ran and the instance
type in `pi_cloud_end`, and `attempt_infra` prices that at Cloudflare's list
rates as the attempt's `infra_cost`. Containers bill the instance's provisioned
memory and disk for every running second, and CPU for active use only.

`check_run` reads Cloudflare's own container meters for the run's objects
through the GraphQL Analytics API and writes `cloudflare.json` into the run
directory: billed time and price per attempt, and a flag on each object
billed for container time its attempt did not report. `account_window` reads
the same meters for the whole account over a time window, for Cloudflare work
that runs outside ohflow.

The credential is `CLOUDFLARE_API_TOKEN` (Account Analytics Read), else the
token `wrangler auth token --json` prints. The account is
`CLOUDFLARE_ACCOUNT_ID`, else the only account the token can see. The meters
lag the containers by a few minutes, so a check made at run end can miss the
last minutes; `cloud-spend --run DIR` repeats it later.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

__all__ = ["PRICES_READ", "INSTANCES", "container_cost", "attempt_infra",
           "pi_cloud_attempts", "check_run", "account_window", "read_check",
           "report_lines", "main"]

PRICES_READ = "2026-11-14"
PRICES_URL = "https://developers.cloudflare.com/containers/pricing/"
MEMORY_USD_PER_GIB_S = 0.0000025
CPU_USD_PER_VCPU_S = 0.000020
DISK_USD_PER_GB_S = 0.00000007
INCLUDED_MEMORY_GIB_H = 25.0
INCLUDED_DISK_GB_H = 200.0
INCLUDED_CPU_VCPU_MIN = 375.0

INSTANCES: dict[str, tuple[float, float, float]] = {
    "lite": (1 / 16, 0.25, 2.0),
    "basic": (0.25, 1.0, 4.0),
    "standard-1": (0.5, 4.0, 8.0),
    "standard-2": (1.0, 6.0, 12.0),
    "standard-3": (2.0, 8.0, 16.0),
    "standard-4": (4.0, 12.0, 20.0),
}

CHECK_FILE = "cloudflare.json"
API = "https://api.cloudflare.com/client/v4"
USER_AGENT = "ohflow-cloud-spend/1"
HTTP_TIMEOUT_S = 30.0
WRANGLER_TIMEOUT_S = 90.0
LAG_S = 600.0
TOLERANCE_S = 120.0
TOLERANCE_SHARE = 0.2
MAX_WINDOW_DAYS = 30
GIB = float(1 << 30)

Fetch = Callable[[str, str, Mapping[str, str], bytes | None], Any]


def container_cost(instance: str | None, seconds: Any) -> float | None:
    if instance not in INSTANCES or not isinstance(seconds, (int, float)):
        return None
    _, memory_gib, disk_gb = INSTANCES[instance]
    return round(seconds * (memory_gib * MEMORY_USD_PER_GIB_S
                            + disk_gb * DISK_USD_PER_GB_S), 6)


def attempt_infra(start: Mapping[str, Any] | None,
                  container: Mapping[str, Any] | None) -> tuple[dict[str, Any] | None, float | None]:
    start = start or {}
    if not container and not start.get("durable_object_id"):
        return None, None
    container = container or {}
    instance = container.get("instance") or start.get("instance")
    seconds = container.get("seconds")
    cost = container_cost(instance, seconds)
    return ({"provider": "cloudflare",
             "durable_object_id": container.get("durable_object_id")
             or start.get("durable_object_id"),
             "instance": instance, "container_seconds": seconds,
             "launches": container.get("launches"),
             "stopped_at_end": container.get("stopped"),
             "priced": "list rates read " + PRICES_READ + ", memory and disk"},
            cost)


def _utc(epoch: float) -> str:
    return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _start_line(attempt_dir: Path) -> dict[str, Any] | None:
    log = attempt_dir / "logs" / "pi-cloud-events.jsonl"
    try:
        with log.open("r", encoding="utf-8") as handle:
            for raw in handle:
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("type") == "pi_cloud_start":
                    return event
    except OSError:
        return None
    return None


def pi_cloud_attempts(run_dir: Path) -> list[dict[str, Any]]:
    run_dir = Path(run_dir)
    found: list[dict[str, Any]] = []
    for remote_file in sorted(run_dir.glob("phases/*/*/attempts/*/remote.json")):
        attempt_dir = remote_file.parent
        remote = _read_json(remote_file) or {}
        result = _read_json(attempt_dir / "result.json") or {}
        cloud = result.get("pi_cloud") if isinstance(result, dict) else None
        if cloud is None and "pi-cloud" not in str(remote.get("branch") or ""):
            continue
        infra = (result.get("infra") or {}) if isinstance(result, dict) else {}
        start = _start_line(attempt_dir) or {}
        object_id = infra.get("durable_object_id") or start.get("durable_object_id")
        result_file = attempt_dir / "result.json"
        found.append({
            "dir": str(attempt_dir.relative_to(run_dir)).replace("\\", "/"),
            "coord": result.get("coord"), "attempt": result.get("attempt"),
            "key": remote.get("key"), "durable_object_id": object_id,
            "instance": infra.get("instance") or start.get("instance"),
            "reported_seconds": infra.get("container_seconds"),
            "reported_usd": result.get("infra_cost"),
            "launched_at": remote_file.stat().st_mtime,
            "ended_at": result_file.stat().st_mtime if result_file.is_file() else None,
        })
    return found


def _wrangler_token() -> tuple[str | None, str | None]:
    exe = shutil.which("wrangler")
    if not exe:
        return None, "no CLOUDFLARE_API_TOKEN and no wrangler on PATH"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        done = subprocess.run([exe, "auth", "token", "--json"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=WRANGLER_TIMEOUT_S, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"wrangler auth token failed: {type(e).__name__}"
    text = done.stdout or ""
    start = text.find("{")
    try:
        data = json.loads(text[start:]) if start >= 0 else {}
    except ValueError:
        data = {}
    token = data.get("token") if isinstance(data, dict) else None
    if done.returncode != 0 or not token:
        return None, (f"wrangler auth token gave no token (exit {done.returncode}); "
                      f"run `wrangler login`")
    return str(token), None


def _http(method: str, url: str, headers: Mapping[str, str],
          body: bytes | None) -> Any:
    request = urllib.request.Request(url, data=body, method=method,
                                     headers=dict(headers))
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


class _Client:
    def __init__(self, fetch: Fetch | None = None, token: str | None = None,
                 account: str | None = None):
        self.fetch = fetch or _http
        self.token = token
        self.account = account

    def open(self) -> str | None:
        if not self.token:
            self.token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not self.token:
            self.token, problem = _wrangler_token()
            if problem:
                return problem
        if not self.account:
            self.account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        if not self.account:
            try:
                answer = self.fetch("GET", API + "/accounts", self._headers(), None)
            except (urllib.error.URLError, OSError, ValueError) as e:
                return f"the Cloudflare API refused the account list: {e}"
            accounts = [a.get("id") for a in (answer or {}).get("result") or []]
            if len(accounts) != 1:
                return (f"the token sees {len(accounts)} accounts; set "
                        f"CLOUDFLARE_ACCOUNT_ID")
            self.account = accounts[0]
        return None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "User-Agent": USER_AGENT,
                "Content-Type": "application/json"}

    def containers(self, since: str, until: str, ids: list[str] | None,
                   by: str = "durableObjectId") -> list[dict[str, Any]]:
        where = f'datetime_geq: "{since}", datetime_leq: "{until}"'
        if ids is not None:
            where += ", durableObjectId_in: " + json.dumps(ids)
        query = ('{ viewer { accounts(filter: {accountTag: "%s"}) { '
                 'containersMetricsAdaptiveGroups(limit: 10000, filter: {%s}) { '
                 'sum { allocatedMemory allocatedDisk cpuTimeSec } '
                 'dimensions { %s } } } } }') % (self.account, where, by)
        body = json.dumps({"query": query}).encode("utf-8")
        answer = self.fetch("POST", API + "/graphql", self._headers(), body)
        errors = (answer or {}).get("errors")
        if errors:
            raise ValueError("; ".join(str(e.get("message")) for e in errors))
        accounts = ((answer or {}).get("data") or {}).get("viewer", {}).get("accounts") or []
        return (accounts[0].get("containersMetricsAdaptiveGroups") or []) if accounts else []


def _billed(group: Mapping[str, Any]) -> dict[str, float]:
    total = group.get("sum") or {}
    memory = float(total.get("allocatedMemory") or 0) / GIB
    disk = float(total.get("allocatedDisk") or 0) / 1e9
    cpu = float(total.get("cpuTimeSec") or 0)
    usd = (memory * MEMORY_USD_PER_GIB_S + disk * DISK_USD_PER_GB_S
           + cpu * CPU_USD_PER_VCPU_S)
    return {"memory_gib_s": round(memory, 1), "disk_gb_s": round(disk, 1),
            "cpu_s": round(cpu, 1), "usd": round(usd, 6)}


def _flag(row: Mapping[str, Any]) -> str | None:
    billed_s = row.get("billed_seconds")
    reported = row.get("reported_seconds")
    if billed_s is None or billed_s <= 0:
        return None
    if reported is None:
        return (f"billed {billed_s:.0f} s of container time that the attempt "
                f"never reported")
    if billed_s - reported > max(TOLERANCE_S, TOLERANCE_SHARE * reported):
        return (f"billed {billed_s:.0f} s against {reported:.0f} s reported: "
                f"the container ran on after its step")
    return None


def check_run(run_dir: Path, *, now: float | None = None,
              fetch: Fetch | None = None, token: str | None = None,
              account: str | None = None) -> dict[str, Any] | None:
    run_dir = Path(run_dir)
    attempts = pi_cloud_attempts(run_dir)
    if not attempts:
        return None
    now = now if now is not None else _dt.datetime.now(_dt.timezone.utc).timestamp()
    first = min(a["launched_at"] for a in attempts) - 3600
    first = max(first, now - MAX_WINDOW_DAYS * 86400)
    since, until = _utc(first), _utc(now)
    reported_usd = round(sum(a["reported_usd"] or 0 for a in attempts), 6)
    out: dict[str, Any] = {
        "checked_at": until, "since": since, "until": until,
        "prices_read": PRICES_READ, "prices_url": PRICES_URL,
        "reported_usd": reported_usd, "billed_usd": None, "error": None,
        "lag_note": None, "attempts": [], "flags": [],
    }
    client = _Client(fetch, token, account)
    ids = sorted({a["durable_object_id"] for a in attempts if a["durable_object_id"]})
    problem = client.open()
    groups: dict[str, dict[str, Any]] = {}
    if problem is None and ids:
        try:
            for group in client.containers(since, until, ids):
                object_id = (group.get("dimensions") or {}).get("durableObjectId")
                if object_id:
                    groups[object_id] = group
        except (urllib.error.URLError, OSError, ValueError) as e:
            problem = f"the container meters could not be read: {e}"
    out["error"] = problem
    billed_total = 0.0
    for a in attempts:
        row = {k: a[k] for k in ("dir", "coord", "attempt", "durable_object_id",
                                 "instance", "reported_seconds", "reported_usd")}
        group = groups.get(a["durable_object_id"] or "")
        if problem is None and a["durable_object_id"]:
            billed = _billed(group or {})
            memory_gib = INSTANCES.get(a["instance"] or "standard-1", (0, 4.0, 0))[1]
            row.update(billed=billed,
                       billed_seconds=round(billed["memory_gib_s"] / memory_gib, 1))
            billed_total += billed["usd"]
            flag = _flag(row)
            if flag:
                out["flags"].append(f"`{a['dir']}`: {flag}")
        out["attempts"].append(row)
    if problem is None:
        out["billed_usd"] = round(billed_total, 6)
        ends = [a["ended_at"] for a in attempts]
        if None in ends or now - max(ends) < LAG_S:
            out["lag_note"] = (f"Cloudflare's meters lag by a few minutes, so this "
                               f"is the bill so far; repeat with `cloud-spend --run "
                               f"{run_dir}` after {_utc(now + LAG_S)}")
    (run_dir / CHECK_FILE).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def read_check(run_dir: Path) -> dict[str, Any] | None:
    data = _read_json(Path(run_dir) / CHECK_FILE)
    return data if isinstance(data, dict) else None


def _usd(value: Any) -> str:
    return f"${value:.4f}" if isinstance(value, (int, float)) else "-"


def report_lines(check: Mapping[str, Any]) -> list[str]:
    lines = [f"Container time at Cloudflare list rates (read {check.get('prices_read')}), "
             f"checked {check.get('checked_at')}: {_usd(check.get('reported_usd'))} "
             f"reported by the Worker, {_usd(check.get('billed_usd'))} billed by "
             f"Cloudflare's meters. The Workers Paid plan includes "
             f"{INCLUDED_MEMORY_GIB_H:.0f} GiB-hours of memory a month, so a "
             f"small run is usually inside it."]
    if check.get("error"):
        lines.append(f"The meters were not read: {check['error']}.")
    for flag in check.get("flags") or []:
        lines.append(f"- {flag}")
    if check.get("lag_note"):
        lines.append(check["lag_note"] + ".")
    return lines


def account_window(since: str, until: str | None = None, *,
                   fetch: Fetch | None = None, token: str | None = None,
                   account: str | None = None,
                   now: float | None = None) -> dict[str, Any]:
    now = now if now is not None else _dt.datetime.now(_dt.timezone.utc).timestamp()
    until = until or _utc(now)
    client = _Client(fetch, token, account)
    out: dict[str, Any] = {"since": since, "until": until,
                           "prices_read": PRICES_READ, "objects": [],
                           "billed_usd": None, "month": None, "error": None}
    problem = client.open()
    if problem is None:
        try:
            groups = client.containers(since, until, None)
            month_start = _dt.datetime.fromtimestamp(now, _dt.timezone.utc).strftime(
                "%Y-%m-01T00:00:00Z")
            month = client.containers(month_start, _utc(now), None, by="date")
        except (urllib.error.URLError, OSError, ValueError) as e:
            problem = f"the container meters could not be read: {e}"
    out["error"] = problem
    if problem is None:
        total = 0.0
        for group in groups:
            billed = _billed(group)
            total += billed["usd"]
            out["objects"].append({"durable_object_id": (group.get("dimensions") or {})
                                   .get("durableObjectId"), **billed})
        out["objects"].sort(key=lambda o: -o["usd"])
        out["billed_usd"] = round(total, 6)
        memory_h = sum(_billed(g)["memory_gib_s"] for g in month) / 3600
        out["month"] = {"since": month_start, "memory_gib_h": round(memory_h, 2),
                        "included_memory_gib_h": INCLUDED_MEMORY_GIB_H,
                        "over_included_usd": round(max(0.0, memory_h - INCLUDED_MEMORY_GIB_H)
                                                   * 3600 * MEMORY_USD_PER_GIB_S, 4)}
    return out


def _say_window(data: Mapping[str, Any]) -> list[str]:
    if data.get("error"):
        return [f"cloud-spend: meters not read: {data['error']}"]
    lines = [f"cloud-spend: {_usd(data['billed_usd'])} of container time at list rates "
             f"from {data['since']} to {data['until']}, "
             f"{len(data['objects'])} Durable Object(s) ran a container"]
    for o in data["objects"][:20]:
        lines.append(f"  {o['durable_object_id']}  {_usd(o['usd'])}  "
                     f"{o['memory_gib_s'] / 3600:.2f} GiB-h memory  {o['cpu_s']:.0f} s CPU")
    month = data["month"]
    lines.append(f"calendar month since {month['since']}: {month['memory_gib_h']:.2f} of "
                 f"{month['included_memory_gib_h']:.0f} included GiB-hours of container "
                 f"memory, {_usd(month['over_included_usd'])} above the included amount")
    return lines


def main(ns: Any) -> int:
    if getattr(ns, "run", None):
        check = check_run(Path(ns.run).resolve())
        if check is None:
            print(f"cloud-spend: no cloud attempt in {ns.run}")
            return 0
        if getattr(ns, "json", False):
            print(json.dumps(check, indent=2))
        else:
            print("cloud-spend: " + "\n".join(report_lines(check)))
        return 1 if check.get("error") or check.get("flags") else 0
    data = account_window(ns.since, ns.until)
    if getattr(ns, "json", False):
        print(json.dumps(data, indent=2))
    else:
        print("\n".join(_say_window(data)))
    return 1 if data.get("error") else 0
