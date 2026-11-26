# Contributing to ohflow

## What ohflow is

ohflow is a Python workflow engine for agent work. You define ordered phases of steps, and the engine starts agents through their harnesses, runs commands, checks results and merges contributions. A campaign coordinates these workflows to deliver a larger design through accepted milestones.

An agent invocation is a nondeterministic unit of work. Its brief, tool policy, work area, write scope, limits and output contract state what it is meant to do; checks determine whether the tested conditions hold. A final message reports a claim, while the artifact and check records supply evidence. Steps can pass selected findings through explicit handovers.

[SKILL.md](SKILL.md) is the agent-facing entry point. [Workflow patterns](references/workflow-patterns.md) help choose how to divide the work; [the guided glossary map](docs/glossary-map.html) teaches the terms through one example. A new operator starts with [the README](README.md) and [the quickstart](references/quickstart.md). This page is for people who change the engine. Workflow construction starts from an agreed brief or specification; developing that agreement belongs to the separate intention-alignment method.

## How a run works

ohflow runs coding agents as gated steps. Its program is the Python package `ohflow` in `scripts/`. A workflow holds phases, and a phase holds steps of kind `agent`, `command`, `gate` or `merge`. A workflow works on one or more workspaces: git repositories, and folders that ohflow turns into one for work that is not code. Each agent step runs in its own git worktree of one workspace, started through one harness executor: `pi`, `claude`, `codex`, `durable`, `pi-cloud`, `claude-cloud` or `codex-cloud`. The step names it, because ohflow has no default harness executor. Tool policy is the gate. An agent calls only the tools it was built with. A gate checks the agent's artifact, because the agent's final message is a claim. Every run leaves a run log. A run also serves a live dashboard, unless it is a dry run, a roll-call test case or a run with `--no-dashboard`. Every run except a dry run writes an exit report.

Agents read [SKILL.md](SKILL.md). It routes by task and lists the verbs. Terms are in [CONTEXT.md](CONTEXT.md). [docs/glossary.md](docs/glossary.md) maps each term to its code and explains how the terms relate, with the m0 milestone as a worked example. `python3 docs/glossary_sync.py --write` copies the CONTEXT.md definitions into the glossary and its map; `tests/check_docs.py` fails when they disagree or when the public vocabulary surface changed without review. Facts live in [references/](references/).

The [GitHub issues of `esinecan/ohflow`](https://github.com/esinecan/ohflow/issues) track the open work on ohflow.

## Module map

Each deep module hides one fact behind a small interface. Where a caller still goes around the interface, the bullet says so.

- `worktree.py` hides how a worktree and its repository come and go. Interface: `create(repo, spec)`, `ensure_workspace(space)`, which creates the repository of an owned workspace, `workspace_faults(space)`, `write_revert_plan` and `revert(plan)`. `Workflow.all_workspaces()` and `Workflow.workspace_of(worktree)` in `workflow.py` resolve the workspace of a step; the engine, preflight and the position block ask them.
- `handover.py` hides the question contract and validated attempt-file reads. `Step.consumes` selects producer findings; `Run.handover(coord)` reads recorded evidence.
- `attention.py` hides the rules that turn a run's state into the dashboard's attention strip. Interface: `derive(source, now, steps, invocations)`, one item per condition, grouped `intervention`, `recovering`, `signal`. Only `dashboard_data.workflow_data` calls it.
- `harness_executors.py` hides which module owns each harness executor. Interface: `harness_executor_module(name)` answers `agent_errors`, `usage`, `activity`, `resume_target`, `reattach_target`, `transcript` and `make_harness_executor`. The engine calls `harness_executor_module(harness_executor).resume_target` itself for `carry_context`. `HARNESS_EXECUTOR_FIX` in `preflight.py` also names every harness executor.
- `cli_harness_executor.CliAgentRuntime` hides the child process of a CLI harness executor. Interface: start, event log, heartbeat, stall deadline and kill.
- `rundir.open_run(path)` hides the layout of a run directory. Interface: `run.steps()`, `run.attempts(coord)`, `run.latest_attempt(coord)`, `run.usage(attempt)`, `run.summary()`. `Run.write_summary` writes `summary.json` at run end and after a hard kill. These readers still parse run files directly: `live.py`, `exit_report.py`, `retrodraft.py`, `table.py`, `runstatus.dashboard_url`, `cli transcript`, `rollcall.py` and `campaign.py`.
- `attempt_record` hides what `result.json` holds. Interface: `write` and the token vocabulary `TOKEN_KEYS`.
- `live.read_out(run_dir, now)` hides the parsing of run log, logs and sessions. Interface: one JSON document that the dashboard and both exit reports show.
- `runstatus.sentence` hides how a run is described. Interface: one status sentence and the `facts` a watcher compares.
- `supervisor.run_workflow` hides the start of a run. Interface: one function that reserves the run directory, starts the dashboard, runs the engine and writes the exit report in its `finally` block.
- `proc.spawn_managed` hides the Windows kill-on-close job object. Interface: start a child, then end its whole tree. Every harness executor starts its child through it, with the environment from `proc.agent_env`.
- `exec` hides shell choice and log capture. Interface: run a command and get its exit code, log paths and a 4 KB tail.
- `budget.Ledger` hides the run's token budget. Interface: `admit`, `observe`, `settle` and `release` per agent attempt, and `snapshot`, which `budget.json` holds. The engine calls it around `_run_agent`.
- `retry.should_retry` hides the retry rule. Interface: a pure function that returns a decision and its reason.
- `failure.classify` hides the rate-limit signatures. Interface: error text in, `transient` or `structural` out.

The engine, the run log and the workflow model sit beside these. The run log is the truth about a run.

Smaller modules:

- `structured.py` parses an agent's fenced JSON. Five runner modules import it: `pi_runner`, `claude_runner`, `codex_runner`, `durable_runner` and `pi_cloud_runner`. A `command` step's JSON goes through a separate copy, `_fenced_json` in `engine.py`.
- `estimate.py` forecasts a workflow from the history of finished runs: `Prior.from_history` reads every `summary.json` up to four levels under the history roots, `estimate_workflow` rolls steps into phases (the barrier rule) and the run (times the retry multiplier), `render_text` prints the block. `supervisor.run_workflow` writes `estimate.json`; `live.eta`, `dashboard_data`, `exit_report` and `retrodraft` read it back.
- `pilot.py` prices each unit path before a full run: `pick` chooses the smallest unit of each unit path, `pilot_workflow` builds the pilot workflow on `-pilot` worktrees, `measure` reads the pilot's `summary.json`, and `project` multiplies each unit path's measured cost by its unit count. `supervisor.run_workflow` runs the pilot in `<run-dir>/pilot` and writes `pilot.json`; `cli` (`estimate`, `status`, `go`), `watch` and `dashboard_data` read it back.
- `preflight.py` holds the check framework, the Git Bash check, the workflow checks, the harness executor checks and the fix hints in `HARNESS_EXECUTOR_FIX`. Each harness executor's own check is its `HarnessExecutor.preflight()`, which calls the runner module's `preflight()`. The engine runs `workflow_problems` at the start of every fresh run. The `preflight` verb runs every check, and a roll-call test case runs only the harness executor checks.
- `report.py` writes `board.md`. The engine calls it after each run log event. No code reads `board.md`.
- `summary_audit.py` checks each `summary.json` against `references/summary.schema.json`. It does work only when the test suite sets `OHFLOW_TEST_SUMMARY_SCHEMA`.
- `watch.py` holds `ohflow watch` and `ohflow campaign watch`.
- `construct.py` holds `ohflow construct`. `read_bundle` parses a bundle of milestone specs and refuses it with every fault it finds, `executor_for` derives a step's harness executor from its box and harness, and `write_campaign` writes the charter, `campaign.py` and each milestone's spec, `milestone.json`, `workflow.py` and briefs. [construct](references/construct.md) is the bundle format.
- `patterns.py` builds a constructed milestone's workflow from its `milestone.json`, in one of six workflow patterns. Each constructed `workflow.py` calls its `build_milestone`, so a judge's edit to `milestone.json` or a brief reaches the next round.
- `campaign_history.py` holds `ohflow campaign history`. It joins the campaign log, each judge handover's lead paragraph and each packet's acceptance checks. It reads files only.
- `paths.py` renders a path for each destination. Twenty-seven modules import it.
- `settings.py` reads the operator settings.
- `tiers.py` resolves a model tier, `heavy` or `light`, to the model the settings map it to on a harness executor. `workflow.validate`, `harness_executor.spec_json`, `estimate.estimate_workflow`, `validate -v`, `patterns.model_config` and `sessions.open_session` call it. `construct.read_bundle` checks each tier name against its `TIERS`. Nothing else reads a tier.
- `durable_host.py` installs the durable host from `host/` on the machine that runs a `durable` step, this one for box `local` or a box over ssh, as `~/.pi-durable/ohflow-host/<version>/`. `host/` is a Node package (Node 22.19 or newer): `ohflow-step.mjs` opens a pi-durable `Harness` over the step's `session.sqlite`, and `install.cjs` is the installer `durable_host.py` feeds to `node` on stdin.

## Operator settings

`ohflow.settings.json` at the skill root names every setting with the value a new operator starts with. Your own values go in `ohflow.settings.local.json` beside it, which git ignores and which is merged over the base file. Your house rules for agents go in `references/local.md`, which git also ignores. `OHFLOW_SETTINGS` names another local file. [examples/setups/](examples/setups/) holds one operator's whole setup to copy from, and [the boundary](docs/release/boundary.md) lists each setting and what reads it.

The suite reads `tests/operator.settings.json` instead of your local file, so your values never change a result. `tests/test_boundary_01_no_local_values.py` fails when a shipped file holds a real home path or a token from your private list at `~/.config/ohflow/leak-tokens.txt`.

## Running the suite

The suite uses `unittest` from the standard library. It runs from a fresh clone on Windows and Linux and needs no network and no git identity. Every command in this section runs from the root of the ohflow clone.

**A change runs the tests it reaches.** `run_tests.py --changed [BASE]` selects test files from the files changed since `BASE`, committed or not, and runs them after `tests/check_docs.py`. `BASE` defaults to the merge base of `HEAD` and `main`. A gate passes the step's base commit as `--changed {base}`, as [ohflow](references/ohflow.md#gate-checks) states.

```bash
python3 tests/run_tests.py --changed
python3 tests/run_tests.py --changed 88beb7d
```

| Changed file | Test files it runs |
|---|---|
| `tests/test_*.py` | itself |
| `scripts/ohflow/<module>.py` | the test files that import `ohflow.<module>` directly, and the test files whose name holds `<module>` |
| `tests/support.py`, `tests/verb_support.py`, `tests/run_tests.py`, `tests/summary_schema_audit.py` | that file's own tests (`OWN_TESTS` in `run_tests.py`) and the smoke list `SMOKE` |
| another file under `tests/`: a `*_support.py` helper, a fake, a fixture | the test files that name it, and `SMOKE` |
| a Markdown file outside `scripts/` | the test files that name its path from the skill root: the string `references/x.md` or the parts `"references" / "x.md"`; a file at the root only after `ROOT /` or `parents[1] /` |
| any other file | the test files that name it |

Imports count one level deep, because `tests/support.py` imports `ohflow.workflow` and `ohflow.cli`, and a transitive map would select nearly every file. The output names every selected file with its reasons and its estimated seconds from `tests/file_seconds.json`, and its last line gives the selection's runtime. A selection estimated past 300 s runs the changed test files, then the direct part (direct imports, own tests, files that name the change) cheapest first up to 300 s, and names each file it leaves to CI.

**The full suite runs in CI only.** The GitHub Actions workflow `.github/workflows/ci.yml` runs on each push to `main`, on each pull request into `main` and on a manual dispatch. It skips a push or pull request that changes only Markdown files. It runs on `ubuntu-latest` and `windows-latest`, with Python 3.12 and Node 22. Each runner runs the Worker's node tests, then the suite in three shards, then the real-process tests. Shards 2 and 3 and the real-process tests also run after an earlier step fails. No stage, gate, acceptance check or agent runs it, so nobody waits for it. On Linux (WSL Ubuntu) a full pass takes about five minutes (1538 tests, 274 s on 2026-11-21). A `windows-latest` runner takes about twenty minutes (1538 tests, 1225 s on 2026-11-21), and a Windows desktop about 34 minutes (1600 tests, 2018 s on 2026-11-23). When CI fails, run the failing test files by name. For a Markdown-only change, `--changed` runs `check_docs.py` and the test files that name each changed Markdown file's path. These commands run the CI steps by hand:

```bash
node --test worker/test/*.test.mjs
python3 tests/run_tests.py --shard 1/3
python3 tests/run_tests.py --shard 2/3
python3 tests/run_tests.py --shard 3/3
python3 tests/run_tests.py --real-process
```

Deterministic. `-k` takes one substring of a test name:

```bash
python3 tests/run_tests.py -k rollcall
```

One test may run 300 s, and 1800 s under `--e2e`, whose live matrix is one test of a few minutes. A test past that limit ends the run with exit code 1, and the output names the test and prints the stack of every thread. The run ends every child process it still has first, so a caller that reads the output through a pipe is released. `--test-timeout SECONDS` sets the limit and wins over both defaults, and `--test-timeout 0` turns it off.

`--e2e` adds the live smoke matrix. It needs `ZAI_CODING_CN_API_KEY` and the Claude and Codex CLIs logged in. See "Testing with live agents".

**Add a regression test.** Name the file `tests/test_defect_NN_<what>.py` and put one defect in it. Take the helpers from `tests/support.py`: `TempCase`, `FakeHarnessExecutor`, `AgentScript`, `git_repo`, `simple_workflow`, `agent_step`, `stub_preflight`, `quiet`. Make the test fail first, then fix the code. Real provider errors go in `tests/fixtures/real_errors.py`. A test asserts on document text only where a program reads that text, such as a template, the synced glossary or a count `check_docs.py` compares.

## Testing with live agents

`ohflow rollcall` is the one live harness. A roll call is a trivial task: each agent writes who it is, commits that file and ends with a JSON block in its final message. The harness executor records what its harness announced. The `rollcall_matches` check then fails the report on any of three faults:

- it names a tool the harness never announced;
- it names an MCP server the harness never announced;
- its `harness_executor` field is not the step's harness executor.

Codex announces no tool list, so a codex agent's tools go unchecked.

**What each harness executor needs before a live test case.** `ohflow preflight` checks each one and names the fix.

- `pi`: the pi CLI, `npm install -g @earendil-works/pi-coding-agent`, and the provider key of the preset in its variable (`ZAI_CODING_CN_API_KEY` for the default preset).
- `claude`: the Claude CLI on PATH and `claude auth login`.
- `codex`: the Codex CLI on PATH and its login.
- `durable`: `durable.box` in `ohflow.settings.local.json`, `local` or a box's ssh host alias; Node 22.19 or newer on that machine, reached by `ssh <box>` when it is not `local`. ohflow installs the host from `host/` there at the first step.
- `pi-cloud`: `PI_CLOUD_TOKEN`, and `pi_cloud.url` in `ohflow.settings.local.json`.
- `claude-cloud`: the same as `pi-cloud`, and the Worker secret `CLAUDE_CODE_OAUTH_TOKEN`.
- `codex-cloud`: the same as `pi-cloud`, and a Codex login on the Worker from `node worker/scripts/codex-login.mjs`.

A **test case** is one test scenario on some harness executors at some scale. A **test matrix** is a named table of test cases. Test cases run one after another. Run the verb from `scripts`.

### Test scenarios

Each test scenario is one pattern of the roll-call workflow, chosen with the first word of a test case. The aliases `r0`, `r1` and `r2` mean `fanout`, `relay` and `merge`.

| Scenario | What it proves | Command |
|---|---|---|
| `single` | one gated agent finishes on one harness executor | `rollcall --cases single:pi` |
| `fanout` | one agent per harness executor, each in its own worktree | `rollcall --cases fanout:pi,claude` |
| `relay` | agents in series hand one shared file on | `rollcall --cases relay:pi,claude` |
| `merge` | fanout, then one merge per agent, then a consolidator writes a table | `rollcall --cases merge:pi,claude:2:consolidator=codex` |
| `retry` | a failed gate retries; the retry reads the hidden text of the failed `file_contains` check in its position block | `rollcall --cases retry:pi` |
| `review` | an agent on one harness executor, then a reviewer on another ends with a `VERDICT:` line | `rollcall --cases review:pi,claude` |
| `campaign` | a judge revises a bad brief, the milestone then passes, and the integration branch moves past its base | `rollcall --cases campaign:pi` |
| `silent` | an agent survives one command that prints nothing for twice the stall limit (45 s unless `stall_timeout_s` is given), then copies the line it printed | `rollcall --cases silent:codex` |

The `campaign` test case starts no plain run. It drives `CampaignController` over a one-milestone campaign. It passes only when the judge decisions are REVISE, then PASS.

Every command in this section starts with `cd scripts && PYTHONPATH=. python3 -m ohflow.cli`. A test case has the form `scenario:harness-executors[:count][:option]`. The options are `consolidator`, `reviewer`, `judge` (each names a harness executor), the agent profile `agent_profile=hermetic` (`claude` and `codex` only) and `carry_context`.

### Execution presets

An execution preset is the harness executor, its model configuration and its cost basis. A test case first builds its workflow. A workflow that does not build gives `FAIL`. Then each harness executor's own preflight runs. A harness executor that fails it, or whose `api_key_env` is unset, gives `SKIP` and not `FAIL`.

| Harness executor | Default model | Preflight needs | Cost basis |
|---|---|---|---|
| `pi` | `zai/glm-5.3-flash`, `thinking=low` | the pi CLI, `ZAI_CODING_CN_API_KEY` | Z.AI flat rate |
| `claude` | `claude-haiku-4-5-20251001` | the Claude CLI, logged in | Claude subscription; `total_cost_usd` is notional |
| `codex` | `gpt-5.6-luna`, `reasoning_effort=low` | the Codex CLI, logged in | ChatGPT quota |
| `durable` | `zai/glm-5.3-flash`, `thinking=low` | `durable.box` set; Node 22.19 or newer on this machine for `local`, else `ssh <box>` reaches the box and its node is that new | Z.AI key on the box |
| `pi-cloud` | `zai/glm-5.3-flash`, `thinking=low` | `PI_CLOUD_TOKEN`, and the Worker at `pi_cloud.url` answering | Z.AI key in the Worker |
| `claude-cloud` | `claude-haiku-4-5-20251001` | the same as `pi-cloud` | Claude subscription login in the Worker |
| `codex-cloud` | `gpt-5.6-luna` | the same as `pi-cloud`, and the Worker holds a Codex login | ChatGPT login in the Worker |

A pi agent also needs Git Bash. A test case's preflight does not check it, so a missing Git Bash never gives `SKIP`. The `preflight` verb checks it. Harness executor facts and launch rules: [harness executors](references/harness-executors.md).

A `durable` test case on an ssh box also needs `--repo` with a remote: the executor pushes the step's start commit to the repository's own `origin` and the box pushes its answer back to the same branch, and `make_repo` builds its throwaway repository with no remote. A `pi-cloud`, `claude-cloud` or `codex-cloud` test case needs the same, and the remote must be one the Worker may clone: a private repo of the Worker's `GIT_OWNER` that its `GITHUB_TOKEN` reaches.

### Scales

- **`count`** is the number of agents per harness executor. `fanout:pi:3` starts three agents on `pi`.
- **Parallelism** is the workflow argument `max_parallel`. A matrix run keeps its default of 3.
- **Execution and stall limits** are the workflow arguments `execution_timeout_s` (default 600) and `stall_timeout_s`. The stall limit defaults per harness executor: 600 s for `codex`, `claude-cloud` and `codex-cloud`, 180 s for `pi`, `claude`, `durable` and `pi-cloud`. The argument replaces that table for every harness executor that takes a limit.

Pass workflow arguments to `validate` and `run` with `--workflow ohflow.workflows.rollcall --args repo=<repo> --args scenario=<scenario>`.

### Matrices

`--matrix` takes a name. The default is `quick`. `--list` prints every test case of every matrix.

| Matrix | Test cases | Contents | Wall time |
|---|---|---|---|
| `smoke` | 3 | `single` on `pi`, `claude` and `codex` | `single pi` 31 s (5.4 k tokens, m5 acceptance run) |
| `quick` | 8 | `single`, `fanout`, `relay` and `merge` on `pi`, `claude`, `codex`; `retry` on `pi`; `review` on `pi` then `claude` | under 24 m 27 s (1466.5 s: the sum of these eight test cases' times and two more in the first full matrix run on 2026-10-01) |
| `full` | 13 | `quick`, plus `fanout` on `pi` with `count=3`, `campaign` on `pi`, `single` hermetic on `claude` and on `codex`, `retry` on `claude` with `carry_context` | under 32 m 23 s (1942.7 s for these thirteen test cases and two more, same run) |
| `liveness` | 3 | `silent` on `pi`, `claude`, `codex` | under 14 m 19 s (the sum of these three test cases and two more on 2026-10-10) |

Cost: `pi` runs on the Z.AI flat rate. `claude` and `codex` use their subscription quotas, so every matrix spends them. `run_tests.py --e2e` runs `smoke`.

Live. This runs the smoke matrix:

```bash
cd scripts && PYTHONPATH=. python3 -m ohflow.cli rollcall --matrix smoke
```

Deterministic. These check every workflow without starting an agent:

```bash
cd scripts && PYTHONPATH=. python3 -m ohflow.cli rollcall --list
cd scripts && PYTHONPATH=. python3 -m ohflow.cli rollcall --matrix full --dry-run
cd scripts && PYTHONPATH=. python3 -m ohflow.cli rollcall --cases merge:pi,claude:2:consolidator=codex --dry-run
```

### Read a matrix result

Each test case prints one line, verdict first:

    PASS single pi count=1  0m31s  5.4 k tokens  <run dir>
    FAIL review pi,claude count=1  1m02s  9.0 k tokens  <run dir>  step reviewer: <check>
    SKIP single claude count=1  claude harness executor: <why>

A `FAIL` line ends with the first failing step and check. Read that run with `status --run <run dir>` and open its transcript with `transcript`. The last line is `ROLLCALL PASS: P of N test cases` or `ROLLCALL FAIL: F of N test cases failed, S skipped`. A `PASS` line ends with `, S skipped` when a test case skipped. A run where every test case skipped reads `FAIL`. `--dry-run` prints one `WORKFLOW` line per test case and ends with `ROLLCALL DRY: N test cases valid`. A test case whose workflow does not build prints an `INVALID` line instead. That dry run ends with `ROLLCALL DRY: B of N test cases invalid` and exits 2.

| Exit | Meaning |
|---|---|
| 0 | `ROLLCALL PASS` or `ROLLCALL DRY: N test cases valid` |
| 1 | `ROLLCALL FAIL` |
| 2 | a bad test case, matrix or config, or `ROLLCALL DRY: B of N test cases invalid` |

A passing test case has also proved its resume: resuming the finished run starts no step. The `campaign` test case does not check resume.

`matrix.json` in `--out` is the heartbeat. It is rewritten after each test case, so a long run is readable while it goes. Each test case's run directory is `<out>/NN-<scenario>-<harness-executors>-<count>/run`. Without `--repo`, the verb makes a throwaway repo with one commit under `--out`. Stdout carries only the verdicts. `-v` streams each run's own lines.

### The A/B seam

`--config FILE` overrides the model of any harness executor for the whole matrix:

```json
{"name": "claude-heavy", "harness_executors": {"claude": {"model": "heavy"}}}
```

A harness executor entry may set `model` (a tier or a model id), `base_url`, `api_key_env` and `params`. Comparing two configs is out of scope today. Run the same test cases once per config file with a separate `--out`, then compare the two `matrix.json` files by hand.

## Add a harness executor

A harness executor is a module that answers seven questions, plus one row in the registry and an entry in each other place that names every harness executor. The top of [harness executors](references/harness-executors.md) lists those places.

1. **Register it.** Add a `HarnessExecutorInfo` row to `HARNESS_EXECUTOR_INFO` in `scripts/ohflow/harness_executors.py`. It names the module and the capabilities that validation reads. Add the harness executor's fix hint to `HARNESS_EXECUTOR_FIX` in `scripts/ohflow/preflight.py`.
2. **Answer the harness executor questions** in the module: `agent_errors`, `usage`, `activity`, `resume_target`, `reattach_target`, `transcript` and `make_harness_executor`. `harness_executors.py` lists what each returns. `usage` answers in the vocabulary of `attempt_record.TOKEN_KEYS`. `resume_target` is what a retry forks into a new attempt (`carry_context`); `reattach_target` is where a dead supervisor's attempt continues under the same attempt number, and it needs `CAP_REATTACH` in the registry row. An executor without one of them answers `None`; `durable_runner.py` answers `None` to the first and a `<box>:<dir>` to the second.
   Two more questions keep a silent command alive and visible: how the executor reports a tool call's start and end, and how it feeds the call's output to the tool-output contract (`CliEventAction.calls`, or `poll_calls` when stdout carries no events). [Harness executors](references/harness-executors.md#liveness-and-tool-output) lists each executor's answer.
3. **Write a fake CLI** in `tests/fakes/fake_<name>.py`, after the five fake CLIs there. It replays a session recorded from the real CLI. `fake_pi_cloud.py` beside them is a fake Worker that a test imports.
4. **Record fixtures** under `tests/fixtures/<name>/`: the real session, usage and error text.
5. **Write the contract test** `tests/test_harness_executor_contract_<name>.py`. Take the shared assertions from `tests/contract_support.py`: usage equals the tokens in `result.json`, activity ends on the last tool call, a retry names its resume target or none, the transcript points at a file.
6. **Add the roll-call execution preset.** Put the harness executor's cheap model in `MODELS` and its stall limit in `STALL_S`, both in `scripts/ohflow/workflows/rollcall.py`. The matrices in `scripts/ohflow/rollcall.py` run the harness executors in `THREE`; any other harness executor runs through `--cases`.
7. **Run a live `single`.** The test case proves the harness executor end to end:

```bash
cd scripts && PYTHONPATH=. python3 -m ohflow.cli rollcall --cases single:<name>
```

Done when the contract test passes and the live `single` prints `PASS`. Harness executor facts go in [harness executors](references/harness-executors.md).

## Add a test scenario

A test scenario is one pattern of the roll-call workflow.

1. **Add the scenario.** Name it in `SCENARIOS` in `scripts/ohflow/workflows/rollcall.py` and build its phases there. Its gate checks the artifact, not the agent's words.
2. **Add a deterministic test.** `tests/test_rollcall_01_scenarios.py` builds each scenario's workflow and validates it. Copy its pattern, so a broken scenario fails without a live agent.
3. **Add a matrix row.** Put a `_case(...)` in `MATRICES` in `scripts/ohflow/rollcall.py`. `rollcall --list` then shows it.
4. **Update the tables** above: the test scenario row and the test case count of each matrix that holds the new test case. `tests/check_docs.py` fails while a count differs from `MATRICES`.

Done when the new test passes, `rollcall --cases <scenario>:pi --dry-run` prints `ROLLCALL DRY`, and one live test case prints `PASS`.

## License

ohflow is licensed under the Apache License, Version 2.0. The full text is in [LICENSE](LICENSE).
