"""Ends an owner's process groups when the owner dies without ending them.

Off Windows nothing closes a job for a dead process, so `proc` starts this
script once per owner, in its own session, with the read end of a pipe as
stdin. Only the owner holds the write end. The owner writes `+<pgid>` when it
starts a group and `-<pgid>` when it has ended one. The end of the input means
the owner is gone, however it went, and the groups it still owned get SIGTERM
and then SIGKILL after the grace given as the first argument.

It imports nothing of ohflow and runs with `-I -S`, so it starts fast and
reads no environment.
"""

from __future__ import annotations

import os
import signal
import sys
import time

_POLL_S = 0.05


def _signal_group(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def owned_groups(lines) -> set[int]:
    """The groups still owned once `lines` end."""
    groups: set[int] = set()
    for line in lines:
        word = line.decode("ascii", "replace").strip()
        if not word[1:].isdigit() or int(word[1:]) <= 1:
            continue
        if word[0] == "+":
            groups.add(int(word[1:]))
        elif word[0] == "-":
            groups.discard(int(word[1:]))
    return groups


def end_groups(groups: set[int], grace_s: float) -> None:
    for pgid in groups:
        _signal_group(pgid, signal.SIGTERM)
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline and any(_group_alive(g) for g in groups):
        time.sleep(_POLL_S)
    for pgid in groups:
        _signal_group(pgid, signal.SIGKILL)


def main(argv: list[str]) -> int:
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, signal.SIG_IGN)
    with open(0, "rb", closefd=False) as owner:
        groups = owned_groups(owner)
    end_groups(groups, float(argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
