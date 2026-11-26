"""The four run notes: what the run log cannot record about a run.

The run log records what the engine did. It cannot record what the
orchestrator agent predicted before the run, or what the operator did by hand
during it or judged afterwards. Those
four things are what a retrospective is made of, and none of them can be
rebuilt later from the artefacts.

A fresh run writes one file for each, at the root of the run directory, from
the templates in `run_notes/` beside this module:

    predictions.md   five lines, written before any result is read
    notes.md         one line per manual action or surprise, during the run
    retro.md         the engine's draft, then one row per step to judge, after the run
    ground-truth.md  the checks on the merged head, and what changed

The orchestrator agent writes the predictions only when the operator asks for
an orchestrator calibration, so an untouched `predictions.md` is no gap. Section 1 of `ground-truth.md` is done
when it names a CI run, or when the run recorded a gate pass on the tree of
the merged head (`gate_pass`).

Three rules keep this from ever costing a run anything.

* **Write only what is absent.** A file opens with mode `x`. A person's edits
  are never overwritten, and the engine calls this for a fresh run only, so a
  resume does not reach it.
* **Never raise.** A note is not a gate. A missing template or an unwritable
  directory comes back as a problem string and the run carries on.
* **Stay out of every identity.** The notes live in the run directory, not in a
  worktree, and no fingerprint reads them. Adding or editing one keeps every
  cached step cached.

The package resolves its own root from `__file__` and names no skill directory,
so the templates sit next to `dashboard.html`.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from . import check_passes, exec as ohexec
from .coords import coord
from .paths import win
from .workflow import Workflow

__all__ = ["NOTE_FILES", "TEMPLATE_DIR", "scaffold", "log_line", "check",
           "gate_pass"]


NOTE_FILES = ("predictions.md", "notes.md", "retro.md", "ground-truth.md")

#: Read at call time, so a test can point it somewhere else.
TEMPLATE_DIR = Path(__file__).resolve().parent / "run_notes"

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def _cell(text: str) -> str:
    """One table cell: a pipe would split it and a newline would end the row."""
    return " ".join(str(text).split()).replace("|", "/")


def _values(run_dir: Path, workflow: Workflow, run_id: str, base_sha: str) -> dict[str, str]:
    now = _dt.datetime.now().astimezone()
    rows = []
    for pi, phase, si, step in workflow.steps():
        what = _cell(step.objective or step.note or "")
        rows.append(f"| {coord(pi, phase.slug, si, step.id)} | {what} |  |  |  |  |")
    spaces = workflow.all_workspaces()
    baseline = "".join(
        f"\nBaseline command: `{space.baseline_cmd}`"
        + (f" in workspace `{space.name}`" if len(spaces) > 1 else "")
        for space in spaces if space.baseline_cmd)
    return {
        "run_id": run_id,
        "workflow": workflow.name,
        "repo": win(workflow.repo),
        "base_branch": workflow.base_branch,
        "base_sha": base_sha,
        "base_sha_short": base_sha[:8],
        "run_dir": win(run_dir),
        "started": now.isoformat(timespec="minutes"),
        "baseline_line": baseline,
        "step_rows": "\n".join(rows),
    }


def _fill(text: str, values: dict[str, str]) -> str:
    """Replace each `{{name}}`. An unknown name stays visible in the output."""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def scaffold(run_dir: Path, workflow: Workflow, *, run_id: str, base_sha: str,
             predictions_text: str | None = None
             ) -> tuple[list[str], list[str]]:
    """Write the four notes into `run_dir`, each only if it is not there yet.

    `predictions_text`, when given, becomes `predictions.md` as it is. The
    template stays the fallback.

    Returns `(created, problems)`: the file names written, and one line for
    each file that could not be written. It does not raise.
    """
    created: list[str] = []
    problems: list[str] = []
    run_dir = Path(run_dir)
    try:
        values = _values(run_dir, workflow, run_id, base_sha)
    except Exception as e:  # noqa: BLE001 - a note must never stop a run
        return created, [f"all: {type(e).__name__}: {e}"]
    for name in NOTE_FILES:
        try:
            if name == "predictions.md" and predictions_text is not None:
                text = predictions_text
            else:
                text = _fill((TEMPLATE_DIR / name).read_text(encoding="utf-8"),
                             values)
            with (run_dir / name).open("x", encoding="utf-8") as fh:
                fh.write(text)
            created.append(name)
        except FileExistsError:
            continue
        except Exception as e:  # noqa: BLE001 - a note must never stop a run
            problems.append(f"{name}: {type(e).__name__}: {e}")
    return created, problems


# ------------------------------------------------------------ the two verbs


def predictions_filled(run_dir: Path) -> bool:
    text = _read(run_dir, "predictions.md")
    if text is None:
        return False
    numbered = [m for m in map(_NUMBERED.match, text.splitlines()) if m]
    return bool(numbered) and not any(m.group(2).endswith(":") for m in numbered)


def log_line(run_dir: Path, text: str) -> str:
    """Append `HH:MM | <text>` to `notes.md` and return the line.

    A run that has no `notes.md` yet gets a minimal one.
    """
    path = Path(run_dir) / "notes.md"
    line = f"{_dt.datetime.now().strftime('%H:%M')} | {' '.join(text.split())}"
    body = path.read_text(encoding="utf-8") if path.exists() else \
        f"# Run notes - run {Path(run_dir).name}\n\n---\n"
    if not body.endswith("\n"):
        body += "\n"
    path.write_text(body + line + "\n", encoding="utf-8")
    return line


_NUMBERED = re.compile(r"^\s*([1-5])\.\s+(.*\S)\s*$")
_RESULT_LABEL = re.compile(r"^-\s+(Test|Typecheck|Lint) command:\s*(.*)$")
_RESULT_LINE = re.compile(r"^-\s+Result:\s*(.*)$")
_EVIDENCE = re.compile(r"^-\s+The gate's recorded pass on this tree, or the CI run "
                       r"on the pushed head:\s*(.*)$")
_DRAFT = re.compile(r"<!-- ohflow:auto begin -->(.*?)<!-- ohflow:auto end -->",
                    re.S)
_DRAFT_EMPTY = "Filled in when the run ends."


def _read(run_dir: Path, name: str) -> str | None:
    try:
        return (Path(run_dir) / name).read_text(encoding="utf-8",
                                                errors="replace")
    except OSError:
        return None


def check(run_dir: Path, *, run_live: bool = False) -> list[str]:
    """One line per gap in the four notes. No line means the notes are done.

    An engine draft that is still empty is a gap only when the run is no
    longer live: the engine writes it when the run ends.
    """
    gaps: list[str] = []

    text = _read(run_dir, "predictions.md")
    if text is None:
        gaps.append("predictions.md is missing")
    else:
        lines = [m for m in map(_NUMBERED.match, text.splitlines()) if m]
        if any(not m.group(2).endswith(":") for m in lines):
            gaps += [f"predictions.md line {m.group(1)} is empty: "
                     f"{m.group(2).rstrip(':')}"
                     for m in lines if m.group(2).endswith(":")]

    text = _read(run_dir, "retro.md")
    if text is None:
        gaps.append("retro.md is missing")
    else:
        draft = _DRAFT.search(text)
        if not run_live and (draft is None or _DRAFT_EMPTY in draft.group(1)
                             or not draft.group(1).strip()):
            gaps.append("retro.md has no engine draft: run `ohflow report` "
                        "to write it")
        for raw in text.splitlines():
            if not raw.startswith("|"):
                continue
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if len(cells) < 6 or cells[0] in ("Step", "") \
                    or set(cells[0]) <= set("-: "):
                continue
            if not cells[2]:
                gaps.append(f"retro.md: {cells[0]} has no verdict")

    text = _read(run_dir, "ground-truth.md")
    if text is None:
        gaps.append("ground-truth.md is missing")
    else:
        label, command = None, ""
        for raw in text.splitlines():
            m = _EVIDENCE.match(raw.strip())
            if m and not m.group(1).strip() and gate_pass(run_dir) is None:
                gaps.append("ground-truth.md: section 1 names no CI run, and the "
                            "run recorded no gate pass on the merged head's tree")
            m = _RESULT_LABEL.match(raw.strip())
            if m:
                label, command = m.group(1), m.group(2).strip()
                continue
            m = _RESULT_LINE.match(raw.strip())
            if m and label:
                if not m.group(1).strip():
                    gaps.append(
                        f"ground-truth.md: the {label.lower()} command has no "
                        f"result" if command else
                        f"ground-truth.md: the {label.lower()} command and "
                        f"its result are empty")
                label = None
    return gaps


def gate_pass(run_dir: Path) -> dict | None:
    try:
        record = json.loads(_read(run_dir, "workflow.json") or "")
        repo, branch = Path(record["repo"]), record["base_branch"]
        lines = (Path(run_dir) / check_passes.FILE).read_text(
            encoding="utf-8").splitlines()
        head = ohexec.git(f"rev-parse {branch}^{{tree}}", repo,
                          name="notes-merged-head")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return None
    tree = head.stdout.strip() if head.returncode == 0 else ""
    for line in lines if tree else ():
        try:
            rec = json.loads(line)
            found = check_passes.find(run_dir, rec["cmd"], rec["shell"],
                                      Path(rec["cwd"]), tree)
        except (ValueError, KeyError, TypeError):
            continue
        if found is not None:
            return found
    return None
