"""ohflow - a fan-out orchestrator for agent harnesses: claude, codex and pi.

The package resolves its own root from `__file__` and never names a skill
directory, so extracting it to its own repository later is a move rather than a
rewrite.

Every module runs on plain Python 3.11 or later, so the orchestrator runs in
the signed-in harness's own interpreter.
"""

from pathlib import Path

__version__ = "0.1.0"

#: The directory this package lives in. Nothing here hard-codes a skill path.
PACKAGE_ROOT = Path(__file__).resolve().parent
#: The directory that must be on sys.path for `python -m ohflow.<module>`.
IMPORT_ROOT = PACKAGE_ROOT.parent

__all__ = ["PACKAGE_ROOT", "IMPORT_ROOT", "__version__"]
