"""Copy-and-specialize template for parallel pieces that share a contracts file.

Required args: repo=<git repo> root=<output root> spec=<spec file>
               contracts=<contracts.md> test_cmd=<test command>
               pieces=<name=glob[;glob],name=glob[;glob],...>
Optional args: base=main branch_prefix=fanout harness_executor=pi model=<id>
               review_harness_executor=<harness> review_model=<id>
               max_parallel=5 execution_timeout_s=5400

Each piece runs as one agent step named after it, on its own worktree and
branch, inside its own write scope, against the same contracts. The merge
phase brings every branch into one output branch, and one reviewer reads
all of them against the spec and the contracts and runs the test command. Its
gate fails on a non-empty blocking list; the orchestrator agent then starts
the fix run that references/brief-templates.md describes under
"contract_fanout briefs".
"""

import re
import sys
from pathlib import Path

from ohflow.gates import BASE
from ohflow.workflow import (
    CheckSpec, Contracts, GateSpec, Phase, Workflow, Step, AgentSpec,
    ToolPolicy, WorktreeSpec, HandoverSpec, clean_commit_checks,
)
from ohflow.workflows.implement_review import _model, _reviewer

PIECE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RESERVED = frozenset({"output", "review"})
OUTPUT = "output"
LOCAL_HARNESS_EXECUTORS = ("pi", "claude", "codex")

FINDING = {
    "type": "object",
    "required": ["piece", "path", "line", "claim"],
    "properties": {
        "piece": {"type": "string"},
        "path": {"type": "string"},
        "line": {"type": "integer"},
        "contract": {"type": "string"},
        "claim": {"type": "string"},
        "fix": {"type": "string"},
    },
}

REVIEW_SCHEMA = {
    "type": "object",
    "required": ["blocking", "should_fix", "notes", "suite", "summary"],
    "properties": {
        "blocking": {"type": "array", "items": FINDING},
        "should_fix": {"type": "array", "items": FINDING},
        "notes": {"type": "array", "items": FINDING},
        "suite": {"type": "object", "required": ["command", "exit"],
                  "properties": {"command": {"type": "string"},
                                 "exit": {"type": "integer"}}},
        "summary": {"type": "string"},
    },
}

CHILD_BRIEF = """# Task: build the piece `{name}`

You are in a git worktree of `{repo}`, on branch `{branch}`. Pieces beside you
run at the same time on their own branches, and none of you sees the others'
work. Build the piece `{name}` as the spec at `{spec}` describes it. Your write
scope is {scope}; every other path is frozen.

## Contracts

`{contracts}` fixes every interface your piece shares with another piece. Build
against it exactly, and call the other pieces only through it. If a contract is
unworkable for your piece, stop: commit nothing that works around it, and name
the contract and the reason in your handover under Open.

## Heartbeat

`{heartbeat}` is the one file outside your worktree you write; the position
block's rule against writing outside your worktree does not cover it, and your
gate checks it. Before any other command, append one line to it:
`echo "$(date -u +%FT%TZ) {name} start" >> "{heartbeat}"`.
As your last command, append one line naming the outcome, `done` or
`stopped: <contract>`: `echo "$(date -u +%FT%TZ) {name} end <outcome>" >> "{heartbeat}"`.

## Definition of done

1. Every behaviour the spec gives `{name}` exists inside your write scope.
2. The tests of your piece pass; name the command and its result.
3. Hand-try: use the piece once by hand, the way its caller would, through the
   interface the contracts name. Paste the command and its output in your
   handover under Hand-try.
4. Every change is committed on `{branch}`, `git status --porcelain` prints
   nothing, and no commit message names an AI tool or model.
"""

REVIEW_BRIEF = """# Task: review the merged pieces against the spec and the contracts

You are in the output worktree of `{repo}`, on branch `{branch}`, where
the branches {branches} are merged onto `{base}`. You have a terminal and
nothing else. Do not edit, create or delete any file in this worktree, and do
not commit.

1. Read the spec at `{spec}` and the contracts at `{contracts}`.
2. For each piece, read `git diff {base}...<its branch>` and its handover.
   Check the piece against its part of the spec and against every contract it
   makes or uses. Run each piece's hand-try again.
3. Run `{test_cmd}` once in this worktree and record the command and its exit.
4. Sort every finding into one list. `blocking`: it breaks a contract, the
   spec or the test command, and you would not merge over it. `should_fix`: it
   is wrong but the merge can stand. `notes`: anything else worth knowing.

A non-empty `blocking` list fails this step on purpose: that is how the fix
cycle starts. Report every blocking finding you find. Give each finding its
piece, a repository-relative path, a one-based line, the contract it breaks
when one does, the claim, and the fix in one sentence.
"""


def _pieces(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("pieces must be name=glob[;glob] pairs, comma-separated")
    out: dict[str, tuple[str, ...]] = {}
    for entry in value.split(","):
        name, sep, scope = (part.strip() for part in entry.partition("="))
        globs = tuple(g.strip() for g in scope.split(";") if g.strip())
        if not sep or not globs:
            raise ValueError(f"piece {entry!r} needs name=glob")
        if not PIECE_NAME.fullmatch(name) or name in RESERVED:
            raise ValueError(f"piece name {name!r} must match {PIECE_NAME.pattern} "
                             f"and not be one of {sorted(RESERVED)}")
        if name in out:
            raise ValueError(f"piece {name!r} is named twice")
        out[name] = globs
    if len(out) < 2:
        raise ValueError("a contract fan-out needs at least two pieces")
    return out


def blocking_gate_cmd() -> str:
    python = Path(sys.executable).as_posix()
    return (f'"{python}" -c "import json,os,sys; '
            f"s=json.load(open(os.path.join(os.environ['OHFLOW_ATTEMPT_DIR'],"
            f"'result.json'),encoding='utf-8')).get('structured'); "
            f"sys.exit(0 if isinstance(s,dict) and s.get('blocking')==[] else 1)\"")


def _local(key: str, executor: str) -> None:
    if executor not in LOCAL_HARNESS_EXECUTORS:
        raise ValueError(
            f"{key} {executor!r} runs its agent on another machine, where the spec, "
            f"the contracts file and the heartbeat log are not at their local paths; "
            f"use one of {', '.join(LOCAL_HARNESS_EXECUTORS)}")


def heartbeat_check(name: str, heartbeat: str) -> CheckSpec:
    return CheckSpec("command_exit", {"cmd": f'grep -q -- " {name} start" "{heartbeat}" '
                                             f'&& grep -q -- " {name} end " "{heartbeat}"'})


def build(args: dict) -> Workflow:
    for key in ("repo", "root", "spec", "contracts", "test_cmd", "pieces"):
        if not args.get(key):
            raise ValueError(f"contract_fanout requires {key}=")
    repo, root = Path(args["repo"]), Path(args["root"]).resolve()
    base, prefix = args.get("base") or "main", args.get("branch_prefix") or "fanout"
    pieces = _pieces(args["pieces"])
    contracts = Contracts.read(Path(args["contracts"]).resolve())
    spec, test_cmd = Path(args["spec"]).resolve(), args["test_cmd"]
    harness = args.get("harness_executor") or "pi"
    model = _model(args, harness, args.get("model"))
    _local("harness_executor", harness)
    review_harness, review_model = _reviewer({**args, "harness_executor": harness})
    _local("review_harness_executor", review_harness)
    timeout = int(args.get("execution_timeout_s") or 5400)
    parallel = min(int(args.get("max_parallel") or 5), 5, len(pieces))
    heartbeat = (root / "heartbeat.log").as_posix()
    branch = {n: f"{prefix}/{n}" for n in [*pieces, OUTPUT]}
    worktrees = tuple(WorktreeSpec(n, root / "worktrees" / n, branch[n], base, "none")
                      for n in branch)

    children = tuple(
        Step(id=name, kind="agent", worktree=name, write_scope=scope,
             handover=HandoverSpec(audience="consolidator", extra=("Hand-try",)),
             execution_timeout_s=timeout,
             gate=GateSpec((*clean_commit_checks(scope), heartbeat_check(name, heartbeat))),
             note=f"piece {name}: {', '.join(scope)}",
             objective=f"builds piece {name} inside {', '.join(scope)} against the contracts",
             agent=AgentSpec(role=f"piece-{name}", model=model, harness_executor=harness,
                             max_iterations=150,
                             brief=CHILD_BRIEF.format(
                                 name=name, repo=repo.name, branch=branch[name],
                                 spec=spec.as_posix(), scope=", ".join(f"`{g}`" for g in scope),
                                 contracts=contracts.path.as_posix(), heartbeat=heartbeat)))
        for name, scope in pieces.items())
    names = tuple(pieces)

    merges = tuple(
        Step(id=f"merge-{name}", kind="merge", worktree=OUTPUT, depends_on=(name,),
             merge_branch=branch[name], merge_message=f"contract fan-out: merge {name}")
        for name in names)

    review = Step(
        id="review", kind="agent", worktree=OUTPUT,
        depends_on=names + tuple(m.id for m in merges), consumes=names,
        execution_timeout_s=timeout, schema=REVIEW_SCHEMA,
        gate=GateSpec((CheckSpec("tree_clean", {}), CheckSpec("schema_valid", {}),
                       CheckSpec("command_exit", {"cmd": test_cmd, "expect": 0}),
                       CheckSpec("command_exit", {"cmd": blocking_gate_cmd(), "expect": 0}))),
        note="one review of every branch against the spec and the contracts",
        objective="reviews the merged pieces against the spec and the contracts",
        agent=AgentSpec(role="review", model=review_model, harness_executor=review_harness,
                        tools=ToolPolicy(only=("terminal",)),
                        agent_profile="hermetic" if review_harness == "claude" else None,
                        max_iterations=120,
                        brief=REVIEW_BRIEF.format(
                            repo=repo.name, branch=branch[OUTPUT], base=base,
                            branches=", ".join(f"`{branch[n]}`" for n in names),
                            spec=spec.as_posix(), contracts=contracts.path.as_posix(),
                            test_cmd=test_cmd.replace(BASE, base))))

    return Workflow(
        name=f"contract-fanout-{repo.name}", repo=repo, base_branch=base,
        baseline_cmd=None, max_parallel=parallel, args=dict(args),
        worktrees=worktrees, contracts=contracts,
        phases=(
            Phase("Build pieces", children, "abort", "all", parallel),
            Phase("Merge pieces", merges, "abort", "all", 1),
            Phase("Review", (review,), "continue", "all", 1),
        ))
