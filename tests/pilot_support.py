from __future__ import annotations

import textwrap
import threading
import time
from pathlib import Path

from ohflow.workflow import (AgentSpec, CheckSpec, GateSpec, ModelConfig, Phase,
                             Step, Unit, UnitPath, Workflow, WorktreeSpec)
from support import quiet

__all__ = ["MODULE", "UNITS", "write_module", "two_paths", "wait_until",
           "start_in_thread", "WAIT_S"]

WAIT_S = 20.0

UNITS = [("s1", "single", 3), ("s2", "single", 1), ("s3", "single", 2),
         ("p1", "probe", 2), ("p2", "probe", 1)]

MODULE = '''
from pathlib import Path
from ohflow.workflow import (AgentSpec, CheckSpec, GateSpec, ModelConfig, Phase,
                             Step, Unit, UnitPath, Workflow)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")
GATE = GateSpec(checks=(CheckSpec("final_message_matches", {"regex": "DONE"}),))
UNITS = %r


def agent(step_id, unit=None, depends_on=()):
    return Step(id=step_id, kind="agent", gate=GATE, unit=unit,
                depends_on=depends_on, objective="do " + step_id,
                agent=AgentSpec(harness_executor="pi", role="worker", brief="do " + step_id,
                                model=MODEL, max_iterations=3))


def build(args):
    units = tuple(Unit(id=u, path=p, size=s) for u, p, s in UNITS)
    work = tuple(agent("fix-" + u.id, unit=u.id) for u in units)
    report = agent("report", depends_on=tuple(s.id for s in work))
    return Workflow(name="two-paths", repo=Path(args["repo"]), base_branch="main",
                    max_parallel=2, transient_backoff_s=0,
                    paths=(UnitPath("single", "a family with one occurrence"),
                           UnitPath("probe", "a family with a live probe")),
                    units=units,
                    phases=(Phase(name="Fix", steps=work),
                            Phase(name="Report", steps=(report,))))
'''

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")
GATE = GateSpec(checks=(CheckSpec("final_message_matches", {"regex": "DONE"}),))


def write_module(path: Path, units=UNITS) -> Path:
    path.write_text(textwrap.dedent(MODULE % (list(units),)), encoding="utf-8")
    return path


def _agent(step_id: str, unit=None, depends_on=(), worktree=None) -> Step:
    return Step(id=step_id, kind="agent", gate=GATE, unit=unit,
                depends_on=tuple(depends_on), worktree=worktree,
                objective=f"do {step_id}",
                agent=AgentSpec(harness_executor="pi", role="worker", brief=f"do {step_id}", model=MODEL,
                                max_iterations=3))


def two_paths(repo: Path, units=UNITS, worktrees: bool = False) -> Workflow:
    wt = "work" if worktrees else None
    declared = tuple(Unit(id=u, path=p, size=s) for u, p, s in units)
    work = tuple(_agent(f"fix-{u.id}", unit=u.id, worktree=wt) for u in declared)
    report = _agent("report", depends_on=[s.id for s in work], worktree=wt)
    trees = ()
    if worktrees:
        trees = (WorktreeSpec(name="work", path=Path(repo).parent / "wt-work",
                              branch="atlas/work", base="main",
                              node_modules_mode="none"),)
    return Workflow(name="two-paths", repo=Path(repo), base_branch="main",
                    max_parallel=2, transient_backoff_s=0, worktrees=trees,
                    paths=(UnitPath("single", "a family with one occurrence"),
                           UnitPath("probe", "a family with a live probe")),
                    units=declared,
                    phases=(Phase(name="Fix", steps=work),
                            Phase(name="Report", steps=(report,))))


def wait_until(check, timeout: float = WAIT_S) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return bool(check())


def start_in_thread(fn) -> tuple[threading.Thread, dict]:
    result: dict = {}

    def target():
        with quiet():
            try:
                result["outcome"] = fn()
            except BaseException as e:
                result["error"] = e

    thread = threading.Thread(target=target, name="pilot-run", daemon=True)
    thread.start()
    return thread, result
