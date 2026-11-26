# ohflow terms

One term has one meaning here. Where English gives a word several meanings, each meaning has its own name, and the plain word belongs to one owner. Every other file uses these names.

Read this top part whole: it ends at the core table. Every other term is one line that starts with its bold name, so look it up with grep, such as `grep -m1 '^\*\*harness executor\*\*' CONTEXT.md`. This file is the one source of the definitions; [CONTRIBUTING](CONTRIBUTING.md#the-glossary) says how its copies and its vocabulary check work.

## Core terms

| Term | In one line |
|---|---|
| operator | the person who installs ohflow, owns its settings and accounts, and decides |
| orchestrator agent | the operator's agent: it writes the spec bundle or workflow, then starts, watches and steers runs |
| spec bundle | the folder `construct` reads: `bundle.md` and one milestone spec per milestone |
| campaign | specs delivered milestone by milestone, one workflow per milestone, a fresh judge after each |
| milestone | one slice of the work, with its spec, its workflow and its acceptance checks |
| milestone round | one cycle of running a milestone's workflow and asking its judge |
| judge | the fresh agent that passes a milestone, revises it or escalates one question |
| workflow | phases of steps; a workflow module, in Python, builds the workflow definition |
| workflow pattern | how a workflow arranges its agents, such as relay, fan-out, or implement and review |
| phase | a group of steps that run in parallel behind one barrier; phases run in order |
| step | one piece of work in a phase: an agent, a command, a gate or a merge |
| coordinate | a step's address, `NN.phase/NN.step`, which the run log and the verbs key on |
| agent brief | the instructions an agent reads first, `brief.md` |
| harness | the program that runs the agent loop: Claude Code, Codex or pi |
| harness executor | the part of ohflow that starts, watches and stops one kind of harness, such as `claude` or `pi-cloud` |
| box | where an attempt's commands run: the local box, an ssh box or a cloud box |
| workspace | a git repository that a workflow works on |
| worktree | the git working directory one step edits |
| workflow run | one execution of a workflow, with its resumes; the short form is *run* |
| run directory | the folder one run writes; its name is the run id |
| run log | `run-log.jsonl`, the append-only record of what the engine did, and the truth |
| attempt | one numbered try at a step |
| gate | the checks a step must pass, run as code and never by an agent |
| artifact | a file or commit a step leaves behind as evidence |
| final message | an agent's last text: a claim, which the artifact proves or refutes |
| workflow resume | `run --resume`: continues a run and reuses its matching successes |
| cached step outcome | a recorded success reused because the step's fingerprint matches |
| exit report | `exit-report.md` and `exit-report.html`, written when a run ends |
| estimate | `estimate.json`: the forecast of minutes, tokens and cost from earlier runs |
| step handover | `handover.md`: a producer step's findings for the step that consumes them |
| agent tool policy | `AgentSpec.tools`: the tools an agent step receives |

## The workflow

**workflow** — the general concept of arranged work. Use *workflow definition*, *workflow module* or *workflow run* when the distinction matters.

**workflow definition** — the `Workflow` that a workflow module's `build(args)` returns: its `phases`, its `worktrees` and workspaces, the `args` it was built from, and its limits.

**workflow module** — the Python source that builds a workflow definition. A verb names it with `--workflow` and passes it `--args k=v`.

**phase** — a group of steps (`Phase.steps`) with one barrier, one failure policy and one `max_parallel` limit, which `--max-parallel` caps. Phases run in order; `run --only-phase NAME` runs one alone ([concurrency](references/ohflow.md#concurrency)). (Not an implement-review driver mode, `mode`, nor a stage of a project plan.)

**wave** — a group of a phase's steps that run at once: N steps under `max_parallel` P take `ceil(N/P)` waves, which `/api/plan`, the ETA and the estimate count ([estimate](references/ohflow.md#estimate-a-run)). (A wave is a slice of one phase; a milestone round is one judge cycle.)

**failure policy** — `Phase.on_step_failure`, what a phase does with a failed step: `quarantine` (the default), `continue` or `abort`. `Phase.min_success` (`all`, `any` or a number) sets how many steps the phase needs ([failures](references/ohflow.md#transient-and-structural-failures)).

**step** — a named piece of work within a workflow phase, configured to run an agent, execute a `command` in its `shell` (`sh` or `cmd`), perform checks, or merge the branch `merge_branch` with its `merge_message`.

**unit** — `Unit` in `Workflow.units`: one item a workflow runs over, such as one finding of a review, with an `id`, a unit path and a `size`. Steps name it in `Step.unit`; a step with none is a *shared step* ([units](references/ohflow.md#units-and-unit-paths)).

**unit path** — `UnitPath` in `Workflow.paths`: one kind of unit that takes its own route through the workflow, so its cost per unit differs from the other kinds. The CLI and the dashboard print it as *path* ([units](references/ohflow.md#units-and-unit-paths)).

**coordinate** — the address of a step, `NN.phase-name/NN.step-id` with both numbers 1-based, such as `02.batch-a/01.c9-spill`. A verb's `--step` takes it, or a step id that names one step ([coordinate](references/ohflow.md#the-coordinate-is-the-address)).

**step objective** — `Step.objective`: one display line of at most 120 characters that says what a step is for. It never instructs an agent. (A reader's label for one step; the objective is what the whole run is for.)

**agent step** — a step of kind `agent`: one agent with one agent brief, started through one harness executor, in its worktree or else the default workspace ([workspaces](references/ohflow.md#workspaces)). (A command step runs a command and no agent.)

**gate step** — a step of kind `gate`: it runs only its gate and starts no agent.

**agent brief** — the instructions an agent reads first, written to the attempt's `brief.md`; *brief* for short. `claude` and `codex` get a bootstrap prompt that points at the file, and the other harness executors send its text as the first message ([launch rules](references/harness-executors.md#launch-rules-for-the-cli-harness-executors)).

**position block** — the text the engine writes to `position.md` (`coords.render_position`) and puts before the agent brief, which `ohflow position` prints ([coordinate](references/ohflow.md#the-coordinate-is-the-address)). (The position block says where the step stands; the agent brief says what to do.)

**agent** — an LLM program that a harness executor starts. The dashboard draws one *card* for each step. A card is not an agent.

**harness** — the program around a model that runs the agent loop of model calls, context and tool calls, such as the pi, Claude Code or Codex CLI. The `agents` package classes `ContainerHarness` and `PiHarness`, always named by class name, run one inside the Durable Objects `CliAgent` and `StepAgent`. (A harness runs the loop; a harness executor starts and stops one.)

**signed-in harness** — a harness that runs on a subscription login instead of an API key: Claude Code or Codex. `claude` and `codex` use this machine's login, `claude-cloud` and `codex-cloud` the pi-cloud Worker's ([Claude Code and Codex steps](references/pi-cloud-worker.md#claude-code-and-codex-steps)). Only `claude` and `codex` declare `signed_in`. (`pi` takes an API key.)

**harness executor** — the component that launches, monitors, collects results from and stops a harness: `pi`, `claude`, `codex`, `durable`, `pi-cloud`, `claude-cloud` or `codex-cloud`. Each agent step names one in `AgentSpec.harness_executor`; there is no default ([harness executors](references/harness-executors.md)). (A harness executor is not a model.)

**runner** — the child process a harness executor starts for one attempt: one `<executor>_runner.py` per harness executor, with `cli_cloud_runner.py` holding what `claude-cloud` and `codex-cloud` share. It writes the attempt's `logs/` and result ([liveness](references/harness-executors.md#liveness-and-tool-output)). (The harness executor lives in the run supervisor; the runner is its child for one attempt.)

**model configuration** — the `ModelConfig` of an agent step: a model tier or a model name, `base_url`, `api_key_env`, and `params` from the closed set each harness executor accepts, such as pi's `thinking`.

**model tier** — `heavy` or `light` in `ModelConfig.model` in place of a model: the rung of the inference ladder a step needs. The settings `tiers.<tier>.<harness executor>` map it to a model per harness executor ([model tiers](references/harness-executors.md#model-tiers)).

**execution preset** — a harness executor with its default model configuration and cost basis, as the roll call pairs them; no code names it. (An execution preset picks an executor and a model; a tool preset picks an agent's tools.)

**agent execution configuration** — every setting that governs how an agent step runs: harness executor, execution target, model configuration, agent profile, agent tool policy, agent brief, skills, and execution limits (stall timeout, execution timeout, command time cap, iteration limit). The harness executor decides which it supports.

**agent profile** — the harness setup an agent starts in: the instructions, hooks, memory, skills and inherited tool and MCP configuration it loads, the usual setup or `hermetic`. Only `claude` and `codex` take `agent_profile` ([hermetic](references/harness-executors.md#what-agent_profilehermetic-removes-and-keeps)). (`durable` names its box in `AgentSpec.box`, never here.)

**executor capability** — one feature a harness executor declares in `harness_executors.py`: `stall_timeout`, `carry_context`, `signed_in`, `profile`, `box`, `tools_only` or `reattach`. `validate` refuses a step that needs one its executor lacks ([capabilities](references/harness-executors.md#capabilities)). (A capability is declared; effective agent tools are what one attempt received.)

**execution target** — the kind of place where a step's commands run: the local box, an ssh box or a cloud box, fixed by the harness executor and `AgentSpec.box`; no field names it. (The kind of place; a box is the one machine an attempt uses.)

**box** — the one machine or container where an attempt's commands run: the *local box* `local`, this machine; an *ssh box*, an operator's machine named by its ssh host alias such as `buildbox`, for `durable` only; or a *cloud box* from the default snapshot. `AgentSpec.box` names a `durable` step's box, and `durable.box` the default ([durable](references/harness-executors.md#durable)). (An ssh box keeps its state between steps; a cloud box lasts one attempt.)

**durable host** — the Node program `host/ohflow-step.mjs` that runs one `durable` step's pi-durable session on its box, with the box's own keys for the providers `durable.providers` lists; `durable_host.py` installs it at launch ([durable](references/harness-executors.md#durable)). Bare *host* names nothing. (It is to `durable` what the pi-cloud Worker is to cloud steps.)

**tether** — the durable host's watch on its own connection (`host/src/tether.mjs`), which ends the host and its command within seconds of a dropped ssh connection ([durable](references/harness-executors.md#durable)). (A kill ends a local host directly; the tether ends a remote one.)

**pi-cloud Worker** — the Cloudflare Worker, whatever its `name`, that owns every cloud step: one Durable Object per attempt (`StepAgent` for pi, `CliAgent` for Claude Code and Codex), plus `SkillsMirror`, `SnapshotBuilder` and `CodexLogin` ([pi-cloud Worker](references/pi-cloud-worker.md)). Bare `pi-cloud` is the harness executor. (*Worker* means a Cloudflare Worker; no agent or thread is a worker.)

**Worker pair** — the pi-cloud Worker and its code mode Worker, deployed together from `worker/` as `<name>` and `<name>-codemode` by `worker/scripts/deploy.mjs`; a `name` other than `pi-cloud` deploys a second pair ([second Worker](references/pi-cloud-worker.md#a-second-worker-in-the-same-account)). (A pair is one deployment; its pi-cloud Worker runs the steps.)

**Durable Object** — Cloudflare's stateful object. One per attempt holds that attempt's cloud operation and transcript and starts its box. It is never shortened to *durable*, which names the harness executor. (The object holds state; the box runs the commands.)

**cloud harness executor** — `pi-cloud`, `claude-cloud` or `codex-cloud`: runs a step in a Durable Object of the pi-cloud Worker, on a cloud box, set up by `pi_cloud.url`, `pi_cloud.providers` and `pi_cloud.mcp_servers` ([harness executors](references/harness-executors.md#pi-cloud)). (`durable` runs on the operator's own box, with no cloud provider.)

**container** — the Cloudflare container that is a cloud step's box: `standard-1` (4 GiB memory, 8 GB disk), started from the default snapshot and billed for every second it runs. (One kind of box; the Durable Object that starts it holds the attempt's state.)

**default snapshot** — the saved filesystem every cloud step's container starts from, with the tools, the agent CLIs, the MCP servers with those of `snapshot.mcp_servers`, and the operator's repos, and no credential, built by `SnapshotBuilder` from `worker/snapshot/recipe.mjs`. It expires 30 days after its last restore. (A filesystem to start from; the run state read-out is a JSON view of a run.)

**snapshot key** — the first 16 bytes of the SHA-256 of the recipe's image name and steps; `pi_cloud_start` names the key an attempt started from. (It identifies a recipe version; the stored snapshot id identifies one built filesystem.)

**snapshot pin** — the full commit id at which the default snapshot clones the repo of `snapshot.skills` or of a `snapshot.repos` entry; `node scripts/pins.mjs` moves it ([the pi-cloud Worker](references/pi-cloud-worker.md#settings)). The bare word *pin* has no owner. (It fixes a repo in the snapshot; a skills pin fixes one step's skills.)

**fallback snapshot** — the newest snapshot built under an earlier snapshot key, which steps start from while the current key's snapshot is not built (`SnapshotBuilder.current()`). (The fallback snapshot is an older build of the recipe; the default snapshot is the current one.)

**successor snapshot** — planned, not built: a snapshot saved from a finished step's box, which later steps start from. (The default snapshot is built from the recipe; a successor snapshot comes from a box after its work.)

**remote workspace** — the directory where the agent of a step on an ssh box or a cloud box works: `<dir>/work` on an ssh box; `/workspace/repo` on a cloud box, with `/workspace/out` for the files fetched back. (A worktree is the step's local Git directory; the remote workspace is its copy on another box.)

**sandbox** — a harness's own confinement of the agent's commands, such as Codex's sandbox mode. No harness executor confines an agent's shell on the local box; Codex runs with `danger-full-access`. (A box isolates a remote agent from this machine; ohflow does not call that isolation a sandbox.)

**skills mirror** — the `SkillsMirror` Durable Object of the pi-cloud Worker, which holds the newest commits of the skills repository's `main` for cloud steps to pin ([the pi-cloud Worker](references/pi-cloud-worker.md#skills)). (A `claude-cloud` or `codex-cloud` step that names no skill reads the snapshot's `/opt/agent-skills`.)

**skills pin** — the commit of the skills repository's `main` that a cloud step fixes when it starts (`pinSkills` in `worker/src/skills-feed.mjs`), kept as `{sha, names}` for the attempt. (It fixes one step's skills; a snapshot pin fixes a repo in the snapshot.)

**cloud operation** — one Durable Object's work for one attempt: clone the start commit into the remote workspace, run the agent, push the transport branch, keep the transcript. A reattach continues it; a retry gets a new one. (The attempt is ohflow's record; the operation is the Worker's work for it.)

**abort answer** — the pi-cloud Worker's answer to `POST abort`: `operationId`, `aborted`, `container`, `last_look` (at most 8000 characters) and, for `claude-cloud` and `codex-cloud`, `usage`; kept in `runner-abort.json` or `kill-abort.json`. (The box's last state; the attempt result is ohflow's record.)

**replayed event** — a line of a `pi-cloud` step's event stream marked `replayed: true`: the transcript so far, which `GET events` sends before the live events so that a reattaching runner reads the whole conversation. (A replayed event happened before this connection; a live one arrives during it.)

**attempt key** — the portable name of one attempt, built by `remote_git.attempt_key` from the coordinate, `-a<NN>` and a hash of the attempt directory; it names the `durable` step folder, transport branch, cloud operation and Durable Object. (It names an attempt, not a step.)

**container chronometer** — `infra` in an attempt's `result.json`: the Worker's own count of the container time the attempt held, for memory and disk. Infra cost prices it. (The Cloudflare check reads Cloudflare's own container meters, which lag by minutes.)

**cloud end error** — the error a remote runner records when its operation ends without a done answer: `host_lost`, `unanswered: <reason>` (such as `container_lost`), `push_failed`, `clone_failed`, `skills_failed`, `fetch_back`, or a `pi_cloud_error` or `durable_error` event's `<name>: <message>`. Only `host_lost` reattaches. (`host_lost` covers a lost Worker too; *host* names no owner.)

**agent skills** — `AgentSpec.skills`: skills named for an agent explicitly, which `pi` reads from `AgentSpec.skills_dir`, `durable` from its box and the cloud harness executors from the skills mirror. (`claude` and `codex` refuse it and have only their agent profile's skills.)

**agent tool policy** — `AgentSpec.tools`: the declared tools an agent step should get: built-in tools, `enable_browser`, `enable_sub_agents`, and MCP tools from the servers `mcp_config` names. Support varies by harness executor ([harness executors](references/harness-executors.md#tool-policies)). (The declared policy; the effective agent tools are the result.)

**tool preset** — `ToolPolicy.preset`: the named set of built-in tools that `only`, `allow` and `block` narrow; `default` is the only value any harness executor accepts. (A tool preset picks an agent's tools; an execution preset picks an executor and a model.)

**effective agent tools** — the tools actually exposed to one agent invocation, after the harness, agent profile, tool policy and connected systems. An unavailable listing means unknown, not empty; exposure does not prove authentication or use. (The result; the agent tool policy is the declaration.)

**MCP tool blocklist** — a list of `server.tool` patterns, owned by the workflow, that removes matching tools from the configured MCP tool set. An empty blocklist removes nothing.

**MCP tool allowlist** — an explicit selection of MCP tools by `server.tool` pattern, narrowing the configured tools that the blocklist leaves. An empty allowlist applies no additional restriction; it does not mean no MCP tools.

**worktree** — the Git working directory a step edits: `Step.worktree` names it; `WorktreeSpec` places it in a workspace, from `WorktreeSpec.base`, with `base_sha_mode` `head` or `merge_base`; `revert` removes it with its branch. (It separates working files; it is not a security sandbox.)

**workspace** — `Workspace` in `Workflow.workspaces`: one git repository a workflow works on, with a `name`, `path`, `base_branch`, optional `remote` and optional baseline command ([ohflow](references/ohflow.md#workspaces)). (A workspace is a repository on the operator's machine; the remote workspace is its copy on another box.)

**owned workspace** — a workspace with `owned=True`, for work that is not code, whose repository ohflow creates when a run starts and `revert` keeps ([ohflow](references/ohflow.md#workspaces)). (Any other workspace must already be a repository.)

**default workspace** — the first workspace of a workflow, or the one that `repo`, `base_branch` and `baseline_cmd` declare: a step with no worktree runs there, and `Workflow.repo` and `Workflow.base_branch` read as its fields. (Unplaced work runs here; other work names its workspace.)

**baseline command** — `Workspace.baseline_cmd`, the `baseline` line of a bundle: the command that must exit 0 on the clean base branch before a run starts; `ohflow preflight` does not run it. (It proves the base green before any step; a gate check tests one step's commit.)

**write scope** — `Step.write_scope`: the glob patterns of the paths one step may edit. Two steps of one phase that write in one workspace may not have overlapping write scopes.

**launch method** — how the operating system starts a detached process: `direct`, `breakaway` or `wmi`. It is not a harness executor and not a model. Owner: `detach.py`.

**spec** — the operator's written statement of what they want made, such as an issue, a design document or a folder of notes; the orchestrator agent turns it into a spec bundle, and every objective kind starts from one. `AgentSpec` and `WorktreeSpec` carry no glossary meaning. (A spec is the operator's; a milestone spec is `construct`'s input for one milestone.)

**note** — only the `Step.note` field: one line of caption for the board and the dashboard. The files in the run directory are the *run notes*.

## One run

**workflow run** — one execution of a workflow definition, including later resumes that continue it. The short form is *run*.

**workflow run status** — the current condition of a workflow run, read from its recorded history, supervisor liveness and preparation or exit records, such as `held`, `running`, `paused`, `finished`, `failed`, `crashed`, `interrupted` or `orphaned`. (Describes a run's condition; a workflow phase groups work.)

**held workflow run** — a workflow run whose live supervisor waits for release before the engine starts: a fresh `--hold` or `--pilot` run, or the resumed run of a campaign round that a judge's REVISE starts. `run --resume` cannot hold. (A wait before execution; see also: workflow release.)

**workflow release** — `ohflow go`, which lets a held workflow run proceed; `go --predictions FILE` first seeds `predictions.md`. The supervisor reloads and validates the workflow module, so edits made during the hold run. (Releases a held run; workflow resume continues existing execution history.)

**pilot** — `run --pilot`: the workflow run a held run makes before it waits, of the smallest unit of each unit path plus the shared steps, in `<run-dir>/pilot` on `-pilot` worktrees. A pilot unit does not count as done: [ohflow](references/ohflow.md#pilot-a-run-over-many-units).

**pilot projection** — `pilot.json` in the run directory: the projected cost of the full run, each unit path's unit count times the cost of its pilot unit, plus the shared steps once. Its time is agent time, not elapsed time.

**finished workflow run** — a workflow run whose engine reached the end of the selected execution without aborting or pausing. Steps may still have failed or been skipped under their policies. (Engine completion, not acceptance of every step outcome.)

**engine** — `engine.py`, the scheduler inside the run supervisor: it runs and gates each phase's steps under `max_parallel`, applies the failure policy, and writes the run log, `board.md` and the attempt directories. (The run supervisor hosts a run; the engine executes it.)

**step thread** — the engine thread that carries one step other than a merge step: its attempts, its gate and its retry decision; it can set the run's abort. (The engine schedules the steps; a step thread carries one of them.)

**run supervisor** — `supervisor.run_workflow`, the process that hosts one workflow run: it reserves the run directory, holds a `--hold` or `--pilot` run, serves the dashboard (`--no-dashboard`, `--dashboard-port`, `--open-dashboard`), runs the engine and from then on writes the exit report on every exit path. A running run log under a dead supervisor reads *orphaned*.

**launch record** — what `run --detach` prints after waiting up to 20 s for the supervisor: the `dashboard:` line, the run directory and the supervisor's recorded pid; `--json` prints it as JSON. (A launch record names a run's supervisor; the campaign pid record names a campaign's process.)

**preflight** — the checks a fresh run makes before any step starts; a failure stops the run with `preflight failed:`. `ohflow preflight` runs them alone, plus the Git Bash check, for the executors `--harness-executors` names, with one `FAIL <check>: <observed>; <fix>` line per failure: [ohflow](references/ohflow.md#verbs-and-their-verdict-lines). (`ohflow validate` checks only the workflow definition.)

**worktree path length** — the preflight check that, on Windows, a local worktree's root plus the longest path tracked at its base stays under 260 characters, unless the repository sets `core.longpaths`. (Only a local worktree is checked; a remote workspace lives on another box.)

**run clone** — a clone of the checkout's hosted `origin`, with `core.longpaths=true`, that a run uses while another session works in the checkout: [operate-a-run](references/operate-a-run.md#run-beside-another-session-in-a-dedicated-clone). (A clone is a repository of its own; a worktree shares one.)

**dry run** — `--dry-run`: preflight, the baseline and every step's attempt input files, with no agent started. It writes no exit report, estimate, run notes or dashboard, so it does not prove the run works.

**run directory** — the directory ohflow writes for one run, named by its run id: `run-log.jsonl`, `workflow.json`, `board.md` and one directory per step. A driver's `--out` directory and a roll-call case directory each contain a run directory and are not one.

**run id** — the name of the run directory: `run --run-id` sets it, else ohflow mints one.

**run log** — `run-log.jsonl`, the append-only record of what the engine did, and the run's truth (`run_log.py`). Its events are `run_started`, `phase_started`, `attempt_started`, `attempt_finished`, `gate_ran`, `phase_settled`, `run_finished`, `retry_decided`, `worktree_ready`, `run_log_recovered`, `phase_resumed`, `work_excluded` and `token_budget`; a step's status is `pending`, `running`, `passed`, `failed`, `timeout`, `quarantined`, `skipped`, `cached` or `deferred`. (An attempt's `logs/` holds its event log and tool output, never a run log.)

**event log** — the file in an attempt's `logs/` where the runner writes the harness's events as they arrive, such as `pi-events.jsonl`; live usage and a rebuilt record are read from it. (An event log holds one attempt's harness events; the run log records the whole run.)

**attempt** — one numbered try at executing a step. A command, gate or merge step has an attempt but no agent invocation. `explain` and `actions` take `--attempt N`, the newest by default.

**attempt directory** — `attempts/NN/` below a step directory: one attempt's inputs and available outputs. A file in it can be missing after a preparation failure or an interruption, so count attempts from the run log.

**attempt result** — `result.json` in an attempt directory: the status, error, settings, tool calls, tokens and cost of one attempt, when the attempt produced it.

**rebuilt record** — an attempt result written after its runner died without one (`recover_cli_result` in `cli_harness_executor.py`). `record_source` names its source (`event_log`, `attempt_files` or `none`, against `runner`), and `recovery.ended_basis` how its end time is known: [harness executors](references/harness-executors.md#liveness-and-tool-output). (The runner's record is first-hand; a rebuilt record is pieced together after its death.)

**agent invocation** — the logical execution of an agent within an agent-step attempt. Preparation can fail before an invocation starts; reattach continues an existing invocation.

**reattach** — reconnecting to and continuing the same attempt after losing supervision or connection. It preserves the attempt number and continues the same logical agent invocation.

**execution start** — a recorded start of work: an initial start, retry, auto-resume or reattach. A reattach spends another execution start while continuing the same numbered attempt.

**attempt start** — the beginning of a numbered attempt. Reattach records another execution start without beginning another attempt.

**open tool call** — a tool call whose start was observed and whose end was not. It may still be running; an open record alone does not prove useful progress.

**tool output** — `logs/tool-output/` in an attempt directory: the live output of each tool call, capped at 5 MiB per call, kept apart from the transcript and outside the step fingerprint. A call whose output arrives more than 2 s after it ended is *detached*.

**stall timeout** — `Step.stall_timeout_s`, optional: the longest interval without observed activity while no tool call is open. An open tool call suspends stall detection.

**stall** — a stop triggered when observed inactivity exceeds the configured stall timeout and no tool call is open. It measures silence, not whether the agent is making useful progress.

**execution timeout** — `Step.execution_timeout_s`: the elapsed-time limit for a step's main execution, without preparation or the gate checks, which have their own limits. (An execution timeout counts time; an iteration limit counts model calls.)

**command time cap** — the time limit for one command an agent invokes: derived from the execution timeout, and `command_time_cap_s` can only tighten it. A call open past the cap plus a hardcoded 60 s grace is stopped, except on `claude-cloud` and `codex-cloud`: [ohflow](references/ohflow.md#command-time-caps).

**iteration limit** — `AgentSpec.max_iterations`: the most model calls one attempt may make, the last one's tool calls included; 150 unless the step names another. On the cloud executors the Worker enforces it (`max_iterations_enforced_by`). (An iteration limit counts model calls; an execution timeout counts time.)

**step fingerprint** — a hash of a step's selected inputs: configuration, brief, dependencies, consumed handovers and relevant worktree state, without the run ID or the attempt number. It does not capture every external change.

**step identity** — the pair (step coordinate, step fingerprint) that names one revision of a step's work in a workflow run. Attempts at unchanged work share it; a changed hashed input makes a new identity with fresh allowances, and earlier attempts stay recorded.

**retry** — another attempt of an agent step in the same workflow run, started because its retry policy allows it after a failure; the run log records `start_kind` `retry`. `RetryPolicy.carry_context` lets the `pi` and `claude` executors continue the previous conversation.

**retry budget** — `RetryPolicy.max`: how many additional attempts the retry policy permits. (see also: milestone revision budget; reattach)

**auto-resume budget** — how many automatic recovery passes may retry work postponed by interruptions or temporary failures.

**execution-start budget** — the total allowed recorded starts for unchanged work, including reattachments. (1 initial start + retry budget + auto-resume budget + 1 manual-recovery allowance, `MANUAL_RECOVERY_ALLOWANCE`)

**failure exclusion threshold** — the number of counted failures after which unchanged work gets no further start, even when starts remain: hardcoded to 2 (`EXCLUSION_THRESHOLD` in `attempts.py`). The run log records the refusal as `work_excluded`.

**counted failure** — a started execution of unchanged work that ends in a judged failure (`failed`, `timeout` or `quarantined`) or a genuine transient deferral. Cached, skipped and never-started work and abort victims do not count. See [ohflow](references/ohflow.md#the-run-log-is-the-truth).

**abort victim** — an execution that ended without its own verdict because something outside it stopped it or kept it from starting: a run abort, an attempt kill, a workflow resume closing what a dead run supervisor left open, or a reattach. It is recorded `deferred` with `abort_victim` and is never a counted failure: [ohflow](references/ohflow.md#the-run-log-is-the-truth).

**attempt kill** — `ohflow kill [--reason TEXT]`: an upper rank ends one agent or command step's running attempt while the other steps run on. It is recorded `deferred` as an abort victim, and only a workflow resume starts it again, as a new attempt. (An attempt kill ends one attempt; a run abort ends every attempt in flight.)

**kill request** — `kill-request.json` in a step directory: the attempt number, reason, time and supervisor pid that `ohflow kill` writes for the engine's next poll. The verb waits up to `--timeout` seconds for `KILLED`, `NOT KILLED` or `KILL SENT`. (The kill request asks; the attempt kill is what the engine does with it.)

**retry eligibility** — whether a failed agent step may start another attempt: `RetryPolicy.on` must cover every failure token (`timeout`, `agent_error`, `gate:<check>`; `validate` refuses `gate:ownership` and `gate:no_ai_attribution`), the budgets must have room, and no exclusion or other refusal may apply. Deferred work takes the auto-resume or manual-resume path. See [ohflow](references/ohflow.md#retry).

**workflow resume** — `run --resume RUN_ID`: continuing a workflow run from its history with the workflow definition loaded now. Matching successes may be reused and unfinished work may reattach or start another attempt, within spent budgets and exclusions. It is refused while the run's supervisor lives; `run --detach` checks first and passes `--resume-checked`.

**workflow rerun** — starting a new workflow run in a new directory, with a new log and fresh run-scoped budgets; earlier successes are not reused. `ohflow compare --runs A B` sets two runs side by side.

**cached step outcome** — an outcome that reuses a recorded step success because its step fingerprint matches and any required recorded handover is intact. The step and its gate do not run again, and no execution start is spent.

**deferred** — a step outcome for work postponed or interrupted before its own verdict: a temporary failure, a run abort, an attempt kill, or an execution its dead run supervisor left open. Recovery stays under the budgets and the exclusion threshold.

**auto-resume** — the pass that restarts a phase's deferred steps by itself after a cooldown, except a step an attempt kill ended. `Workflow.auto_resume` or `run --auto-resume` sets how many passes a phase may make; each is a `phase_resumed` event, and its attempts carry `start_kind` `auto_resume`.

**provider cooldown** — the engine's wait before the next start after a transient failure: until a provider's announced quota reset plus 60 s, else `transient_backoff_s`, doubled per hit up to ten times its base. The run log keeps it, so a resume waits too: [ohflow](references/ohflow.md#transient-and-structural-failures).

**provider usage window** — a provider's usage limit over a rolling window, such as Z.AI's 5-hour limit. A workflow step that reaches it fails transiently and waits out a provider cooldown; a session turn ends on the error with no wait: [steer-a-run](references/steer-a-run.md#recorded-failures-and-the-move-for-each). (The window is the provider's limit; the cooldown is the engine's wait.)

**token budget** — the most tokens a run's agent steps may use, prompt plus completion with cached input: `Workflow.token_budget` or `--token-budget`. Each agent attempt reserves a grant (`Workflow.token_reserve`); one not admitted is deferred and pauses the run: [ohflow](references/ohflow.md#token-budget). (The token budget counts observed tokens; the billing estimate prices them and is never compared with it.)

**token ledger** — `budget.Ledger`: the token budget's account of one run, with its snapshot in `budget.json` at the run root. (The token ledger counts a run's tokens; the campaign log records a campaign's decisions.)

**transient failure** — a recognized temporary external problem, such as rate limiting, provider overload or a dropped connection, for which waiting may change the outcome.

**structural failure** — a failure classified as a work or setup problem, such as failed checks, malformed output or invalid credentials, and the class of every unrecognized failure. The class alone does not decide retry eligibility. (A check-in judges the work as a deviation, a design flaw or a miss; this classifies one failed attempt.)

**board** — the file `board.md`, the status table the engine rewrites. The command `ohflow board` prints an empty board for a workflow.

## Checks and reports

**gate** — the `GateSpec` of a step: the conjunction of its `checks`. A *quality gate* is that group of checks. A gate with no checks passes.

**gate check** — one named test of a gate, a `CheckSpec` with its `name` and `args`. It appears as `gate:<check>` in retry tokens, and a check that reads a diff measures from `since` ([ohflow](references/ohflow.md#gate-checks)).

**mechanical check** — an acceptance condition that a command decides: a `command_exit` gate check or a milestone spec's `- command:` line, which passes when its command exits 0 ([construct](references/construct.md#acceptance-checks)). (A command decides a mechanical check; the judge grades a rubric check.)

**mechanical check pass** — a `command_exit` check that passed on a clean worktree, recorded in `check-passes.jsonl` (`check_passes.py`). A later identical check in the same run reuses it, unless it sets `reuse: false` ([ohflow](references/ohflow.md#gate-checks)). (A mechanical check pass confirms one result; a cached step skips a whole step.)

**change-sized check** — the rule that checking a change costs in proportion to the change: gates, `check-` steps and acceptance checks run only the tests the change reaches; CI runs the full suite ([ohflow](references/ohflow.md#gate-checks)). (A change-sized check tests one change; CI tests the whole product.)

**changed-test selection** — `tests/run_tests.py --changed BASE`: the test files that the files changed since BASE reach, plus `check_docs.py`, capped at about 300 s. A gate runs it as `--changed {base}` ([CONTRIBUTING](CONTRIBUTING.md#running-the-suite)). (This repository's selection; another workspace brings its own.)

**check time** — the wall time of a step's `command_exit` gate checks, the only checks with `duration_s` in `gate.json`; the `checks p50` of `ohflow estimate` and the signal `checks_over_agent` read it ([dashboard](references/dashboard.md#attention)). (Check time prices each check you add; the execution timeout covers only the agent's work.)

**gate report** — `gate.json`, the result of every gate check for one attempt.

**execution error** — the error that ended an attempt, as the engine recorded it, such as a stall or `max iterations N exceeded` ([ohflow](references/ohflow.md#run-it)). (The execution error is the cause; a gate check that failed after it is a consequence.)

**final message** — the last text of an agent that completed its answer. It is a claim; the artifact is the evidence. A stopped attempt's last text in `final.md` is an *interrupted last message*, never a final message.

**artifact** — a file or commit that a step leaves behind as evidence of its work. Gate checks read artifacts, not the final message.

**structured output** — the JSON a step returns for `Step.schema`, in its final message or, for a `claude` step, its latest `StructuredOutput` call. The runner puts it in `result.json` as `structured`, or records `schema_error`. Only the `schema_valid` gate check validates it ([ohflow](references/ohflow.md#structured-results-and-dimensional-review)).

**exit report** — `exit-report.md` and `exit-report.html`, written when a run ends; `exit.json` is the same record for tools. `ohflow report` rebuilds all three after a hard kill.

**verdict** — a first-line result. A *verb verdict* is `PASS`, `FAIL`, `VALID`, `COMPLETE` and the like. A judge's answer is a *judge decision*, not a verdict.

**review verdict** — the `VERDICT:` line of a reviewer: `MERGEABLE` or `BLOCKED`. A gate check can accept a valid `BLOCKED` line without approving the work.

**finding severity** — the list a reviewer sorts each finding into: `blocking` (the reviewer would not merge over it), `should_fix` or `notes`. Any `blocking` finding fails the review gate ([brief-templates](references/brief-templates.md#review-brief)). (Severity sorts one review's findings; the review verdict is the reviewer's one-line answer.)

**fix cycle** — one implement-review run in `mode=fix` that the orchestrator agent starts after a blocking review; at most two run ([implement-review](references/implement-review.md#the-procedure)). (A fix cycle answers a review; a retry repeats a failed attempt.)

**hand-try** — a brief's instruction to use the work once by hand, as its caller would, and paste the command and output under "Hand-try" in the handover; the reviewer runs it again. (A hand-try uses the work; a mechanical check tests it.)

**heartbeat** — plain English for a periodic sign of life; ohflow gives the word no owner. Each mechanism keeps its own name: a piece's lines in `heartbeat.log`, the Worker's `pi_cloud_beat`, the stall deadline's heartbeat in `CliAgentRuntime`, and the roll call's `matrix.json`.

**campaign log** — `campaign.jsonl`, the append-only record of each run's commit, round and decision in a campaign, which `ohflow campaign history` reads ([campaign](references/campaign.md#run-it)). The bare word *ledger* has no owner; the token budget's account is the *token ledger*.

**agent transcript** — the file where a human reads one attempt, as the harness executor module names it. The command is `ohflow transcript`. The short form is *transcript*.

**model call** — one request from a harness to its model. One model call may ask for several tool calls.

**tool call** — one operation an agent asks a tool to run. The engine counts them per attempt in `tool_calls`; `ohflow actions` lists them under their model calls.

**run state read-out** — the one JSON document `live.read_out` builds from a run directory: the whole run at one instant. `ohflow status` (redrawn by `--watch`), `ohflow watch`, `/api/read-out` and the exit report show it; the page polls `/api/workflow`, its own view ([dashboard](references/dashboard.md#the-read-out)). It is a derived view, not a checkpoint a run resumes from.

**plan** — the declared plan of one run: its workflow definition, limits and forecast in run order, shown by the Plan view and served by `/api/plan`. A *project plan* keeps its qualifier. (A plan is declared before the run; the run state read-out says what happened.)

**Plan view** — the dashboard's third view: a run's declared plan, which `/api/plan` builds from `workflow.json` and `estimate.json`. A `--hold` run opens on it; `exit-report.html` embeds it ([dashboard](references/dashboard.md#plan-view)). (The Plan view shows what was declared; the run state read-out shows what happened.)

**attention item** — one entry of the dashboard's attention list, in one of three groups: `intervention` (the engine starts nothing more by itself), `recovering` (the engine acts alone, as in a cooldown) and `signal` (a measured threshold, never a verdict).

**attention kind** — the `kind` of an attention item: the condition it reports within its group, such as `failed_step` or `token_overshoot` in `intervention`, `deferred_cooldown` in `recovering`, and `deadline` or `checks_over_agent` in `signal` ([dashboard](references/dashboard.md#attention)). (The group says who acts next; the kind says what happened.)

**standing item** — an attention item that a fresh watch cursor finds on its first look, printed by `watch` as `attention standing <group>` because it may be hours old ([ohflow](references/ohflow.md#run-it)). (A standing item was already there; a new item arrived since the cursor's last report.)

**watch cursor** — `.watch.<name>.json` in a run directory or campaign root: what one named reader (`--cursor NAME`) of `ohflow watch` has already seen. It is observation state, not execution history.

**run notes** — `predictions.md`, `notes.md`, `retro.md` and `ground-truth.md` at the root of a fresh run directory: the orchestrator calibration before the run, manual interventions during it, the retrospective and the measured facts after it. They are outside every fingerprint.

**orchestrator calibration** — the orchestrator agent's own forecast of a run in `predictions.md`, written before it reads the estimate or any result ([operate-a-run](references/operate-a-run.md#keep-the-run-notes)). Plain *calibration* is the candidate objective kind. (The orchestrator calibration tests the orchestrator agent's picture of the run; the estimate forecasts from earlier attempts.)

**estimate** — the forecast `estimate.json` records before a run: per step a `p50` and `p80` of wall time, check time and tokens, and a median cost, from `n` attempts in the runs `--history` names, with `basis` and `confidence` ([ohflow](references/ohflow.md#estimate-a-run)). A percentile is not a guarantee, and a missing measurement is not zero.

**cost source** — `result.json` `cost_source`: where an attempt's model cost came from, one value per harness executor: `pi-catalog`, `claude-cli`, `durable-host`, `pi-cloud-worker`, `subscription` (a known 0 that `ohflow table` prints) or `unpriced` (no known price, not a measured zero) ([transcripts](references/transcripts.md#tokens-and-cost)). (The model cost only; infra cost prices the container.)

**infra cost** — `result.json` `infra_cost`: the list price of the container memory and disk time a `pi-cloud`, `claude-cloud` or `codex-cloud` attempt held, from the Worker's container chronometer in `infra`, apart from its model `cost` ([harness executors](references/harness-executors.md#pi-cloud)).

**Cloudflare check** — `cloudflare.json` in the run directory: Cloudflare's own container meters for the run's Durable Objects, read before the exit report and again by `ohflow cloud-spend --run`. It flags an object billed well beyond the container time its attempt reported ([ohflow](references/ohflow.md#run-it)).

**cloud-spend** — `ohflow cloud-spend`: the verb that reads Cloudflare's own container meters, for one run (`--run`, which writes `cloudflare.json`) or for the whole account over a window (`--since`, `--until`). (It reads Cloudflare's bill; the container chronometer is the Worker's own count.)

## Monitoring a run

These terms come from [monitor-a-run](references/monitor-a-run.md), which the orchestrator agent follows. No code enforces them.

**bill** — the hand-over message that carries the dashboard URL: the objective kind, the price in cost scalars, the proposed spending caps, the run's worth and the user's one decision, logged as a `bill:` line ([monitor-a-run](references/monitor-a-run.md#at-hand-over-write-the-bill)). (A bill prices a run before the work; the exit report records what it cost.)

**cost scalar** — one of the four measures of a run's price: agent tokens per model, wall time, the user's attention minutes, and money paid out to billed APIs and to Cloudflare. (A scalar measures; a spending cap limits it.)

**spending cap** — the most the user would spend on the outcome, one per cost scalar, set by the user or, when the user defers, by the agent's proposal. It acts only through a limit ([monitor-a-run](references/monitor-a-run.md#at-hand-over-write-the-bill)). (A spending cap limits money and attention; the engine enforces an execution timeout on one attempt and a token budget on the run.)

**stop-and-ask limit** — a threshold below a spending cap at which the orchestrator agent stops and asks the user, with a default for no answer. It serves only when the user can answer in the session while the step runs. (A stop-and-ask limit waits for the user; an execution timeout kills the step and asks nobody.)

**objective** — the wanted effect that a campaign or a run serves; its objective kind says how far agents may steer the work towards it. (A step objective is one display line on one step; the objective is what the whole run is for.)

**objective kind** — what the operator wants from this stretch of the work, a delivery or an empirical procedure, named in the bill with its reason. It sets what a check-in may do about a deviation, a design flaw or a miss ([campaign](references/campaign.md#intervention-by-kind-of-objective)); the engine never reads it. (The kind decides the check-in, not the construction.)

**check-in** — a poll, a phase boundary or a judge round, where the orchestrator agent or a judge re-reads the objective kind and decides whether to stop, change or continue work in flight. (A check-in judges the work; a gate check only tests a commit.)

**delivery** — an objective whose wanted effect is known and fairly deterministic, such as a feature, a fix, research or a specific output. It is open to revision at any time ([campaign](references/campaign.md#intervention-by-kind-of-objective)). (An empirical procedure keeps its procedure.)

**empirical procedure** — an objective that tests a hypothesis, such as an A/B test, by putting a control arm and an experiment arm through one procedure, fixed once committed; only a deviation stops it ([campaign](references/campaign.md#intervention-by-kind-of-objective)). (A delivery may change course.)

**deviation** — work that left its plan, such as a step that ignored its brief; the fix is to redo it as planned. It is the only ground for stopping an empirical procedure. (The plan stands; the work strayed.)

**design flaw** — a plan that is itself wrong, such as a gate that tests the wrong file. The fix is to change the plan; in an empirical procedure that change restarts every arm. (The work followed a plan that was wrong.)

**miss** — a result that misses the objective although the plan was right and followed. A delivery may replan; in an empirical procedure the miss is the result. (A miss is information, not a mistake.)

**intervention** — an upper rank's stop or change of work in flight, bounded by the objective kind. The attention group `intervention` marks a run that the engine will not advance by itself. (The group marks where an intervention is needed; the intervention is the act.)

**move** — one action by which the orchestrator agent changes the course of a running agent, such as `send`, `interrupt` or `close` on a session; how the agent runs decides the moves it allows ([steer-a-run](references/steer-a-run.md#the-moves)). (An intervention is the decision to stop or change work; a move is the command that carries it out.)

**recorded failure** — one dated failure of an agent role on one kind of box, with the move that answers it, in the table of [steer-a-run](references/steer-a-run.md#recorded-failures-and-the-move-for-each). (A recorded failure is a lesson for the next brief; a counted failure is one execution the engine counts toward exclusion.)

**stop rule** — the condition, set before a step starts, at which its work ends early: an engine limit such as the execution timeout, or a sign the orchestrator agent watches for, such as no new commits. (A stop rule ends a step that has stopped paying; the gate judges the step's result.)

**phase boundary** — the moment the last step of a phase reaches a final state, where the orchestrator agent asks whether, knowing what it knows now, it would start this run ([monitor-a-run](references/monitor-a-run.md#at-each-phase-boundary-take-the-critical-look)). (The engine writes `phase_settled` at the same moment; the boundary is the agent's checkpoint, not an engine event.)

**bad trade** — a "no" to the phase boundary question, or a spending cap the run will pass, reported in two sentences: the trade as it stands, then the correction with its default if the user defers.

**teach-back** — one question that asks the user to choose or to predict, asked after a doubtful "yes" on scope, effort, budget or stop; a correct answer closes the check. (A teach-back checks one answer; a walk-through rebuilds understanding.)

**walk-through** — a sequence of 2 to 10 messages, opened after a stated overload or a missed teach-back; each holds one fact and one question, and the last ends in the user's decision ([monitor-a-run](references/monitor-a-run.md#each-reply-from-the-user-check-understanding)).

## The roll call and the campaign

**roll call** — the live-agent test: most agents write who they are into a file, commit it and report. Owner: `ohflow rollcall` ([CONTRIBUTING](CONTRIBUTING.md#testing-with-live-agents)).

**test scenario** — one pattern of the roll-call workflow: `single`, `fanout`, `relay`, `merge`, `retry`, `review`, `campaign` or `silent`.

**test case** — one test scenario on some harness executors at some scale, written `scenario:harness-executors[:count][:option]`: a `RollCallCase`. `rollcall --cases` runs a list of them in place of a matrix.

**test matrix** — a named table of test cases: `smoke`, `quick`, `full` or `liveness`, which `rollcall --matrix` runs and `rollcall --list` prints.

**campaign** — a design document or a spec bundle delivered milestone by milestone, one workflow per milestone, with a fresh judge agent after each. The `ohflow campaign` verbs name its module with `--campaign` ([campaign](references/campaign.md)).

**spec bundle** — the folder `ohflow construct --bundle` reads: `bundle.md`, an optional `contracts.md` and one milestone spec per milestone, written by the orchestrator agent. Owner: `construct.py` ([construct](references/construct.md#the-bundle)). (The specs live in many places; construct reads only the bundle.)

**bundle header** — the field lines above `bundle.md`'s first `##` section: `integration branch` (default `campaign/<name>`), `kind`, `judge harness` and `judge tier` ([construct](references/construct.md#bundlemd)). (The header configures the campaign; the other sections become its charter.)

**milestone file** — `milestones/<id>/milestone.json`, which `construct` writes: the workflow pattern, the steps with executor, box and tier, and the commands, from which each round builds the workflow. (The milestone spec stays fixed; a REVISE changes the milestone file.)

**step placement** — the `box`, `harness`, `tier` and `durable` lines of a milestone spec, for the milestone or one pattern role, from which `construct` picks each step's executor ([construct](references/construct.md#the-executor-comes-from-the-box-and-the-harness)). (Placement says where a step runs; the workflow pattern says how steps are arranged.)

**workflow pattern** — how a workflow arranges its agents: single agent, relay, fan-out, fan-out with consolidation, fan-out under contracts, or implement and review. A milestone spec's `pattern:` line names one, `implement-and-review` by default ([workflow patterns](references/workflow-patterns.md)). (A pattern arranges agents; a phase groups steps under one barrier.)

**pattern role** — a step's position in a workflow pattern: `agent`, `implement`, `review` or `consolidate`, addressed by a milestone spec's `<role> <field>` lines. (A pattern role is where a step sits; an agent role labels its history.)

**agent role** — `AgentSpec.role`: the label estimates match an agent's history by, with its harness executor and model; `construct` sets it to the step id. The bare word *role* has no owner. (An agent role labels one agent; a pattern role is a position.)

**piece** — one step of a relay or fan-out pattern, named after the milestone spec's `### <name>` part it is built from; a fan-out declares it a unit on the unit path `piece`. (A piece is one contribution; the consolidator makes the pieces fit.)

**output worktree** — a milestone's worktree on its output branch `milestone/<campaign>/<id>`, one per workspace a step writes in, where merges land and mechanical checks run. (Each piece has its own branch; the output worktree is where they meet.)

**command placeholder** — `{base}` or `{<workspace>}` in a milestone spec's command. `{base}` is the commit the work started from, `{<workspace>}` that workspace's output worktree. No workspace may be named `base` ([construct](references/construct.md#acceptance-checks)). (Filled per run; the command text stays fixed.)

**rubric check** — a `- rubric:` acceptance line of a milestone spec: a condition no command decides, graded by the judge. (The judge grades a rubric check; a command decides a mechanical check.)

**campaign charter** — the file `Campaign.charter` names: the standard a campaign's work must meet. Every judge packet contains it, and a judge may not edit it.

**campaign contracts** — `contracts.md` in the campaign root (`Campaign.root`), or the file `Campaign.contracts` names: the interfaces parallel steps share, held as `Workflow.contracts`; no judge may edit it. Other uses of *contract* take a qualifier, such as *schema contract* or *contract test* ([campaign](references/campaign.md#write-the-contracts)). (Contracts fix the interfaces between pieces; a milestone spec fixes one milestone's target.)

**judge edit stash** — the git stash entry `judge edit to <path> on <id> rNN` holding a judge's edit to `contracts.md`, which the controller restores ([campaign](references/campaign.md#write-the-contracts)). (The stash keeps the edit for the operator; the contracts stay unchanged.)

**campaign controller** — the program that runs the milestones, asks for the judge and applies the decision: `CampaignController`.

**campaign lead** — the orchestrator agent or the operator, in the role of planning, watching and steering one campaign. The engine records only the lead's milestone revision grants. (A role in one campaign, not a third actor.)

**campaign status** — the state in `campaign-status.json`: `running`, `held`, `judging`, `paused`, `escalated`, `preflight_failed` or `delivered` ([campaign](references/campaign.md#run-it)). (Campaign scope; workflow runs and steps have their own statuses.)

**milestone** — one slice of a design with a milestone spec and acceptance checks: a `Milestone` with its `title`, its workflow, its spec and its `acceptance_checks`.

**milestone spec** — `milestones/<id>/spec.md`: one milestone's target, with its `source:` line, step placement, `## Scope`, `## Acceptance` and, with pieces, `## Steps`; the judge may not change it ([construct](references/construct.md#specmd)). (The spec is what the operator wants; a milestone spec cuts one deliverable from it.)

**milestone acceptance check** — a named mechanical command, `AcceptanceCheck.cmd`, that the controller runs after a milestone's workflow run, before the judge, with its own `cwd` and `timeout_s`; exit 0 passes ([campaign](references/campaign.md#land-in-several-workspaces)). (It checks milestone acceptance; a gate check checks a step attempt.)

**milestone round** — one cycle of running or resuming a milestone's workflow, checking acceptance and asking for a judge decision, numbered by recorded judgings. The bare word *round* means a milestone round. (A round can hold many step attempts.)

**fresh round** — a milestone's first round, the only one that starts a new run directory; every later round resumes it and is a *resumed round* ([campaign](references/campaign.md#run-it)). (A fresh round starts a run; a resumed round continues one.)

**campaign hold** — `campaign run --hold`: the first fresh round waits for `ohflow go`; a later milestone's first round or a REVISE round waits when its estimate runs half over the first round's minutes ([campaign](references/campaign.md#run-it)). (A campaign hold holds rounds; a held workflow run is one run.)

**round pilot** — `campaign run --pilot`, which implies `--hold`: a fresh round whose workflow declares units runs its pilot first and then holds ([campaign](references/campaign.md#run-it)). (The pilot of one round; a single run's pilot is `run --pilot`.)

**campaign pid record** — `campaign.pid`: the pid that the process running the campaign writes when it starts, which `campaign run --detach` prints ([campaign](references/campaign.md#run-it)). (The campaign pid names the campaign's own process; the launched pid can name a wrapper.)

**finishing milestone** — a milestone added at a campaign's end, such as a smoke test when a user drives the product through a CLI verb or MCP tool ([campaign](references/campaign.md#finishing-milestones)). (A finishing milestone tests the whole product; a mechanical check tests one change.)

**milestone revision** — a judge's permitted edits to milestone inputs, which the controller commits after a valid `REVISE` so the workflow resumes against them. (Changes the work definition; a step retry starts another attempt.)

**milestone revision budget** — how many milestone revisions the controller may commit and continue automatically: `Milestone.max_revisions`, else `Campaign.max_revisions` (default 2), plus recorded revision grants. (Distinct from step retry and execution-start budgets.)

**milestone revision grant** — an addition to a milestone's revision budget, recorded through `ohflow campaign grant --milestone ID --revisions N`, which reopens an escalated milestone ([campaign](references/campaign.md#run-it)). (Adds allowance; does not itself restart execution.)

**campaign escalation** — the controller stopping milestone progression and recording a reason, such as a judge's `ESCALATE`, an invalid judge result, a refused `PASS` or a spent revision budget ([campaign](references/campaign.md#what-the-controller-refuses)). (Distinct from a paused workflow run awaiting recovery.)

**campaign estimate** — `ohflow campaign estimate`: the forecast of the milestones that have not landed, each run estimate scaled by the median number of REVISE rounds, an upper bound ([campaign](references/campaign.md#estimate-the-campaign)). (Campaign scope; see also: estimate.)

**judge** — the fresh agent that passes a milestone, revises it or escalates one question, in a workflow run of its own under `Campaign.judge_execution_timeout_s` ([campaign](references/campaign.md#the-judge)).

**judge packet** — `judge/rNN/packet.md`: the milestone spec, workflow evidence, acceptance check results and earlier decisions one judge reads. The bare word *packet* means a judge packet; another use carries a qualifier, such as the dashboard's *evidence packet*.

**judge handover** — `judge-handover.md`: the note one judge leaves for the next milestone's judge, with a title, a lead paragraph and the core headings of a step handover ([campaign](references/campaign.md#the-judge)).

**judge decision** — the JSON the judge returns: `PASS`, `REVISE` or `ESCALATE`, under the key `decision`. The campaign controller checks it before it acts.

**finding cause** — the word a judge gives each finding's cause, `cause` in the judge decision: `brief`, `distribution`, `tool_policy`, `gate`, `product` or `spec`, which escalates ([campaign](references/campaign.md#the-judge)). (A cause says why a milestone fell short; finding severity sorts a reviewer's findings.)

**REVISE price** — what a judge's REVISE costs the operator: one more milestone round, which the judge's brief prices at the minutes of the run's estimate ([campaign](references/campaign.md#the-judge)). (The judge applies the price; the controller enforces the milestone revision budget.)

**milestone acceptance** — approval of a milestone's work: a valid judge `PASS`, a finished workflow run with every step passed or cached, and every milestone acceptance check passing; milestone landing records it.

**campaign integration branch** — `Campaign.integration_branch`, the Git branch that accumulates accepted milestone commits, one of that name in each workspace; the one-repository form creates it at `integration_base` ([campaign](references/campaign.md#land-in-several-workspaces)). (Campaign scope; see also: milestone output branch.)

**milestone output branch** — `Milestone.output_branch`, the optional Git branch holding a milestone's work for acceptance and landing, one name in each workspace the milestone writes in. (Milestone scope; see also: campaign integration branch.)

**fan-out output branch** — the branch where a hand-written fan-out under contracts (`workflows/contract_fanout.py`) merges its pieces: `fanout/output`, or `<branch_prefix>/output`. It plays the part of a constructed milestone's output branch and output worktree. (The campaign integration branch is the campaign's alone.)

**transport branch** — the branch `ohflow/<harness executor>/<attempt key>` on the workspace's `origin` that carries one step's start commit to an ssh box or a cloud box and its result back ([harness executors](references/harness-executors.md#durable)). (Neither a milestone output branch nor the campaign integration branch.)

**milestone landing** — recording a milestone as accepted and, with an output branch, moving the campaign integration branch to the output commit in every workspace it wrote in, or in none ([campaign](references/campaign.md#land-in-several-workspaces)). (The judge decision allows a landing; the landing moves the branches.)

## The operator layer

**operator** — The person who installs ohflow and owns its settings, its accounts and the decisions of its runs; “the user” where it means that human. (The campaign lead is a role in one campaign, held by the operator or the orchestrator agent.)

**orchestrator agent** — the agent the operator works with: it writes the workflow or spec bundle and the bill, and starts, watches and steers the run ([orchestrator](references/orchestrator.md)). Bare *orchestrator* means it; `ohflow` is the program. (The engine runs the steps it is given; the orchestrator agent decides which run and when one stops.)

**upper rank** — whoever may stop or change work in flight: the orchestrator agent, a judge or the operator. The kind of objective sets how far it may go ([campaign](references/campaign.md#intervention-by-kind-of-objective)). (A step's own agent is never an upper rank.)

**operator settings** — the shipped `ohflow.settings.json` with the operator's git-ignored `ohflow.settings.local.json` merged over it (`settings.py`); `OHFLOW_SETTINGS` names another local file ([boundary](docs/release/boundary.md#the-settings)). (Operator settings configure ohflow; Worker settings configure the Worker pair.)

**pi provider settings** — the operator settings `pi.api_key_env` and `pi.base_url`, keyed by provider: the key's variable (else `<PROVIDER>_API_KEY`) and the endpoint, for `pi` steps that `construct` builds (`patterns.model_config`). (A hand-written workflow sets both in its model configuration; `durable` and the pi-cloud Worker hold their own keys.)

**Worker settings** — the shipped `worker/pi-cloud.settings.json` with the operator's git-ignored `worker/pi-cloud.settings.local.json` over it: `name`, `account_id`, `url`, `git_owner`, `git_identity`, `skills_repo`, `skills_root_skill` and `snapshot` ([settings](references/pi-cloud-worker.md#settings)). (Worker settings configure the Worker pair; operator settings configure ohflow.)

**house rules** — `references/local.md`: the operator's own git-ignored instructions for agents, which `SKILL.md` tells an agent to read when present. (House rules are text an agent reads; house checks are gate checks.)

**house checks** — the gate checks the operator settings turn on for every committing agent, appended to `clean_commit_checks`: today only `no_ai_attribution`, behind `commit_checks.no_ai_attribution`, base value `false`.

**judge model** — the operator setting `campaign.judge_model`, the tier or model of `default_judge`, which a `Campaign` that names no judge uses; base value the tier `heavy` ([campaign](references/campaign.md#the-judge)). (A campaign or milestone that names its own judge does not read it.)

**escalation marker** — the heading that opens `ESCALATION.md` when a campaign escalates, from `operator.escalation_marker`; the default is "ACTION NEEDED FROM THE OPERATOR".

**escalation command** — the command the controller runs when a campaign escalates: the campaign's own `on_escalate`, else the setting `operator.on_escalate`, with `{file}` replaced by the escalation file's path. (A campaign that `construct` writes names none, so the setting carries its escalations.)

**the four homes** — where a piece of ohflow lives: ohflow core, the operator layer, shipped examples (`examples/setups/`) or private ([boundary](docs/release/boundary.md)). A piece is core when a newcomer on a clean machine needs it to run an advertised harness executor.

**leak scan** — `tests/test_boundary_01_no_local_values.py`: it fails when a committed core file names a real home directory or a token from the operator's private list ([boundary](docs/release/boundary.md#the-leak-scan)). (It finds a leaked value; a missing piece shows only on a clean machine. The *release leak scan* checks the extracted release package.)

**recorded evidence** — `docs/`, `.impeccable/`, `references/examples/` and `tests/fixtures/`, kept as recorded. The leak scan skips them, so the release extraction reviews them by hand.

## Handovers

**step handover** — `handover.md`, written by a producer step's agent for a receiving agent, following its handover spec, `Step.handover`. The `handover_written` gate check requires it. [Contract](references/step-handover.md).

**consumes** — `Step.consumes`: the producer steps whose step handovers an agent receives, each also named in `depends_on`; the consumed content enters the receiver's step fingerprint.

**handover spec** — `HandoverSpec`: the `audience`, the `extra` headings beside the core questions, and the size limit `max_chars` that govern one step handover.

## Sessions

**session** — one named pi conversation that the orchestrator agent opens with `ohflow session open NAME --cwd DIR` (optional `--model` and `--thinking`), sends turns to and closes for good ([sessions](references/sessions.md)). (A step's agent answers to the engine and its gate; a session answers to the orchestrator agent after every turn.)

**session controller** — `ohflow session` (`sessions.py`): it keeps up to three sessions open for the orchestrator agent and wakes it when a turn finishes, on pi alone (`--harness pi`). (The engine runs steps fixed in advance; the orchestrator agent decides after each turn.)

**session record** — the directory named by `--dir`: `events.jsonl`, the append-only truth of the events `opened`, `sent`, `queued`, `delivered`, `interrupted` and `closed`, and one folder per session ([record](references/sessions.md#the-record)). Every verb derives the state from it.

**turn** — one message to a session and the process that answers it: `--message TEXT` or `--brief FILE` on `open`, the text or `--file` on `send`. It ends when that process exits; `<n>.exit.json` records how, and a turn without it is delivered as lost.

**delivered turn** — a finished turn that `ohflow session wait` has handed to the orchestrator agent, once, recorded as a `delivered` event in the session record ([verbs](references/sessions.md#the-verbs)). (A delivered turn is one session turn handed over; a delivery is a kind of objective.)

**interrupt** — `ohflow session interrupt NAME`: it stops one session's running turn and keeps the conversation for the next `send` ([verbs](references/sessions.md#the-verbs)). (An interrupt throws away one unfinished turn; `close` ends the session for good, and `close --force` interrupts a running turn first.)

**queued message** — a message that `send` holds as `turns/queued-<id>.md`, noted `queued` in the session record, while the session runs a turn or holds earlier queued ones. (A queued message waits for a turn; a message to an idle session starts one at once.)
