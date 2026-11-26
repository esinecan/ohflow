"""Coordinates and the position block. Pure functions, no I/O.

The coordinate is the step directory name, the `usage_id` on the LLM, the
run log key, the board row key and the gate report key. One string joins the
brief, the transcript, the token bucket and the verdict.

`render_position` is the whole answer to the position requirement. Every clause
comes from a field the engine already holds, so no brief author can make it
drift from the run.
"""

from __future__ import annotations

from typing import Any

from .run_log import RunState, StepRecord
from .paths import win
from .workflow import Contracts, Workflow, Step, carried_by_git

__all__ = ["coord", "coord_of", "phase_coord", "render_position", "render_gate",
           "render_schema_contract", "step_dir_parts"]


def coord(phase_index: int, phase_name: str, step_index: int, step_id: str) -> str:
    """02.batch-a/01.c9-spill - both indexes 1-based."""
    return f"{phase_index:02d}.{phase_name}/{step_index:02d}.{step_id}"


def phase_coord(phase_index: int, phase_slug: str) -> str:
    return f"{phase_index:02d}.{phase_slug}"


def coord_of(workflow: Workflow, step_id: str) -> str:
    pi, phase, si, step = workflow.step_by_id(step_id)
    return coord(pi, phase.slug, si, step.id)


def step_dir_parts(c: str) -> tuple[str, str]:
    """'02.batch-a/01.c9-spill' -> ('02.batch-a', '01.c9-spill')."""
    head, _, tail = c.partition("/")
    return head, tail


# ------------------------------------------------------------------- render


def render_gate(step: Step, indent: str = "  ") -> list[str]:
    """One line per check, in workflow order, in the words the check itself uses."""
    if step.gate is None or not step.gate.checks:
        return [indent + "none - this step has no mechanical gate"]
    from . import gates
    out = []
    for check in step.gate.checks:
        fn = gates.REGISTRY.get(check.name)
        describe = getattr(fn, "describe", None)
        if describe is not None:
            out.append(indent + describe(dict(check.args)))
        else:
            args = ", ".join(f"{k}={v!r}" for k, v in sorted(dict(check.args).items()))
            out.append(indent + f"{check.name}({args})")
    return out


# ------------------------------------------------------- the output contract

#: A schema bigger than this renders its first lines and points at the file.
SCHEMA_LINE_BUDGET = 120


def _type_word(schema: dict) -> str:
    t = schema.get("type")
    if t == "array":
        item = (schema.get("items") or {}).get("type")
        return f"array of {item}" if item else "array"
    return t or "any"


def render_schema_contract(schema: dict | None,
                           schema_path: str | None = None,
                           report_path: str | None = None) -> list[str]:
    """The keys the `schema_valid` gate will check, in the agent's words.

    The outline walks `type`, `required`, `properties`, `items` and `enum`, which
    is exactly the subset `gates._validate_schema` enforces. The agent therefore
    reads the criterion it will be judged by, generated from the same dict the
    gate reads. Nothing here is written by a brief author, so nothing here can
    drift from the gate.
    """
    if not schema:
        return []
    if report_path:
        shape = (f"  Write one JSON object with these keys to {report_path} "
                 "in your worktree. The gate reads that file, not your "
                 "messages:")
    else:
        shape = ("  Your final message must end with one fenced ```json "
                 "block. It holds one object with these keys:")
    out: list[str] = [
        "Your output contract, checked by the `schema_valid` gate:",
        shape,
    ]
    required = list(schema.get("required") or [])
    if required:
        out.append("  Required at the top level: " + ", ".join(required))
    body: list[str] = []
    _walk(schema, body, indent="    ", budget=SCHEMA_LINE_BUDGET)
    out.extend(body)
    if len(body) >= SCHEMA_LINE_BUDGET:
        out.append("    ... the rest of the contract is in schema.json")
    if schema_path:
        out.append(f"  The same contract, as JSON Schema: {schema_path}")
    return out


def _walk(schema: dict, out: list[str], indent: str, budget: int) -> None:
    if len(out) >= budget:
        return
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    for key, sub in properties.items():
        if len(out) >= budget:
            return
        sub = sub if isinstance(sub, dict) else {}
        mark = "required" if key in required else "optional"
        line = f"{indent}{key}  -  {_type_word(sub)}, {mark}"
        if sub.get("enum"):
            line += "  one of: " + " | ".join(str(v) for v in sub["enum"])
        out.append(line)
        if sub.get("type") == "object":
            _walk(sub, out, indent + "  ", budget)
        elif sub.get("type") == "array" and isinstance(sub.get("items"), dict):
            item = sub["items"]
            if item.get("properties"):
                out.append(f"{indent}  each item is an object with:")
                _walk(item, out, indent + "    ", budget)
            elif item.get("enum"):
                out.append(f"{indent}  each item is one of: "
                           + " | ".join(str(v) for v in item["enum"]))


def _worktree_facts(workflow: Workflow, state: RunState, step: Step) -> dict[str, Any]:
    if step.worktree is None:
        return {}
    spec = workflow.worktree(step.worktree)
    live = (state.meta.get("worktrees") or {}).get(step.worktree, {})
    return {
        "path": live.get("path") or str(spec.path),
        "branch": live.get("branch") or spec.branch,
        "base": live.get("base") or spec.base,
        "base_sha": live.get("base_sha"),
    }


def _merged_before(workflow: Workflow, state: RunState, phase_index: int) -> list[str]:
    """Every step in an earlier phase, with its verdict. Comes from the run log,
    so it states what actually happened and not what the workflow hoped for."""
    lines: list[str] = []
    for pi, phase, si, st in workflow.steps():
        if pi >= phase_index:
            continue
        c = coord(pi, phase.slug, si, st.id)
        rec: StepRecord | None = state.steps.get(c)
        status = rec.status if rec else "pending"
        sha = (rec.head_sha[:7] if rec and rec.head_sha else "-")
        # `cached` renders exactly like `passed` on purpose. The position block
        # feeds the fingerprint, so a step that reads "gate PASSED (cached)" on
        # a resume would get a different fingerprint from the same step on the
        # first run, and nothing downstream would ever cache.
        verdict = {
            "passed": "gate PASSED", "cached": "gate PASSED",
            "failed": "gate FAILED", "timeout": "TIMED OUT",
            "quarantined": "QUARANTINED", "skipped": "skipped",
            "deferred": "DEFERRED - not run, a transient failure deferred it",
        }.get(status, "not run yet")
        note = f" - {st.note}" if st.note else ""
        lines.append(f"  {c} - role `{_role(st)}` - commit {sha} - {verdict}{note}")
    return lines


def _role(step: Step) -> str:
    if step.agent is not None:
        return step.agent.role
    return step.kind


def _quarantined(workflow: Workflow, state: RunState, phase_index: int) -> list[str]:
    out = []
    for pi, phase, si, st in workflow.steps():
        if pi >= phase_index:
            continue
        c = coord(pi, phase.slug, si, st.id)
        rec = state.steps.get(c)
        if rec and rec.status in ("quarantined", "failed", "timeout"):
            branch = rec.branch or (workflow.worktree(st.worktree).branch
                                    if st.worktree else "-")
            out.append(f"  {c} on branch {branch} - status {rec.status}")
    return out


def _beside(workflow: Workflow, phase_index: int, step_id: str) -> list[str]:
    phase = workflow.phases[phase_index - 1]
    out = []
    for si, st in enumerate(phase.steps, start=1):
        if st.id == step_id:
            continue
        c = coord(phase_index, phase.slug, si, st.id)
        write_scope = ", ".join(st.write_scope) if st.write_scope else "no declared write scope"
        out.append(f"  {c} write scope: {write_scope}")
    return out


def _after(workflow: Workflow, phase_index: int, step: Step) -> list[str]:
    """The next phase's steps that name this step's worktree or branch."""
    if phase_index >= len(workflow.phases):
        return []
    nxt_index = phase_index + 1
    nxt = workflow.phases[nxt_index - 1]
    branch = workflow.worktree(step.worktree).branch if step.worktree else None
    out = []
    for si, st in enumerate(nxt.steps, start=1):
        touches = (st.merge_branch == branch) or (st.worktree == step.worktree)
        if not touches:
            continue
        c = coord(nxt_index, nxt.slug, si, st.id)
        if st.kind == "merge":
            out.append(f"  {c} - a mechanical `git merge --no-ff {st.merge_branch}` "
                       f"run by the orchestrator. A textual conflict there means "
                       f"you wrote outside your write scope.")
        else:
            out.append(f"  {c} - a {st.kind} step, role `{_role(st)}`, in the same "
                       f"worktree.")
    if out:
        out.insert(0, f'Consolidates after you (phase {nxt_index} - "{nxt.name}"):')
    return out


def _work_of(workflow: Workflow, step: Step) -> str:
    """Where a step's commits sit: its workspace, worktree and branch."""
    space = workflow.workspace_of(step.worktree)
    if step.worktree is None:
        return f"workspace `{space.name}`, {win(space.path)}"
    spec = workflow.worktree(step.worktree)
    return (f"workspace `{space.name}`, worktree {win(spec.path)}, "
            f"branch {spec.branch}")


def _other_workspaces(workflow: Workflow, step: Step) -> list[str]:
    """The workspaces a step may read and may not write, in a workflow that
    has more than one."""
    spaces = workflow.all_workspaces()
    if len(spaces) < 2:
        return []
    mine = workflow.workspace_of(step.worktree)
    out = [f"Other workspaces of this run. Your commits, your diff and your "
           f"write scope are in workspace `{mine.name}` alone:"]
    for space in spaces:
        if space.name == mine.name:
            continue
        out.append(f"  {space.name} - {win(space.path)}"
                   + (" - owned by ohflow" if space.owned else ""))
        for w in workflow.worktrees:
            if workflow.workspace(w.workspace).name == space.name:
                out.append(f"    worktree {w.name}: {win(w.path)}, branch {w.branch}")
    if step.agent is not None and carried_by_git(step.agent):
        out.append("  This step runs on another machine, which holds your "
                   "workspace alone. You cannot read the others there.")
    else:
        out.append("  You may read them. Write nothing there.")
    return out


def _contracts(contracts: Contracts, step: Step) -> list[str]:
    where = "your handover" if step.handover is not None else "your report"
    return [f"Contracts: {win(contracts.path)}",
            "  Fixed for this run. Every step builds against them, the steps beside you too.",
            "  You may not change them, and you may not work around them.",
            f"  If a contract is unworkable, stop and say in {where} which contract fails and why.",
            "~~~~ contracts",
            contracts.text.rstrip(),
            "~~~~"]


def render_position(workflow: Workflow, state: RunState, step: Step, *,
                    attempt: int = 1,
                    previous_failures: list[str] | None = None,
                    include_run_id: bool = True,
                    schema_path: str | None = None,
                    handovers: dict[str, tuple[str, str]] | None = None,
                    handover_path: str | None = None,
                    previous_handover: str | None = None) -> str:
    """The block the engine prepends to every brief and writes to position.md.

    `include_run_id=False` is used by the fingerprint, so that a new run id
    alone never invalidates the cache. It suppresses `schema_path` for the same
    reason: that path names the run directory. The schema's key names are not
    suppressed, because a changed contract is a changed brief and the step must
    then run again.
    """
    pi, phase, si, _ = workflow.step_by_id(step.id)
    c = coord(pi, phase.slug, si, step.id)
    wt = _worktree_facts(workflow, state, step)

    L: list[str] = ["## Your position in this run", ""]
    if include_run_id:
        L.append(f"Run:       {state.run_id or '(not started)'}     "
                 f"workflow: {workflow.name}")
    L.append(f'Phase:     {pi} of {len(workflow.phases)} - "{phase.name}"')
    L.append(f"Step:      {si} of {len(phase.steps)} in this phase - "
             f"id `{step.id}`, role `{_role(step)}`, attempt {attempt}")
    L.append(f"Coordinate: {c}")
    if wt:
        L.append(f"Worktree:  {win(wt['path'])}")
        sha = wt["base_sha"][:7] if wt.get("base_sha") else "(not created yet)"
        L.append(f"           branch {wt['branch']}, created from "
                 f"{wt['base']} at {sha}")
    if step.write_scope:
        L.append(f"Write scope: {', '.join(step.write_scope)}")
        L.append("Frozen:    every other path in this repository")
    else:
        L.append("Write scope: no path is reserved for you in this workflow")
    L.append("")

    others = _other_workspaces(workflow, step)
    if others:
        L.extend(others)
        L.append("")

    if workflow.contracts is not None:
        L.extend(_contracts(workflow.contracts, step))
        L.append("")

    merged = _merged_before(workflow, state, pi)
    if merged:
        L.append(f"Already done, before you (phases 1 to {pi - 1}):")
        L.extend(merged)
        L.append("")

    quarantined = _quarantined(workflow, state, pi)
    if quarantined:
        L.append("Quarantined, excluded from consolidation:")
        L.extend(quarantined)
        L.append("  Nothing from those branches reaches the integration branch. "
                 "Do not assume their work exists.")
        L.append("")

    if step.consumes:
        L.append("Handed to you (producer findings are claims to verify):")
        for sid in step.consumes:
            dc = coord_of(workflow, sid)
            rec = state.steps.get(dc)
            producer = workflow.step_by_id(sid)[3]
            L.append(f"  {dc} - role `{_role(producer)}` - commit "
                     f"{rec.head_sha if rec and rec.head_sha else '-'} - "
                     f"{'gate PASSED' if rec and rec.ok else 'not passed'}")
            if others:
                L.append(f"  its work: {_work_of(workflow, producer)}")
            if include_run_id:
                item = (handovers or {}).get(sid)
                if item:
                    path, text = item
                    L.extend([f"  file: {win(path)}", text])
                else:
                    L.append("  handover: not available (no accepted attempt, or dry run)")
        L.append("")

    beside = _beside(workflow, pi, step.id)
    if beside:
        L.append("Running beside you right now (same phase, same base commit, "
                 "do not wait for them):")
        L.extend(beside)
        L.append("")

    after = _after(workflow, pi, step)
    if after:
        L.extend(after)
        L.append("")

    L.append("Your gate, run by the orchestrator and not by you:")
    L.extend(render_gate(step))
    L.append("")

    report_path = next(
        (c.args.get("path") for c in (step.gate.checks if step.gate else ())
         if c.name == "schema_valid" and c.args.get("path")), None)
    contract = render_schema_contract(
        dict(step.schema) if step.schema else None,
        schema_path if include_run_id else None,
        report_path=report_path)
    if contract:
        L.extend(contract)
        L.append("")

    if step.handover is not None:
        from .handover import instructions
        readers = workflow.steps_consuming(step.id)
        audience = ", ".join(f"{s.id} (role `{_role(s)}`)" for s in readers) or step.handover.audience
        L.append(f"Your handover, read by {audience}:")
        destination = win(handover_path) if include_run_id and handover_path else "handover.md in this attempt's directory"
        L.append(f"Write {destination} before your final message. At most {step.handover.max_chars} characters.")
        L.append(instructions(step.handover))
        L.append("")

    if attempt > 1 and (previous_failures or previous_handover):
        L.append(f"What failed last time (attempt {attempt - 1}):")
        for f in previous_failures or []:
            L.append(f"  {f}")
        if previous_handover:
            L.extend(["Previous attempt's handover (may describe incomplete work):", previous_handover])
        L.append("")

    L.append("Your report is your final message. Write no file outside your "
             "worktree" + (", except your handover at the path above." if step.handover else "."))
    return "\n".join(L) + "\n"
