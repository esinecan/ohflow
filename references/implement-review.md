# Implement, then review: the two-agent workflow

Workflow: [`workflows/implement_review.py`](../scripts/ohflow/workflows/implement_review.py). Briefs:
[brief-templates](brief-templates.md).

One `ohflow run` runs two agents back to back. Nobody looks between phases;
the gates check each phase's exit condition mechanically. **The agent's final
message is a claim; the artifact is the evidence.**

`ohflow run --workflow ohflow/workflows/implement_review.py` builds the workflow from its
`--args`, and the [ohflow](ohflow.md) engine runs the phases, applies the gates and keeps the
run log. The `run` flags apply as for any workflow: `--dry-run`, `--hold`, `--detach`,
`--predictions`, `--history`, `--no-dashboard`, `--dashboard-port` and `--open-dashboard`.

## Phases and gates

| Phase | Tool policy | Gate |
|---|---|---|
| implement | `terminal`, `file_editor`, `task_tracker`; the skills `impl_skills` names; 150 iterations | ≥1 commit past base; `test_cmd` exits 0; `git status --porcelain` empty; the reviewer handover is complete |
| review | `terminal` only, on `pi`, a hermetic `claude` or `durable`; no skills; 80 iterations | a `VERDICT: MERGEABLE` or `VERDICT: BLOCKED` in the final message; tree still clean; tests still green |

Phase 2 runs only when phase 1 passed. The gate on the reviewer's clean tree is
what proves it obeyed the no-edit instruction; the tool policy alone cannot,
because `terminal` can write files.

## Arguments

Pass each argument as `--args name=value`.

| Argument | Default | Meaning |
|---|---|---|
| `repo`, `branch`, `worktree` | required | the repo, the feature branch to create, the worktree directory |
| `base` | `main` | branch the worktree starts from |
| `impl_brief`, `review_brief` | required | brief files |
| `dimensions`, `brief_dir` | off | for `all` or `review`, replace the single reviewer with parallel named reviewers; the directory contains one `<dimension>.md` |
| `harness_executors` | `harness_executor` | optional `dimension=pi` overrides, comma-separated; a dimension reviewer runs on `pi` only |
| `schema_retry` | 1 | automatic retries of a dimension reviewer's `schema_valid` check |
| `install_cmd` | `npm ci --no-audit --no-fund` | run once in the fresh worktree |
| `test_cmd` | `npm test` | the test gate; exit 0 is pass. It runs the tests the change reaches, never the full suite: `{base}` in it is the step's base commit, as in `python3 tests/run_tests.py --changed {base}` ([ohflow](ohflow.md#gate-checks)) |
| `impl_iter`, `review_iter` | 150, 80 | `max_iterations` per phase |
| `mode=all` | | create worktree, implement, gate, review, gate |
| `mode=review` | | reuse the worktree, gate it, review only |
| `mode=fix` with `fix_brief=F` | | implementer again with brief F in the worktree, gate, review, gate |
| `impl_skills` | none | the skills the implementer loads, comma-separated, such as `impl_skills=codebase-design` |
| `skills_dir` | none | the directory that holds the skills `impl_skills` names; a pi agent fails validation when one is missing there |
| `harness_executor` | required | `pi` or `durable`: the implementer's harness executor, and the reviewer's unless `review_harness_executor` names another |
| `model` | the `light` tier on pi and durable | both agents' tier, `heavy` or `light`, or a model id; `review_model` overrides the reviewer's |
| `review_harness_executor` | `harness_executor` | `pi`, `claude` or `durable`: the reviewer's harness executor |
| `review_model` | `model` on the same harness executor, else that harness executor's default | the reviewer's tier or model; a `claude` reviewer needs it |
| `box` | the `durable.box` setting | where a durable agent runs, its `AgentSpec.box`: `local` for this machine, else the ssh host alias of an ssh box; ignored for other harness executors |
| `base_url` | `https://api.z.ai/api/coding/paas/v4` | the provider endpoint; refused when an agent runs on `durable`, whose host holds its keys on its own box |
| `api_key_env` | `ZAI_CODING_CN_API_KEY` | the name of the variable that holds the key; the key never enters a spec; refused when an agent runs on `durable` |
| `thinking` | `high` | pi thinking level: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| `fork_session` | none | a prior pi session file that the implementer forks; use it with `mode=fix` |
| `execution_timeout_s` | 5400 | the execution timeout of each agent step |

A `claude` agent gets a `ModelConfig` with the model alone: no `base_url`, no `api_key_env` and no params.

The loop is `all` → read verdict → `fix` → read verdict → merge by hand.

The reviewer runs with the terminal alone, so it runs only where a harness executor can narrow to
that. `pi` can. `claude` can when hermetic, and the workflow makes a `claude` reviewer
hermetic. `durable` can, with the box named by `box` and the model keys it
needs already on that machine. `codex` refuses `tools.only` even when hermetic, so the workflow refuses
it as the reviewer. `review_harness_executor` and `review_model` set the single reviewer; dimensional reviewers take `harness_executors`.

When `dimensions` is present, each reviewer runs read-only with the
same structured schema and one automatic retry for `schema_valid`. The engine
keeps each structured response in that reviewer's attempt artifacts. A Python
command step reads the latest attempts in the requested dimension order and
writes `review.md` plus `verdict.json` beside its own engine artifacts. The
consolidated verdict is `BLOCKED` if any dimension blocks and `PASS` otherwise.

**Read the verdict, not the gate.** A gate asks for *a* verdict line, so BLOCKED passes it.
The review step's final message says which verdict it was.

`mode=review` runs no implementer and still applies the three implement gates to the
tree that is already there. `mode=fix` refuses at once when `fix_brief` is absent,
before anything is created.

## What the run writes

The run directory sits under the `--out` runs root. It holds `summary.json`, the exit report and
one attempt directory per agent attempt. Each attempt directory holds the agent's `final.md` and
its transcript. Transcripts follow [transcripts](transcripts.md).

## Measured runs

`ohflow table` generates the numbers. Run it on any directory of finished runs:

    cd ohflow/scripts && PYTHONPATH=. python3 -m ohflow.cli table --runs <runs root> --by phase

`transcripts.md` explains the columns and the cost source.

## The procedure

1. **Clean the repo.** One branch, clean tree, CI green on the base commit. Done when `git status --porcelain` is empty on the base branch and the last CI run on the base commit passed.
2. **Write the two briefs** from [brief-templates](brief-templates.md): `impl.brief.md` and `review.brief.md`. The implementation brief numbers the change's rules and makes each pair of rules that can meet in one run an acceptance case. The review brief repeats the rules, and its Step 3 makes the reviewer combine two of them in a scenario of its own. Done when no template slot is left.
3. **Set the tool policies.** The workflow sets them in `ohflow/workflows/implement_review.py`. The implementer is lenient and the reviewer is strict ([implement-review](implement-review.md#phases-and-gates)). Change a tool policy in the workflow, never in the brief. Done when the workflow names the tools you intend.
4. **Fire.**

   ```bash
   cd <ohflow clone>/scripts && PYTHONPATH=. python3 -m ohflow.cli run \
     --workflow ohflow/workflows/implement_review.py \
     --args repo=<repo> --args branch=feat/<x> --args worktree=<repo>-<x> \
     --args harness_executor=pi --args skills_dir=$HOME/.agents/skills \
     --args impl_brief=impl.brief.md --args review_brief=review.brief.md \
     --out <runs root> --detach
   ```

   Both agents run on one model by default, so the two transcripts
   compare tool use under two tool policies. `review_model` and `review_harness_executor` put
   the reviewer on another model when a second model's view is wanted. On one harness executor that is
   `--args model=heavy --args review_model=light`.

   Follow [Operate a run](operate-a-run.md). When the operator must see the plan before it starts, add `--hold`.
   Done when the run's `summary.json` exists.
5. **Read the final output only.** Read `summary.json` and the review step's `final.md`. Do not read the implementer's work before the reviewer has. Done when you have the verdict and both gate results.
6. **Loop on BLOCKED.** Test each blocking finding against its check. A finding from a check that did not hold the field constant is a brief fault, so fix `review.brief.md`. Otherwise write `fix.brief.md` and fire again with `--args mode=fix --args fix_brief=fix.brief.md`. Make at most two fix cycles, then hand the last review to the operator. Done when the verdict is MERGEABLE or the cap is reached.
7. **Merge and close.** Read the final diff once. Fast-forward the base branch. Run `revert --run <run dir>`: it removes the junction, the worktree and the branch. Restart any daemon that serves the changed code. Done when the base branch holds the commits and the worktree is gone.
8. **Leave the capability behind.** Copy the briefs, `summary.json` and the review final messages into `references/examples/<feature>/` under the skill root. Fix anything the run proved wrong in this skill. Done when the example directory exists.


The reviewer receives the implementer’s [step handover](step-handover.md) in `all` and `fix` modes. Its answers are claims to verify against the revision and checks. Review-only mode starts from the existing worktree.
