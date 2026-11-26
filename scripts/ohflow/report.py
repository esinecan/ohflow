"""The writer of `board.md`.

The engine calls `write_board_md` after each run log event, and the board is
rewritten whole each time. No code reads `board.md`: it is for a person.
`summary.json` is computed and written by `rundir.Run.write_summary`.
"""

from __future__ import annotations

from pathlib import Path

from .coords import coord, phase_coord
from .run_log import RunState
from .workflow import Workflow
from . import rundir

__all__ = ["write_board_md", "render_board_md"]


_MARK = {
    "passed": "PASS", "cached": "CACHED", "failed": "FAIL",
    "timeout": "TIMEOUT", "quarantined": "QUARANTINED",
    "skipped": "skipped", "running": "running", "pending": "pending",
    "deferred": "DEFERRED",
}


def render_board_md(workflow: Workflow, state: RunState) -> str:
    L = [f"# Board - {state.run_id or '(not started)'} - workflow `{workflow.name}`", "",
         f"status: **{state.status}**   started: {state.started or '-'}   "
         f"finished: {state.finished or '-'}", "",
         "| coordinate | kind | status | wall s | gate | note |",
         "|---|---|---|---|---|---|"]
    quarantined = []
    for pi, phase, si, step in workflow.steps():
        c = coord(pi, phase.slug, si, step.id)
        rec = state.steps.get(c)
        status = rundir.step_status(state, c)
        wall = f"{rec.wall_seconds:.1f}" if rec and rec.wall_seconds else "-"
        if rec and rec.gate:
            failed = [ch["name"] for ch in rec.gate.get("checks", [])
                      if not ch.get("passed")]
            gate = "PASSED" if rec.gate.get("passed") else (
                "FAILED: " + ", ".join(failed) if failed else "FAILED")
        else:
            gate = "-"
        # The note first, then an error, which is more urgent to a reader than
        # the objective, and the objective when the step has neither.
        note = step.note or (rec.error[:80] if rec and rec.error
                             else (step.objective or ""))
        L.append(f"| `{c}` | {step.kind} | {_MARK.get(status, status)} | {wall} "
                 f"| {gate} | {note} |")
        if status in ("quarantined", "failed", "timeout"):
            branch = rec.branch if rec and rec.branch else (
                workflow.worktree(step.worktree).branch if step.worktree else "-")
            quarantined.append(f"- `{c}` on branch `{branch}` - {status}")

    L += ["", "## Phases", "",
          "| phase | status | good/total | policy | max_parallel |",
          "|---|---|---|---|---|"]
    for pi, phase in enumerate(workflow.phases, start=1):
        pc = phase_coord(pi, phase.slug)
        e = state.phases.get(pc, {})
        # The effective limit the engine applied. A phase that has not started
        # has none yet, and a run log written before the key existed has none
        # either; both render as a dash rather than as a guess.
        parallel = e.get("max_parallel")
        L.append(f"| `{pc}` - {phase.name} | {e.get('status', 'pending')} "
                 f"| {e.get('good', '-')}/{e.get('total', len(phase.steps))} "
                 f"| {phase.on_step_failure} "
                 f"| {parallel if parallel is not None else '-'} |")

    if quarantined:
        L += ["", "## Quarantined, excluded from consolidation", ""] + quarantined
    return "\n".join(L) + "\n"


def write_board_md(run_dir: Path, workflow: Workflow, state: RunState) -> Path:
    p = Path(run_dir) / "board.md"
    p.write_text(render_board_md(workflow, state), encoding="utf-8")
    return p
