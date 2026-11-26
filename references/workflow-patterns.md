# Choose a workflow pattern

A workflow contains ordered phases containing steps. These six workflow patterns describe how the work is divided. `construct` builds a milestone from one of them by name; a hand-written workflow follows them as guidance.

| Pattern | Choose it when | Construction example |
|---|---|---|
| Single agent | One assignment can be checked on its own | [`_single`](../scripts/ohflow/workflows/rollcall.py) |
| Relay | Each assignment needs findings from the preceding one | [`_relay`](../scripts/ohflow/workflows/rollcall.py) |
| Fan-out | Contributions can proceed independently with separate write scopes | [`_fanout`](../scripts/ohflow/workflows/rollcall.py) |
| Fan-out with consolidation | Contributions need merging and an integration assessment | [`_merge`](../scripts/ohflow/workflows/rollcall.py) |
| Fan-out under contracts | Parallel pieces share interfaces, and one review must judge the merge | [`contract_fanout`](../scripts/ohflow/workflows/contract_fanout.py) |
| Implement and review | A change needs independent judgment before landing | [implement-review](implement-review.md) |

## Single agent
An agent fixes a CSV importer that drops the final row when the file has no trailing newline. A gate runs regression tests and checks that the agent edited only the importer and its tests.

## Relay
One agent investigates authentication and writes an evidence-backed implementation brief. A second uses that brief to add session expiry, and a third documents the finished behaviour.

Use separate steps in separate phases, with `depends_on` and `consumes` for the relevant predecessor. Context continuity comes through [handovers](step-handover.md); working files reach the consumer through a shared worktree, a merge, or explicitly readable artifacts.

## Fan-out
After shared interfaces are established, three agents independently implement PostgreSQL, SQLite, and MySQL adapters. Each owns separate files, and each adapter must pass the same contract tests.

## Fan-out with consolidation
Separate agents add tracing to the API, background worker, and database layer in their own worktrees. Their branches are merged, then a consolidator checks that trace context flows consistently across all three parts.

The consolidator consumes the contributing agents’ handovers and depends on the merges that make their code available. Receiving a handover does not merge a branch.

## Fan-out under contracts
A parser and a printer are built at once, and the printer calls the parser. `contracts.md` fixes `parse(text) -> Tree`, so both build against the same shape. Each piece is a step named after it, on its own branch and write scope; merge steps bring the branches together, and one reviewer reads every branch against the spec and the contracts, runs the merged suite and sorts its findings blocking, should-fix and note. A blocking finding fails the review, and the orchestrator agent starts the implement-review fix cycle on the fan-out output branch. The briefs and the fix route are in [brief templates](brief-templates.md#contract_fanout-briefs). The template runs its agents on this machine only (`pi`, `claude` or `codex`), because the briefs name the spec, the contracts and the heartbeat log by their local paths.

### Across repositories
An API change and its client change live in two repositories. Each repository is a [workspace](ohflow.md#workspaces), and each piece is one step in its own workspace, so each step keeps one branch, one diff and one `ownership` check. `contracts.md` fixes the interface between the repositories. No merge step joins them, because a branch stays in its workspace: a `command` step whose command names both worktree paths runs the tests across them. Notes, a report or other work that is not code goes to an owned workspace, which ohflow creates.

## Implement and review
An implementer adds password-reset support, including token expiry and single-use enforcement. A fresh reviewer checks the code and security tests, and blocking findings become a bounded fix cycle.

## Campaign: coordinate milestone workflows
A team migrates a service from a legacy queue to a new job system through compatibility, worker migration, and cutover milestones. Each milestone runs its own workflow and acceptance checks, then a fresh judge assesses whether to accept it, revise its inputs, or request intervention.

A [campaign](campaign.md) coordinates workflows; its milestone workflows can use any pattern above.

## Specialized compositions
- **Evidence atlas:** scouts → independent syntheses → challenges → cartographer, with claim provenance and contradictions preserved. Read [context-gathering](context-gathering.md); specialize the [template](../scripts/ohflow/workflows/evidence_atlas_template.py).
- **Review by dimension:** independent reviewers inspect different properties of the same revision, then a deterministic consolidator combines their findings. Read [review-by-dimension](review-by-dimension.md).

Retry and auto-resume are recovery behaviour. Gates check outputs; handovers preserve findings across agents. Choose these policies for each pattern as needed; schema validation proves shape, and each other check proves only its tested condition.
