"""What the opt-in end-to-end test and its deterministic guards share."""

from __future__ import annotations

import os
import shutil

from ohflow.harness_executors import harness_executor_for
from ohflow.preflight import HARNESS_EXECUTOR_FIX

E2E_ENV = "OHFLOW_E2E"
KEY_ENV = "ZAI_CODING_CN_API_KEY"
#: The harness executors the smoke matrix runs on.
SMOKE_HARNESS_EXECUTORS = ("pi", "claude", "codex")


def why_skip() -> str | None:
    """The reason the end-to-end test cannot run, or None. Never reads a key's value."""
    if not os.environ.get(E2E_ENV):
        return (f"the end-to-end test is opt-in. Pass --e2e to run_tests.py "
                f"(it sets {E2E_ENV}=1). It runs the smoke matrix of "
                f"`ohflow rollcall` on pi, claude and codex against real "
                f"models and takes a few minutes.")
    if not os.environ.get(KEY_ENV):
        return (f"{KEY_ENV} is not set in this environment. That variable names "
                f"the Z.AI flat-rate subscription this test spends. Set it and "
                f"run again; its value is never printed.")
    for name in SMOKE_HARNESS_EXECUTORS:
        problems = list(harness_executor_for(name).preflight())
        if problems:
            return (f"the {name} harness executor is not ready: "
                    f"{'; '.join(problems)}. Fix: {HARNESS_EXECUTOR_FIX[name]}.")
    if shutil.which("git") is None:
        return "git is not on PATH, and the run needs a real worktree."
    return None

