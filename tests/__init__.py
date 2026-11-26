"""The ohflow regression suite.

Importing this package puts `ohflow/scripts` on `sys.path`, which is the
directory `ohflow` must be imported from. Every path is resolved from
`__file__`, so the suite works from a fresh clone at any location and depends on
nothing outside this repository.

Run it with:

    python ohflow/tests/run_tests.py

See `ohflow/CONTRIBUTING.md`, section "Running the suite", for the shards, the
opt-in flag and for where a new regression test goes.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: `ohflow/tests`
TESTS_ROOT = Path(__file__).resolve().parent
#: `ohflow`
SKILL_ROOT = TESTS_ROOT.parent
#: `ohflow/scripts` - the import root for `ohflow`, mirroring
#: `ohflow.IMPORT_ROOT` in a running orchestrator.
IMPORT_ROOT = SKILL_ROOT / "scripts"

# `support` and `fixtures` are imported by name from every test module, so the
# tests directory goes on the path as well. Both entries are inserted at the
# front, so a same-named package installed elsewhere never shadows these.
for _entry in (str(IMPORT_ROOT), str(TESTS_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

__all__ = ["TESTS_ROOT", "SKILL_ROOT", "IMPORT_ROOT"]
