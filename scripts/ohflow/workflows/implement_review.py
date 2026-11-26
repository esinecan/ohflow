"""The two agent implement-then-review workflow, as an ohflow workflow.

`ohflow run --workflow` builds this workflow from its `--args` and runs it.

Three modes, and each one is two phases.

    all      create the worktree, install, implement, gate, review, gate
    review   reuse the worktree, gate it, review, gate
    fix      reuse the worktree, implement again from a fix brief, gate,
             review, gate

**`review` has a gate-only first step, not an empty phase.** The legacy driver
computed the three implement gates from the existing tree even when it ran no
implementer, and a phase with no steps would pass by having nothing to judge.
The step is `kind="gate"`, so the same three checks run and nothing is launched.

**The reused worktree reports the base it started from.** `WorktreeSpec.
base_sha_mode` is `merge_base` here, so `commits_past_base` counts the
implementer's commits rather than seeing `HEAD` and reading zero.

The tool policies keep the legacy driver's: the reviewer gets `only=("terminal",)`.

Arguments, all of them named by the shim:

    repo branch base worktree out mode
    impl_brief review_brief fix_brief
    install_cmd test_cmd impl_iter review_iter skills_dir
    harness_executor thinking carry_context fork_session
    model base_url api_key_env
    review_harness_executor review_model box

`out` and `carry_context` are recorded in `run.json`, and no step reads them.
`harness_executor` is required. A missing or empty `model` takes the `light`
tier on pi and durable, and a missing `base_url` or `api_key_env` takes the
Z.AI default on pi. `model` and `review_model` take a tier, `heavy` or
`light`, or a model id.

With ``dimensions`` and ``brief_dir``, the review becomes a parallel phase
with one schema-gated reviewer per dimension followed by the Python
consolidator from ``review_by_dimension``. ``harness_executors`` supplies optional
``dim=harness_executor`` overrides and ``schema_retry`` defaults to one.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

# Absolute, like every other workflow module. `workflow.load_workflow` imports a workflow by
# file path, so the module has no parent package and a relative import raises.
from ohflow import settings
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             ToolPolicy, AgentSpec, WorktreeSpec, HandoverSpec)
from ohflow.workflows.review_by_dimension import (_review_steps,
                                                  consolidation_step)

#: The name every phase's worktree is known by inside the workflow.
WORKTREE = "feature"

#: The verdict line the reviewer must produce. The capturing group is what the
#: `final_message_matches` check records.
VERDICT_REGEX = r"VERDICT:\s*(MERGEABLE|BLOCKED)"

#: The first phase's step id, which is the agent's role and the tail of its
#: coordinate.
IMPLEMENT_IDS = {"all": "implement", "fix": "fix", "review": "implement"}


REVIEW_HARNESS_EXECUTORS = ("pi", "claude", "durable")



def _model(args: dict, harness_executor: str, model: str | None) -> ModelConfig:
    if harness_executor in ("claude", "codex"):
        return ModelConfig(model=model or "", base_url="", api_key_env="")
    if harness_executor == "durable":
        # The host on the box holds its own keys and takes only the model id
        # and the thinking level, so no endpoint or key name crosses over.
        return ModelConfig(
            model=model or "light", base_url="", api_key_env="",
            params={"thinking": args.get("thinking") or "high"})
    return ModelConfig(
        model=model or "light",
        base_url=args.get("base_url") or "https://api.z.ai/api/coding/paas/v4",
        # A variable name. The key itself is read in the agent's own process
        # and never enters a spec, a run log or a brief.
        api_key_env=args.get("api_key_env") or "ZAI_CODING_CN_API_KEY",
        params={"thinking": args.get("thinking") or "high"},
    )


def _reviewer(args: dict) -> tuple[str, ModelConfig]:
    harness_executor = args["harness_executor"]
    reviewer = args.get("review_harness_executor") or harness_executor
    if reviewer not in REVIEW_HARNESS_EXECUTORS:
        raise ValueError(
            f"review_harness_executor {reviewer!r} cannot run a reviewer with the "
            f"terminal alone; use one of {', '.join(REVIEW_HARNESS_EXECUTORS)}")
    model = args.get("review_model") or (args.get("model") if reviewer == harness_executor else None)
    if reviewer == "claude" and not model:
        raise ValueError("a claude reviewer needs review_model; claude has no Z.AI default")
    return reviewer, _model(args, reviewer, model)


def _implement_gate(test_cmd: str) -> GateSpec:
    """E1a, E1b and E1c, in the order the legacy driver checked them."""
    return GateSpec(checks=(
        CheckSpec("commits_past_base", {"min": 1}),
        CheckSpec("command_exit", {"cmd": test_cmd, "expect": 0}),
        CheckSpec("tree_clean", {}),
    ))


def _review_gate(test_cmd: str) -> GateSpec:
    """E2a, E2b and E2c."""
    return GateSpec(checks=(
        CheckSpec("final_message_matches", {"regex": VERDICT_REGEX}),
        CheckSpec("tree_clean", {}),
        CheckSpec("command_exit", {"cmd": test_cmd, "expect": 0}),
    ))


def _dimension_review_gate(test_cmd: str) -> GateSpec:
    """The reusable split reports PASS/BLOCKED in its consolidated artifact."""
    return GateSpec(checks=(
        CheckSpec("final_message_matches", {
            "regex": r"VERDICT:\s*(PASS|BLOCKED)"}),
        CheckSpec("tree_clean", {}),
        CheckSpec("command_exit", {"cmd": test_cmd, "expect": 0}),
    ))


def build(args: dict) -> Workflow:
    mode = args.get("mode") or "all"
    if mode not in ("all", "review", "fix"):
        raise ValueError(f"unknown mode {mode!r}; use all, review or fix")

    repo = Path(args["repo"])
    worktree = Path(args["worktree"])
    base = args.get("base") or "main"
    test_cmd = args.get("test_cmd") or "npm test"
    install_cmd = args.get("install_cmd") or "npm ci --no-audit --no-fund"
    skills_dir = Path(args["skills_dir"]) if args.get("skills_dir") else None
    harness_executor = args["harness_executor"]
    box = args.get("box") or settings.get("durable.box")
    model = _model(args, harness_executor, args.get("model"))
    fresh = mode == "all"

    spec = WorktreeSpec(
        name=WORKTREE,
        path=worktree,
        branch=args["branch"],
        base=base,
        # The legacy driver ran `--install-cmd` once in the fresh worktree and
        # touched node_modules no other way.
        node_modules_mode="install" if fresh else "none",
        install_cmd=install_cmd if fresh else None,
        reuse_existing=not fresh,
        # Only meaningful for a reused worktree, and that is the case it exists
        # for: the tree already carries the implementer's commits.
        base_sha_mode="head" if fresh else "merge_base",
    )

    first_id = IMPLEMENT_IDS[mode]
    if mode == "review":
        # Not an empty phase. The three implement gates still judge the tree
        # that is already there, exactly as the legacy driver did.
        first_step = Step(
            id=first_id, kind="gate", worktree=WORKTREE,
            gate=_implement_gate(test_cmd),
            note="the implement gates, applied to the existing worktree")
    else:
        brief_key = "fix_brief" if mode == "fix" else "impl_brief"
        first_step = Step(
            id=first_id, kind="agent", worktree=WORKTREE,
            # The compatibility shim historically gave its implementer the
            # whole feature worktree.  Preserve that contract explicitly so
            # the pi edit/write guard does not interpret an empty ownership
            # set as "no files may be changed".
            write_scope=("**",),
            execution_timeout_s=int(args.get("execution_timeout_s") or 5400),
            gate=_implement_gate(test_cmd),
            note=f"the {first_id} agent, lenient tool policy",
            agent=AgentSpec(
                role=first_id,
                brief=Path(args[brief_key]).read_text(encoding="utf-8"),
                model=model,
                # The default preset: terminal, file_editor, task_tracker.
                tools=ToolPolicy(),
                skills=tuple(s.strip() for s in (args.get("impl_skills") or "").split(",") if s.strip()),
                # The box reads the skill by name from its own
                # ~/.agents/skills, so no directory on this machine applies.
                skills_dir=None if harness_executor == "durable" else skills_dir,
                box=box if harness_executor == "durable" else None,
                max_iterations=int(args.get("impl_iter") or 150),
                harness_executor=harness_executor,
                fork_session=args.get("fork_session")))

    dimensional = bool(args.get("dimensions"))
    if dimensional:
        review_steps = _review_steps(args, worktree=WORKTREE)
        reviewer_ids = tuple(step.id for step in review_steps)
        review_phases: tuple[Phase, ...] = (
            Phase(name="Review by dimension", steps=review_steps,
                  min_success="all", on_step_failure="abort",
                  max_parallel=len(review_steps),
                  slug_override="review-by-dimension"),
            Phase(name="Review", steps=(consolidation_step(
                      args, reviewer_ids, worktree=WORKTREE,
                      review_phase_number=2, output_phase_number=3,
                      output_phase_slug="review",
                      gate=_dimension_review_gate(test_cmd)),),
                  min_success="all", on_step_failure="continue", max_parallel=1,
                  slug_override="review"),
        )
    else:
        review_harness_executor, review_model = _reviewer(args)
        review_step = Step(
            id="review", kind="agent", worktree=WORKTREE,
            execution_timeout_s=int(args.get("execution_timeout_s") or 5400),
            gate=_review_gate(test_cmd),
            note="the reviewer, terminal only, no skills",
            agent=AgentSpec(
                role="review",
                brief=Path(args["review_brief"]).read_text(encoding="utf-8"),
                model=review_model,
                # `terminal` alone. The gate on the clean tree is what proves the
                # reviewer obeyed the no-edit rule, because `terminal` can write
                # files whatever the tool policy says.
                tools=ToolPolicy(only=("terminal",)),
                skills=(),
                skills_dir=None if review_harness_executor in ("claude", "durable") else skills_dir,
                agent_profile="hermetic" if review_harness_executor == "claude" else None,
                box=box if review_harness_executor == "durable" else None,
                max_iterations=int(args.get("review_iter") or 80),
                harness_executor=review_harness_executor))
        review_phases = (
            Phase(name="Review", steps=(review_step,), min_success="all",
                  on_step_failure="continue", max_parallel=1,
                  slug_override="review"),
        )

    if mode != "review":
        first_step = replace(first_step, handover=HandoverSpec(audience="reviewer"))
        review_phases = tuple(replace(phase, steps=tuple(
            replace(s, depends_on=tuple(dict.fromkeys(s.depends_on + (first_id,))), consumes=(first_id,))
            if s.kind == "agent" else s for s in phase.steps)) for phase in review_phases)

    return Workflow(
        name="implement-review",
        repo=repo,
        base_branch=base,
        # The legacy driver ran no baseline command, and the caller's own
        # preflight is what it relied on.
        baseline_cmd=None,
        max_parallel=1,
        # One agent at a time, so nothing here needs an auto-resume pass or a retry. Both
        # stay at their defaults, which is off.
        transient_backoff_s=int(args.get("transient_backoff_s") or 0),
        worktrees=(spec,),
        args=dict(args),
        phases=(
            # The shim requires a passed implement gate before review. `abort`
            # expresses that requirement now that `continue` always lets later
            # phases run, regardless of `min_success`.
            Phase(name="Implement", steps=(first_step,), min_success="all",
                  on_step_failure="abort", max_parallel=1,
                  slug_override="implement"),
        ) + review_phases,
    )
