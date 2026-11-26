"""Stage 2 acceptance workflow: exec, worktrees and the whole gate library.

No agent runs here. Three junctioned worktrees are created off one base. One
branch is seeded to be known-good and one to be known-bad, then the same gate --
every built-in check -- runs against both. `gate.json` `passed` must read true
for the good branch and false for the bad one, and every individual check must
land where the header table below says it lands.

| check                 | good | bad  | why the bad one fails                 |
|-----------------------|------|------|---------------------------------------|
| commits_past_base     | pass | pass | both branches commit once             |
| test_counts           | pass | FAIL | the bad branch adds a failing test    |
| command_exit tsc      | pass | FAIL | the bad branch adds a type error      |
| command_exit build    | pass | FAIL | the same type error                   |
| tree_clean            | pass | FAIL | the bad branch leaves a stray file    |
| ownership             | pass | FAIL | the bad branch writes outside its set |
| paths_untouched       | pass | FAIL | the bad branch edits package.json     |
| no_ai_attribution     | pass | FAIL | the bad commit carries a trailer      |
| final_message_matches | pass | FAIL | the bad step prints no VERDICT line   |
| schema_valid          | pass | FAIL | the bad step prints invalid JSON      |

    python -m ohflow.cli run --workflow <this file> --out <runs root>
"""

from __future__ import annotations

from pathlib import Path

from ohflow.workflow import (CheckSpec, GateSpec, Phase, Workflow, Step, WorktreeSpec)

GOOD_WRITE_SCOPE = ("src/cli/s2good.ts", "src/cli/s2good.test.ts")
BAD_WRITE_SCOPE = ("src/cli/s2bad.ts",)

VERDICT_RE = r"VERDICT:\s*(MERGEABLE|BLOCKED)"
FINDINGS_SCHEMA = {
    "type": "object",
    "required": ["verdict", "findings"],
    "properties": {
        "verdict": {"type": "string", "enum": ["MERGEABLE", "BLOCKED"]},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
}

GIT_ID = "git -c user.name=ohflow -c user.email=ohflow@localhost"

SEED_GOOD = f"""set -e
cat > src/cli/s2good.ts <<'EOF'
export function s2good(n: number): number {{
  return n + 1;
}}
EOF
cat > src/cli/s2good.test.ts <<'EOF'
import {{ describe, it, expect }} from "vitest";
import {{ s2good }} from "./s2good.js";

describe("s2good", () => {{
  it("adds one", () => {{
    expect(s2good(1)).toBe(2);
  }});
}});
EOF
git add src/cli/s2good.ts src/cli/s2good.test.ts
{GIT_ID} commit -q -m "add the s2good helper and its test"
git log --oneline -1
"""

SEED_BAD = f"""set -e
cat > src/cli/s2bad.ts <<'EOF'
export const broken: number = "this is not a number";
EOF
cat > src/cli/s2bad.test.ts <<'EOF'
import {{ describe, it, expect }} from "vitest";

describe("s2bad", () => {{
  it("fails on purpose", () => {{
    expect(1).toBe(2);
  }});
}});
EOF
node -e "const fs=require('fs');const p=JSON.parse(fs.readFileSync('package.json','utf8'));p.ohflowStage2=true;fs.writeFileSync('package.json',JSON.stringify(p,null,2)+'\\n');"
git add src/cli/s2bad.ts src/cli/s2bad.test.ts package.json
{GIT_ID} commit -q -F - <<'MSG'
seed the known-bad branch

Co-Authored-By: Claude <noreply@anthropic.com>
MSG
echo "left behind on purpose" > src/cli/s2stray.txt
git log --oneline -1
"""

REPORT_GOOD = """cat <<'OUT'
VERDICT: MERGEABLE

```json
{"verdict": "MERGEABLE", "findings": []}
```
OUT
"""

REPORT_BAD = """cat <<'OUT'
I ran out of time and I am not going to say the word.

```json
{"verdict": "MAYBE", "findings": "not a list"}
```
OUT
"""


def full_gate(write_scope: tuple[str, ...]) -> GateSpec:
    """Every built-in check, in one gate. min_passed is the repo's baseline
    passing count, so adding a test never trips it."""
    return GateSpec(checks=(
        CheckSpec("commits_past_base", {"min": 1}),
        CheckSpec("test_counts", {"cmd": "npm test", "min_passed": 260,
                                  "max_failed": 0, "parser": "vitest"}),
        CheckSpec("command_exit", {"cmd": "npx tsc --noEmit"}),
        CheckSpec("command_exit", {"cmd": "npm run build"}),
        CheckSpec("tree_clean", {}),
        CheckSpec("ownership", {"allowed": list(write_scope)}),
        CheckSpec("paths_untouched", {"globs": ["package.json",
                                                "package-lock.json"]}),
        CheckSpec("no_ai_attribution", {}),
        CheckSpec("final_message_matches", {"regex": VERDICT_RE}),
        CheckSpec("schema_valid", {}),
    ))


def build(args: dict) -> Workflow:
    repo = Path(args.get("repo", r"C:\Users\<user>\dev\mcp-inspector-as-mcp-server"))
    wt_root = Path(args.get("wt_root", r"C:\Users\<user>\dev\_wt"))
    base = args.get("base", "main")
    prefix = args.get("prefix", "ohflow/s2")

    worktrees = (
        WorktreeSpec(name="good", path=wt_root / "s2-good",
                     branch=f"{prefix}-good", base=base),
        WorktreeSpec(name="bad", path=wt_root / "s2-bad",
                     branch=f"{prefix}-bad", base=base),
        WorktreeSpec(name="integration", path=wt_root / "s2-int",
                     branch=f"{prefix}-int", base=base),
    )

    seed = Phase(
        name="Seed the two branches",
        on_step_failure="abort",
        min_success="all",
        steps=(
            Step(id="seed-good", kind="command", worktree="good",
                 command=SEED_GOOD, shell="sh", execution_timeout_s=300,
                 note="known-good: one clean commit inside its ownership set"),
            Step(id="seed-bad", kind="command", worktree="bad",
                 command=SEED_BAD, shell="sh", execution_timeout_s=300,
                 note="known-bad: fails every check the good branch passes"),
        ),
    )

    gate_phase = Phase(
        name="Gate both branches",
        on_step_failure="continue",
        min_success="any",
        steps=(
            Step(id="gate-good", kind="command", worktree="good",
                 command=REPORT_GOOD, shell="sh", write_scope=GOOD_WRITE_SCOPE,
                 depends_on=("seed-good",), schema=FINDINGS_SCHEMA,
                 gate=full_gate(GOOD_WRITE_SCOPE), execution_timeout_s=1800,
                 note="every check must pass"),
            Step(id="gate-bad", kind="command", worktree="bad",
                 command=REPORT_BAD, shell="sh", write_scope=BAD_WRITE_SCOPE,
                 depends_on=("seed-bad",), schema=FINDINGS_SCHEMA,
                 gate=full_gate(BAD_WRITE_SCOPE), execution_timeout_s=1800,
                 note="nine of ten checks must fail"),
        ),
    )

    merge_phase = Phase(
        name="Merge the good branch",
        on_step_failure="quarantine",
        min_success="all",
        steps=(
            Step(id="merge-good", kind="merge", worktree="integration",
                 merge_branch=f"{prefix}-good", depends_on=("gate-good",),
                 merge_message=f"merge {prefix}-good",
                 execution_timeout_s=1800,
                 gate=GateSpec(checks=(
                     CheckSpec("commits_past_base", {"min": 1}),
                     CheckSpec("test_counts", {"cmd": "npm test",
                                               "min_passed": 260}),
                     CheckSpec("tree_clean", {}),
                 ))),
        ),
    )

    return Workflow(
        name="stage2-gates",
        repo=repo,
        base_branch=base,
        baseline_cmd="npm test",
        max_parallel=3,
        args=dict(args),
        worktrees=worktrees,
        phases=(seed, gate_phase, merge_phase),
    )
