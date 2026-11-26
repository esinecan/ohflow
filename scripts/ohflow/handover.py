"""Question contract and recorded-file reader for handovers between steps."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .workflow import HandoverSpec

CORE = (
    ("State", "Which artifact or commit is authoritative, where is it, and which copies are stale?"),
    ("Done and undone", "What is finished and what remains incomplete? Mark completed side effects: already done, do not repeat."),
    ("Decisions", "Which decisions and reasons must the reader preserve, and what evidence could reopen them?"),
    ("Verified and assumed", "What did you verify, by which command or source? What remains assumed?"),
    ("Tried and failed", "Which approaches failed, with what symptom, and which workaround worked?"),
    ("Open", "Which questions and contradictions remain unresolved?"),
    ("Next", "What should the reader do, verify first, and wait for?"),
)
AUDIENCES = {
    "next": (),
    "reviewer": (
        ("How to run it", "Which command runs it in isolation, what setup is required, and what goes wrong without it?"),
        ("What passing does not prove", "What do the checks establish, and what remains untested?"),
        ("Never relax", "Which invariant must remain true, and what breaks if it is relaxed?"),
    ),
    "consolidator": (
        ("Interfaces", "Which interfaces and assumptions connect this work to the other contributions?"),
        ("Integration risks", "Which conflicts or mismatches could occur, and which check exposes them?"),
    ),
}


def questions(spec: HandoverSpec) -> tuple[tuple[str, str], ...]:
    return CORE + AUDIENCES[spec.audience] + tuple((h, h) for h in spec.extra)


def instructions(spec: HandoverSpec) -> str:
    rows = ["Answer each heading in order. Use `not established` where you have no answer.",
            "Cite artifact paths or commands; reference rather than copy. Label findings [verified] or [assumed].",
            "Keep secrets out. Omit routine timestamps and usage counts already recorded by the engine."]
    rows.extend(f"## {h}\n{q}" for h, q in questions(spec))
    return "\n\n".join(rows)


def check_text(text: str, spec: HandoverSpec) -> str | None:
    """Checks structure, never the truth of an answer."""
    if len(text) > spec.max_chars:
        return f"{len(text)} characters; limit {spec.max_chars}"
    # Only actual level-two headings count; fenced examples cannot answer a question.
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        else:
            lines.append(line)
    clean = "".join(lines)
    matches = list(re.finditer(r"(?m)^## ([^\r\n]+)\s*$", clean))
    expected = [h for h, _ in questions(spec)]
    found = [m.group(1).strip() for m in matches]
    if found != expected:
        return "headings must appear once, in order: " + ", ".join(expected)
    for i, m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(clean)
        if not clean[m.end():end].strip():
            return f"empty: {expected[i]}"
    return None


def recorded(root: Path, rec) -> tuple[Path, str]:
    """Read only the recorded attempt file, verifying its content digest."""
    if not rec or not rec.handover_path or not rec.handover_sha256:
        raise ValueError("no handover recorded")
    root = Path(root).resolve()
    relative = Path(rec.handover_path)
    path = (root / relative).resolve()
    expected = root / "phases" / rec.coord / "attempts" / f"{rec.attempt:02d}" / "handover.md"
    if relative.is_absolute() or path != expected or not path.is_relative_to(root):
        raise ValueError("invalid handover path")
    try:
        data = path.read_bytes()
    except OSError as e:
        raise ValueError("recorded handover is missing or unreadable") from e
    if hashlib.sha256(data).hexdigest() != rec.handover_sha256:
        raise ValueError("recorded handover content changed")
    try:
        return path, data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("handover is not UTF-8") from e


def intact(root: Path, rec) -> bool:
    try:
        recorded(root, rec)
        return True
    except ValueError:
        return False


def received(workflow, state, step, root: Path) -> dict[str, tuple[str, str]]:
    from .coords import coord_of
    return {sid: (str(path), text) for sid in step.consumes
            for path, text in [recorded(root, state.steps.get(coord_of(workflow, sid)))]}
