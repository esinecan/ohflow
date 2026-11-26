"""Stage 3 acceptance workflow: one agent, no fan-out.

One phase, one step, the implement phase of `implement_review.py` expressed as
an ohflow workflow: the lenient implementer tool policy, one design skill, a git
worktree, and a mechanical gate the agent never runs itself.

The repo is a scratch repo the check creates, so no real project is touched and
`node_modules_mode` is `none`.

    python -m ohflow.cli run --workflow <this file> --out <runs root> \\
        --args repo=<scratch repo> --args wt=<worktree path>
"""

from __future__ import annotations

from pathlib import Path

from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             ToolPolicy, AgentSpec, WorktreeSpec)

GLM_FLASH = ModelConfig(model="zai/glm-5.3-flash",
                        base_url="https://api.z.ai/api/coding/paas/v4",
                        api_key_env="ZAI_CODING_CN_API_KEY")

BRIEF = """# Task

Create one file, `greet.js`, in the root of this worktree. It exports one
function:

```js
export function greet(name) { ... }
```

`greet("world")` returns exactly the string `hello, world`. A name that is
empty or missing returns exactly `hello, stranger`.

# Acceptance, checked by the orchestrator and not by you

- `node -e "import('./greet.js').then(m => console.log(m.greet('world')))"`
  prints `hello, world`.
- `git log --oneline` shows at least one commit past the base.
- `git status --porcelain` prints nothing: everything is committed.
- `git diff --name-only <base>..HEAD` names `greet.js` and nothing else.
- No commit message carries an AI attribution trailer or a generated-with
  footer. Author the commit clean.

# Your report

End your final message with a line reading exactly `DONE`.
"""


def build(args: dict) -> Workflow:
    repo = Path(args["repo"])
    wt = Path(args.get("wt", str(repo.parent / "stage3-wt")))
    base = args.get("base", "main")
    skills_dir = Path(args["skills_dir"]) if args.get("skills_dir") else None
    skills = tuple(s for s in str(args.get("skills", "")).split(",") if s)
    max_iter = int(args.get("max_iterations", 60))
    timeout = int(args.get("execution_timeout_s", 1800))

    worktree = WorktreeSpec(
        name="impl",
        path=wt,
        branch=args.get("branch", "ohflow/s3-implement"),
        base=base,
        node_modules_mode="none",
    )

    step = Step(
        id="implement",
        kind="agent",
        worktree="impl",
        write_scope=("greet.js",),
        execution_timeout_s=timeout,
        note="the implement phase of implement_review.py, as one ohflow step",
        agent=AgentSpec(
            role="implementer",
            brief=BRIEF,
            model=GLM_FLASH,
            harness_executor="pi",
            tools=ToolPolicy(preset="default", enable_browser=False,
                             enable_sub_agents=False),
            skills=skills,
            skills_dir=skills_dir,
            max_iterations=max_iter,
        ),
        gate=GateSpec(checks=(
            CheckSpec("commits_past_base", {"min": 1}),
            CheckSpec("tree_clean", {}),
            CheckSpec("ownership", {"allowed": ["greet.js"]}),
            CheckSpec("no_ai_attribution", {}),
            CheckSpec("command_exit", {
                "cmd": "node -e \"import('./greet.js')"
                       ".then(m => { if (m.greet('world') !== 'hello, world') "
                       "process.exit(1); })\""}),
            CheckSpec("final_message_matches", {"regex": r"^DONE\s*$"}),
        )),
    )

    return Workflow(
        name="stage3-one agent",
        repo=repo,
        base_branch=base,
        baseline_cmd=None,
        max_parallel=1,
        args=dict(args),
        worktrees=(worktree,),
        phases=(Phase(name="Implement", steps=(step,), min_success="all",
                      on_step_failure="continue"),),
    )
