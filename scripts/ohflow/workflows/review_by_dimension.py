"""Run one read-only reviewer per dimension, then consolidate their reports.

The agent outputs are ordinary ohflow structured artifacts.  The second phase
is deliberately a Python command step: it reads those artifacts in dimension
order and writes ``review.md`` and ``verdict.json`` beside its own attempt
artifacts.  No reviewer has to edit the reviewed worktree to communicate with
the consolidator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from ohflow import rundir
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             RetryPolicy, Step, ToolPolicy, AgentSpec,
                             WorktreeSpec)

WORKTREE = "review"
DIMENSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
HARNESS_EXECUTORS = frozenset({"pi"})

REVIEW_SCHEMA = {
    "type": "object",
    "required": ["dimension", "verdict", "findings", "summary"],
    "properties": {
        "dimension": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PASS", "BLOCKED"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["severity", "path", "line", "claim"],
                "properties": {
                    "severity": {"type": "string",
                                 "enum": ["BLOCKING", "MINOR"]},
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "claim": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


def _dimensions(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError("dimensions must be a comma-separated list")
    values = tuple(part.strip() for part in value.split(","))
    if not values or any(not item for item in values):
        raise ValueError("dimensions must contain non-empty comma-separated names")
    invalid = [item for item in values if not DIMENSION_RE.fullmatch(item)]
    if invalid:
        raise ValueError(f"invalid dimension name(s): {', '.join(invalid)}")
    if len(set(values)) != len(values):
        raise ValueError("dimensions must not contain duplicates")
    return values


def _harness_executors(value: object, dimensions: tuple[str, ...], default: str) -> dict[str, str]:
    if default not in HARNESS_EXECUTORS:
        raise ValueError(f"harness executor must be one of {sorted(HARNESS_EXECUTORS)}, got {default!r}")
    result = {dimension: default for dimension in dimensions}
    if value in (None, ""):
        return result
    if not isinstance(value, str):
        raise ValueError("harness executors must be a comma-separated dim=harness_executor list")
    seen: set[str] = set()
    for entry in value.split(","):
        if entry.count("=") != 1:
            raise ValueError(f"invalid harness executor override {entry!r}; use dim=harness_executor")
        dimension, harness_executor = (part.strip() for part in entry.split("=", 1))
        if dimension not in result:
            raise ValueError(f"harness executor override names unknown dimension {dimension!r}")
        if dimension in seen:
            raise ValueError(f"duplicate harness executor override for {dimension!r}")
        if harness_executor not in HARNESS_EXECUTORS:
            raise ValueError(f"harness executor for {dimension!r} must be one of {sorted(HARNESS_EXECUTORS)}")
        seen.add(dimension)
        result[dimension] = harness_executor
    return result


def _schema_retry(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("schema_retry must be a non-negative integer") from exc
    if parsed < 0 or isinstance(value, bool):
        raise ValueError("schema_retry must be a non-negative integer")
    return parsed


def _model(args: dict, harness_executor: str) -> ModelConfig:
    return ModelConfig(
        model=args.get("model") or "light",
        base_url=args.get("base_url") or "https://api.z.ai/api/coding/paas/v4",
        api_key_env=args.get("api_key_env") or "ZAI_CODING_CN_API_KEY",
        params={"thinking": args.get("thinking") or "high"},
    )


def _brief(dimension: str, text: str, base: str) -> str:
    return f"""# Review dimension: {dimension}

Review the changes from `{base}` through `HEAD` only for this dimension.  You
are a read-only reviewer: inspect and test, but do not edit or commit anything.

{text.rstrip()}

Return exactly one fenced JSON object matching the supplied schema.  Set
`dimension` to `{dimension}`.  Use verdict `BLOCKED` when this dimension has a
blocking defect and `PASS` otherwise.  Findings use severity `BLOCKING` or
`MINOR`, a repository-relative path, a one-based line, and a concise claim.
"""


def _review_steps(args: dict, *, worktree: str = WORKTREE) -> tuple[Step, ...]:
    dimensions = _dimensions(args.get("dimensions"))
    brief_dir = Path(str(args.get("brief_dir") or ""))
    if not brief_dir.is_dir():
        raise ValueError(f"brief_dir is not a directory: {brief_dir}")
    missing = [str(brief_dir / f"{d}.md") for d in dimensions
               if not (brief_dir / f"{d}.md").is_file()]
    if missing:
        raise ValueError("missing dimension brief(s): " + ", ".join(missing))
    harness_executor_by_dimension = _harness_executors(args.get("harness_executors"), dimensions,
                                                       str(args["harness_executor"]))
    retries = _schema_retry(args.get("schema_retry", 1))
    base = str(args.get("base") or "main")
    return tuple(
        Step(
            id=f"review-{dimension}", kind="agent", worktree=worktree,
            execution_timeout_s=int(args.get("execution_timeout_s") or 5400),
            schema=REVIEW_SCHEMA,
            gate=GateSpec(checks=(CheckSpec("tree_clean", {}),
                                  CheckSpec("schema_valid", {}))),
            retry=RetryPolicy(max=retries, on=("gate:schema_valid",))
            if retries else RetryPolicy(),
            note=f"read-only review: {dimension}",
            agent=AgentSpec(
                role=f"review-{dimension}",
                brief=_brief(dimension,
                             (brief_dir / f"{dimension}.md").read_text(
                                 encoding="utf-8"), base),
                model=_model(args, harness_executor_by_dimension[dimension]),
                tools=ToolPolicy(only=("terminal",)),
                skills=(),
                max_iterations=int(args.get("review_iter") or 80),
                harness_executor=harness_executor_by_dimension[dimension],
            ),
        )
        for dimension in dimensions
    )


def _attempt_dir(run_dir: Path, phase: str, index: int, step_id: str) -> Path:
    return rundir.open_run(run_dir).latest_attempt_dir(
        f"{phase}/{index:02d}.{step_id}")


def consolidate(run_dir: Path, dimensions: tuple[str, ...], *,
                review_phase: str = "01.review-by-dimension",
                output_phase: str = "02.consolidate",
                output_dir: Path | None = None) -> tuple[Path, Path]:
    """Read structured reviewer artifacts and write deterministic outputs."""
    run_dir = Path(run_dir)
    reports = []
    for index, dimension in enumerate(dimensions, start=1):
        attempt = _attempt_dir(run_dir, review_phase, index,
                               f"review-{dimension}")
        result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
        report = result.get("structured")
        if not isinstance(report, dict):
            raise ValueError(f"review {dimension!r} has no structured result")
        if report.get("dimension") != dimension:
            raise ValueError(
                f"review {dimension!r} reported dimension {report.get('dimension')!r}")
        reports.append(report)

    verdict = "BLOCKED" if any(r.get("verdict") == "BLOCKED" for r in reports) \
        else "PASS"
    payload = {"verdict": verdict, "dimensions": reports}
    output = (Path(output_dir) if output_dir is not None else
              _attempt_dir(run_dir, output_phase, 1, "consolidate"))
    verdict_path = output / "verdict.json"
    verdict_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [f"VERDICT: {verdict}", "", "# Review by dimension", ""]
    for report in reports:
        lines += [f"## {report['dimension']}: {report['verdict']}", "",
                  str(report.get("summary") or ""), ""]
        findings = report.get("findings") or []
        if findings:
            for finding in findings:
                lines.append(
                    f"- {finding['severity']} `{finding['path']}:{finding['line']}`: "
                    f"{finding['claim']}")
        else:
            lines.append("- No findings.")
        lines.append("")
    review_path = output / "review.md"
    review_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return review_path, verdict_path


def consolidation_step(args: dict, reviewer_ids: tuple[str, ...], *,
                       worktree: str = WORKTREE,
                       review_phase_number: int = 1,
                       output_phase_number: int = 2,
                       output_phase_slug: str = "consolidate",
                       gate: GateSpec | None = None) -> Step:
    dimensions = _dimensions(args.get("dimensions"))
    scripts_dir = Path(__file__).resolve().parents[2]
    tail = (
        f'--dimensions "{",".join(dimensions)}" '
        f'--review-phase "{review_phase_number:02d}.review-by-dimension" '
        f'--output-phase "{output_phase_number:02d}.{output_phase_slug}"'
    )
    if os.name == "nt":
        shell = "cmd"
        command = (
            f'set "PYTHONPATH={scripts_dir};%PYTHONPATH%" && '
            f'"{sys.executable}" -m ohflow.workflows.review_by_dimension --consolidate '
            f'"%OHFLOW_RUN_DIR%" --output-dir "%OHFLOW_ATTEMPT_DIR%" ' + tail
        )
    else:
        # cmd.exe exists only on Windows. The same command for a POSIX shell.
        shell = "sh"
        command = (
            f'PYTHONPATH="{scripts_dir}:$PYTHONPATH" '
            f'"{sys.executable}" -m ohflow.workflows.review_by_dimension --consolidate '
            f'"$OHFLOW_RUN_DIR" --output-dir "$OHFLOW_ATTEMPT_DIR" ' + tail
        )
    return Step(
        id="consolidate", kind="command", worktree=worktree,
        depends_on=reviewer_ids, command=command, shell=shell,
        execution_timeout_s=300,
        gate=gate,
        note="write review.md and verdict.json from structured review artifacts",
    )


def build(args: dict) -> Workflow:
    dimensions = _dimensions(args.get("dimensions"))
    repo = Path(str(args.get("repo") or Path.cwd())).resolve()
    worktree = Path(str(args.get("worktree") or repo)).resolve()
    base = str(args.get("base") or "main")
    branch = str(args.get("branch") or base)
    reviewers = _review_steps(args)
    reviewer_ids = tuple(step.id for step in reviewers)
    consolidator = consolidation_step(args, reviewer_ids)
    return Workflow(
        name="review-by-dimension", repo=repo, base_branch=base,
        baseline_cmd=None, max_parallel=len(reviewers),
        transient_backoff_s=int(args.get("transient_backoff_s") or 0),
        args=dict(args),
        worktrees=(WorktreeSpec(
            name=WORKTREE, path=worktree, branch=branch, base=base,
            node_modules_mode="none", reuse_existing=True,
            base_sha_mode="merge_base"),),
        phases=(
            Phase(name="Review by dimension", slug_override="review-by-dimension",
                  steps=reviewers, min_success="all", on_step_failure="abort",
                  max_parallel=len(reviewers)),
            Phase(name="Consolidate", slug_override="consolidate",
                  steps=(consolidator,), min_success="all",
                  on_step_failure="continue", max_parallel=1),
        ),
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--consolidate", type=Path, required=True)
    parser.add_argument("--dimensions", required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--review-phase", default="01.review-by-dimension")
    parser.add_argument("--output-phase", default="02.consolidate")
    ns = parser.parse_args(argv)
    review, _verdict = consolidate(ns.consolidate, _dimensions(ns.dimensions),
                                   review_phase=ns.review_phase,
                                   output_phase=ns.output_phase,
                                   output_dir=ns.output_dir)
    sys.stdout.write(review.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
