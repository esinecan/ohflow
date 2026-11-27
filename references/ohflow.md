# ohflow: many agents, phases, gates, consolidation

The built-in implement-review workflow runs two agents back to back. A workflow of your own runs many, across phases, with barriers and merge steps between them. Reach for it when one diff needs several agents at once, or when the work has phases that must finish in order.

Driver: `python3 -m ohflow.cli`, from `scripts/`, with `PYTHONPATH=.`. The orchestrator is plain Python, so a workflow validates under the system Python. Terms: [CONTEXT](../CONTEXT.md).

**Own files, not features.** This is the decomposition rule, and it decides whether parallelism pays. Splitting by feature fails: on a small codebase every feature edits the same few files, so N agents produce N conflicting diffs in the same hunks. Split by file ownership. One serial scaffold step writes every shared file (the arg table, the help text, the config block, the empty modules with typed signatures) and commits once. Then each parallel agent fills in modules nobody else touches. The `ownership` gate enforces this from `git diff --name-only`, so an agent that strays fails its own gate rather than poisoning the merge.

## Write the workflow

A workflow module is a Python module that exports `build(args: dict) -> Workflow`, which returns the workflow definition. Copy the layout from [`workflows/rollcall.py`](../scripts/ohflow/workflows/rollcall.py) or [`workflows/implement_review.py`](../scripts/ohflow/workflows/implement_review.py). The demonstration workflows (demo, overlap, gates, one agent, fan-out) live in `tests/fixtures/workflows/`.

- `Workflow`: `name`, `workspaces` or the one-repository form `repo`, `base_branch` and `baseline_cmd`, then `max_parallel`, `transient_backoff_s`, `auto_resume`, `token_budget`, `token_reserve`, `worktrees`, `phases`, `paths`, `units`, `contracts`. The two token fields are in [Token budget](#token-budget).
- `Workspace`: `name`, `path`, `base_branch`, `remote`, `baseline_cmd`, `owned`. [Workspaces](#workspaces) describes it.
- `WorktreeSpec`: `name`, `path`, `branch`, `base`, `workspace`, the `node_modules` fields, `reuse_existing`, `base_sha_mode`.
- `Phase`: `steps`, `min_success` (`"all"`, `"any"` or an integer), `on_step_failure` (`abort`, `continue` or `quarantine`), `max_parallel`.
- `Step`: `id`, `kind` (`agent`, `command`, `gate`, `merge`), `worktree`, `write_scope`, `depends_on`, `consumes`, `handover`, `gate`, `retry`, `schema`, `objective`, `unit`, and for agents a `AgentSpec`.

`depends_on` names step ids in earlier phases only. A workflow cannot order steps inside one phase. The engine runs `merge` steps first and serially, then the rest under the phase's limit, in the start order [Concurrency](#concurrency) describes. `validate` refuses a workflow where two steps in one phase own the same path of one workspace, and names both.

### Workspaces

A workspace is one git repository that a workflow works on. A workflow that works on one repository sets `repo`, `base_branch` and `baseline_cmd`: that is one workspace, named after the repository's folder. A workflow that works on several declares them and leaves `repo` unset:

```python
Workflow(
    name="api-and-docs",
    workspaces=(
        Workspace("api", Path(args["api"]), baseline_cmd="npm test"),
        Workspace("docs", Path(args["docs"]), base_branch="trunk"),
        Workspace("notes", root / "notes", owned=True),
    ),
    worktrees=(
        WorktreeSpec(name="api", path=root / "wt" / "api", branch="feat/api",
                     base="main", workspace="api"),
        WorktreeSpec(name="docs", path=root / "wt" / "docs", branch="feat/docs",
                     base="trunk", node_modules_mode="none", workspace="docs"),
        WorktreeSpec(name="notes", path=root / "wt" / "notes", branch="feat/notes",
                     base="main", node_modules_mode="none", workspace="notes"),
    ),
    phases=...,
)
```

- **Each worktree names its workspace.** `WorktreeSpec.workspace` is a `Workspace.name`. A workflow with several workspaces names one on every worktree. The first workspace is the default workspace: a step with no worktree runs there, and `Workflow.repo` and `Workflow.base_branch` read as its path and base branch.
- **An agent step writes in one workspace, and on the local box it may read the others.** The step's worktree fixes its workspace, so one attempt gives one branch, one diff, one `ownership` check and one transport branch. In a workflow with several workspaces the position block lists the other workspaces with their paths and worktrees, and tells the agent to write nothing there. A step on an ssh box or a cloud box holds its own workspace alone, and its position block says so.
- **Steps `consume` across workspaces.** A handover is a file in the run directory, so the consumer reads it whatever workspace the producer wrote in. The position block adds the producer's workspace, worktree and branch under each handover.
- **A branch stays in its workspace.** `validate` refuses a `merge` step whose `merge_branch` belongs to a worktree of another workspace. A change that crosses repositories is one step for each repository, under fixed [contracts](workflow-patterns.md#fan-out-under-contracts), and a `command` step whose command names each worktree path runs the tests across them.
- **Work that is not code runs in an owned workspace.** `owned=True` names a folder that ohflow creates. When a run starts and the folder holds no repository, the engine runs `git init` there, names the base branch and makes one empty root commit, so the worktrees, branches, diffs, handovers and `revert` work as they do for code. The engine refuses a folder that holds files and no repository. A worktree of an owned workspace sets `node_modules_mode="none"`.
- **`remote` is the URL of the workspace's `origin`.** A step on an ssh box or a cloud box pushes and fetches its transport branch through that `origin`. For an owned workspace the engine sets `origin` to `remote` when it creates the repository. For any other workspace preflight fails when `origin` differs from a `remote` the workflow names. `validate` refuses a step on an ssh box or a cloud box that writes in an owned workspace with no `remote`. ohflow creates no remote repository.
- **A campaign lands in every workspace.** A [campaign](campaign.md#land-in-several-workspaces) declares the same `Workspace` records, keeps one integration branch in each, and on PASS moves the integration branch of each workspace where the milestone's workflow has a worktree on the output branch, all of them or none.
- **Preflight checks every workspace, and `revert` covers every workspace.** Each workspace is a git repository, is on its `base_branch` and has a clean tree. After preflight passes, the engine runs each `baseline_cmd` in its own workspace, and each must exit 0. `ohflow preflight` runs none. `revert` removes each worktree and its branch from the workspace that holds it, and it keeps an owned workspace's repository. `run.json` and `revert.json` list the workspaces.

Done when `validate` ends its `VALID` line with `; N workspaces`, `validate -v` lists them, and `preflight --workflow <module> --args ...` prints `PREFLIGHT PASS`.

`Step.objective` is one optional line of at most 120 characters. The dashboard shows it as the step's assigned objective. It is display data: no fingerprint and no position block reads it. `validate` warns when an agent step has none.

`ModelConfig.api_key_env` is a variable name. The key never appears in a workflow.

Done when `ohflow validate` prints `VALID <workflow>: ...` with the phases, steps and harness executors you meant, and exits 0.

### Units and unit paths

A workflow that runs over many items declares them, so `run --pilot` can price each kind before the full run ([Pilot](#pilot-a-run-over-many-units)). Each item is a unit, and each kind of item is a unit path. A finding that needs only a fix and a finding that needs a live probe first are two unit paths.

- `Workflow.paths` holds one `UnitPath(name, description)` per unit path. The name is what the CLI and the dashboard print as `path`.
- `Workflow.units` holds one `Unit(id, path, size)` per unit. `path` names a declared unit path. `size` is a positive number, 1 by default, and the pilot runs the unit with the smallest size on each unit path. A tie goes to the unit declared first.
- `Step.unit` names the unit whose work the step does. A unit's work may span several steps and several phases. A step with no unit is a shared step: it runs once per run, whatever the unit count.

`validate` refuses a unit on an undeclared unit path, a step that names an undeclared unit, a unit that no step names, a duplicate unit id or unit path name, and a size that is not a positive number. `validate` adds `; N units on K paths` to its `VALID` line, and `validate -v` prints `path <name>: N units, pilot unit <id>` for each unit path. `Step.unit` is outside the step fingerprint, so adding units to a workflow keeps every cached step cached.

### Concurrency

`Workflow.max_parallel` is the limit for a phase that declares none. `Phase.max_parallel` is that phase's own limit. `--max-parallel` sets the default and caps every phase, so the command line throttles a run without a workflow edit. `validate -v` prints the limit each phase will get as `max_parallel=N` on its `phase` line, and `board.md` prints the limit it ran at.

In each phase the merge steps run first, one at a time in workflow order, on the engine's own thread. Every other step runs in a step thread of its own, which carries its attempts, its gate and its retry decision.

**Longest step first.** Inside one phase the engine grants the slots in the order of each step's `p50` wall time in the run's `estimate.json`, longest first. It pays when a phase holds more steps than its limit: the longest step then never waits behind shorter ones, so the phase ends sooner. A step with no `p50` there (a `command` step, or an agent step the history has no timed attempt for) keeps its place in the workflow order, and the steps with one share out the places left. Two steps with the same `p50` keep their workflow order. A run with no estimate (neither `--history` nor `OHFLOW_HISTORY` names a history) starts its steps in workflow order. The order follows the history and not the workflow, so no workflow may depend on which step starts first.

**Keep a Z.AI reserve.** For steps on the Z.AI provider, set `Workflow.max_parallel` and every phase override to at most five. That leaves about four request slots for other work on the shared account. Raise the limit only for a measured, isolated run. Token capacity does not lift the burst-request ceiling: a nine-agent fan-out on the Z.AI model of the `light` tier hit `RateLimitError` and aborted, and the same workflow ran at three. Done when no `phase` line of `validate -v` shows `max_parallel` above five while a step under it has a `model=` value that starts with `zai/`, or the workflow records the measurement that justified the override.

## Retry

Automatic retry is active through `RetryPolicy(max=..., on=(...))`. Example: `RetryPolicy(max=1, on=("timeout", "gate:test_counts"))`. A retry is a fresh agent in the same worktree. It gets the same brief plus a "What failed last time" section, and the run log records it as a new attempt under the same coordinate. Every execution has its own attempt directory. Use a fix phase when the next pass needs a different brief or role.

Three token forms exist, and no others:

| Token | Fires when |
|---|---|
| `timeout` | the engine's execution timeout killed the agent |
| `agent_error` | an agent step recorded an error of its own and its status is not `timeout` |
| `gate:<check>` | that named check failed |

A **stall** is an `agent_error`. When `stall_timeout_s` expires while no tool call is open, the harness executor kills the agent and the attempt records `stall` as its error. The attempt's tokens then include `agent_error`. While a tool call is open the stall clock waits, and the command time cap applies instead: a call open past it plus a 60 s grace records `command_time_cap: <tool> call open longer than N s`, also an `agent_error` ([harness executors](harness-executors.md#liveness-and-tool-output)).

A failed check reaches the next attempt by two separate paths. Its token `gate:<check>` goes only to `retry.should_retry`, which decides whether a retry runs. The next attempt's `position.md` shows the failure under "What failed last time", one line per failed check: `<check>: observed X, expected Y`.

**Every failure must be covered.** A retry runs only when every token that describes the execution's failures is in `retry.on`. An agent that errors usually fails its `final_message_matches` check too. Its tokens are `agent_error` and `gate:final_message_matches`, and a workflow that wants the retry lists both. An execution timeout names `timeout` alone, because the engine writes that error text itself.

Five refusals stand whatever a workflow lists:

- `gate:ownership` and `gate:no_ai_attribution` failures (`FORBIDDEN_RETRY_ON`). The agent did the wrong thing, and the same brief repeats it.
- A structural provider refusal: a rejected key, a 400, an exceeded context window, an empty account.
- A `command`, `merge` or `gate` step. It is deterministic, and `validate` refuses a retry budget on one.
- An abort. It stops every pending retry.
- An attempt kill (`ohflow kill`). An upper rank stopped this work, and `run --resume` starts it again.

The run log records the decision either way. Read it in `summary.json` under the step's `retry_decision`.

### A deferred phase can resume itself

`Workflow.auto_resume` and `--auto-resume N` set how many times a phase that settled `deferred` re-runs its deferred steps after the cooldown. The default is 0: the run pauses and a person runs `--resume`. An auto-resume pass re-runs exactly the coordinates recorded `deferred`, except a step that `ohflow kill` ended. A step that passed beside them stays cached.

### Transient and structural failures

`on_step_failure` acts on a **structural** failure. `quarantine`, the default, records the step `quarantined`, `continue` keeps it `failed`, and `abort` stops the run. `min_success` counts passed and cached steps. A phase that misses it settles `deferred` when at least one step is deferred and none is `failed` or `timeout`, even beside quarantined or skipped steps. Otherwise it settles `failed`. A structural failure is a failed gate, a schema violation, an auth rejection, a non-zero exit from a deterministic command. A **transient** failure records the step `deferred`. Examples: a rate limit, a provider overload, a 5xx, a dropped or timed-out connection. `ohflow.failure.classify` draws the line, and it defaults to structural for text it does not recognise.

An agent's execution timeout is read from its text like any other agent failure. When the engine kills an agent, `CliHarnessExecutor.collect` recovers a result from the runner's event log. A `command`, `merge` or `gate` timeout is structural without reading text.

What follows from `deferred`:

- The phase does not abort, and steps that have not started keep their assignments.
- `transient_backoff_s` (default 60, doubling per hit, capped at ten times the base) holds the next start back.
- A provider usage limit that names its reset holds the cooldown until one minute after that reset. `engine._provider_reset_at` reads the z.ai `1308` message and the Codex "You've hit your usage limit ... try again at 3:23 AM" message. The Codex time is local, and a time already past means the next day.
- A phase that ends with deferred steps and no hard failures settles `deferred`. The run ends `paused`, and later phases do not start.
- `--resume` re-runs exactly the deferred steps.

A structural failure under `on_step_failure="abort"` stops the run. The phase settles `failed`, later phases do not start, and the run ends `failed`. The abort's victims reach no verdict, so they record `deferred` with a reason in `error`. A step the abort killed in flight reads "the run aborted while this step was still running". A step that never got a slot reads "the run aborted before this step started", and it is never launched. The engine does not gate a killed agent. `summary.json` lists `deferred` beside `quarantined`: the first is what `--resume` re-runs, the second is what was judged and rejected. `board.md` marks a deferred step `DEFERRED`.

## Token budget

`Workflow.token_budget` is the most tokens a run's agent steps may use, counted as `prompt_tokens + completion_tokens` with cached input included. `--token-budget N` on `run` overrides it. The run log records the budget and the grant in a `token_budget` event of kind `limit`, and a resume keeps the recorded budget unless `--token-budget` is given again. A raised flag is how a run paused by the budget continues. A resume starts the ledger from the tokens the run directory's attempt records hold. A run without a budget has no ledger.

`budget.Ledger` holds the run's token ledger. Before an agent attempt opens, it reserves a grant: `Workflow.token_reserve` tokens, or `token_budget // max_parallel` when the workflow names none. An attempt is admitted only while the settled tokens, every grant in flight and the new grant fit inside the limit. When they do not fit and other attempts hold grants, the attempt waits for one to settle. When nothing is in flight and the free allowance is smaller than one grant, the attempt is not admitted: it records `deferred` with the reason, no execution is counted, the run log gets a `token_budget` event of kind `refused`, and the run ends `paused`. `command`, `merge` and `gate` steps need no grant.

While the attempt runs, the engine reads its live usage from the harness executor's event log at every poll (2 s). An attempt whose usage reaches its grant is extended from the allowance no grant holds. With nothing free, the engine kills it: the attempt fails structurally with `token budget: stopped at ...`. When it ends, the attempt settles its recorded usage from `result.json`, else its live usage, else the larger of its grant and its last live reading, listed under `unknown_usage`. A `durable` or cloud attempt that reattaches after a lost host settles each part from the same event log, so the ledger counts the part before the loss twice and the run stops early rather than late.

The bound: settled tokens never exceed `token_budget` plus the recorded overshoot. An attempt overshoots when its settled usage exceeds its grant plus the allowance free at that moment, and each overshoot is an error in three places: a `token_budget` event of kind `overshoot` in the run log, the exit report's verdict, `What needs a person` and `## Token budget` section, and the dashboard's `run.token_budget` field with a `token_overshoot` attention item. How far one attempt can overshoot depends on when its harness reports usage:

| Harness executor | Live usage arrives | Most one attempt can overshoot |
|---|---|---|
| `pi` | after each model call, in the event log and to the guard | the model call in flight when the grant was reached. `ohflow-guard.ts` starts no further call once the attempt's own usage reaches its grant, waits up to 30 s for an extension, then stops pi and writes `budget-stop.json` |
| `claude`, `durable`, `pi-cloud` | after each assistant message | the message that crossed the grant, plus what arrives before the next poll |
| `codex`, `codex-cloud`, `claude-cloud` | only at the end of the attempt: `codex` when its turn completes, `codex-cloud` and `claude-cloud` when the Worker's session settles | everything the attempt used past its grant and the free allowance |

`budget.json` at the run root is the token ledger's snapshot: `limit_tokens`, `reserve_tokens`, `settled_tokens`, `observed_tokens` (settled plus the live usage of the attempts in flight), `reserved_tokens`, `free_tokens`, `in_flight`, `stopped`, `refused`, `unknown_usage`, `overshoot_tokens` and `overshoots`. The billing estimate is a separate field, `billing_estimate_usd`, summed from the priced `cost` of the settled attempts beside `billing_priced_attempts` and `billing_unpriced_attempts`. The budget never reads it.

## The run log is the truth

Every bound counts from the run log, keyed by the identity `(coordinate, fingerprint)`. Editing a brief changes the fingerprint, so the new revision gets its own budget. The old attempt directories stay on disk.

Fingerprint version 7 hashes explicit handover contracts, readers and consumed content digests, alongside `Step.merge_message`, `AgentSpec.skills_dir` and the other selected inputs. A test classifies every workflow field as hashed or excluded. The key includes a worktree's uncommitted, non-ignored state: `git diff HEAD --binary` plus every path and byte of `git ls-files --others --exclude-standard`. Ignored build output is outside the key. The committed `HEAD` is outside it too, so an agent's own commit returns to the same clean identity and a clean resume stays cached. `AgentSpec.command_time_cap_s` is part of the step fingerprint.

| Bound | What it counts |
|---|---|
| `retry.max` | retries of this work |
| `auto_resume` | auto-resume passes of this work |
| total executions | `1 + retry.max + auto_resume + 1`, the last being one manual recovery |
| exclusion | two failed executions of unchanged work |

**Two failures exclude the work.** A judged failure and a transient deferral count the same, so one of each is two. An excluded step does not start again in that run directory, by an auto-resume pass or by `--resume`, and the refusal says so on the record.

An abort victim is not a failure. Its name comes from the run abort, its first case. A workflow resume, an attempt kill and a reattach close executions the same way. It never advances the count toward exclusion. It does spend a start when the abort killed it in flight. One recorded before it launched spends nothing, not even an attempt number.

A step whose harness executor declares `reattach` (`durable`, `pi-cloud`, `claude-cloud` or `codex-cloud`) has a fourth start kind, `reattach`. When the supervisor dies over an open attempt, or the remote side ends without a verdict (`host_lost`), the engine closes the execution `deferred` as an abort victim and reattaches: the same attempt number, the same attempt directory, `start_kind: "reattach"` in the run log, and the same work continues: a `durable` host replays its session. The closed execution carries `reattached` and the error `reattach: <reason>`. The engine gives the reattached execution a fresh execution-timeout deadline. A reattach has no per-kind budget: it spends a start from the total-execution bound, exactly as an abort victim killed in flight does, and it does not advance the exclusion. A stall, the command time cap or a judged failure is an ordinary failure and the retry rules own it.

The cooldown is durable. A verdict that defers a step carries the absolute wake time and the hit count, so a run resumed in a new process does not ask the provider the question it was just rate-limited for.

## Command time caps

Every agent has an effective command time cap: the longest one command it invokes may run. With `AgentSpec.command_time_cap_s=None`, `default_command_time_cap` gives:

- Execution timeout at or below 120 s: reserve 10% of it, at least 1 s.
- Execution timeout from 121 s through 228 s: a cap of 108 s, so the cap cannot fall at the boundary.
- Execution timeout above 228 s: `execution_timeout_s - max(120, ceil(10% of execution_timeout_s))`.

Execution timeouts of 120, 121, 228, 900 and 5400 s give caps of 108, 108, 108, 780 and 4860 s. An explicit `command_time_cap_s` may only tighten the cap. `validate` rejects a non-positive value and a value above the default cap.

The pi `bash` guard clamps each requested timeout to the cap. Each clamp appends `{requested, applied, coord, attempt}` to the attempt's `logs/command_time_caps.jsonl`. `result.json.settings.requested.command_time_cap_s` and `.effective.command_time_cap_s` record the workflow value and the applied cap. The runner exports the cap as `OHFLOW_BASH_TIMEOUT_S`. On pi, the command dies at the cap. The step execution timeout and the process-tree kill are the backstop.

A command that can outlast its cap runs in the background. Redirect its output to `.scratch/` and read that file while it runs, so the agent keeps reporting progress.

## One kill path: the job object

`proc.spawn_managed` starts a child suspended in a kill-on-close Windows Job Object, then resumes it with `NtResumeProcess`. These children start this way: a `command` step, a `merge` or `gate` command, the engine's own `git` calls, the harness executor runners, and the `claude auth status` and `--version` probes (`proc.run_managed`). The engine's `git` calls go `exec.git` → `exec.run` → `proc.spawn_managed`. A step timeout or a harness executor `kill` ends the job, and the job takes the whole process tree with it, re-parented grandchildren included. A command that leaves a background process behind loses it when the step ends.

The launch methods start outside a kill-on-close job on purpose, so a detached supervisor outlives its launcher. The supervisor then starts its own children through `spawn_managed`, so the tree below it is one job. Short helpers start through `proc.run`, which gives the child a stdin handle and no job. These helpers are the `git` calls of `fingerprint.py` and `campaign.py`, the detach shim, the pi session export and the `revert` script.

Off Windows the child leads its own process group, and the group is the tree. The supervisor ends its groups itself when it exits and on SIGTERM and SIGHUP. For a supervisor that dies any other way, a SIGKILL included, `proc` starts one group watcher per supervisor (`group_watcher.py`), in its own session, on a pipe that only the supervisor can write. The supervisor names each group it starts and each group it has ended. When the pipe ends, the watcher ends the groups still named. Three limits stay. A child that leaves its group by starting its own session is outside the tree. A supervisor killed between starting a child and naming its group leaves that child. A supervisor whose watcher was killed goes on without one.

## Structured results and dimensional review

An agent with `schema` ends with one fenced JSON object. Every harness executor parses and validates it through `structured.parse_structured`. A `command` step with a `schema` prints the JSON on stdout, and the engine parses that with its own copy, `_fenced_json` in `engine.py`. Malformed JSON or a schema mismatch is a `schema_valid` gate failure. `result.json.schema_error` and `gate.json` keep the parse detail. Retry only through an explicit `gate:schema_valid` policy, so the next position block carries the detail.

The position block renders the contract `schema_valid` applies: every key name, its type, whether it is required, every enum, and the path of `schema.json` beside the brief. It walks the subset the gate enforces (`type`, `required`, `properties`, `items`, `enum`) from the same dict the gate reads. Put the contract in `step.schema` and do not restate keys in prose, because a hand-written copy drifts.

`ohflow.workflows.review_by_dimension` builds one read-only reviewer per named dimension, each answering `{dimension, verdict, findings, summary}`. A deterministic command step reads the numerically latest `attempts/NN/result.json` of each reviewer and writes `review.md` and `verdict.json`. Any blocked dimension makes the verdict `BLOCKED`. The driver's flags for it are in [implement-review](implement-review.md). Command steps receive `OHFLOW_RUN_DIR`, `OHFLOW_ATTEMPT` and the absolute `OHFLOW_ATTEMPT_DIR`, so their artifact paths are attempt-local.

A command step in the `sh` shell runs as `bash -lc`, a login shell, so it reads the operator's login profile first. The PATH the profile sets reaches the step, so a workflow names a tool by its name, not by its full path. A secret the profile exports reaches the step as a variable, so no agent has to copy a sensitive string into a command. Access control belongs to the layers around ohflow, not to this one. The cost is that a step reads each operator's own profile: anything the profile prints ends up in the step's output, and a slow profile slows every step.

`references/summary.schema.json` is the executable `summary.json` contract. It uses the validator-supported subset (`type`, `required`, `properties`, `items`, `enum`, `additionalProperties`). The test runner audits every `summary.json` it sees: an unfiltered suite emits receipts and zero rejections. A new output field needs a schema update.

## Every execution owns a directory

    <step>/attempts/01/   position.md brief.md spec.json final.md result.json
                          gate.json handover.md logs/ conversations/ completions/
    <step>/               the small files of the latest finished attempt

An agent's `out_dir` is its attempt directory, so every path it records stays valid and nothing moves afterwards. The step root keeps a copy of the eight small files. The engine clears it when an attempt starts and writes it when the attempt finishes, so it never mixes two attempts. `run-log.jsonl` is append-only and is the source of truth. `board.md`, `summary.json`, `result.json` and `gate.json` derive from it.

Every `spec.json` and `result.json` carries its attempt number. The engine rejects a result whose attempt is missing, closed or different from the active handle. Gate commands receive `OHFLOW_ATTEMPT` and the absolute `OHFLOW_ATTEMPT_DIR`. Every agent attempt also writes `agent.pid` before execution.

`result.json.settings.requested` records the model values in the workflow. `result.json.settings.effective` records what the harness executor reports it got: the model, its thinking or effort level and the effective tool names. API keys are omitted. Read `effective` when you audit what the agent received.

A workflow that needs findings after a failed gate gives the agent an absolute run-level `reports/` output path and guards it with a `command_exit` check. The engine does not create or collect that directory itself. The position block says the final message is the agent's answer and forbids writes outside the worktree. State the exception in every affected brief, restrict it to named files, and gate both the fenced JSON and the file.

## Four run notes sit at the run root

A fresh run writes four files beside `run-log.jsonl`: `predictions.md`, `notes.md`, `retro.md` and `ground-truth.md`. They hold what the run log cannot: what the orchestrator agent expected, and what the operator did by hand and judged afterwards. The run never waits for them. Nothing rebuilds them after the run.

- **Templates:** `scripts/ohflow/run_notes/`, one file per note. `{{name}}` fills from the workflow and the run (`run_id`, `workflow`, `repo`, `base_branch`, `base_sha`, `run_dir`, `started`, `baseline_line`, `step_rows`). An unknown name stays visible. `retro.md` gets one row per step with the step's `objective` or `note`. The code is `ohflow/runnotes.py`, and `NOTE_FILES` names the four.
- **Written once.** Each file opens in exclusive mode, so a person's edits survive. Only a fresh run writes them: `--resume` and `--dry-run` write none.
- **Never a gate.** A missing template or an unwritable file prints `[run notes] not written, the run goes on`.
- **Three verbs.** `run --predictions FILE` seeds `predictions.md` from FILE. `ohflow notes log --run D "<text>"` appends one `HH:MM | text` line to `notes.md`. `ohflow notes check --run D` prints `NOTES COMPLETE` (exit 0) or `NOTES INCOMPLETE: G gaps` (exit 1) and one line per gap.
- **Predictions are written for an orchestrator calibration only.** The orchestrator agent answers them when the operator asks ([operate-a-run](operate-a-run.md)). An untouched `predictions.md` is no gap, but once one line is answered, each empty line is.
- **Section 1 of `ground-truth.md` takes the gate's pass.** It is done when it names the CI run on the pushed head, or when the run's `check-passes.jsonl` holds a pass on the tree of the merged head: the `base_branch` of `workflow.json` in its `repo`. A merged head with another tree leaves the gap.
- **Outside every identity.** They live in the run directory, so no fingerprint reads them. Editing one starts no step on a resume.

Adding a fifth note means adding its template, its name in `NOTE_FILES` and a line in `tests/test_run_notes_01_four_files_at_the_run_root.py`.

### The engine drafts the retro

`retro.md` holds a block between `<!-- ohflow:auto begin -->` and `<!-- ohflow:auto end -->`. When a run ends, after `summary.json` is written, `ohflow/retrodraft.py` rewrites that block from `summary.json` and the attempts' `gate.json`. Everything outside the markers belongs to the person. A resume rewrites the block and nothing else.

- **Totals:** status and times, steps by status, agent steps that passed first time, after a retry, or not at all, agent time against elapsed, LLM calls, tool calls, tokens, cost, model, and each branch's diff stat.
- **Per step:** one row with the sums and test case formats of `ohflow table --by step`. The module calls `table._fold` and `table._case`, and a test compares both outputs. A dash means an agent execution wrote no numbers.
- **Pointers:** places to look, never verdicts. A retry, with each attempt's status, failure class and failed checks. A step that did not pass, with its `retry_decision`. An excluded step. An attempt that recorded an error and still passed its gate. A step at twice the median for tool calls or agent time (three or more agent steps, above a floor, `OUTLIER_*`). An attempt with three or more tool errors. Unpriced cost is not a pointer.
- **Never a gate.** No `retro.md`, no `summary.json`, a missing marker or a failed write prints one `[retro]` line and the run goes on.
- **After a hard kill:** `ohflow report --run DIR` writes the missing `summary.json` from the run log, then the draft. A dry run has no `retro.md`. The engine never fills the person's columns (verdict, gate right, cause).

The operator's steps for the notes are in [operate-a-run](operate-a-run.md#keep-the-run-notes).

## Provider options on a ModelConfig

`ModelConfig.params` is a closed set per harness executor. `pi`, `durable` and `pi-cloud` take `thinking`. `claude` takes `effort`, and `codex` takes `reasoning_effort`. `claude-cloud` and `codex-cloud` take none. Each executor's `agent_errors` refuses any other key ([harness executors](harness-executors.md)). Every harness executor refuses a non-empty `extra_body`. The field stays on `ModelConfig` because the step fingerprint hashes the whole model configuration.

```python
ModelConfig("light", "", "DEEPSEEK_API_KEY", params={"thinking": "off"})
```

### The DeepSeek execution preset

A second provider exists for the day Z.AI rate-limits a run. Provider failover itself is not built. To move a tier onto DeepSeek, map it in `ohflow.settings.local.json`, such as `tiers.light.pi`.

| Field | Value |
|---|---|
| model id | `deepseek/` followed by the DeepSeek model id |
| base URL | empty: pi's built-in `deepseek` provider |
| key variable | `DEEPSEEK_API_KEY` on `pi`, and empty on `durable` and `pi-cloud`, which hold their own key |

DeepSeek's flash model thinks by default. Set `thinking` per workflow, per phase. Reasoning tokens bill as output at $1.20/M. A scout that reads a repository wants thinking on. A step that reformats a result does not.

## Gate checks

Checks in `ohflow.gates`: `commits_past_base`, `command_exit`, `test_counts`, `tree_clean`, `ownership`, `paths_untouched`, `no_ai_attribution`, `final_message_matches`, `schema_valid`, `file_contains`, `handover_written`, `rollcall_matches`. Every check is a command plus the exact output that means pass, and holds the field constant, as in [brief-templates](brief-templates.md). `rollcall_matches` compares a roll-call agent's report of its own tool policy with what its harness announced. Its rules are in the [CONTRIBUTING](../CONTRIBUTING.md#testing-with-live-agents).

**A mechanical check pass is reused within its run.** A passed `command_exit` on a clean worktree is a mechanical check pass, recorded in the run's `check-passes.jsonl` with the command, its shell, its folder and the tree hash. A later `command_exit` in the same run with the same command, shell and folder on the same clean tree reuses it, and the campaign's acceptance checks do too. Its evidence is the first run's log. A failure, a timeout and a dirty tree always run the command. A check whose result depends on files outside the worktree that change during a run sets `reuse: false`. `construct` sets it on a command that names another workspace.

**A gate tests the change, never the whole suite.** Checking a change costs in proportion to the change. A gate, a `check-` step and a campaign acceptance check run only the tests that the step's changed files reach, in minutes. The full suite runs in CI after a push, where nobody waits for it, and never blocks a stage, a gate, an acceptance check or an agent's work. `{base}` in a `command_exit` command or a command step is the commit the step's worktree was created from. In an acceptance check it is the commit of the campaign's integration branch in the check's workspace. A command with `{base}` fails on a step that has no worktree. For this repository the gate command is `python3 tests/run_tests.py --changed {base}`, run from the root of the ohflow clone. The [CONTRIBUTING](../CONTRIBUTING.md#running-the-suite) gives its selection rules and its budget.

`validate` reads each `CheckSpec` against its check: an unknown check name, an argument the check does not take and a missing argument the check needs are each refused with the step, the check and the argument named, before any agent runs.

The checks that read git history (`commits_past_base`, `ownership`, `paths_untouched`, `no_ai_attribution`) take `since`. `tree_clean` reads the working tree and takes none. `since` names the commit the check measures from:

| `since` | Commit |
|---|---|
| `base` (default) | the commit that created the worktree, `GateContext.base_sha` |
| `step_start` | the commit this attempt began from |
| `last_merge` | the newest merge commit, else the base |
| any ref name | that ref |

A relay step says `since="step_start"` and a consolidator says `since="last_merge"`.

`file_contains(path, text, hidden=False)` passes when the worktree file holds the text. With `hidden=True` the check's description does not print the text, so a retry brief never shows it. Only the failure line in `previous_failures` carries it. A path outside the worktree fails as `bad arguments`.

`workflow.clean_commit_checks(write_scope, since="base", min_commits=1, marker=None)` returns the checks every committing agent repeats (`commits_past_base`, `tree_clean`, `ownership`), then `workflow.house_checks(since)`, then `final_message_matches` when you give a marker. `house_checks` adds `no_ai_attribution` when the `commit_checks.no_ai_attribution` setting is on.

## Run it

Run each command from the `scripts/` folder of your ohflow clone.

```bash
export PYTHONPATH=.
python3 -m ohflow.cli preflight [--workflow ohflow/workflows/<workflow>.py --args k=v] [--harness-executors pi,claude] [-v]
python3 -m ohflow.cli validate --workflow ohflow/workflows/<workflow>.py --args k=v [-v] [--history DIR]
python3 -m ohflow.cli estimate --workflow ohflow/workflows/<workflow>.py --args k=v --history DIR [--pilot <run-dir>] [--json]
python3 -m ohflow.cli board    --workflow ohflow/workflows/<workflow>.py --args k=v
python3 -m ohflow.cli construct --bundle <bundle> --out <campaign> [--history DIR]
python3 -m ohflow.cli run      --workflow ohflow/workflows/<workflow>.py --args k=v --out <runs-root> --dry-run
python3 -m ohflow.cli run      --workflow ohflow/workflows/<workflow>.py --args k=v --out <runs-root> [--predictions FILE] [--history DIR]
python3 -m ohflow.cli run      --workflow ohflow/workflows/<workflow>.py --args k=v --out <runs-root> --hold
python3 -m ohflow.cli run      --workflow ohflow/workflows/<workflow>.py --args k=v --out <runs-root> --pilot [--history DIR]
python3 -m ohflow.cli go       --run <run-dir>
python3 -m ohflow.cli kill     --run <run-dir> --step <coord> [--reason TEXT] [--timeout S]
python3 -m ohflow.cli watch    --run <run-dir> [--timeout S] [--until change|end|attention] [--cursor NAME] [--json]
python3 -m ohflow.cli status   --run <run-dir> [--watch] [--json]
python3 -m ohflow.cli notes log   --run <run-dir> "<text>"
python3 -m ohflow.cli notes check --run <run-dir>
python3 -m ohflow.cli campaign watch --campaign <campaign.py> [--timeout S]
python3 -m ohflow.cli campaign history --campaign <campaign.py or folder> [--milestone ID] [--json]
python3 -m ohflow.cli campaign estimate --campaign <campaign.py> [--history DIR] [--json]
python3 -m ohflow.cli position --run <run-dir> --step <step-id>
python3 -m ohflow.cli explain  --run <run-dir> --step <step-id> [--attempt N] [--json]
python3 -m ohflow.cli compare  --runs <run-A> <run-B> [--json]
python3 -m ohflow.cli actions  --run <run-dir> --step <step-id> [--attempt N] [--json]
python3 -m ohflow.cli revert   --run <run-dir>
python3 -m ohflow.cli dashboard --run <run-dir> [--port N] [--open]
python3 -m ohflow.cli report   --run <run-dir>
python3 -m ohflow.cli table    --runs <runs-root> [--by phase|step] [--reconcile]
python3 -m ohflow.cli rollcall --matrix smoke
```

The roll call is in the [CONTRIBUTING](../CONTRIBUTING.md#testing-with-live-agents). `board` renders the workflow as a board before any run. `validate -v` prints each phase's parallel limit.

**`run` flags.** `python3 -m ohflow.cli run --help` lists every flag, and the `run` subparser in `build_parser()` of `scripts/ohflow/cli.py` owns them. `--json` works only with `--detach`. An attached run refuses it and exits 2.

**`--args` takes one `k=v`.** Repeat the flag once per key: `--args repo=X --args sweep=0`. Every verb that takes `--args` refuses the comma-joined form `--args repo=X,sweep=0` with exit 2, because it would read as one `repo` value. A value that is itself a comma list of `name=value` pairs, such as `harness_executors=security=pi,correctness=pi`, is accepted.

### Verbs and their verdict lines

Line one of each verb's output is its verdict.

| Verb | What it does | What it prints |
|---|---|---|
| `preflight` | checks Git Bash, the workflow and each harness executor | `PREFLIGHT PASS` or `PREFLIGHT FAIL`, then one `FAIL` line per fault |
| `construct` | writes a campaign from a bundle of milestone specs ([construct](construct.md)) | `CONSTRUCTED <campaign>: N milestones` or `REFUSED <bundle>: N problems` |
| `validate` | checks a workflow without a run | `VALID <workflow>: ...` or `INVALID <workflow>: N problems` |
| `estimate` / `campaign estimate` | forecasts a run's or a campaign's minutes, tokens and cost from past runs | `ESTIMATE ...` or `CAMPAIGN ESTIMATE ...`, then a table |
| `run` | fires a workflow: `--dry-run` rehearses, `--detach` backgrounds, `--hold` waits for `go`, `--pilot` prices each unit path, then holds | `dashboard: <url>` first, then the run lines |
| `go` | releases a held run | `go sent to <run-dir>` |
| `kill` | ends one step's running attempt while the other steps run on | `KILLED <coord> attempt <n>: <error>`, or `NOT KILLED` or `KILL SENT` with the reason |
| `status` | reads a run without waiting | the status sentence, then one line per need |
| `watch` | waits for news | the status sentence, then new step changes, digest entries and attention items |
| `campaign watch` / `history` | `watch` for a campaign / its rounds | new log events / each round's reason |
| `notes log` / `check` | appends to or audits the run notes | the logged line / `NOTES COMPLETE` or `NOTES INCOMPLETE: G gaps` |
| `table` | totals the runs' cost and tokens | one row per phase or step |
| `transcript` | exports one step's agent transcript | a path |
| `explain` | triages one step's attempt | `EXPLAIN <coord> attempt <n>: ...`, then evidence lines |
| `compare` | diffs two runs | `COMPARE <A> -> <B>: ...` |
| `actions` | lists an attempt's model calls | `ACTIONS <coord> attempt <n>: ...`, then calls and their actions |
| `position` | prints a step's position block | the block |
| `revert` | removes a run's worktrees and branches in every workspace | what it removed |
| `dashboard` | serves a finished run again | the URL |
| `report` | rebuilds the exit report after a hard kill | `status:`, `verdict:`, then its paths |
| `cloud-spend` | reads Cloudflare's container bill | `cloud-spend: ...` |
| `rollcall` | runs the live-agent matrix | `ROLLCALL PASS: N of N cases`, `FAIL` or `DRY` |

### Estimate a run

`ohflow estimate --workflow M --history DIR` forecasts a workflow before it runs: minutes, tokens and cost per step, per phase and for the run, as a p50 and a p80 with the sample count. The history is every `summary.json` up to four levels under each `--history` directory (repeatable). Without the flag the verb reads `OHFLOW_HISTORY` (`os.pathsep`-separated), and with neither it prints `estimate: no history given (--history DIR or OHFLOW_HISTORY)` and exits 0. One sample per attempt, failed ones included. A step is looked up by `(role, harness executor, model)`, falling back to `(executor, model)`, `(executor,)`, then the whole corpus. The `basis` column says which key answered. A phase is `ceil(agents / max_parallel)` waves of the median step. A command, gate or merge step and a cached step add nothing. The run is the phases in order, times the retry multiplier (attempts over steps in the corpus). The `checks p50` column is the time a step's gate checks take: the `duration_s` a `command_exit` result records, and for a step recorded without it, the step's time less its attempts' agent time. Confidence is `low` when a key has fewer than three samples, a fallback key answered, or the cost is unpriced. `validate -v --history DIR` and `run --dry-run --history DIR` print the same block. `run --history DIR` (and `campaign run --history DIR`) prints it at run start and writes `<run-dir>/estimate.json`. A resume counts only the steps it will run again. A held run writes it before it waits, so the hold page and `status` show it, and again after the reload on `go`. The dashboard, the exit report and the retro draft read the file: [dashboard](dashboard.md#signals-and-eta). A whole campaign is forecast by [`campaign estimate`](campaign.md#estimate-the-campaign), which sums its milestones' run estimates, each one times one plus the median number of REVISE rounds a milestone takes.

**Hold.** `run --hold` claims the run directory, writes `workflow.json` and `.ohflow-hold` (the supervisor pid and the time), starts the dashboard, runs preflight, prints `held: waiting for go (ohflow go --run <run-dir>)` and waits. No run log line exists while it waits, and the run reads `held`. The dashboard opens on its Plan view, which shows every step's full brief, position block, gate checks, handover, schema, command and limits ([dashboard](dashboard.md#plan-view)). `ohflow go --run <run-dir>` writes `<run-dir>/go`. The supervisor removes `.ohflow-hold`, loads the workflow module again with the recorded `--args`, validates it, rewrites `workflow.json` and runs. An edit made to the module while held is therefore what runs. A module that no longer builds ends the run as `crashed` with the message. The run stays unstarted and the `go` file stays as evidence. A preflight failure while held ends the run as `crashed`, as it does without the hold. `--hold` with `--resume` is refused: a resume already started. Only the campaign controller holds a resumed run, for a round that a judge's REVISE starts ([campaign](campaign.md)). That hold removes the earlier round's `go` file before it waits. `--hold` with `--dry-run` holds nothing. A detached `run --hold` prints `go: ohflow go --run <run-dir>` after the pid line (`"go"` and `"held": true` with `--json`). `go` exits 1 when no `.ohflow-hold` exists or its pid is dead. `go --predictions FILE` first writes FILE to `predictions.md` and logs it in `notes.md`, so predictions that the operator gives during the hold are in place before the first step. It exits 1 and sends no go when `predictions.md` already holds predictions.

**Kill one step.** `kill --run <run-dir> --step <coord> [--reason TEXT]` ends the running attempt of one `agent` or `command` step, and the other steps run on. `--step` also takes a step id that names one step. The verb finds the running attempt in the run log and writes `kill-request.json`, naming that attempt, into the step directory. It refuses a step with no running attempt, a `merge` or `gate` step, and a run with no live supervisor. The engine reads the request at its next poll (2 s for an agent, 1 s for a command) and ends the attempt through the harness executor's `kill`, or a command's process tree. That `kill` stops the remote work too: a `durable` host ends with its ssh connection, and a cloud executor posts `abort` ([harness executors](harness-executors.md)). The request moves into the attempt directory as evidence. No gate runs, and the attempt closes `deferred` as an abort victim, with the error `killed by ohflow kill: <reason>` and `killed` (`reason`, `requested_at`) in its `attempt_finished` payload. No retry and no auto-resume pass starts it again. The phase goes on, and when it misses `min_success` without the killed step it settles `deferred` and the run pauses. `run --resume` then starts the step as a new attempt with a fresh conversation, never a reattach. That attempt's position block lists `killed by ohflow kill: <reason>` under "What failed last time", so the reason redirects the step without a brief edit. A brief edited before the resume runs as a new revision with its own budget. The kill spends a start, as an abort victim killed in flight does, and it is not a counted failure. The verb waits up to `--timeout` (default 120 s) for the attempt to close. It exits 0 with `KILLED <coord> attempt <n>: <error>`. It exits 1 with `NOT KILLED` when the attempt ended on its own first, for example while its gate ran, and with `KILL SENT` when the supervisor has not closed it yet.

**Resume.** `--resume <RUN_ID>` takes the run id. The run id is the run directory's name under `--out`. `--resume` refuses a run without a run log. It also refuses a run that its supervisor still runs: when the run log reads `running` and the supervisor that the run directory records (`supervisor.pid`, or `.ohflow-owner.json` without it) is alive, it prints `run <RUN_ID> is still running under supervisor pid <pid>; resume it once that supervisor has stopped: <run-dir>`, exits 1 and writes nothing. `run --detach --resume` refuses before it starts a supervisor. A resume writes no `run_started` event. It writes `run_finished` at its end, as every run does. The run reader decides from the run log alone: a run that has any work event (`phase_started`, `attempt_started` and the rest) after its last `run_finished` is `running` again, and its finish time is cleared. A resumed run whose supervisor died reads `orphaned`. An attempt killed together with its supervisor stays `running` in the run log until the resume: before any step starts, the resume closes it `deferred` as an abort victim with `interrupted: true` and the error "the supervisor stopped before this attempt finished". The closure spends nothing more than the start already did and does not advance the exclusion. An open attempt of a step whose harness executor declares `reattach` (`durable`, `pi-cloud`, `claude-cloud` or `codex-cloud`) waits for the reattach rule instead, and closes the same way when it cannot reattach. `status` and `watch` write nothing to the run log, so until the resume they derive the step's `interrupted` from the dead supervisor. An `exit.json` older than the run log's last write belongs to an earlier stop, so `status`, `watch` and the exit report ignore it. The resume leaves the old exit files in place, and the next stop replaces them.

**Exit codes.** 0 is success. 2 means the workflow or its arguments are wrong: a missing `--args` key prints `workflow argument missing: <name> (pass --args <name>=...)`, and an invalid workflow prints `WORKFLOW INVALID` and the reasons. Any other exception prints the last lines of its traceback and exits 1. A workflow reads optional arguments with `args.get(name, default)`.

| Verb | Exit |
|---|---|
| `preflight` | 0 pass, 1 fail |
| `construct` | 0 `CAMPAIGN OK`, 2 a refused bundle, or a milestone or campaign that does not validate |
| `validate` | 0 valid, 2 invalid |
| `status` | 0, or 2 for an unknown run |
| `watch`, `campaign watch` | 0 every step passed, 1 ended otherwise (a `crashed` run and a never-started launch included), 2 unknown run, 3 a workflow and nothing else (start a run with a new `--run-id`, or delete the directory first), 10 still going (a `starting` or `held` run included, and a held run adds one line with the `go` command) |
| `go` | 0 go sent, 1 no hold, a dead supervisor, or a pilot still running |
| `estimate` | 0 printed (the no-history line included), 1 a `--pilot` directory with no `pilot.json` |
| `notes check` | 0 complete, 1 gaps |
| `explain` | 0 explained, 1 not a run, a missing or ambiguous step, or no such attempt |
| `compare` | 0 compared, 1 a directory that is not a run |
| `actions` | 0 listed, 1 not a run, a missing or ambiguous step, no such attempt, a command, gate or merge step, or no transcript |
| `campaign history` | 0 listed, 1 no campaign log, or a `--milestone` with no round or event |
| `campaign estimate` | 0 printed (the no-history line included) |
| `rollcall` | 0 pass or dry, 1 fail, 2 bad test case, matrix or config |

`preflight` runs each check as data and prints one `FAIL <check>: <observed>; <fix>` line for each check that fails. The checks, by the name a `FAIL` line gives them:

| Check | What it asks |
|---|---|
| `Git Bash` | Git Bash runs, and where it comes from is below |
| `workflow` | the workflow module loads with its `--args`, and only the `preflight` verb lists this check |
| `repository` | each [workspace](#workspaces) is a git repository |
| `model keys` | each key variable an agent step's model names is set in this shell |
| `<name> harness executor` | the harness executor's own questions (`harness_executor.preflight()`) |
| `base branch` | each workspace is on its base branch |
| `clean tree` | each workspace's tracked files hold no uncommitted change |
| `workspace remote` | each workspace's `origin` is the `remote` the workflow names |
| `worktree path length` | on Windows, a local worktree's root plus the longest path tracked at its base stays under 260 characters, unless the repository sets `core.longpaths` |
| `node_modules source` | a worktree that links `node_modules` as a junction finds the folder it links |

`tests/check_docs.py` fails when this table and the checks that `scripts/ohflow/preflight.py` builds disagree, so a new check needs its row here. The engine runs the rows from `repository` down at the start of every fresh run and stops on the same words, as `preflight failed:` and one line per problem. With several workspaces a `FAIL` line names the workspace at fault. `--harness-executors` defaults to the workflow's harness executors, or every harness executor with no workflow. Git Bash comes from `paths.bash_exe()`: `OHFLOW_BASH` when set, else the first `bash` on PATH that is not a WSL launcher, else the usual Git install paths. The two WSL launchers are `bash.exe` under `%SystemRoot%` and the app execution alias in `WindowsApps`. A command that runs in WSL by mistake shows an empty current branch, and then every base ref reports that it does not resolve.

`runstatus.sentence` writes the status sentence, and `status` and `watch` both use it. It reads step facts through `rundir.open_run` and the harness executor questions. These readers still parse run files directly: `live.py`, `exit_report.py`, `retrodraft.py`, `table.py`, `runstatus.dashboard_url`, the `transcript` verb, `rollcall.py` and `campaign.py`.

**Each reader keeps a watch cursor.** `watch` stores the facts it last reported in `<run-dir>/.watch.<name>.json` (`--cursor NAME`, default `agent`). `campaign watch` stores it in the campaign root. A repeat call prints only what is new, so a second call on a quiet run prints one line. Each cursor name keeps its own place. `watch` waits up to `--timeout` seconds (default 300) for a change, or for the end with `--until end`. When the run is already over, it returns at once. When the supervisor died, `watch` writes `exit.json` and the exit report and prints the verdict, and the run reads as `orphaned`. `status --watch` redraws every 3 s and prints no ANSI codes when stdout is not a terminal.

**`watch` carries the digest and the attention items.** These are the dashboard's digest and attention strip, read from the run directory by `dashboard_data.agent_view`, so they need no dashboard. After the head line and the step change lines, `watch` prints one line per new digest entry, oldest first, then one line per new or cleared attention item, in consequence order (`intervention`, `recovering`, `signal`). Each line is at most 300 characters: the text gives way, and the run-log pointer stays. A next command is never cut: when it alone fills the cap, its line runs longer.

- `digest: <text> · run-log.jsonl:<line>` for each digest entry above the cursor's `digest_line`. A first call prints the newest 10 entries, after `... <n> earlier digest entries not shown` when it cut some.
- `attention <group>: <observed> · next: <command, or why there is none> · run-log.jsonl:<line>` for each item the cursor has not reported. The pointer is left out when the item has no run-log line.
- `attention standing <group>: <observed> · next: <command, or why there is none> · run-log.jsonl:<line>` for each item a fresh cursor finds on its first look. A fresh cursor has reported nothing, so it cannot call such an item new: the item may be hours old. An item that arrives while that first call waits prints without `standing`.
- `attention cleared: <kind> <coord, or run>` for each reported item that is gone.

The cursor file holds two more keys: `attention`, the keys of the items reported (`group|kind|coord|attempt`), and `digest_line`, the highest run-log line reported as a digest entry. A cursor written before these keys existed keeps its step facts and reads as a first call for the digest and the attention items. A first call is a snapshot, so with `--until change` it returns at once: every step that already moved, the newest digest entries and the standing attention items are all unreported. `--until change` also returns on a new digest line and on a new or cleared attention item. `--until attention` returns when an `intervention` item the cursor has not reported appears, when the run stops, or at the timeout. A digest line or a step change alone does not return it. A standing `intervention` item returns a fresh cursor at once, because the reader has not seen it. `watch --json` adds `attention` (every current item, in full), `attention_new` (the keys of the items that arrived since the cursor's last report, empty on a fresh cursor's first look) and `digest` (the entries this call printed, in full). `status --json` adds `attention` (every current item). Text `status` is unchanged. Exit codes are the same.

**`watch` names the phase boundary check.** After the attention lines, `watch --run` prints `phase boundary: phase <number> <name> settled <status> · next: the phase boundary check in references/monitor-a-run.md` for each phase that settled since the cursor last looked, for an orchestrator agent whose harness dropped the skill body. The cursor file holds the settled phases in `phases`. A cursor that holds no `phases` key gets the line for the newest settled phase only, and a phase that starts again and settles again gets its line again. The line counts as news for `--until change` and does not return `--until attention`. `watch --json` adds `phase_boundaries`, the coordinates of the phases this call named.

**`explain` prints the step inspector as text.** `explain --run <run-dir> --step <step id or coordinate>` explains the newest attempt of the step, and `--attempt N` names another. It reads the run directory through `ohflow/explain.py`, so it needs no dashboard. Line one is the verdict: `EXPLAIN <coord> attempt <n>: <status>[, <failure class>[: <signature>]]; <retry decision>`. The failure class and the retry decision are the ones the engine recorded. `explain` does not classify again. Then one line each, left out when empty:

- `step:` id, role, harness executor, phase and status.
- `cause:` the attempt's cause, with its `attempt_finished` run-log line. When the engine recorded an execution error, such as `stall` or `pi-cloud runner was killed`, the line is `cause: execution error: <error>`. An attempt the execution timeout stopped with no error text reads `cause: execution error: the execution timeout stopped the attempt`. With no execution error, the cause is the failed gate checks.
- `gate failed:` one line per failed check with observed and expected, and the gate file. After an execution error, the checks failed because the attempt stopped, so each line reads `gate failed after the execution error:` and follows the `cause:` line. `gate passed:` the passed checks by name.
- `attempt <n>:` one line per attempt of the step, oldest first, at most 10, each with its cause (the execution error when one is recorded), its retry decision and its run-log line.
- `handover:` the first line of the handover, with its path.
- `final:` the first line of `final.md`, with its path, only when the agent completed its answer: the runner recorded `execution_status: finished` with no error, or a command step's command exited. A stall, a kill, an execution timeout, an abort or a provider error leaves the last intermediate message in `final.md`, and `explain` prints it as `last message, interrupted:`. `--json` carries the verdict as `final.completed`.
- `tool output:` the open call, else the newest, with its exit and the call count. Its last 10 output lines follow, indented by `  | `.
- `tool:` the 5 newest tool calls from the harness executor's activity, then `reasoning:` and `last error:`. A command step prints `command:` and its log tail instead.
- `next:` one line per attention item of the step or of the run, with its next command, or `next: nothing waits on a person for this step`.

Each line is at most 300 characters, and the whole text at most 6,000 (about 1,500 tokens). A next command is never cut: the text before it gives way, and a command that alone fills the cap makes its line longer. A cut takes the lines before the `next:` lines, puts `... cut at 6000 characters; --json carries every field` in their place, and keeps every `next:` line. `--json` prints the same view as schema `ohflow.explain/1`, every claim with a `run-log.jsonl` line or a run-relative path. On four recorded failing runs the text was 1,742 to 2,250 characters, about 16 % of the `/api/evidence` plus `/api/agent` payloads the page reads for the same attempt.

**`compare` diffs two runs by fixed rules.** `compare --runs <run-A> <run-B>` reads each run directory through `ohflow/compare.py` (a directory with only `summary.json` is read from it), so it needs no dashboard, and the same two directories always print the same text. Steps pair by step id: a step that moved to another phase keeps its pair, and a step id in one run only prints `only in A` or `only in B`, after the paired steps. Line one is the verdict: `COMPARE <run A> -> <run B>: <n> paired, <d> differ, <a> only in A, <b> only in B`. Then one `A:` and one `B:` line (workflow, status, elapsed, base commit, directory), a `totals:` line, and one line per step: `step <id>: <status A> -> <status B>` with attempts, agent time, tokens and tool calls as `<A> -> <B>`, and the `run-log.jsonl` line of each side's final `attempt_finished`. Sums follow `table`'s rules: an unmeasured execution prints `-` and an unpriced cost `unpriced`. Under a step, one indented line per rule that fired, in this order:

- `coord:` the step moved. `status:` the step status differs. `attempts:` the attempt statuses differ.
- `failure:` the final failure class or its signature differs. `gate:` a check's verdict differs (`<check> passed -> failed (observed ...)`), or a check exists in one run only.
- `retry:` the final retry decision differs.
- `definition:` a field of the step's `workflow.json` entry differs, as a dotted path (`agent.harness_executor pi -> claude`). A string over 80 characters prints its lengths, never its text.
- `fingerprint:` the fingerprint differs while the definition does not, so the base commit or a dependency changed.

Each line is at most 300 characters, the evidence part never cut, and the whole text at most 6,000. A cut text ends with `... cut at 6000 characters; --json carries every field`. `--json` prints schema `ohflow.compare/1`: `runs`, `totals` and one `steps` entry per step id with its `a` and `b` sides and its `changes`. An LLM comparison of two runs stays an agent step that reads this output. On two recorded pairs that differ, the text was 27 to 33 % of `table --by step` on both runs plus `explain` on each changed step, and it alone names the definition change.

**`actions` lists what an agent did in one attempt.** `actions --run <run-dir> --step <step id or coordinate>` reads the newest attempt of the step, and `--attempt N` names another. It reads the attempt's transcript through `ohflow/actions.py`, so it needs no dashboard. It prints rows and names no failure layer. The orchestrating agent reads the rows to find the layer. Example layers: a tool the agent never called, a tool error the next call ignored.

```
ACTIONS <coord> attempt <n>: <C> model calls, <A> actions, <F> failed; tokens in <p> out <c> (<harness executor>)
source: <transcript path> · join: <the call key in words>
call <i> <hh:mm:ss> · in <p> out <c> · <latency> s · <k> actions · line <n>
  said: <the first sentence the model wrote>
  <tool> <summary> -> ok|failed|pending (<duration> s): <first result line> · line <n>
```

Tokens sit on the call line once, because one model call can launch several actions. `in` counts prompt tokens with cache reads and writes, as `result.json` does. The evidence is the line in the file the `source:` line names. An action's evidence is its result line, else its call line. A field the format does not record prints `-`. Paths under the worktree print as `./`, and paths under the run directory as `<run>/`.

| Harness executor | Call key | What is missing |
|---|---|---|
| pi | assistant `message.responseId`, and latency is the entry time minus `message.timestamp` | nothing |
| claude | assistant `message.id` | latency, and output tokens per call: the stream records them as of the first block. The head takes the attempt's output total from the `result` record. |
| codex | none: one `turn` holds every action, with the turn's tokens | latency and every duration, because codex events carry no time |
| pi-cloud | `message_end` `message.responseId`, read from `logs/pi-cloud-events.jsonl`, and latency is `message.durationMs` | the duration of a replayed action, because a replayed event's `t` is the replay's clock. A replayed event counts once, by the client's keys: `entryId` for `message_end` and `tool_execution_end`, `toolCallId` for `tool_execution_start`. The head takes the token total from `pi_cloud_end` when the log has one. |
| codex-cloud | `message_end` `message.responseId`, read from `logs/codex-cloud-events.jsonl`. The message arrives when the session settles and claims, by its toolCall ids, the actions that ran before it, and one `turn` holds them | while the attempt runs or after it was killed, everything a settled message carries: the actions then sit in one call with no key, time or tokens. A replayed event counts once, as for pi-cloud. |
| claude-cloud | the same, read from `logs/claude-cloud-events.jsonl`, one model call per message | the same as codex-cloud, and the tokens of each call: its messages carry the subscription's zero usage, so the head takes the total from `pi_cloud_end`. |

The dashboard's transcript panel reads the same event log of a pi-cloud, codex-cloud or claude-cloud step and passes over a replayed line. Its activity panel counts a replayed pi-cloud model call once.

A codex command arrives wrapped as `"...pwsh.exe" -Command "<command>"`. The summary shows the inner command. Each line is at most 300 characters and the whole text at most 8,000. A cut text keeps the head and the newest calls after `... <n> earlier calls not shown; --json carries every call`. `--json` prints schema `ohflow.actions/1` with every call and action and their run-relative evidence, and is not cut. On four recorded runs, one per harness executor, the text was 1,663 to 7,748 characters for transcripts of 79 KB to 1 MB.

**A run with no run log line takes its name from its files.** `Run.status_without_run_log` reads `held` while `.ohflow-hold` names a live process, and `starting` while the process named by `supervisor.pid` (else `.ohflow-owner.json`) is alive. An attached run writes the owner file before `workflow.json`, so a run in preflight or its baseline command reads `starting`. A run whose engine died reads as the status `exit.json` records. A preflight failure records `crashed` and the error. A launch that left a handoff file but no run log, no live engine and no `exit.json` gets 30 s of grace, then `watch` exits 1 with `the run never started: no supervisor and no run log; see <supervisor.log>`. Any other run reads `not started`. A run with a run log reads `held` too while `.ohflow-hold` names a live process: a campaign round that a judge's REVISE starts holds on its resumed run directory ([campaign](campaign.md)).

**Dashboard and exit report.** A run serves one dashboard and writes an exit report. `--no-dashboard` and a roll-call test case serve no dashboard. A dry run serves none and writes no exit report. The contract is [dashboard](dashboard.md). Here are the flags and files:

- An attached `run` prints `dashboard: http://127.0.0.1:PORT/` first and records the URL in `<run-dir>/dashboard.json`.
- `run --detach` waits up to 20 s for the supervisor's pid and the dashboard, and prints `dashboard: <url>` as line one, or `dashboard: pending (see <run-dir>/dashboard.json)`. The run directory and the supervisor pid follow. `--no-dashboard` makes line one `dashboard: off`. The pid is the one the supervisor records in the run directory: `.ohflow-owner.json` for a fresh run, and for a resume the `supervisor.pid` the engine writes with its next run log line. The process the launcher started can be a wrapper around the supervisor (the `cmd.exe` of the `wmi` launch method, the redirector of a Windows virtual environment), so its pid is printed only when no record arrives in those 20 s.
- An attached run ends with the exit verdict, the exit-report path and, for a paused run or a step that did not pass, the resume command.
- The server is a daemon thread of the supervisor on an OS-picked port. It only reads files. `--dashboard-port N` pins the port. `--open-dashboard` opens a browser, which no run does by default.
- When a run stops, on any path that runs code, the `finally` block of `supervisor.run_workflow` writes `exit.json`, `exit-report.md` and `exit-report.html`. The HTML opens from disk.
- A run with a cloud step (`pi-cloud`, `claude-cloud` or `codex-cloud`) reads Cloudflare's container meters for its Durable Objects before the exit report and writes `cloudflare.json`. The verdict names the figure, and `exit-report.md` has a `## Cloudflare` section with a flag for each object billed well beyond its reported container time. The read covers every `pi-cloud`, `claude-cloud` and `codex-cloud` attempt that wrote a `result.json`. A flag marks an object billed more than 120 s or 20 % beyond the time its attempt reported, whichever is larger, or billed for time its attempt never reported. The meters lag by a few minutes, so `cloud-spend --run DIR` repeats the read later. `cloud-spend --since ISO [--until ISO]` reads the whole account over a window, with the calendar month's container memory against the 25 included GiB-hours. The credential is `CLOUDFLARE_API_TOKEN`, else `wrangler auth token`.
- After a hard kill, `report --run` writes the missing `summary.json` and `retro.md`, rebuilds the three files and calls the run `orphaned`. `dashboard --run` serves any run directory later. When the run's own dashboard still serves, it prints that URL and starts nothing. `--dry-run` starts no dashboard and writes no exit report.

**`position --run` needs no `--workflow`.** `run.json` records `workflow_path` (absolute, because a workflow module can live outside `workflow.repo`, the repository the agents edit) and `workflow_args` (the `--args` verbatim, so a workflow that copies nothing into `Workflow.args` stays rebuildable). `--workflow` overrides a moved path.

**Dry-run before you burn agents.** `--dry-run` creates the worktrees, writes every brief, spec and position block, and launches nothing. Read a brief and a position block. Then run `revert` on the dry run, to prove teardown works before an agent has produced anything worth keeping. A successful rehearsal exits 0 and records each step as `dry-run`. `--dry-run` with `--resume` is refused, because a dry run writes run log events and a resume would write them into the real run's log. `status --run` shows what a resume would start.

**Detach.** `run --detach` and `campaign run --detach` start the background process through `ohflow/detach.py`. With `--json`, `run --detach` returns the launch method in `"launch_method"` and the dashboard address in `"url"`.

| Launch method | Meaning |
|---|---|
| `direct` | the launcher is not in a Windows Job Object |
| `breakaway` | the launcher's job allows `CREATE_BREAKAWAY_FROM_JOB`, so closing the job leaves the child alive |
| `wmi` | the job denied breakaway (`WinError 5`). WMI `Win32_Process.Create` creates the child through `run-hidden.vbs`, which sits beside `detach.py` (`OHFLOW_RUN_HIDDEN` names another shim) |

On `wmi`, the shim starts a PowerShell script that hands its environment to WMI as `Win32_ProcessStartup.EnvironmentVariables`, so no file holds an environment value. WMI starts the command from `<log>.launch.cmd`, which changes to the right directory and appends output to the log. `campaign.log.launch.*` is in the campaign's `.gitignore`. When the shim is missing or fails too, the command prints guidance to run outside that job, removes a run reservation it made, exits 1 and prints no traceback.

## Pilot a run over many units

`run --pilot` prices each unit path before the full run starts. It implies `--hold`, and it needs `Workflow.units` ([Units and unit paths](#units-and-unit-paths)).

1. The supervisor claims the run directory, writes `workflow.json` and `.ohflow-hold`, starts the dashboard and runs preflight, as for any held run. With a history, it writes `estimate.json` before the pilot.
2. The pilot workflow holds the smallest unit of each unit path, every step of that unit, and every shared step. A `depends_on` or `consumes` entry that names a dropped step is dropped, a phase left with no step is dropped, and an integer `min_success` falls to the steps left.
3. The pilot runs as a workflow run of its own in `<run-dir>/pilot`, with its own run log, summary, run notes and exit report, and no dashboard. Its worktrees are separate: each worktree path and branch gets the suffix `-pilot`, and a `WorktreeSpec.base` or `Step.merge_branch` that names a workflow branch follows it. A command that writes a worktree path or branch into its own text reaches the full run's worktree. Build it from paths relative to its working directory. The pilot's worktrees stay for reading, and `ohflow revert --run <run-dir>\pilot` removes them.
4. The supervisor measures each pilot unit from the pilot's `summary.json` and writes `<run-dir>/pilot.json`. Time is the summed wall time of the unit's attempts. A command step's time comes from its step record. Tokens and cost are summed over the attempts. A unit with tokens and no price reads `unpriced`.
5. The projection of a unit path is the number of its units times the measured cost of its pilot unit. The shared steps count once. A unit path whose pilot unit recorded no time reads `not measured`, and the total names it.
6. The run waits for `go`. `go` refuses with exit 1 while `pilot.json` reads `running`. On `go` the module is loaded again, and `pilot.json` is projected again with the reloaded module's unit counts, so the page shows the projection of the workflow that runs.

**The full run runs every unit, the pilot's units included.** A pilot unit does not count as done, for three reasons. The pilot exists to change the workflow, and an edit at the hold makes the pilot's output a product of the old workflow. The pilot's work sits on its own worktrees, and merging it would need a second integration path. The price is one extra unit per unit path. A unit whose work acts outside the repository, such as a live probe, therefore acts twice.

**The projection leans low in two cases.** The pilot runs the smallest unit of each unit path, so the projection is low when cost grows with size. A shared step that reads every unit's output costs more in the full run than in the pilot. The projected time is agent time, while the history estimate's minutes beside it are elapsed time.

**Where it shows.** `run --pilot` prints `PILOT <workflow>: projected <time>, <tokens> tokens, <cost> for N units on K paths; measured on k pilot units in <time>, pilot run <status>`, then one table row per unit path and one for the shared steps. On a held run, `status` and `watch` print a `pilot:` line, one `pilot <path>:` line per unit path, a `pilot shared steps:` line and the `ESTIMATE` line when `estimate.json` exists. `--json` carries `pilot`. While the pilot runs, `watch` ends with `held: the pilot runs first · ohflow watch --run <run-dir>\pilot`, and a change of `pilot.json` counts as news. The dashboard shows the pilot panel above the estimate while the run is held ([dashboard](dashboard.md#signals-and-eta)). After an edit at the hold, `estimate --workflow M --pilot <run-dir>` prints the projection again with the unit counts of the module as it reads now.

**Refusals.** `--pilot` with `--dry-run` or with `--resume` exits 2. A workflow with no units exits 2 with `--pilot needs units: ...`. A detached `run --pilot` prints `pilot: <run-dir>\pilot` before the `go:` line, and `"pilot"` with `--json`. A pilot that did not start, for example on a preflight fault, ends the run as `crashed`, and `pilot.json` reads `crashed` with the problem.

## The coordinate is the address

Every step gets a coordinate, `NN.phase/NN.step`. It names the step directory, keys the run log, and is the LLM `usage_id`, so the token bucket, the agent transcript, the gate report, `board.md` and the brief join on one string. The engine writes a position block to the attempt's `position.md` and prepends it to every brief: the run, the phase, the step, the attempt, the coordinate, the worktree, branch and base commit, the write scope, the other workspaces when the workflow has several, the contracts when the workflow has them, what earlier phases merged, the quarantined branches, the received handovers, who runs alongside, what consolidates afterwards, the step's gate, its schema contract, its own handover instructions, and from the second attempt the previous attempt's failures and handover. `ohflow position` prints it for one step.

## Narrow an MCP tool policy

`ToolPolicy.only` selects built-in tools. ohflow's own MCP tool policy is two lists of `server.tool` globs, `allow` and `block`:

```python
tools=ToolPolicy(
    only=("terminal", "file_editor"),
    allow=("note-store.memory_search", "tracker.*"),
    block=("tracker.post",),
)
```

A tool is offered when it matches an `allow` glob, or when `allow` is empty, and it matches no `block` glob. So the example offers `memory_search` from `note-store` and every `tracker` tool except `post`, and keeps the named built-ins. In a glob, `*` and `?` stay inside one segment of `server.tool`, and `**` crosses the dot. An `allow` glob that matches no tool fails the attempt.

A non-empty `allow` or `block` is part of the step fingerprint, and `mcp_config` always is. `pi` applies `allow`, `block` and `mcp_config`. `pi-cloud` applies `allow` and `block` to the MCP servers of the box's gateway, and refuses `mcp_config`. `claude` and `codex` take `mcp_config` when the agent sets `agent_profile="hermetic"`, and refuse `allow` and `block`. `durable`, `claude-cloud` and `codex-cloud` refuse all three. Every harness executor keeps server-qualified MCP tool names.

`mcp_config` is a flat server map on the agent, for example `{"note-store": {"url": "http://127.0.0.1:8767/mcp", "transport": "http"}}`. The wrapped `{"mcpServers": ...}` form is invalid.

## Traps

**A `pi` or `durable` brief needs no `--no-pager`.** The `pi` and `durable` harness executors set `GIT_PAGER=cat` in the agent's shell. The other harness executors leave the pager to the harness they run.

**An agent that writes a named file ends on a summary.** `schema_valid` reads only the last message. An agent that wrote its findings file, sent the JSON block, then sent a summary fails the gate although the file is valid. When the file is the deliverable, gate the file: a `command_exit` check that loads it and runs `ohflow.gates._validate_schema` against the step's schema. End the brief with "End with exactly one last message. That message holds the fenced JSON block, and no message follows it."

**Remove the `node_modules` link before the worktree.** On Windows the link is a junction, and `git worktree remove --force` follows it and empties the shared target, so every sibling worktree breaks. `ohflow.cli revert --run <run-dir>` takes the link out first, then removes each worktree and its branch through git, and checks the sentinel. It is one Python code path on Windows, macOS and Linux, and it reads `revert.json` in the run directory. A hand-rolled `git worktree remove` on Windows does not remove the junction first (`cmd /c rmdir <path>\node_modules` removes the link and not its target). Off Windows the link is a symbolic link. Repair is `npm ci` in the main repo.

**Take `min_passed` from a worktree, not the main checkout.** Tests that skip on a worktree checkout make a main-checkout baseline too high, and every agent fails a gate for a reason unrelated to its code.

## Handovers between steps

`consumes` names the earlier agent steps whose findings this agent reads. It is a subset of `depends_on`. Validation gives consumed producers a handover contract and gate. Read [step-handover](step-handover.md) for the questions, received context, cache integrity and role-specific answers.
