"""A deliberately invalid workflow: two steps in one phase own the same file.

`ohflow validate --workflow <this file>` must exit 2 and name both steps.
It is the negative half of the stage 1 acceptance check.
"""

from __future__ import annotations

from pathlib import Path

from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             AgentSpec, WorktreeSpec)

GLM_FLASH = ModelConfig(model="zai/glm-5.3-flash",
                        base_url="https://api.z.ai/api/coding/paas/v4",
                        api_key_env="ZAI_CODING_CN_API_KEY")


def _agent(brief: str) -> AgentSpec:
    return AgentSpec(role="implementer", brief=brief, model=GLM_FLASH, harness_executor="pi")


def build(args: dict) -> Workflow:
    repo = Path(args.get("repo", r"C:\Users\<user>\dev\mcp-inspector-as-mcp-server"))
    wt_root = Path(args.get("wt_root", r"C:\Users\<user>\dev\_wt"))
    gate = GateSpec(checks=(CheckSpec("tree_clean", {}),))
    return Workflow(
        name="stage1-overlap",
        repo=repo,
        worktrees=(
            WorktreeSpec(name="a", path=wt_root / "ov-a", branch="exp/ov-a",
                         base="main"),
            WorktreeSpec(name="b", path=wt_root / "ov-b", branch="exp/ov-b",
                         base="main"),
        ),
        phases=(Phase(name="Overlapping batch", steps=(
            Step(id="writer-one", kind="agent", worktree="a",
                 write_scope=("src/cli/spill.ts", "src/cli/shared.ts"),
                 agent=_agent("write spill.ts"), gate=gate),
            Step(id="writer-two", kind="agent", worktree="b",
                 write_scope=("src/cli/shared.ts", "src/cli/encode.ts"),
                 agent=_agent("write encode.ts"), gate=gate),
        )),),
    )
