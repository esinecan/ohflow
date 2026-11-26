"""Stage 1 acceptance workflow: validation, coordinates and the position block.

No step here is ever executed by the stage 1 check. The workflow exists so that
`ohflow validate`, `ohflow board` and `ohflow position` have a workflow with the
shape the first consumer has: a scaffold phase, a parallel batch of three
file-owning implementers, and a consolidation phase of mechanical merges.

Step ids match the ones named in the stage 1 acceptance check of the workflow
document (`c9-spill`, `c2-describe`, `c4-format`).

    python -m ohflow.cli validate --workflow <this file>
    python -m ohflow.cli position --workflow <this file> --step c9-spill
"""

from __future__ import annotations

from pathlib import Path

from ohflow.workflow import (
    CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step, ToolPolicy, AgentSpec,
    WorktreeSpec,
)

GLM_FLASH = ModelConfig(
    model="zai/glm-5.3-flash",
    base_url="https://api.z.ai/api/coding/paas/v4",
    api_key_env="ZAI_CODING_CN_API_KEY",
)

CANDIDATES = [
    ("c9-spill", "spill", "candidate 9: spill oversized tool output to a file"),
    ("c2-describe", "describe", "candidate 2: a describe command for one tool"),
    ("c4-format", "encode", "candidate 4: an output encoder"),
]


def implementer_gate(base_branch: str, write_scope: tuple[str, ...]) -> GateSpec:
    return GateSpec(checks=(
        CheckSpec("commits_past_base", {"min": 1}),
        CheckSpec("test_counts", {"cmd": "npm test", "min_passed": 263,
                                  "max_failed": 0, "parser": "vitest"}),
        CheckSpec("command_exit", {"cmd": "npx tsc --noEmit"}),
        CheckSpec("command_exit", {"cmd": "npm run build"}),
        CheckSpec("tree_clean", {}),
        CheckSpec("ownership", {"allowed": list(write_scope)}),
        CheckSpec("paths_untouched", {"globs": ["package.json",
                                                "package-lock.json"]}),
        CheckSpec("no_ai_attribution", {}),
    ))


def build(args: dict) -> Workflow:
    repo = Path(args.get("repo", r"C:\Users\<user>\dev\mcp-inspector-as-mcp-server"))
    wt_root = Path(args.get("wt_root", r"C:\Users\<user>\dev\_wt"))
    base = args.get("base", "main")
    skills_dir = Path(args["skills_dir"]) if args.get("skills_dir") else None

    integration = WorktreeSpec(
        name="integration",
        path=wt_root / "prune-integration",
        branch="exp/prune-integration",
        base=base,
    )
    per_candidate = tuple(
        WorktreeSpec(name=cid, path=wt_root / cid, branch=f"exp/prune-{cid}",
                     base="exp/prune-integration")
        for cid, _, _ in CANDIDATES
    )

    scaffold = Step(
        id="scaffold",
        kind="agent",
        worktree="integration",
        write_scope=("src/cli/args.ts", "src/cli/index.ts", "src/cli/config.ts",
                     "src/cli/output.ts"),
        note="writes the shared files every candidate imports",
        agent=AgentSpec(
            role="implementer",
            brief="Write the shared CLI scaffolding. Every candidate module is "
                  "imported and called from index.ts before you finish.",
            model=GLM_FLASH,
            harness_executor="pi",
            tools=ToolPolicy(),
            skills=("codebase-design",),
            skills_dir=skills_dir,
            max_iterations=150,
        ),
        gate=implementer_gate(base, ("src/cli/args.ts", "src/cli/index.ts",
                                     "src/cli/config.ts", "src/cli/output.ts")),
    )

    batch = []
    for cid, module, title in CANDIDATES:
        write_scope = (f"src/cli/{module}.ts", f"src/cli/{module}.test.ts")
        batch.append(Step(
            id=cid,
            kind="agent",
            worktree=cid,
            write_scope=write_scope,
            depends_on=("scaffold",),
            note=title,
            agent=AgentSpec(
                role="implementer",
                brief=f"Implement {title}. Touch only the files you own.",
                model=GLM_FLASH,
                harness_executor="pi",
                tools=ToolPolicy(),
                skills=("codebase-design",),
                skills_dir=skills_dir,
                max_iterations=150,
            ),
            gate=implementer_gate("exp/prune-integration", write_scope),
        ))

    consolidate = [
        Step(id=f"merge-{cid}", kind="merge", worktree="integration",
             merge_branch=f"exp/prune-{cid}", depends_on=(cid,),
             note=f"mechanical merge of {cid}",
             gate=GateSpec(checks=(
                 CheckSpec("test_counts", {"cmd": "npm test", "min_passed": 263}),
                 CheckSpec("tree_clean", {}),
             )))
        for cid, _, _ in CANDIDATES
    ]

    return Workflow(
        name="stage1-demo",
        repo=repo,
        base_branch=base,
        baseline_cmd="npm test",
        max_parallel=3,
        args=dict(args),
        worktrees=(integration,) + per_candidate,
        phases=(
            Phase(name="Scaffold", steps=(scaffold,), min_success="all",
                  on_step_failure="abort"),
            Phase(name="Generate: batch A", steps=tuple(batch),
                  min_success="any", on_step_failure="quarantine"),
            Phase(name="Consolidate A", steps=tuple(consolidate),
                  min_success="any", on_step_failure="quarantine"),
        ),
    )
