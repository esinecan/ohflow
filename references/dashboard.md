# Run dashboard and exit report

The contract that agents and people read. An ohflow run serves a live page while it executes and writes an exit report when it stops. Both come from one function, `live.read_out(run_dir, now)`, so the page, `exit-report.html` and `exit-report.md` cannot disagree.

Verbs that print this data: `ohflow status`, `ohflow watch`, `ohflow dashboard`, `ohflow report`. The run command and its flags live in [ohflow.md](ohflow.md) ("Run it"). Terms live in [../CONTEXT.md](../CONTEXT.md).

## Rules the reader keeps

- The dashboard reads. It writes `dashboard.json` into the run directory and nothing else.
- The run log is the truth. `workflow.json`, `run-log.jsonl`, `run.json`, `supervisor.pid`, the attempt directories and `result.json` feed the read-out. `live.py` tails `run-log.jsonl` itself and hands the records to `rundir.open_run`. `live.read_out` reads no derived file, `summary.json` included.
- The server is a daemon thread inside the supervisor process. It uses the standard library only, and the page works offline.

## The read-out

Schema `ohflow.read-out/2`. The example is abridged. Its text values are illustrative.

```json
{
  "schema": "ohflow.read-out/2",
  "generated": "2026-09-30T14:02:11Z",
  "mode": "live",
  "run": {
    "id": "r-20260930-135000-ab12cd34", "workflow": "g1-agent-error-auto-resume",
    "status": "running", "started": "2026-09-30T13:50:00Z", "elapsed_s": 731,
    "supervisor_alive": true, "last_event_age_s": 12, "last_activity_age_s": 3,
    "cooldown_until": null, "eta_s": 540, "eta_basis": "median 212 s over 3 steps",
    "counts": {"running": 2, "waiting": 3, "restarted": 1, "done": 4},
    "tokens": {"input": 812000, "output": 41000, "cache_read": 300000},
    "resume_command": null,
    "revert_command": "python3 -m ohflow.cli revert --run <run-dir>"
  },
  "phases": [
    {"coord": "02.fix", "name": "Fix", "state": "running", "good": 1, "total": 4,
     "max_parallel": 2, "policy": "quarantine", "auto_resumes": 0}
  ],
  "agents": [
    {"coord": "02.fix/02.parser", "kind": "agent", "role": "parser fixer",
     "harness_executor": "pi", "model": "<the light tier's pi model>",
     "display": {"state": "running", "reason": null, "restarted": true},
     "attempt": 2, "start_kind": "retry",
     "objective": "Make parse_row accept quoted commas",
     "objective_source": "objective",
     "latest_reasoning": {"text": "The failing test expects the quote stripped first.",
                          "at": "2026-09-30T14:02:08Z"},
     "limits": {"elapsed_s": 190, "execution_timeout_s": 5400,
                "llm_calls": 14, "max_iterations": 150,
                "max_iterations_effective": null, "max_iterations_enforced_by": null,
                "idle_s": 3, "stall_timeout_s": null},
     "running_tool": {"name": "bash", "summary": "npm test -- parser", "since_s": 3},
     "tool_calls": [
       {"at": "14:01:55", "name": "edit", "summary": "src/parser.ts",
        "duration_s": 0.2, "ok": true, "first_line": "Edited 1 block"}
     ],
     "attempts": [
       {"n": 1, "start_kind": "initial", "status": "failed", "wall_s": 402,
        "cause": "gate command_exit failed", "retry_decision": "retry 1 of 1 on gate:command_exit"},
       {"n": 2, "start_kind": "retry", "status": "running"}
     ],
     "tokens": {"input": 91000, "output": 5200},
     "evidence": {"attempt_dir": "phases/02.fix/02.parser/attempts/02"}}
  ],
  "events": [
    {"at": "14:01:02", "coord": "02.fix/02.parser",
     "text": "attempt 1 failed its gate (command_exit); retry 1 of 1 starts"}
  ]
}
```

| Block | Source |
|---|---|
| Workflow order, phase names, step roles, step objectives, limits | `workflow.json` |
| Run, phase and step statuses, attempts, gates, retries | `run-log.jsonl` |
| Supervisor alive | `supervisor.pid`, through `rundir.Run.supervisor_alive` |
| Tool calls, latest reasoning, live tokens | the attempt directory, through the harness executor module's `activity()` |
| Final tokens and cost | `result.json` per attempt |

## Display states

The dashboard derives one display state per card. The rules apply in this order.

| Display state | Condition | Reason text |
|---|---|---|
| `waiting` / hold | The run status is `held`: no run log, and `.ohflow-hold` names a live supervisor. | "held: waiting for go" |
| `waiting` / phase | The phase has no `phase_started`. | "waits for phase N" |
| `waiting` / cooldown | The phase started, the step has no `attempt_started`, and `run.cooldown_until` is later than now. | "waits for provider cooldown until HH:MM:SS" |
| `waiting` / slot | The phase started, the step has no `attempt_started`, and no cooldown is active. | "waits for a free slot (K of L busy)" |
| `running` | The newest attempt has `attempt_started` and no `attempt_finished`. | "attempt N, <start_kind>" |
| `waiting` / auto-resume | Engine status is `deferred`, the run is not paused, and the auto-resume budget is not spent. | "deferred: <error first line>" and "an auto-resume pass reruns it", joined by a semicolon |
| `waiting` / resume | Engine status is `deferred` and the run status is `paused`. | "paused: run `<resume_command>`" |
| `done` | Any other terminal status. | the engine status, plus "excluded" when a `work_excluded` names it |

- A step whose dependency failed never waits. The engine closes it as `skipped` at phase start.
- `cooldown_until` comes from the newest `attempt_finished` payload that carries it.
- A `cached` step counts as passed everywhere.
- `restarted` is true when `attempt >= 2` or `start_kind` is `retry`, `auto_resume` or `resume`.
- An attempt row carries its cause: the failed gate check names, or the `failure_class` and first error line. The `retry_decided.retry_decision` text follows it.
- Phase states: `waiting` (no `phase_started`), `running`, then the status of `phase_settled`. A `phase_resumed` event sets the phase back to `running` and adds one to `auto_resumes`.
- Run states before the run log exists: `held` (a live supervisor waits behind `.ohflow-hold`), `starting` (a live supervisor, no hold), the status `exit.json` records, else `not started`. `held` and `starting` are live: the page polls.
- A step with zero invocations opens the inspector in its planned view. `/api/workflow` gives each step a `plan` (`brief`, `tool_policy`, `harness_executor`, `model`, `write_scope`, `worktree`, `retry`, `consumes`, `depends_on`, `gate`, `limits`, `handover`) and each phase a `plan` (`on_step_failure`, `min_success`, `max_parallel`), read from `workflow.json`. The brief there is capped at 2,000 characters. The whole plan is the Plan view below. The invocation inspector is unchanged.

## Agent activity

A harness executor module's `activity(attempt_dir, ...)` returns the running tool, the last N tool calls (8 by default, 20 on request), the latest reasoning, the idle time and the live tokens.

- **pi harness executor.** Source: `attempts/NN/session/*.jsonl`. An assistant message holds `thinking`, `text` and `toolCall` items. A `toolResult` message pairs with its call by id. A call with no result is the running tool. The `usage` of each assistant message gives live tokens. Until the first assistant message exists, the card says "starting: no model reply yet". `logs/heartbeat.json` (`at`, `tool_calls`) gives idle time while the session file is empty.
- **cli harness executors** (claude, codex). `CliAgentRuntime` writes the event log that `activity()` reads.
- **Mechanical steps.** A `command`, `gate` or `merge` step shows its command string and the last 5 lines of its newest `logs/*.out.log`.

One tool call renders as: local time `HH:MM:SS`, tool name, a summary of at most 120 characters, duration, `ok` or `error`, and the first result line on expand. The summary is the command for `bash` (a leading `cd "<worktree>" &&` removed), the worktree-relative path for `read`, `ls`, `edit`, `write`, `grep` and `find`, and compact JSON of the arguments for any other tool.

Redaction runs before any text leaves `live.py`. It masks `sk-…`, `Bearer …`, `ghp_…`, `xox…-…` and the value of any variable whose name ends in `_KEY`, `_TOKEN` or `_SECRET`.

## Step objective

A card shows two lines that answer two questions.

**Assigned objective**: what the workflow told the agent. The first value found in this order wins, and the read-out names it in `objective_source`:

1. `Step.objective`: one line, at most 120 characters (`workflow.OBJECTIVE_MAX`).
2. `Step.note`.
3. The first plain sentence of `AgentSpec.brief`. The rule skips empty lines, Markdown headings, list items and indented lines. The card marks this guess "(from brief)".

`ohflow validate` prints a `WARNING:` line for an agent step with no `objective`. It never refuses the workflow. `Step.objective` is display data: it stays out of `fingerprint_input`, so adding one keeps the cache.

**Latest reasoning**: what the agent says it does now. It is the first sentence of the newest assistant `text` item, else of its `thinking` item. The card shows at most 200 characters and the age. The label never says "objective".

## Signals and ETA

| Signal | Amber | Red |
|---|---|---|
| Agent idle time | above half of `stall_timeout_s`, or 300 s when unset | above `stall_timeout_s`, or 900 s when unset |
| Agent wall time | above 75 % of `execution_timeout_s` | above 90 % |
| Agent model calls | above 75 % of `max_iterations` | above 90 % |
| Run activity | no run log event and no agent activity for 300 s | the same for 600 s, or `supervisor_alive` is false |

`limits.max_iterations` is the declared limit. `limits.max_iterations_effective` and `limits.max_iterations_enforced_by` come from the newest attempt's `result.json` (`settings.effective`), so they are null until it finishes. The cloud executors fill them ([harness executors](harness-executors.md#pi-cloud)).

The ETA is on `/api/workflow` and `/api/read-out` alike, as `run.eta_s` and `run.eta_basis`, computed by `live.eta`. Phases are barriers, so the ETA adds them in order. The current phase adds `ceil(waiting / max_parallel) × wave` plus the longest remaining time of its running steps. Each later phase adds `ceil(agents / max_parallel) × wave`. A wave lasts the median wall time of the run's own finished agent steps once one has finished. Before that, a run started with `--history` uses each step's p50 from `estimate.json`, and a run without one reads "unknown until one agent step finishes". The basis names the source. The page header shows `ETA ~N (basis)` while the run is live and `Predicted N · actual M` when it is over.

**Estimate fields.** When `estimate.json` exists, `/api/workflow` carries `run.estimate` (`wall_s` and `tokens` as `{p50, p80}`, `cost_usd`, `confidence`, `basis`), `run.actual` (`wall_s`, `tokens` recorded so far), and an `estimate` block on every phase and step (`wall_s`, `tokens`, `cost_usd`, `n`, `basis`, `confidence`). Without the file every one of them is null. The Workflow view's phase header shows `~N · p80 M · n samples`, a running invocation shows `expected N` beside its elapsed time, and the digest shows predicted against actual minutes and tokens. The estimate itself: [ohflow](ohflow.md#estimate-a-run).

**Token budget field.** `/api/workflow` carries `run.token_budget`, the run's `budget.json` ledger snapshot, or null for a run without a budget. Its fields: [ohflow](ohflow.md#token-budget).

**Pilot fields.** When `pilot.json` exists, `/api/workflow` carries `run.pilot`: `state` (`running`, the pilot run's final status, or `crashed`), `run_dir`, `units` (the pilot unit ids), `elapsed_s`, `problem`, `head` (the line after `PILOT <workflow>:`), and `projection` with one entry per unit path (`name`, `description`, `units`, `pilot_unit`, `status`, `unit` and `projected` as `{wall_s, tokens, cost_usd}`), `shared`, and `total` (`units`, `complete`, `missing`). Without the file it is null. The digest panel draws a pilot panel: the head line, a table of unit paths with the cost per unit and the projected cost, a shared-steps row and the projected total. While the run is held, the pilot panel and the estimate panel come first in the digest. The pilot itself: [ohflow](ohflow.md#pilot-a-run-over-many-units).

A failed fetch shows "lost contact with the run" and keeps the last answer on screen.

## Attention

`/api/workflow` carries `attention`, a list derived by `attention.py` from the same run-log replay and invocation rows the graph uses. One item per condition, in consequence order. A healthy run has none. An evidence packet, such as `tests/fixtures/dashboard-basis`, has none, because it is historical evidence. The page draws the list as a strip above the map and hides it when it is empty.

| `group` | `kind` | Condition |
|---|---|---|
| `intervention` | `failed_step` | the step's status is `failed`, `timeout` or `quarantined`, and `next.text` repeats the recorded `retry_decision` |
| `intervention` | `excluded` | a `work_excluded` event names the work |
| `intervention` | `killed_step` | a deferred step in a live run that `ohflow kill` ended, and `next.text` names `run --resume` |
| `intervention` | `budget_spent` | a deferred step in a live run that `attempts.may_start` refuses an auto-resume pass |
| `intervention` | `token_overshoot` | a `token_budget` event of kind `overshoot`: an attempt settled past the run's token budget |
| `intervention` | `paused_run`, `orphaned_run`, `crashed_run`, `interrupted_run` | the run status. `next.command` is `live.resume_command` when `run.json` records it, and a run the token budget or an attempt kill paused says so in `observed` |
| `recovering` | `deferred_cooldown` | a deferred step with a pass left while `cooldown_until` is in the future |
| `recovering` | `deferred_auto_resume` | a deferred step with a pass left and no cooldown |
| `recovering` | `retry_running` | the step's latest invocation is running and its `start_kind` is `retry` or `auto_resume` |
| `signal` | `idle_red`, `idle_amber` | the running invocation's `health.idle_signal` |
| `signal` | `deadline` | a running invocation past 75 % of its `execution_timeout_s` |
| `signal` | `checks_over_agent` | a step whose last attempt's `command_exit` checks (`duration_s`) ran longer than its agent: the attempt's `wall_seconds` less those checks. A cached step and a step with no agent raise none |

Each item: `coord`, `attempt`, `step_id`, `role`, `phase`, `observed` (`text`, `ts`), `expected`, `impact` (`phase`, `phase_name`, `dependants` from `depends_on`, `text`), `next` (`command` or null, `text`) and `evidence` (`id` of the invocation, `coord`, `attempt`, `event`, `line` in `run-log.jsonl`, `ts`). A paused run is one item that owns the resume command. Its deferred steps are its impact, not an item each.

## Lanes

Each phase on `/api/workflow` carries `lanes`: `running` (steps whose `display` is `running`), `waiting_by` (counts by `waiting_on`: `hold`, `slot`, `cooldown`, `auto_resume`, `resume`, `phase`, `dependency`, `stopped`), `waiting_words` (`live.waiting_words`), `max_parallel`, and `text`, the line the page shows above the graph and in the Workflow view's phase header: "2 running · 1 for a free slot (2 of 2 busy) · 3 for their phase". A step that waits for a dependency names it in its own `reason`. The graph draws the `depends_on` edges that touch the selected invocation's step stronger, and the inspector's details list "depends on X · feeds Y".

Two step rules `/api/workflow` shares with the read-out: a pending step waits for `cooldown` while `cooldown_until` is in the future, and a deferred step in a live run waits for `auto_resume` only while a pass is left and no attempt kill ended it. Otherwise it is `done`, and its `reason` names the budget or the kill.

## Peek

The page keeps one row per running invocation under the graph: role and attempt, elapsed time, the running tool, the idle age and its signal, the last 5 transcript lines, and the command the agent waits on with its last 20 output lines (`activity.command_output`, from the tool-output contract). While that call is open, the health note says the stall clock waits for it. The inspector's overview lists every call of the attempt with its output tail (`/api/evidence` `tool_output`), and opens the call that was open when the attempt stopped (`open_tool_call`). The first look asks `/api/transcript?coord=C&attempt=N&tail=5`, and every later poll continues from the returned `next_cursor`, so the tail costs one page per tick. A line is the record's tool call, else its text, else its reasoning, with its UTC time and role. Clicking a row selects the invocation and opens its transcript. The panel is hidden when nothing runs, and an offline report shows the rows without lines.

`tail=N` on `/api/transcript` returns the last N complete records with their real ids, sizes the page N, ignores `limit` and `cursor`, and hands back the cursor the top-down pager would hold at the end. `tail` must be between 1 and 400.

## Digest

`/api/workflow` carries `digest`: one entry per `attempt_finished`, `retry_decided` (a decision not to retry a passed attempt is left out), `work_excluded`, `phase_settled` and `run_finished`, in run-log order. Fields: `ts`, `kind`, `coord`, `attempt`, `id` (the invocation, when one is recorded), `text`, `tone`, `tokens`, `wall_s`, `handover_first_line`, `evidence` (`path`, `line`). An `attempt_finished` reads as one sentence, its parts joined by semicolons: "Implement attempt 2 passed in 4 m 12 s, 31 k tokens", "gate command_exit ok", "handover: <first prose line>". Tokens come from the attempt's `result.json`. The handover line comes through `handover.recorded`, so a file whose bytes changed since the finish is not quoted. The evidence packet's digest takes its numbers from `case.json` and has no handover. The page lists the entries under the retry story, newest first, each linking to its invocation.

## Plan view

The view button `Plan` opens the third view. It shows the declared plan of the run: what will run, in which order, with which limits. A run started with `--hold` opens on it. Every other run opens on Start order. It stays available for the whole run and in `exit-report.html`.

The view has three parts.

- A summary strip of six tiles:
  - phases and steps by kind
  - agent steps per harness executor, model and effort
  - the forecast (p50, p80, tokens, cost, confidence, samples) or the reason there is none
  - the timeout bound
  - parallelism, worktrees, base branch, auto-resume and backoff
  - gate checks, retries, handover contracts and schemas
- A collapsible phase tree. One `details` line per phase: name, state chip, step kinds and waves, the failure policy, and the phase forecast. Open, it shows the barrier sentence and one table row per step: kind, role and step objective, harness executor and model, agent tool policy, write scope, worktree, dependencies and consumed handovers, limits, retry, gate check count, forecast. A gate step reads `gate only, no agent` where the model goes. A step the estimate calls `mechanical` or `cached` shows that word as its forecast. A plan of at most 8 steps opens every phase, and a longer plan opens phase 1. The search box filters the rows by id, role, objective, model, harness executor, worktree, write scope, command and brief text. A search opens every phase that has a match. `Expand all phases` and `Collapse all` set every phase at once.
- A drawer per step, opened by the row's `Open` button, with seven tabs: `Brief` (the full text, under the artifact cap of 32,000 characters), `Position` (the block `coords.render_position` writes to `position.md`, rendered with an empty run state, so it is the hold-time preview), `Gate` (every check in the words its `describe` function uses, with its name and arguments), `Handover`, `Schema`, `Command` (the shell command, or the `git merge --no-ff` a merge step runs), `Limits` (timeouts, model calls, the command time cap, retry, agent profile, box, unit, agent tool policy, worktree path and branch, write scope, dependencies, objective). A gate step opens on `Gate`, and its `Brief` and `Command` tabs say it starts no agent and has no command.

A held run shows a banner above the strip: held since when, the `go` command, and that an edit to the module while held is what runs. The `Inspect the plan` button of the Workflow view opens the step's drawer in the Plan view and keeps the planned inspector as it is. On an evidence packet's page, and on a report that embeds no plan, the button opens the planned inspector in place, because there is no plan to show.

**`/api/plan`.** A `GET` with no query, fetched once when the view opens and never polled. It answers `{schema: "ohflow.plan/1", generated, run, totals, estimate, worktrees, phases, diagnostics}`.

| Block | Fields |
|---|---|
| `run` | `id`, `workflow`, `status`, `repo`, `base_branch`, `max_parallel`, `auto_resume`, `transient_backoff_s`, `baseline_cmd`, `held_since` and `hold_pid` from `.ohflow-hold`, `go_command`, `dashboard_url` from `dashboard.json`, `plan_stamp` |
| `totals` | `phases`, `steps`, `kinds` (`agent`, `command`, `merge`, `gate`), `by_model` (`harness_executor`, `model`, `effort`, `n` per agent group), `gate_checks`, `gated_steps`, `retry_steps`, `handovers`, `schemas`, `worktrees`, `timeout_bound_s` (waves × longest execution timeout per phase, phases added) |
| `estimate` | `wall_s` and `tokens` as `{p50, p80}`, `cost_usd`, `n` (the history's samples), `basis`, `confidence`, `generated`, `history`, from `estimate.json`. Every field is null without the file |
| `worktrees` | `name`, `path`, `branch`, `base` per declared worktree |
| `phases[]` | `index`, `coord`, `name`, `max_parallel` (the effective limit), `declared_max_parallel` (null means the workflow default), `min_success`, `on_step_failure`, `waves`, `worst_timeout_s`, `timeout_bound_s`, `estimate`, `steps` |
| `steps[]` | `coord`, `id`, `kind`, `role`, `objective`, `note`, `harness_executor`, `model`, `effort` (`params.effort`, else `extra_body.thinking.reasoning_effort`), `profile`, `box`, `tools`, `max_iterations`, `command_time_cap_s`, `worktree`, `unit`, `write_scope`, `depends_on`, `consumes`, `execution_timeout_s`, `stall_timeout_s`, `retry`, `gate` (`name`, `args`, `text` per check), `handover`, `schema`, `command`, `shell`, `merge_branch`, `merge_message`, `brief`, `position`, `estimate` |

Every string passes the same redaction as the other routes and a cap of 32,000 characters. `totals`, `worktrees`, `phases[]` and `steps[]` come from `workflow.json` alone and `estimate` from `estimate.json`, so a run-log line changes none of them. The `run` block follows the run: `status` is the status the run log replays to, `held_since` and `hold_pid` are null once `go` removes `.ohflow-hold`, `dashboard_url` comes from `dashboard.json`, and `plan_stamp` changes when `workflow.json` is written again. An evidence packet answers 404. A run with a run log and no `workflow.json` answers the phases the run log names, no position blocks, and a diagnostic.

`/api/workflow` carries `run.plan_stamp`, the `mtime_ns` and `size` of `workflow.json`. The page fetches `/api/plan` again when the stamp changes between two polls, which is how the rewrite after `go` reaches the view. The estimate is written before the hold wait and again after the reload, so the held page shows a forecast.

`exit-report.html` embeds the plan payload as `plan` beside the read-out, with the read-out's final run status in `run.status`. The Plan view opens from disk for a finished run, but `exit.json` and `exit-report.md` do not carry it.

## Page

- Agents appear in workflow order under their phase.
- A running card is open. A done or waiting card is one line.
- A click opens or closes a card, and open cards stay open across refreshes.
- The page follows `prefers-color-scheme`. Each display state has one colour and a text label.

## Server

- It binds to `127.0.0.1` on port `0` by default, so two runs never collide. `--dashboard-port N` fixes the port.
- It writes `dashboard.json` (`url`, `port`, `pid`, `started`, `supervisor`) into the run directory.
- The page polls `/api/workflow` every 2 s. That route builds its own view in `dashboard_data.py`, not from the read-out. The reader caches each file by `(mtime, size)`.
- The browser does not open unless `--open-dashboard` is set.
- A detached run waits for the dashboard before it prints line one. The wait and the line are in [ohflow](ohflow.md#run-it).

| Path (`GET` only) | Returns |
|---|---|
| `/` | the page |
| `/api/read-out` | the run state read-out as JSON |
| `/api/agent?coord=C&attempt=N&limit=20` | the activity block of one attempt |
| `/api/workflow` | the graph truth the page polls: run (with `plan_stamp`), phases with `lanes`, steps, invocations, edges, segments, events, `attention`, `digest` |
| `/api/plan` | the declared plan, whole, for the Plan view: run, totals, estimate, worktrees, phases with their steps. It is fetched once and never polled, and answers 404 for an evidence packet |
| `/api/transcript?coord=C&attempt=N&limit=150&cursor=…` or `&tail=5` | one attempt's transcript, paged from the top, or its last N records |
| `/api/evidence?coord=C&attempt=N[&id=…]` | one attempt's gate, final message, events and whitelisted files |

Every other path answers 404. The server never serves a file by name, so it cannot expose `attempts/NN/pi-agent/auth.json`. It has no `POST` and no token: any local process can read the run directory already.

## Exit report

A run that was estimated adds a "Predicted vs actual" table: per phase and for the run, the predicted p50 and p80 minutes and tokens beside what the run recorded. A run without `estimate.json` has no such table.

Every exit path that runs code writes three files into the run directory.

| File | Reader | Content |
|---|---|---|
| `exit.json` | tools | `status`, `at`, `error`, `traceback_tail` (last 20 lines), `run_id`, `verdict` (the verdict sentence), `reports` (the names of the two report files) |
| `exit-report.md` | agents, forum posts, the terminal | the exit report as Markdown |
| `exit-report.html` | people | the page template with the final read-out and the plan payload embedded. It opens from disk, Plan view included |

| Exit path | Written by | `exit.json` status |
|---|---|---|
| All phases done | `supervisor.run_workflow` `finally` | `finished` |
| A phase aborted the run | `supervisor.run_workflow` `finally` | `failed` |
| A transient fault paused the run | `supervisor.run_workflow` `finally` | `paused` |
| `PreflightError` or another exception | `supervisor.run_workflow` `except` and `finally` | `crashed` |
| Ctrl+C | `supervisor.run_workflow` `except` and `finally` | `interrupted` |
| Hard kill, machine restart | `ohflow report --run DIR`, later | `orphaned` |

The crash path writes no run log event. `run_finished` keeps `finished`, `failed` and `paused`, so a crashed run that has a run log stays resumable. A run that crashed in preflight has no run log, and `--resume` refuses it. A later `--resume` replaces the exit report when it stops.

The exit report reads in this order:

1. Verdict, one sentence: "Run r-… finished: 5 of 6 agents passed, 1 quarantined, 2 restarts, 41 min, 1.2 M tokens."
2. What needs a person: quarantined branches, deferred and excluded steps, the exact `--resume` command, the `revert --run <run-dir>` command.
3. Phases: state, good/total, auto-resumes.
4. Agents: final status, attempts with causes, wall time, tokens, gate result.
5. Failed attempts: cause, latest reasoning, last 8 tool calls.
6. Timeline: one bar per attempt, inline SVG in `exit-report.html` only.
7. Evidence: paths to `run-log.jsonl`, `summary.json` and each attempt directory.
8. Run log health: any `run_log_recovered` event.

`summary.json` stays as it is. `exit_report.build` reads it for the verdict numbers when it describes this stop: the same final status at the same finish time. Otherwise it computes the same numbers from the read-out built from the run log.

## Verbs

| Verb | Effect |
|---|---|
| `ohflow run` | starts the dashboard, runs the workflow, writes the exit report on every exit path |
| `ohflow run --no-dashboard` | no server, but the exit report is still written |
| `ohflow run --dry-run` | no dashboard and no exit report |
| `ohflow run --hold` | writes the plan and `.ohflow-hold`, starts the dashboard, passes preflight, then waits for `go`. The page reads `held` and opens on the Plan view |
| `ohflow go --run DIR [--predictions FILE]` | writes FILE to `predictions.md` when given, then `<run-dir>/go`. It exits 1 when no hold exists, its supervisor is dead, or `predictions.md` already holds predictions |
| `ohflow dashboard --run DIR [--port N] [--open]` | serves the page for a finished, orphaned or detached run. When the run's own dashboard still serves, it prints its URL and starts nothing |
| `ohflow report --run DIR` | writes the three exit-report files from the run directory |
| `ohflow run --history DIR` | writes `estimate.json` before the first agent starts, and the page, the exit report and the retro draft read it |
| `ohflow status --watch` | the terminal view: redraws the status sentence every 3 s, prints no ANSI codes when stdout is not a terminal |
| `ohflow watch --run DIR` | the agent view: prints only what changed since its last call |
