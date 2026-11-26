"""The run's token ledger: admission, grants, live observation and settlement.

A run with a token budget holds one `Ledger`. Every agent attempt asks it for
admission before its harness executor launches, and the ledger grants the
attempt a reservation only while the settled tokens, plus every grant still in
flight, plus the new reservation fit inside the limit. While the attempt runs
the engine reports its live usage at every poll. An attempt whose usage
reaches its grant is extended from the allowance nobody holds, and when none
is left it is stopped. At the end the attempt settles its recorded usage.

The one invariant, kept under the lock:

    settled + sum(grants in flight) <= limit + sum(recorded overshoot)

An attempt overshoots only when its settled usage is larger than its grant
plus the allowance free at that moment, which happens when a harness reports
usage late. Every token of overshoot is returned to the caller as a record,
and the engine writes each record to the run log as an error.

Tokens are `prompt_tokens + completion_tokens` of `attempt_record.TOKEN_KEYS`,
so cached input counts. The billing estimate is a separate field: the sum of
the priced `cost` the settled attempts recorded. The ledger never compares
money with the limit.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from . import attempt_record

__all__ = ["Ledger", "SNAPSHOT", "GRANT_FILE", "STOP_FILE", "total_tokens",
           "read_snapshot", "default_reserve"]

SNAPSHOT = "budget.json"
GRANT_FILE = "budget-grant.json"
STOP_FILE = "budget-stop.json"


def total_tokens(tokens: Mapping[str, Any] | None) -> int | None:
    """The total of a usage record, or None when the record is not one."""
    checked, _ = attempt_record.checked_tokens(tokens, "usage")
    if checked is None:
        return None
    return checked["prompt_tokens"] + checked["completion_tokens"]


def default_reserve(limit: int, max_parallel: int) -> int:
    """The grant one attempt receives when the workflow names none."""
    return max(1, limit // max(1, max_parallel))


def read_snapshot(run_dir: Path) -> dict | None:
    try:
        data = json.loads((Path(run_dir) / SNAPSHOT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Ledger:
    def __init__(self, limit: int, reserve: int, *, run_dir: Path | None = None,
                 settled: int = 0, billing_usd: float = 0.0,
                 priced_attempts: int = 0, unpriced_attempts: int = 0,
                 overshoots: list[dict] | None = None):
        if limit < 1 or reserve < 1:
            raise ValueError("a token budget and its reserve must be at least 1")
        self.limit = int(limit)
        self.reserve = min(int(reserve), self.limit)
        self.run_dir = Path(run_dir) if run_dir is not None else None
        self.settled = int(settled)
        self.billing_usd = float(billing_usd)
        self.priced_attempts = int(priced_attempts)
        self.unpriced_attempts = int(unpriced_attempts)
        self.overshoots: list[dict] = list(overshoots or [])
        self.grants: dict[str, int] = {}
        self.observed: dict[str, int] = {}
        self.stopped: set[str] = set()
        self.refused: list[dict] = []
        self.unknown: list[str] = []
        self._grant_dirs: dict[str, Path] = {}
        self._turn = threading.Condition()
        self._write()

    @property
    def overshoot(self) -> int:
        return sum(int(o.get("overshoot_tokens") or 0) for o in self.overshoots)

    def _free(self) -> int:
        return max(0, self.limit - self.settled - sum(self.grants.values()))

    def holds(self, key: str) -> bool:
        with self._turn:
            return key in self.grants

    def attach(self, key: str, attempt_dir: Path) -> None:
        """Name the attempt directory that receives this grant's file."""
        with self._turn:
            if key in self.grants:
                self._grant_dirs[key] = Path(attempt_dir)
                self._write_grant(key)

    def release(self, key: str) -> None:
        """Return a grant that no agent spent, after a fault before launch."""
        with self._turn:
            if self.grants.pop(key, None) is None:
                return
            self.observed.pop(key, None)
            self._grant_dirs.pop(key, None)
            self._write()
            self._turn.notify_all()

    def admit(self, key: str, *, cancelled: Callable[[], bool] = lambda: False,
              wait_s: float = 1.0) -> tuple[int | None, str]:
        """Reserve `reserve` tokens for one attempt, or refuse.

        While the reservation does not fit and other attempts hold grants,
        the call waits for one of them to settle. With nothing in flight and
        no room, it refuses.
        """
        with self._turn:
            while True:
                if self._free() >= self.reserve:
                    self.grants[key] = self.reserve
                    self.observed[key] = 0
                    self._write()
                    return self.reserve, (
                        f"granted {self.reserve} tokens; "
                        f"{self._free()} of {self.limit} unreserved")
                if not self.grants:
                    why = (f"token budget spent: {self.settled} settled of "
                           f"{self.limit}, {self._free()} free and a step "
                           f"needs {self.reserve}. Raise --token-budget and "
                           f"resume the run.")
                    self.refused.append({"key": key, "reason": why})
                    self._write()
                    return None, why
                if cancelled():
                    return None, "the run aborted while this step waited for tokens"
                self._turn.wait(wait_s)

    def observe(self, key: str, tokens: int | None) -> bool:
        """Record live usage. False when the attempt must stop now."""
        with self._turn:
            if key not in self.grants:
                return True
            if tokens is not None and tokens > self.observed.get(key, 0):
                self.observed[key] = int(tokens)
            used = self.observed.get(key, 0)
            grant = self.grants[key]
            if used >= grant:
                extra = min(self._free(), used - grant + self.reserve)
                if extra > 0:
                    self.grants[key] = grant + extra
            if self.observed.get(key, 0) >= self.grants[key]:
                self.stopped.add(key)
                self._write_grant(key)
                self._write()
                return False
            if self.grants[key] != grant:
                self._write_grant(key)
            self._write()
            return True

    def settle(self, key: str, tokens: int | None, *, cost: Any = None,
               cost_source: Any = None) -> dict | None:
        """Close the attempt's grant with its usage. Returns an overshoot record."""
        with self._turn:
            if key not in self.grants:
                return None
            grant = self.grants.pop(key)
            seen = self.observed.pop(key, 0)
            self._grant_dirs.pop(key, None)
            known = tokens is not None
            used = int(tokens) if known else max(grant, seen)
            if not known:
                self.unknown.append(key)
            free = max(0, self.limit - self.settled - sum(self.grants.values()) - grant)
            over = max(0, used - grant - free)
            self.settled += used
            if isinstance(cost, (int, float)) and not isinstance(cost, bool) \
                    and cost_source not in (None, "unpriced"):
                self.billing_usd += float(cost)
                self.priced_attempts += 1
            else:
                self.unpriced_attempts += 1
            record = None
            if over > 0:
                record = {"key": key, "grant_tokens": grant, "used_tokens": used,
                          "overshoot_tokens": over, "settled_tokens": self.settled,
                          "limit_tokens": self.limit,
                          "usage_known": known}
                self.overshoots.append(record)
            self._write()
            self._turn.notify_all()
            return record

    def snapshot(self) -> dict:
        with self._turn:
            return self._snapshot()

    def _snapshot(self) -> dict:
        in_flight = {k: {"grant_tokens": g, "observed_tokens": self.observed.get(k, 0)}
                     for k, g in sorted(self.grants.items())}
        observed = self.settled + sum(v["observed_tokens"] for v in in_flight.values())
        return {
            "limit_tokens": self.limit,
            "reserve_tokens": self.reserve,
            "settled_tokens": self.settled,
            "observed_tokens": observed,
            "reserved_tokens": sum(self.grants.values()),
            "free_tokens": self._free(),
            "in_flight": in_flight,
            "stopped": sorted(self.stopped),
            "refused": list(self.refused),
            "unknown_usage": list(self.unknown),
            "overshoot_tokens": self.overshoot,
            "overshoots": list(self.overshoots),
            "billing_estimate_usd": round(self.billing_usd, 6),
            "billing_priced_attempts": self.priced_attempts,
            "billing_unpriced_attempts": self.unpriced_attempts,
        }

    def _write(self) -> None:
        if self.run_dir is None:
            return
        try:
            _write_json(self.run_dir / SNAPSHOT, self._snapshot())
        except OSError:
            pass

    def _write_grant(self, key: str) -> None:
        d = self._grant_dirs.get(key)
        if d is None:
            return
        try:
            _write_json(d / GRANT_FILE, {"grant_tokens": self.grants.get(key, 0),
                                         "final": key in self.stopped})
        except OSError:
            pass
