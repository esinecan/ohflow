---
name: ohflow
description: Deliver a feature, or a whole design document milestone by milestone, through gated agent steps and fresh judge agents that revise and resume, and audit what a run did. Use for ohflow, a campaign over a design's milestones, phased multi-agent implementation, or agents on the pi or signed-in harnesses.
---

# ohflow

**IF A PART OF THIS TEXT APPLIES TO YOUR PROCEDURE, READ THE REFERENCE IT POINTS TO BEFORE YOU ACT. OTHERWISE THE REFERENCE IS OPTIONAL.**

Write briefs, set tool policies, fire the command and read the result. **Tool policy is the gate**: an agent calls only the tools it was built with. **The agent's final message is a claim; the artifact is the evidence.** Terms: grep [CONTEXT](CONTEXT.md) after its core table.

## The attitude

Own the result. Check artifacts, tools and documentation; explain failed runs. Wire for the transcript first. Read [orchestrator guidance](references/orchestrator.md) before constructing or revising a run.

**Pilot first, whatever the pattern.** Send one small representative subset through every phase first, and change the workflow on what it shows; `run --pilot` does this for a workflow that declares units.

**You stay in charge during the run.** Give each step one change, a stop rule and a gate that tests only that change ([ohflow](references/ohflow.md#gate-checks)), judge its result before the next step starts, and in a delivery kill a step the moment it stops producing value. A workflow that can run unattended does not make you unattended: packing the remaining work into a few multi-task steps and waiting for the run to end is the failure.

**The objective kind limits intervention.** A delivery, search and research included, is open to revision; an empirical procedure, such as an A/B test, stops only for a deviation, and changing its procedure restarts every arm. The bill names the kind and why; rules: [campaign](references/campaign.md#intervention-by-kind-of-objective).

## Route by the work

| Work | Route | Read |
|---|---|---|
| One bounded assignment | Single agent | [ohflow](references/ohflow.md) |
| A chain of dependent assignments | Relay | [patterns](references/workflow-patterns.md), [handovers](references/step-handover.md), [ohflow](references/ohflow.md) |
| Independent contributions | Fan-out | [patterns](references/workflow-patterns.md), [ohflow](references/ohflow.md) |
| Contributions that must join | Fan-out with consolidation | [patterns](references/workflow-patterns.md), [handovers](references/step-handover.md), [ohflow](references/ohflow.md) |
| A feature needing independent review | Implement and review | [implement-review](references/implement-review.md) |
| Specs or a design delivered through milestones | Campaign, built by `construct` | [construct](references/construct.md), [campaign](references/campaign.md) |
| An evidence map of an unfamiliar system | Evidence atlas | [context-gathering](references/context-gathering.md), [ohflow](references/ohflow.md) |
| Review across independent dimensions | Review by dimension | [review-by-dimension](references/review-by-dimension.md) |
| One agent without orchestration | Dispatch | [harness executors](references/harness-executors.md) |
| Understand what a run did | Audit | [transcripts](references/transcripts.md) |
| Agents steered turn by turn | Sessions | [sessions](references/sessions.md) |
| Prove a harness works | Roll call | [CONTRIBUTING](CONTRIBUTING.md#testing-with-live-agents) |

Start from the agreed brief or specification. Declare `consumes` when an agent needs another step's findings, `depends_on` for ordering.

House rules: `references/local.md`, when present.

For every run, follow [operate-a-run](references/operate-a-run.md), and read [monitor-a-run](references/monitor-a-run.md) when you hand the user the dashboard. Done when the user has the verdict and exit report, and `notes check` reads `NOTES COMPLETE`.

## Harness executors

| Harness executor | Use for |
|---|---|
| `pi` | new workflows. Hermetic pi CLI child with only what the workflow names |
| `claude`, `codex` | a step that needs that signed-in harness's model, memory or fleet |
| `durable`, `pi-cloud`, `claude-cloud`, `codex-cloud` | a step that must survive this machine |

ohflow has no default harness executor. Facts, tool policies and launch rules: [harness executors](references/harness-executors.md). An agent needing an MCP server: `mcp_config`, in [ohflow](references/ohflow.md#narrow-an-mcp-tool-policy).

## Verbs

Run each from `scripts/` as `PYTHONPATH=. python3 -m ohflow.cli <verb>`. Verdict lines, `--json` and exit codes: [ohflow](references/ohflow.md#run-it).

| Verb | What it does |
|---|---|
| `preflight` | checks Git Bash, the workflow and each harness executor; run it first |
| `construct` | writes a campaign from milestone specs |
| `validate` | checks a workflow without a run |
| `estimate` / `campaign estimate` | forecasts minutes, tokens and cost from history |
| `run` | fires a workflow; `--dry-run` rehearses, `--detach` backgrounds, `--hold` waits for `go`, `--pilot` prices each unit path, then holds |
| `go` / `kill` | releases a held run; stops one step |
| `status` / `watch` | reads a run now, or waits for news |
| `campaign watch` / `history` | `watch` for a campaign; its rounds |
| `notes log` / `check` | appends to or audits run notes |
| `table` | totals the runs' cost and tokens |
| `transcript` / `explain` / `actions` | one step's attempt: its transcript, triage or model calls |
| `compare` | diffs two runs |
| `position` | prints a step's position block |
| `revert` | removes a run's worktrees |
| `dashboard` / `report` | serves a finished run; rebuilds a dead supervisor's exit report |
| `cloud-spend` | reads Cloudflare's container bill |
| `rollcall` | runs the live-agent matrix |

## Agents commit under your name

With `commit_checks.no_ai_attribution` on, the house check `no_ai_attribution` fails a commit naming an AI author or co-author, and each committing brief says so.

## Improve this skill

Update verified operating guidance in its reference; keep run evidence in notes, and open bugs where `references/local.md` says, else in GitHub issues. Mark assumptions; verify fixes before closing them.
