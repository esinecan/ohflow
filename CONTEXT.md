# ohflow terms

One term has one meaning here. Where English gives a word several meanings, each meaning has its own name, and the plain word belongs to one owner. Every other file uses these names.

This file is the one source of the definitions. `python docs/glossary_sync.py --write` copies them into [the written glossary](docs/glossary.md) and [the glossary map](docs/glossary-map.html). `python tests/check_docs.py` fails when either copy disagrees with this file, when the public vocabulary surface of the code changed after the last vocabulary review, and when an entry of the recorded surface stands in no backtick span of this file, alone or after a qualifier (`max_iterations` or `AgentSpec.max_iterations`; `run --hold`), unless `docs/vocabulary-unnamed.json` lists it with a one-line reason. That surface is the workflow and campaign dataclass fields, the listed constants (a number counts by its constant's name), the run-log statuses and events, the campaign states, the CLI verbs and the flags of each verb, the keys of `ohflow.settings.json` and of `worker/pi-cloud.settings.json` (an empty object is a key of its own), the executor capabilities, the cost sources and the cloud end errors.

## The workflow

**workflow** — the general concept of arranged work. Use *workflow definition*, *workflow module* or *workflow run* when the distinction matters.

**workflow definition** — the configuration describing phases, steps and execution policies: the `Workflow` that a workflow module's `build(args)` returns, with its `phases`, its `worktrees` and workspaces, the `args` it was built from and its limits.

**workflow module** — the Python source that builds a workflow definition. A verb names it with `--workflow` and passes it `--args k=v`.

**phase** — a group of steps (`Phase.steps`) in a workflow that share a barrier and a failure policy. The phases run in order, and `run --only-phase NAME` runs one of them alone. The merge steps of a phase run first, one at a time, in workflow order, outside the concurrency limit. The other steps of the phase then run in parallel, and `max_parallel` limits how many run at once (`--max-parallel` sets the default and caps every phase); the slots go to the longest step first, by its p50 in the run's `estimate.json`, and a run with no estimate keeps the workflow order. The `mode` argument of the implement-review workflow selects a *driver mode* (`all`, `review` or `fix`). It does not name a phase. The parts of ohflow's own project plan are *stages*, such as Stage 1 in `docs/todo.md`, never phases.

**wave** — a group of a phase's steps that run at once: a phase of N steps under `max_parallel` P takes `ceil(N/P)` waves. In `/api/plan` each phase carries `waves`, and its `timeout_bound_s` is `waves` times its longest execution timeout; the ETA (`live.eta`) and the estimate count a phase's agent steps in waves of the median step. (A wave is a slice of one phase; a milestone round is one judge cycle.)

**failure policy** — `Phase.on_step_failure`, what a phase does with a failed step: `quarantine` (the default) records it as `quarantined`, `continue` keeps it `failed`, and `abort` stops the run and kills the agents still running. `Phase.min_success` (`all`, `any` or a number) counts passed and cached steps. A phase that misses it settles `deferred` when at least one step is deferred and none is `failed` or `timeout`, even if other steps are quarantined or skipped; otherwise it settles `failed`.

**step** — a named piece of work within a workflow phase, configured to run an agent, execute a `command` in its `shell` (`sh` or `cmd`), perform checks, or merge the branch `merge_branch` with its `merge_message`.

**unit** — `Unit` in `Workflow.units`: one item that a workflow runs over, such as one friction family. It has an `id`, a unit path and a `size`. The steps that do its work name it in `Step.unit`. A step with no unit is a *shared step*, which runs once per run whatever the unit count.

**unit path** — `UnitPath` in `Workflow.paths`: one kind of unit that takes its own route through the workflow, so its cost per unit differs from the other kinds. A friction family with one occurrence and a family with a live probe are two unit paths. The CLI and the dashboard print it as *path*.

**coordinate** — the address of a step, `NN.phase-name/NN.step-id` with both numbers 1-based, such as `02.batch-a/01.c9-spill`. The run log, the board and the gate report all key on it, and a verb's `--step` takes it, or a step id that names one step.

**step objective** — `Step.objective`: one display line of at most 120 characters that says what a step is for. It is outside the step fingerprint and outside the position block, so it never instructs an agent. `validate` warns when an agent step has none. (A reader's label for one step; the objective is what the whole run is for.)

**agent step** — a step of kind `agent`: one agent with one agent brief, started through one harness executor. It runs in its worktree, or in the default workspace when it has none. A campaign's judge step has no worktree and runs in the campaign repository. (A command step runs a command and no agent.)

**gate step** — a step of kind `gate`: it runs only its gate and starts no agent.

**agent brief** — the instructions an agent reads first, written to the attempt's `brief.md`. `claude` and `codex` get a bootstrap prompt that only says where it is; `pi`, `durable` and the cloud executors send the brief's text as the first message. A step on an ssh box or a cloud box gets a copy whose local paths are rewritten to its remote workspace, and a step on the local box reads the brief as written. The short form is *brief*.

**position block** — the text the engine writes to `position.md` and puts before the agent brief (`coords.render_position`), which `ohflow position` prints for one step: run, phase, step, attempt, coordinate, worktree, branch, base commit and write scope; the other workspaces; the contracts; the merges of earlier phases; the quarantined branches; the received handovers; the steps running beside it and after it; its gate; the schema contract; its own handover instructions; and, from the second attempt, the previous attempt's failures and handover. (The position block says where the step stands; the agent brief says what to do.)

**agent** — an LLM program that a harness executor starts. The dashboard draws one *card* for each step. A card is not an agent.

**harness** — the program around a model that runs the agent loop: model calls, context and tool calls. The pi CLI, the Claude Code CLI and the Codex CLI are three harnesses. Cloudflare's `ContainerHarness` and `PiHarness` are classes of the `agents` package that run a harness; the Durable Objects `StepAgent` and `CliAgent` each hold one, and ohflow text names them only by class name. (A harness runs the loop; a harness executor starts and stops one.)

**signed-in harness** — a harness that runs on a subscription login instead of an API key: Claude Code or Codex. `claude` and `codex` use the login on this machine. `claude-cloud` and `codex-cloud` use a login the pi-cloud Worker holds and writes into request headers outside the container. `pi` takes its API key from the workflow and is not signed in. The executor capability `signed_in` marks only `claude` and `codex`.

**harness executor** — the component that launches, monitors, collects results from and stops a harness: `pi`, `claude`, `codex`, `durable`, `pi-cloud`, `claude-cloud` or `codex-cloud`. Each agent step names its harness executor in `AgentSpec.harness_executor`, because ohflow has no default. A harness executor is not a model. Owner: `harness_executors.py`.

**runner** — the child process a harness executor starts for one agent invocation: one `<executor>_runner.py` module per harness executor in `scripts/ohflow/`, with `cli_cloud_runner.py` holding the part that `claude-cloud` and `codex-cloud` share. It starts the harness or talks to its remote end, writes the files in the attempt's `logs/` directory and writes the attempt result. When it dies before the result, the record is a rebuilt record. (The harness executor lives in the run supervisor; the runner is its child for one attempt.)

**model configuration** — the `ModelConfig` of an agent step: a model tier or a model name, `base_url`, `api_key_env` and `params`, the closed set of keys each harness executor accepts, such as pi's `thinking`.

**model tier** — the rung of the inference ladder a step needs, `heavy` or `light`, named in `ModelConfig.model` in place of a model. The operator settings `tiers.<tier>.<harness executor>` map each tier to a model per harness executor, and validation and the step's `spec.json` use the resolved model. A model name there passes through untouched. Owner: `tiers.py`.

**execution preset** — a harness executor with its default model configuration and cost basis, as the roll call pairs them. No code names it. (An execution preset picks an executor and a model; a tool preset picks an agent's tools.)

**agent execution configuration** — the combined settings governing how an agent step runs: harness executor, execution target, model configuration, agent profile, agent tool policy, agent brief, skills, and execution limits (stall timeout, execution timeout, command time cap and iteration limit). Which settings are supported or enforced depends on the executor.

**agent profile** — the harness setup an agent starts in: the instructions, hooks, memory, skills and inherited tool/MCP configuration it loads, such as the usual setup or a hermetic setup. `claude` and `codex` take it, and `validate` refuses the field `agent_profile` on every other harness executor. (`durable` names its box in `AgentSpec.box`, never here.)

**executor capability** — one feature a harness executor declares in `harness_executors.py`: `stall_timeout`, `carry_context`, `signed_in`, `profile`, `box`, `tools_only` or `reattach`. `validate` refuses a step that needs a feature its harness executor lacks, except `tools_only`: only `claude` declares it, and `pi` and `durable` honour `tools.only` without it. The engine reattaches only a harness executor that declares `reattach`. (A capability is declared; effective agent tools are what one attempt received.)

**execution target** — the kind of place where a step's commands run: the local box, an ssh box or a cloud box. The harness executor and `AgentSpec.box` fix it together, and no field names it. (The kind of place; a box is the one machine an attempt uses.)

**box** — the one machine or container where an attempt's commands run and its working directory sits. It has three kinds. The *local box* is this machine, named `local`, and every executor except the cloud ones can run on it. An *ssh box* is a machine the operator owns and keeps, reached by its ssh host alias, such as `buildbox`; only `durable` runs there. A *cloud box* is a container started from the default snapshot for one attempt and stopped after it. A `durable` step names its box in `AgentSpec.box`, and the setting `durable.box` names only the default box that the preflight and the routes that name no box use. A spec's `box:` line names the local box (`local`), an ssh box by its alias, or `cloud`, because every cloud attempt gets a box of its own. Harness-guide uses the word for any PC. (An ssh box keeps its state between steps; a cloud box lasts one attempt.)

**durable host** — the Node program `host/ohflow-step.mjs` that runs one `durable` step's pi-durable session on its box, with that box's own keys for the providers the setting `durable.providers` lists. ohflow installs it there at the step's launch, into `~/.pi-durable/ohflow-host/<version>/`; the version is the first 16 hex digits of the SHA-256 of its files, so a changed host installs beside the old one (`durable_host.py`). The bare word *host* has no owner. (It plays the part for `durable` that the pi-cloud Worker plays for cloud steps; the old copy in `pi-durable-host/cli/` is not what ohflow runs.)

**tether** — the durable host's watch on its own connection (`host/src/tether.mjs`). On an ssh box it writes one byte to stderr every 2 s and exits with code 70 when a write fails, so the host and its command end within seconds of a dropped connection. On the local box it writes nothing and exits only when stdout or stderr fails. (A kill ends a local host directly; the tether ends a remote one.)

**pi-cloud Worker** — the Cloudflare Worker that owns every cloud step. It holds one Durable Object per attempt (`StepAgent` for pi, `CliAgent` for Claude Code and Codex), and the `SkillsMirror`, `SnapshotBuilder` and `CodexLogin` objects; `CodexLogin` holds the Codex login that `codex-cloud` uses. The bare `pi-cloud` names the harness executor, the local half, and the deployed Worker is the pi-cloud Worker whatever its `name` says. Worker with a capital W means a Cloudflare Worker; ohflow calls no agent and no thread a worker.

**Worker pair** — the pi-cloud Worker and its code mode Worker, deployed together as `<name>` and `<name>-codemode` from `worker/` by `worker/scripts/deploy.mjs`. The Worker setting `name` defaults to `pi-cloud`; another `name` deploys a second pair with its own Durable Objects, default snapshot and secrets, and its address goes to `worker/.pi-cloud-urls.json`. (A pair is one deployment; its pi-cloud Worker is the half that runs steps.)

**Durable Object** — Cloudflare's stateful object. One per attempt holds that attempt's cloud operation and transcript and starts its box. It is never shortened to *durable*, which names the harness executor. (The object holds state; the box runs the commands.)

**cloud harness executor** — `pi-cloud`, `claude-cloud` or `codex-cloud`: runs a step in a Durable Object of the pi-cloud Worker, on a cloud box. The operator settings `pi_cloud.url` (the Worker's address when `OHFLOW_PI_CLOUD_URL` is unset), `pi_cloud.providers` (the providers a `pi-cloud` step may name) and `pi_cloud.mcp_servers` (the box's MCP servers, for validation) configure them. (`durable` runs on the local box or an ssh box, both owned by the operator, with no cloud provider.)

**container** — the Cloudflare container that is a cloud step's box: `standard-1`, with 4 GiB memory and 8 GB disk. It starts from the default snapshot, and Cloudflare bills its memory, disk and CPU for every second it runs; the container chronometer counts memory and disk. (A container is one kind of box; the Durable Object that starts it holds the attempt's state.)

**default snapshot** — the saved filesystem every cloud step's container starts from. `SnapshotBuilder` builds it from the recipe `worker/snapshot/recipe.mjs` in this skill, on `cloudflare/debian-trixie`. The recipe pins the CLI versions and the repo commits; the base image and its Debian packages are unpinned. It holds the tools, the `pi`, `codex` and `claude` CLIs, the npm MCP servers with those the Worker setting `snapshot.mcp_servers` adds, the repos the operator's snapshot settings name, and no credential. It expires 30 days after its last restore. (A filesystem to start from; the run state read-out is a JSON view of a run.)

**snapshot key** — the first 16 bytes of the SHA-256 of the recipe's image name and steps, so one recipe gives one key. `pi_cloud_start` names the key of the snapshot the attempt started from. A new snapshot pin or CLI version in the recipe gives a new key. While that key's snapshot is not built, a step starts from the fallback snapshot. (It identifies a recipe version; the stored snapshot id identifies one built filesystem.)

**snapshot pin** — the full commit id that `snapshot.skills` or a `snapshot.repos` entry of the Worker settings names, at which the default snapshot clones that repo. `node scripts/pins.mjs` moves each one to the head of its repo's `main` (`--dry-run` only prints), and a moved pin takes effect with the next deploy and snapshot build. The bare word *pin* has no owner. (A snapshot pin fixes a repo in the snapshot; a skills pin fixes the skills one step reads.)

**fallback snapshot** — the newest snapshot built under an earlier snapshot key, which a step starts from while the current key's snapshot is not built (`SnapshotBuilder.current()`). `GET /snapshot` then answers `built: false` although steps start, and `POST step` answers 503 only when no snapshot is built at all. An attempt keeps the snapshot it started from. (The fallback snapshot is an older build of the recipe; the default snapshot is the current one.)

**successor snapshot** — planned, not built: a snapshot saved from a finished step's box, which later steps start from. (The default snapshot is built from the recipe; a successor snapshot comes from a box after its work.)

**remote workspace** — the directory where the agent of a step on an ssh box or a cloud box works. On a cloud box it is `/workspace/repo`, a clone of the step's start commit, and `/workspace/out` for the files the runner fetches back. On an ssh box it is `<dir>/work`. The adapter rewrites every path in the agent brief to it. A `durable` step on the local box works in its worktree and has no remote workspace. (A worktree is the step's local Git directory; the remote workspace is its copy on another box.)

**sandbox** — a harness's own confinement of the agent's commands, such as Codex's sandbox mode. ohflow runs Codex with `danger-full-access`, and no harness executor confines the shell of an agent on the local box, so it sees this machine's whole filesystem. `pi` (`ohflow-guard.ts`) and the durable host (`host/src/tools.mjs`) only block their `edit` and `write` tools outside the step's write scope. `worker/sandbox/` keeps pi-codemode's class name `CodemodeSandbox`. (A box isolates a remote agent from this machine; ohflow does not call that isolation a sandbox.)

**skills mirror** — the `SkillsMirror` Durable Object of the pi-cloud Worker. It keeps the newest commits of `main` of the skills repository in its own SQLite. A step that names skills syncs it when the step starts (`pinSkills` in `worker/src/skills-feed.mjs`): the mirror asks GitHub for the head of `main`, copies that commit when it is new to the mirror, and the step pins that commit in its step record. A `pi-cloud` step mounts only the skills it names, read-only, at `/workspace/.agents/skills`. The box of a `claude-cloud` or `codex-cloud` step fetches the skills it names into `/opt/agent-skills` when its container starts. (A `claude-cloud` or `codex-cloud` step that names no skill reads `/opt/agent-skills` in the default snapshot instead, which holds the repo of the Worker setting `snapshot.skills` at its pinned commit, and is an empty folder when that setting is `null`, its base value.)

**skills pin** — the commit of the skills repository's `main` that a cloud step fixes when it starts (`pinSkills` in `worker/src/skills-feed.mjs`): the step record keeps it as `{sha, names}`, and the step reads the skills it names at that commit for its whole attempt. (A skills pin fixes one step's skills; a snapshot pin fixes a repo in the default snapshot.)

**cloud operation** — the work one Durable Object does for one attempt: it clones the start commit into the remote workspace, runs the agent, pushes the transport branch and keeps the transcript. A reattach posts `step` again with the same attempt key, which changes nothing. A retry gets its own attempt key, operation, object and branch. (The attempt is ohflow's record; the cloud operation is the Worker's work for it.)

**abort answer** — what the pi-cloud Worker answers to `POST abort`: `operationId`, `aborted`, `container` (what stopping the box returned) and `last_look`, a read-out of the box of at most 8000 characters taken within 10 s before the stop. The `CliAgent` of `claude-cloud` and `codex-cloud` adds `usage`, the tokens it had counted. The runner keeps the answer to its own abort in `runner-abort.json`, and an attempt kill keeps its answer in `kill-abort.json`; when the event stream carried no token count, the attempt's tokens come from the newest abort answer. (The abort answer is the box's last state; the attempt result is ohflow's record of the attempt.)

**replayed event** — a line of a `pi-cloud` step's event stream marked `replayed: true`. Its `GET events` sends the transcript so far as replayed events before the live ones, so a runner that reattaches reads the whole conversation, and a tool call still running when the request arrives gets a fresh `tool_execution_start` after the replay. The `CliAgent` of `claude-cloud` and `codex-cloud` replays nothing: it streams the live events and sends untagged transcript lines only after the end. (A replayed event happened before this connection; a live event arrives during it.)

**attempt key** — the portable name of one attempt: the coordinate with each run of characters outside `[A-Za-z0-9._-]` turned into one `-`, then `-a<NN>`, then the first 8 hex digits of the SHA-1 of the attempt directory. It names the attempt's step folder on a `durable` box, its transport branch, and its cloud operation and Durable Object. `remote_git.attempt_key` builds it. (It holds the attempt number, so it names an attempt, not a step.)

**container chronometer** — `infra` in an attempt's `result.json`: the Worker's own count of the container time the attempt held, for memory and disk. Infra cost prices it. (The Cloudflare check reads Cloudflare's own container meters, which lag by minutes.)

**cloud end error** — the error a remote runner records when its operation ends without a done answer: `host_lost` (the event stream ended with no end event), `unanswered: <reason>` (such as `container_lost`, when the container stopped), `push_failed` (the Worker could not push the transport branch), `clone_failed` or `skills_failed` (the box of a `claude-cloud` or `codex-cloud` step could not clone the start commit or fetch the step's skills) or `fetch_back` (this machine could not fetch the transport branch), or `<name>: <message>` from a `pi_cloud_error` or `durable_error` event. `durable` records only `host_lost`, `fetch_back` and the event form. Only `host_lost` leads to a reattach; the others are ordinary failures under the retry rules. (`host_lost` also covers a lost Worker, although *host* names no owner.)

**agent skills** — `AgentSpec.skills`: skills named for an agent explicitly. `pi` loads them from `AgentSpec.skills_dir`. `durable` resolves the names on its box. `pi-cloud`, `claude-cloud` and `codex-cloud` take them from the skills mirror, at the commit the step pins when it starts. Each of these five refuses whichever of the two fields it does not use. `claude` and `codex` refuse both fields, so they have only the skills their agent profile holds.

**agent tool policy** — the declared settings for which tools an agent step should receive, `AgentSpec.tools`: built-in tool selection, browser and sub-agent options (`enable_browser`, `enable_sub_agents`), and MCP tool selection over the servers `mcp_config` names. Support and enforcement depend on the harness executor and agent profile; where the harness executor enforces it, the agent is built with those tools only, so tool policy is the gate. (Part of agent execution configuration; see also: effective agent tools.)

**tool preset** — `ToolPolicy.preset`: the named starting set of built-in tools that an agent tool policy narrows with `only`, `allow` and `block`; `default` unless the step names another. Every harness executor refuses a preset other than `default` today. (A tool preset picks an agent's tools; an execution preset picks an executor and a model.)

**effective agent tools** — the tools actually exposed to an agent invocation, resulting from the harness, agent profile, supported tool-policy rules and connected external systems. An unavailable listing means unknown, not empty; exposure alone does not establish successful authentication or use. (The resulting tool set; see also: agent tool policy.)

**MCP tool blocklist** — a list of `server.tool` patterns, owned by the workflow, that removes matching tools from the configured MCP tool set. An empty blocklist removes nothing.

**MCP tool allowlist** — an explicit selection of MCP tools by `server.tool` pattern, narrowing the configured tools that the blocklist leaves. An empty allowlist applies no additional restriction; it does not mean no MCP tools.

**worktree** — the Git working directory a step edits, named by `Step.worktree` and configured by `WorktreeSpec`. It sits in one workspace, which `WorktreeSpec.workspace` names. It is created from `WorktreeSpec.base`, and `base_sha_mode` records its base commit as `head` or as the `merge_base` with that base. It is a step's isolated, revertible working area, for code or any other files: `revert` removes it with its branch. A worktree separates working files; it is not a security sandbox.

**workspace** — `Workspace` in `Workflow.workspaces`: one git repository that a workflow works on. It has a `name`, a `path`, a `base_branch`, an optional `remote` (the URL of its `origin`) and an optional baseline command. An agent step writes in the workspace of its worktree. A step on the local box may also read the other workspaces; a step on an ssh box or a cloud box holds its own workspace alone (`carried_by_git` in `workflow.py`). (A workspace is a repository on the operator's machine; the remote workspace is its copy on another box.)

**owned workspace** — a workspace with `owned=True`, for work that is not code. When a run starts and its folder is absent or empty, ohflow creates the repository with `git init`, the base branch and one empty root commit, and sets `origin` to `remote`; a folder that holds files and no repository is refused (`worktree.py`). `revert` removes its worktrees and branches and keeps the repository. (ohflow creates an owned workspace's repository; any other workspace must already be one.)

**default workspace** — the first workspace of a workflow: a step with no worktree runs there, and `Workflow.repo` and `Workflow.base_branch` read as its path and base branch. A workflow that sets `repo`, `base_branch` and `baseline_cmd` and no `workspaces` has only this one, named after the repository's folder. (Unplaced work runs here; work in any other workspace names it.)

**baseline command** — `Workspace.baseline_cmd`, the `baseline` line of a bundle: the command that must exit 0 on the workspace's clean base branch before a run starts. The engine runs each one in its own workspace after preflight has passed; `ohflow preflight` runs none. (It proves the base is green before any step changes it; a gate check tests one step's commit.)

**write scope** — `Step.write_scope`: the glob patterns of the paths one step may edit. Two steps of one phase that write in one workspace may not have overlapping write scopes.

**launch method** — how the operating system starts a detached process: `direct`, `breakaway` or `wmi`. It is not a harness executor and not a model. Owner: `detach.py`.

**spec** — the operator's written statement of what they want made: an issue, a ticket, a design document or a folder of notes, wherever it lives. ohflow turns specs into outputs: the orchestrator agent reads them with its own connectors and writes them into a spec bundle, and every objective kind starts from one. The dataclasses keep their code names, such as `AgentSpec` and `WorktreeSpec`, and carry no glossary meaning. (A spec is the operator's; a milestone spec is what `construct` reads for one milestone.)

**note** — only the `Step.note` field: one line of caption for the board and the dashboard. The files in the run directory are the *run notes*.

## One run

**workflow run** — one execution of a workflow definition, including later resumes that continue it. The short form is *run*.

**workflow run status** — the current operational condition of a workflow run, established from recorded history, supervisor liveness and preparation or exit records. Examples include `held`, `running`, `paused`, `finished`, `failed`, `crashed`, `interrupted` and `orphaned`. (Describes a run's condition; a workflow phase describes how work is grouped.)

**held workflow run** — a workflow run whose live supervisor awaits explicit release before engine execution starts: a newly prepared run, or the resumed run of a campaign round that a judge's REVISE starts. Its plan and dashboard may already exist before its first run-log event. `run --resume` cannot hold. (A wait before execution; see also: workflow release.)

**workflow release** — the instruction that lets a held workflow run proceed, issued through `ohflow go`. When a workflow module is available, the supervisor reloads and validates it before execution, incorporating edits made during the hold. Release can still end in a preparation failure. (Releases a held run; workflow resume continues existing execution history.) `go` refuses while the pilot still runs. `go --predictions FILE` writes the held run's `predictions.md` before the release, and refuses, sending no go, when `predictions.md` already holds predictions.

**pilot** — `run --pilot`: the workflow run that a held run makes before it waits for release. It runs the smallest unit of each unit path end to end, with the shared steps, in `<run-dir>/pilot`, on worktrees whose path and branch end in `-pilot`. A pilot unit does not count as done: the full run after release runs every unit.

**pilot projection** — `pilot.json` in the run directory: the cost of the full run, as the sum over the unit paths of the path's unit count times the cost the pilot measured for its unit, plus the shared steps once. Its time is the summed wall time of the attempts, so it is agent time, not elapsed time. `go` projects it again from the reloaded workflow module.

**finished workflow run** — a workflow run whose engine reached the end of the selected execution without aborting or pausing. Individual steps may still have failed or been skipped under the configured policies; `finished` alone does not establish that every step was accepted. (Engine completion, distinct from acceptance of all step outcomes.)

**engine** — `engine.py`, the scheduler inside the run supervisor. For each phase it computes the step fingerprints, marks matching steps cached, launches the rest under `max_parallel`, runs each step's gate and applies the failure policy. It writes the run log, `board.md` and the attempt directories. Each step other than a merge step runs in its own step thread. (The run supervisor hosts a run; the engine executes it.)

**step thread** — the engine thread that carries one step other than a merge step: its attempts, its gate and its retry decision, and it can set the run's abort. A merge step runs in the supervisor loop itself. (The engine schedules the steps; a step thread carries one of them.)

**run supervisor** — `supervisor.run_workflow`, the process that hosts one workflow run: it reserves the run directory, holds a fresh run until release, starts the dashboard (unless `--no-dashboard`; `--dashboard-port` fixes its port and `--open-dashboard` opens it), runs the engine and, once it has reserved the run directory, writes the exit report on every exit path; a dry run and a refusal before the reservation write none. A run whose run log still says running while its supervisor is no longer alive is *orphaned*. With `--pilot` it runs the pilot before the hold, and before the exit report it runs the Cloudflare check.

**launch record** — what `run --detach` prints after it waits up to 20 s for the supervisor: the dashboard URL as line one (or `dashboard: pending`, or `dashboard: off`), then the run directory and the supervisor's pid; `--json` prints it as JSON. The pid is the one the supervisor records in the run directory, and the launched pid only when no record arrives, because the launched process can be a wrapper. (A launch record names a run's supervisor; the campaign pid record names a campaign's process.)

**preflight** — the checks a fresh run makes before any step starts, from the repository to the `node_modules` source; a failing check stops the run with `preflight failed:` and one line per problem. `references/ohflow.md` names each one. `ohflow preflight` runs them with no run, adds the Git Bash check, and prints one `FAIL <check>: <observed>; <fix>` line per failing check: for the harness executors `--harness-executors` names, and for a workflow `--workflow` names. (`ohflow validate` checks only the workflow definition.)

**worktree path length** — the preflight check that, on Windows, a local worktree's root plus the longest path tracked at its base stays under 260 characters, unless the repository sets `core.longpaths`. A run clone sets it. (Only a worktree on the local box is checked; a remote workspace lives on another box.)

**run clone** — a clone of the checkout's hosted `origin`, made with `core.longpaths=true`, that a run uses while another session works in the checkout (`references/operate-a-run.md`). Each worktree's branch is fetched back into the checkout before `revert`. (A clone is a repository of its own; a worktree shares one.)

**dry run** — `--dry-run`: preflight, the baseline and the attempt input files of every step, with no agent started. It writes no exit report, no estimate, no run notes and no dashboard, so it is no proof that the run works.

**run directory** — the directory ohflow writes for one run: `run-log.jsonl`, `workflow.json`, `board.md` and one directory per step. Its name is the run id. A driver's `--out` directory and a roll-call case directory each contain a run directory and are not one.

**run id** — the name of the run directory: `run --run-id` sets it, else ohflow mints one.

**run log** — `run-log.jsonl`, the append-only record of what the engine did. The run log is the truth. Owner: `run_log.py`. Its events are `run_started`, `phase_started`, `attempt_started`, `attempt_finished`, `gate_ran`, `phase_settled`, `run_finished`, `retry_decided`, `worktree_ready`, `run_log_recovered`, `phase_resumed`, `work_excluded` and `token_budget`, and a step's status in it is `pending`, `running`, `passed`, `failed`, `timeout`, `quarantined`, `skipped`, `cached` or `deferred`. An attempt's `logs/` directory holds its event log and its tool output, never a run log.

**event log** — the file in an attempt's `logs/` directory where the runner writes the harness's events as they arrive, such as `pi-events.jsonl`, the lines of pi's `--mode json`. The engine reads live usage from it at every poll, and a rebuilt record is built from it (`record_source` `event_log`). (An event log holds one attempt's harness events; the run log is the engine's record of the whole run.)

**attempt** — one numbered try at executing a step. A command, gate or merge step has an attempt but no agent invocation. `explain` and `actions` take `--attempt N`, the newest by default.

**attempt directory** — `attempts/NN/` below a step directory: the inputs and the available outputs of one attempt. A file in it can be absent after a preparation failure or an interruption, so attempts are counted from the run log.

**attempt result** — `result.json` in an attempt directory: the status, error, settings, tool calls, tokens and cost of one attempt, when the attempt produced it.

**rebuilt record** — an attempt result written after its runner died without one (`recover_cli_result` in `cli_harness_executor.py`). `record_source` says what it was built from: `event_log` (the runner's event log), `attempt_files` (no event, so the attempt's other files, such as `remote.json` and `kill-abort.json`) or `none`; a record the runner wrote itself says `runner`. Its `recovery` block adds the attempt's end time and how that time is known, in `ended_basis`: `kill` (the time the kill recorded), `last_write` (the newest write in the attempt directory, a lower bound) or `recovery_time` (the moment of the rebuild, an upper bound). (The runner's own record is first-hand; a rebuilt record is pieced together after its death.)

**agent invocation** — the logical execution of an agent within an agent-step attempt. Preparation can fail before an invocation starts; reattach continues an existing invocation.

**reattach** — reconnecting to and continuing the same attempt after losing supervision or connection. It preserves the attempt number and continues the same logical agent invocation.

**execution start** — a recorded start of work: an initial start, retry, auto-resume or reattach. A reattach spends another execution start while continuing the same numbered attempt.

**attempt start** — the beginning of a numbered attempt. Reattach records another execution start without beginning another attempt.

**open tool call** — a tool operation whose start has been observed but whose completion has not yet been observed. It may still be running; an open record alone does not prove useful progress.

**tool output** — `logs/tool-output/` in an attempt directory: the live output of each tool call, capped at 5 MiB per call, kept apart from the agent transcript and outside the step fingerprint. A call whose output keeps arriving more than 2 seconds after the call ended is marked *detached*.

**stall timeout** — `Step.stall_timeout_s`: the permitted interval without observed activity while no tool call is open. An open tool call suspends stall detection. The setting is optional.

**stall** — a stop triggered when observed inactivity exceeds the configured stall timeout and no tool call is open. It measures silence, not whether the agent is making useful progress.

**execution timeout** — `Step.execution_timeout_s`: the elapsed-time limit for a step's main execution, excluding preparation and subsequent gate checks. Gate commands have their own limits. The engine currently gives a reattach a fresh execution-timeout deadline. On the local box, the kill ends a `durable` step's durable host with its commands; on an ssh box, it drops the host's connection, and the tether ends the step; on a cloud box, the executor posts `abort`, which stops the box.

**command time cap** — the effective time limit for a command invoked by an agent. Its default is derived from the execution timeout; an explicit `command_time_cap_s` can tighten it. The shared CLI runtime also stops an open tool call after this cap plus a currently hardcoded 60-second grace period. On `claude-cloud` and `codex-cloud` no cap stops a running call: the stream reports a call only when the CLI does, Claude Code at its start and Codex some calls only at their end, and no output arrives while a command runs.

**iteration limit** — `AgentSpec.max_iterations`: the most model calls one attempt may make, the tool calls of the last one included; 150 unless the step names another; `construct` writes 150 for a writing step, 80 for a reviewer and 400 for the judge, which `default_judge` also gets. The `claude` and `codex` runners use it as their cap. On `pi-cloud` the Worker enforces it as pi-durable's `maxTurns`, and the result's `settings.effective` names the enforcer in `max_iterations_enforced_by`: `worker`, or `ohflow` when an older Worker names no limit and ohflow counts the turns on the stream. (An iteration limit counts model calls; an execution timeout counts time.)

**step fingerprint** — a hash of selected inputs describing a step's work: configuration, brief, dependencies, consumed handovers and relevant worktree state. It excludes the run ID and actual attempt number. It does not capture every possible external change.

**step identity** — the pair (step coordinate, step fingerprint) identifying a particular revision of a step's work within a workflow run. Attempts at unchanged work share this identity. Changing a hashed input creates a new identity with fresh execution allowances; earlier attempts remain recorded.

**retry** — another attempt of an agent step inside the same workflow run, started because its retry policy allows it after a failure. The run log records it with `start_kind` `retry`. `RetryPolicy.carry_context` lets the `pi` and `claude` executors continue the previous attempt's conversation.

**retry budget** — `RetryPolicy.max`: how many additional attempts the retry policy permits. (see also: milestone revision budget; reattach)

**auto-resume budget** — how many automatic recovery passes may retry work postponed by interruptions or temporary failures.

**execution-start budget** — the total allowed recorded starts for unchanged work, including reattachments. (1 initial start + retry budget + auto-resume budget + 1 manual-recovery allowance, `MANUAL_RECOVERY_ALLOWANCE`)

**failure exclusion threshold** — the number of counted failures after which unchanged work is refused further starts. It is currently hardcoded to 2 (`EXCLUSION_THRESHOLD` in `attempts.py`) and stops unchanged work after **two counted failures**, even if more starts remain available. The run log records the refusal as `work_excluded`.

**counted failure** — a started execution of unchanged work that ends in a judged failure (`failed`, `timeout` or `quarantined`) or a genuine transient deferral. Cached, skipped or never-started work and executions interrupted by a run abort, an attempt kill or the death of the run supervisor do not contribute to the failure exclusion threshold.

**abort victim** — an execution that ended without its own verdict because something outside it stopped it or kept it from starting: a run abort, an attempt kill, a workflow resume closing an execution that its dead run supervisor left open, or the closure of the execution record that a reattach then continues (`reattach: <reason>`). It is recorded `deferred` with `abort_victim`; the name keeps the run abort, its first case. One that never started spends no attempt number and no execution start. One that started spends an execution start. Neither is a counted failure. The closure after a supervisor's death also carries `interrupted`, and the reattach case `reattached`.

**attempt kill** — `ohflow kill`: an upper rank ends the running attempt of one agent or command step while the other steps run on. The engine reads the request at its next poll and stops the attempt, remote work included: an agent step through its harness executor, a command step through its own process. The attempt is recorded `deferred` as an abort victim, with `killed` (`reason`, `requested_at`) and the error "killed by ohflow kill", followed by `: <reason>` when `--reason` names one. No retry and no auto-resume pass starts it again; a workflow resume starts a new attempt, never a reattach, whose position block names the reason under "What failed last time". (An attempt kill ends one attempt; a run abort ends every attempt in flight.)

**kill request** — `kill-request.json` in a step directory: the attempt number, the reason, the time and the supervisor's pid, which `ohflow kill` writes for the engine to read at its next poll; the engine moves it into the attempt directory when it acts. A refusal prints `NOT KILLED` with its reason: no live supervisor, a step that is not an agent or command step, or no running attempt. Otherwise the verb waits up to `--timeout` seconds and prints `KILLED`, `NOT KILLED` when the attempt ended on its own first, or `KILL SENT` when the supervisor has not closed the attempt yet and the request still waits. (The kill request asks; the attempt kill is what the engine does with it.)

**retry eligibility** — whether a failed agent step may start another attempt: its retry policy must cover every failure reason in `RetryPolicy.on`, whose tokens are `timeout`, `agent_error` and `gate:<check>` (`validate` refuses `gate:ownership` and `gate:no_ai_attribution`, because either failure means the agent did the wrong thing), the relevant budgets must have capacity, and no exclusion or other refusal may apply. Deferred work follows the auto-resume/manual-resume recovery path.

**workflow resume** — `run --resume RUN_ID`: continuing an existing workflow run using its history and the currently loaded workflow definition. Matching successes may be reused; unfinished work may reattach or start another attempt when eligible. Spent budgets and exclusions still apply to unchanged work. A resume is refused while the run log reads running and the run supervisor that the run directory records is alive. The `run --detach` launcher asks before it starts a supervisor, and hands that supervisor `--resume-checked`.

**workflow rerun** — starting a new workflow run in a new directory, with a new log and fresh run-scoped budgets. Successful steps from earlier runs are not automatically reused. `ohflow compare --runs A B` sets two runs side by side, step by step.

**cached step outcome** — an outcome that reuses a recorded step success because its step fingerprint matches and any required recorded handover remains intact. The step and its gate checks do not execute again, and no execution start is spent.

**deferred** — a step outcome indicating that work was postponed or interrupted without reaching its own verdict. This includes temporary failures, work interrupted or prevented by a run abort, an attempt kill, and an execution that the death of its run supervisor left open; recovery remains subject to the applicable budgets and exclusion threshold.

**auto-resume** — the pass that restarts the deferred steps of a phase by itself, after a cooldown, except a step an attempt kill ended. `Workflow.auto_resume`, or `run --auto-resume` for one run, sets how many passes a phase may make. The run log records each pass as a `phase_resumed` event, and the attempts it starts carry `start_kind` `auto_resume`.

**provider cooldown** — the wait the engine holds before the next start after a transient failure: until a provider's announced quota reset plus 60 seconds when the error names one, otherwise `transient_backoff_s`, doubled per hit up to ten times its base value. The run log keeps it, so a resume waits out the same cooldown. It reads the z.ai `1308` message and the Codex "usage limit ... try again at 3:23 AM" message; the Codex time is local, and a time already past means the next day.

**provider usage window** — a provider's usage limit over a rolling window, such as Z.AI's 5-hour limit. A workflow step that reaches it fails transiently and waits out a provider cooldown. A session turn that reaches it ends on the provider's error, such as `429` code `1308`, and the session controller holds no cooldown, so the orchestrator agent counts the turns a window holds before it opens sessions on that provider (`references/steer-a-run.md`). (The window is the provider's limit; the provider cooldown is the engine's wait.)

**token budget** — the most tokens a run's agent steps may use, prompt plus completion with cached input included: `Workflow.token_budget` or `--token-budget`. Every agent attempt reserves a grant before it opens, is extended or stopped when its live usage reaches the grant, and settles its usage when it ends. The grant is `Workflow.token_reserve`, else the budget divided by `max_parallel`. The run log records `token_budget` events of kind `limit` (the budget and the grant), `refused` (an attempt not admitted) and `overshoot`. An attempt that cannot be admitted is deferred and pauses the run. Usage that arrives too late to stop is recorded as overshoot, an error in the run log, the exit report and the dashboard. (The token budget counts observed tokens; the billing estimate prices them and is never compared with the budget.)

**token ledger** — `budget.Ledger`: the token budget's account of one run: the budget, the grant per attempt, the settled and observed tokens, the refusals and the overshoots. `budget.json` at the run root is its snapshot. (The token ledger counts a run's tokens; the campaign log records a campaign's decisions.)

**transient failure** — a recognized temporary external problem, such as rate limiting, provider overload or a dropped connection, for which waiting may change the outcome.

**structural failure** — a failure classified as a work or setup problem, such as failed checks, malformed output or invalid credentials. Unrecognized failures default to this class; the classification alone does not determine retry eligibility. (A check-in's judgment of the work is a deviation, a design flaw or a miss; a structural failure classifies one failed attempt.)

**board** — the file `board.md`, the status table the engine rewrites. The command `ohflow board` prints an empty board for a workflow.

## Checks and reports

**gate** — the `GateSpec` of a step: the conjunction of its `checks`. A *quality gate* is that group of checks. A gate with no checks passes.

**gate check** — one named test of a gate, a `CheckSpec` with its `name` and `args`. Its name appears as `gate:<check>` in retry tokens. A check that reads a diff compares against `since`: the worktree base (the default), the step's start commit or the last merge.

**mechanical check** — an acceptance condition that a command can assure: a `command_exit` gate check, or one `- command:` line of a milestone spec, which passes when its command exits 0. `construct` turns such a line into a gate check on the step that writes last in its workspace and on the reviewer, a `check-` step after the merges in the fan-out patterns, and a milestone acceptance check before the judge. Any command counts, such as `grep`, a linter or a grading script, so prose work has mechanical checks too. (A command decides a mechanical check; the judge grades a rubric check.)

**mechanical check pass** — a step's final mechanical confirmation: a `command_exit` check that passed on a clean worktree, right after the agent committed. The run records it in `check-passes.jsonl` (`check_passes.py`), keyed by the command, its shell, its folder and the tree hash. Because the key is the content and not the step, a later identical check in the same run reuses it, as the reviewer's gate or an acceptance check do; `reuse: false` opts out. (A mechanical check pass confirms one result; a cached step skips a whole step.)

**change-sized check** — the rule that checking a change costs in proportion to the change. A gate, a `check-` step and an acceptance check run only the tests that the step's changed files reach, in minutes, and the full suite runs in CI after a push, where nobody waits for it. A cloud step's brief names its tests, because no cap stops a running tool call there. (A change-sized check tests one change; CI tests the whole product.)

**changed-test selection** — `tests/run_tests.py --changed BASE`: the test files that the files changed since BASE reach, plus `check_docs.py`. Past about 300 s it runs the changed tests and the direct part, cheapest first. When no test file is reached, it runs `check_docs.py` alone and passes with it; `NO TESTS RAN` fails a selection whose files load and run no test. A gate runs it as `--changed {base}`. (This repository's selection; another workspace brings its own.)

**check time** — the wall time of a step's `command_exit` gate checks, the only checks that record `duration_s` in `gate.json`: the `checks p50` column of `ohflow estimate`, and the dashboard signal `checks_over_agent`, which compares it with the agent's own time: the attempt's `wall_seconds`, which holds the checks, less the check time. A cached step and a step with no agent raise no signal. (Check time prices each check you add; the execution timeout covers only the agent's work.)

**gate report** — `gate.json`, the result of every gate check for one attempt.

**execution error** — the error that ended an attempt, as the engine recorded it, such as a stall, an attempt kill or `max iterations N exceeded`; an execution timeout may leave no text, and its `timeout` status is then the record. `ohflow explain` prints it before the failed gate checks, because those checks fail only because the attempt stopped. (The execution error is the cause; a gate check that failed after it is a consequence.)

**final message** — the last text of an agent that completed its answer. It is a claim. The artifact is the evidence. A stopped attempt also leaves its last text in `final.md`, and `ohflow explain` prints that as an *interrupted last message*, never as a final message.

**artifact** — a file or commit that a step leaves behind as evidence of its work. Gate checks read artifacts, not the final message.

**structured output** — the JSON a step returns for `Step.schema`: in its final message, or, for a `claude` step, in its latest `StructuredOutput` call, whatever prose follows it. The runner extracts it into `result.json` as `structured`, or records `schema_error`. Extracted JSON proves no schema validity; the `schema_valid` gate check validates it.

**exit report** — `exit-report.md` and `exit-report.html`, written when a run ends. `exit.json` is the same record for tools. The command `ohflow report` rebuilds all three after a hard kill.

**verdict** — a first-line result. A *verb verdict* is `PASS`, `FAIL`, `VALID`, `COMPLETE` and the like. The word does not name a judge's answer: that is a *judge decision*.

**review verdict** — the `VERDICT:` line of a reviewer: `MERGEABLE` or `BLOCKED`. A gate check can accept a valid `BLOCKED` line without approving the work.

**finding severity** — the list a reviewer sorts each finding into: `blocking` (it breaks a contract, the spec or the test command, and the reviewer would not merge over it), `should_fix` (wrong, but the merge can stand) or `notes`. A non-empty `blocking` list fails the review gate on purpose, which starts the fix cycle. Each finding names its piece, a path, a line, the contract it breaks, the claim and the fix (`references/brief-templates.md`). (Severity sorts one review's findings; the review verdict is the reviewer's one-line answer.)

**fix cycle** — one implement-review run in `mode=fix` that the orchestrator agent starts after a blocking review: a fixer works through the blocking findings, and a reviewer judges the result again. At most two cycles run, and then the last review goes to the operator. The engine has no step that turns findings into work. (A fix cycle answers a review; a retry repeats a failed attempt.)

**hand-try** — a brief's instruction to use the work once by hand, the way its user or caller would, and to paste the command and its output under "Hand-try" in the handover. The reviewer runs each hand-try again. (A hand-try uses the work; a mechanical check tests it.)

**heartbeat** — plain English for a periodic sign of life; ohflow gives the word no owner. Each mechanism goes by its own name: a piece's start and end lines in `heartbeat.log`, which its gate checks; the `pi_cloud_beat` line the pi-cloud Worker sends every 15 s; the heartbeat a stall deadline watches in `CliAgentRuntime`; and the roll call's `matrix.json`, rewritten after each test case.

**campaign log** — `campaign.jsonl`, the append-only record of a campaign. It names the commit, the round and the decision of every run, and `ohflow campaign history` joins it with the judge handovers and each round's acceptance checks. The bare word *ledger* has no owner; the token budget's account is the *token ledger*.

**agent transcript** — the file where a human reads one attempt, as the harness executor module names it. The command is `ohflow transcript`. The short form is *transcript*.

**model call** — one request from a harness to its model. One model call may ask for several tool calls.

**tool call** — one operation an agent asks a tool to run. The engine counts them per attempt in `tool_calls`, and `ohflow actions` lists one attempt's model calls with the actions each one launched.

**run state read-out** — the one JSON document `live.read_out` builds from a run directory: the whole run at one instant, with every phase, step and attempt, their tokens, cost and errors, the estimate and ETA, the log tail and the resume and revert commands. `ohflow status` (which `--watch` redraws every 3 s), `ohflow watch`, the route `/api/read-out` and the exit report are built from it. The route `/api/workflow`, which the dashboard page polls, builds its own view in `dashboard_data.py`. The workflow run status is one field in it. It is a derived view, not a checkpoint a run resumes from.

**plan** — the declared plan of one run: the workflow definition with its limits and its forecast, what will run in which order, as the Plan view shows it and `/api/plan` serves it. ohflow's own *project plan* (`docs/todo.md`) keeps its qualifier, and its parts are stages. (A plan is declared before the run; the run state read-out says what happened.)

**Plan view** — the dashboard's third view, after Start order and Workflow: the declared plan of a run, what will run in which order with which limits. `/api/plan` builds its phases and steps from `workflow.json` and its forecast from `estimate.json`; only its `run` block follows the run log, for the status. A run started with `--hold` opens on it, each step has a drawer with its brief, position block, gate and limits, and `exit-report.html` embeds it (`references/dashboard.md`). (The Plan view shows what was declared; the run state read-out shows what happened.)

**attention item** — one entry of the dashboard's attention list, in one of three groups: `intervention` (the engine starts nothing more by itself), `recovering` (the engine acts alone, such as a cooldown or a pending auto-resume) and `signal` (a measured threshold, never a verdict).

**attention kind** — the `kind` of an attention item: the condition it reports within its group, such as `failed_step`, `killed_step` or `token_overshoot` in `intervention`, `deferred_cooldown` in `recovering`, and `deadline` or `checks_over_agent` in `signal` (the table in `references/dashboard.md`). `watch` names a cleared item by its kind. (The group says who acts next; the kind says what happened.)

**standing item** — an attention item that a fresh watch cursor finds on its first look. `watch` prints it as `attention standing <group>`, because a reader that has reported nothing cannot call it new, and it may be hours old; an item that arrives while that first call waits prints without `standing`. A standing `intervention` item returns `--until attention` at once. (A standing item was already there; a new item arrived since the cursor's last report.)

**watch cursor** — `.watch.<name>.json` in a run directory or campaign root: what one named reader (`--cursor NAME`) of `ohflow watch` has already seen. It is observation state, not execution history.

**run notes** — `predictions.md`, `notes.md`, `retro.md` and `ground-truth.md` at the root of a fresh run directory: the orchestrator calibration before the run, manual interventions during it, the retrospective and the measured facts after it. They are outside every fingerprint.

**orchestrator calibration** — the orchestrator agent's own forecast of a run, which it writes into `predictions.md` when the operator asks for one, before it reads the estimate or any result: the cost and wall time, the steps that will burn the most wall time and tokens and why, the gate it trusts least and why, what good looks like, and what would make it stop the run. The operator reads it for signs that the workflow's rigor is mis-sized: a check that every step repeats, a fix loop on every edit, a full suite where a changed-test selection would do, or a gate too loose for its risk. The retro compares it with what happened. The plain word *calibration* stays with the candidate objective kind, tuning an experiment before it is committed. (The orchestrator calibration tests the orchestrator agent's picture of the run; the estimate forecasts from earlier attempts.)

**estimate** — the forecast `estimate.json` records before a run: per step a median (`p50`) and an 80th-percentile (`p80`) of wall time, check time and tokens, and a median cost, from `n` earlier attempts in the finished runs that `--history` names, the `basis` key that answered and a `confidence` of `ok` or `low`. A percentile is not a guarantee, and a missing measurement is not zero.

**cost source** — `result.json` `cost_source`: where an attempt's model cost came from. Each harness executor writes its own value: `pi-catalog` (pi's model catalog), `claude-cli` (Claude Code's own report), `durable-host`, `pi-cloud-worker`, `subscription` or `unpriced`. `subscription` is the value of `codex`, `claude-cloud` and `codex-cloud`: a subscription bills no tokens, so `cost` is a known 0, which the estimate counts as a measurement and `ohflow table` prints as a number. `unpriced` records `cost` 0.0 because no price was known, which is not a measured zero. (The model cost only; infra cost prices the container.)

**infra cost** — `result.json` `infra_cost`: the list price of the cloud machine an attempt held, apart from its model `cost`. Today it is the container time of a `pi-cloud`, `claude-cloud` or `codex-cloud` attempt, memory and disk, from the Worker's container chronometer in `infra`. None means the attempt held no priced machine, or its container time was never reported, as after `host_lost`.

**Cloudflare check** — `cloudflare.json` in the run directory: Cloudflare's own container meters for the run's Durable Objects, read by the run supervisor before the exit report and again by `ohflow cloud-spend --run`. A flag marks an object billed well beyond the container time its attempt reported. The meters lag by a few minutes. It covers every attempt of `pi-cloud`, `claude-cloud` and `codex-cloud` that wrote a `result.json`. It flags an object billed more than 120 s or 20 % beyond the time its attempt reported, whichever is larger, or billed for time its attempt never reported.

**cloud-spend** — `ohflow cloud-spend`: the verb that reads Cloudflare's own container meters, for one run (`--run`, which writes `cloudflare.json`) or for the whole account over a window (`--since`, `--until`). The meters lag by a few minutes. (It reads Cloudflare's bill; the container chronometer is the Worker's own count.)

## Monitoring a run

These terms come from [monitor-a-run](references/monitor-a-run.md), which the orchestrator agent follows. No code enforces them.

**bill** — the hand-over message that carries the dashboard URL: the objective kind and the one sentence on why, its price in the four cost scalars, the proposed spending caps with their basis and their limits, the run's worth in one sentence and the one decision that is the user's. The orchestrator agent logs it as a `bill:` line with `notes log`. (A bill prices a run before the work; the exit report records what it cost.)

**cost scalar** — one of the four measures of a run's price: agent tokens per model, wall time, the user's attention minutes, and money paid out to billed APIs and to Cloudflare. (A scalar measures; a spending cap limits it.)

**spending cap** — the most the user would spend on the outcome, one per cost scalar. The user's answer sets it; when the user defers, the agent's proposal does. The bill names beside each cap the forecast it rests on, and calls a cap a guess when that forecast has low confidence, no history, or attempts of another role, model or executor. Only the orchestrator agent watches it, and it acts only through a limit: an execution timeout, a token budget or a stop-and-ask limit. (A spending cap limits money and attention; an execution timeout limits one attempt's time and a token budget the run's tokens, and the engine enforces both.)

**stop-and-ask limit** — a threshold below a spending cap at which the orchestrator agent stops and asks the user. The bill uses one only when the answer can arrive while the step runs: the user reads the session directly, not through a relay, and the step runs on for longer than the user takes to answer. Otherwise the limit becomes the step's execution timeout. It carries the default that applies when no answer comes. (A stop-and-ask limit waits for the user; an execution timeout kills the step and asks nobody.)

**objective** — what a campaign or a run serves: the wanted effect the operator names. Its objective kind tells the agents how far they may steer the work towards it. (A step objective is one display line on one step; the objective is what the whole run is for.)

**objective kind** — what the operator wants out of this stretch of the work, named with one sentence on why. The orchestrator agent and the judge read it as an instruction at every check-in, and its row in the grid of deviation, design flaw and miss says what a check-in may do (`references/campaign.md`, "Intervention by kind of objective"). It changes as the work moves on, as when a calibration that found its design is committed as an empirical procedure. The bill names it with its reason, and a campaign's charter carries both under "Decisions already made". The engine decides nothing with it. (The kind decides the check-in, not the construction.)

**check-in** — a moment when the orchestrator agent or a judge looks at work in flight and decides whether to stop it, change it or let it go on: each poll, each phase boundary and each judge round. The objective kind and its reason are re-read at each one. (A check-in judges the work; a gate check only tests a commit.)

**delivery** — an objective whose wanted effect is known and fairly deterministic, such as a feature, a fix, a search, research or a specific output. It is open to revision: a deviation or a design flaw aborts the run for a fix, and after a miss an upper rank may replan, pause, continue or propose a restart. (An empirical procedure keeps its procedure.)

**empirical procedure** — an objective that tests a hypothesis, such as an A/B test, by putting a control arm and an experiment arm through one procedure. It is fixed once committed: an upper rank stops it only for a deviation, a change to the procedure restarts every arm, and a miss is its result. Its bill states its arms, its procedure and its stopping rules. (A delivery may change course.)

**deviation** — work that left its plan: a step that ignored its brief, an arm that skipped the procedure, a measurement that did not record. The fix is to redo the work as planned. A delivery aborts for it, and it is the only ground on which an upper rank stops an empirical procedure. (The plan stands; the work strayed.)

**design flaw** — a plan that is itself wrong: a gate that tests the wrong file, a workflow that checks the wrong thing, an experiment that measures the wrong quantity. The fix is to change the plan. A delivery aborts for it; in an empirical procedure only a changed procedure fixes it, which restarts every arm on the operator's decision. (The work followed a plan that was wrong.)

**miss** — a result that misses the objective although the plan was right and the work followed it. Nothing in the work went wrong. After a miss an upper rank may replan a delivery; in an empirical procedure the miss is the result. (A miss is information, not a mistake.)

**intervention** — an upper rank's stop or change of work in flight; the objective kind sets how far it may go. The attention group `intervention` marks a run where the engine starts nothing more by itself, so the run waits for one. (The attention group marks where an intervention is needed; the intervention is the act.)

**move** — one action by which the orchestrator agent changes the course of an agent while it runs. How the agent runs decides the moves it allows (`references/steer-a-run.md`): a session takes `send`, `interrupt` and `close`; a workflow step takes an attempt kill, a brief edit before a resume, and a stop and resume of the supervisor, which reattaches a `durable` or cloud step. The objective kind decides whether a move is allowed, and a move pays when the waiting it saves exceeds the work it throws away. Each move on a run is logged with `notes log`. (An intervention is an upper rank's decision to stop or change work; a move is the command that carries it out.)

**recorded failure** — one dated failure of an agent role on one kind of box, kept in the table of `references/steer-a-run.md` with the move that answers it, such as an implementer on this machine that ran the full suite itself. The orchestrator agent reads the table before it briefs or steers a step. (A recorded failure is a lesson for the next brief; a counted failure is one execution the engine counts toward exclusion.)

**stop rule** — the condition, set before a step starts, at which its work ends early: a limit the engine enforces, such as the execution timeout or the iteration limit, or a sign the orchestrator agent watches for, such as a step that has stopped committing, which it answers with an attempt kill. `SKILL.md` asks for one per step, beside the step's one change and its gate. (A stop rule ends a step that has stopped paying; the gate judges the step's result.)

**phase boundary** — the moment the last step of a phase reaches a final state. At it the orchestrator agent compares the cost still to come with the run's worth, answers "knowing what you know now, would you start this run?", and logs a notes line. `ohflow watch` prints one `phase boundary:` line for each phase that settled since its cursor last looked, and the line names `references/monitor-a-run.md` and the check; a cursor that holds no phases yet gets the line for the newest settled phase only. (The engine writes `phase_settled` at the same moment; the boundary is the agent's checkpoint, not an engine event.)

**bad trade** — a "no" to that question, or a spending cap the run will pass. The agent reports it in two sentences: the trade as it stands, then the correction and its default if the user defers.

**teach-back** — one question that asks the user to choose or to predict, such as "After this yes, how many agent runs do you expect?". The agent asks it after a doubtful "yes" on scope, effort, budget or stop, and a correct answer closes the check. (A teach-back checks one answer; a walk-through rebuilds understanding.)

**walk-through** — a sequence of 2 to 10 messages, opened after a stated overload or a missed teach-back. The first opens with "Step 1 of N, ending in <the decision>". Each step holds one fact and one question that needs a choice or a prediction, and a guess comes before its number. It ends in the user's decision or in "carry on as planned".

## The roll call and the campaign

**roll call** — the live-agent test. Most agents write who they are into a file and commit it; in the review scenario a solo agent commits its file and a reviewer with no write scope changes none. Owner: `ohflow rollcall`.

**test scenario** — one pattern of the roll-call workflow: `single`, `fanout`, `relay`, `merge`, `retry`, `review`, `campaign` or `silent`.

**test case** — one test scenario on some harness executors at some scale, written `scenario:harness-executors[:count][:option]`. The class is `RollCallCase`, and `rollcall --cases` runs a list of them in place of a matrix.

**test matrix** — a named table of test cases: `smoke`, `quick`, `full` or `liveness`, which `rollcall --matrix` runs and `rollcall --list` prints.

**campaign** — a design document or a spec bundle delivered milestone by milestone, one workflow per milestone, with a fresh judge agent after each. The `ohflow campaign` verbs name its module with `--campaign`.

**spec bundle** — the folder `ohflow construct --bundle` reads: `bundle.md` with the bundle header, the charter sections and the workspaces, an optional `contracts.md`, and one milestone spec per milestone, whose `source:` line names the spec it serves. The orchestrator agent writes it from the specs it read with its own connectors, so ohflow carries no connector code. Owner: `construct.py`. (The specs live in many places; the bundle is the one thing construct reads.)

**bundle header** — the field lines above `bundle.md`'s first `##` section: `integration branch` (default `campaign/<name>`), `kind`, `judge harness` and `judge tier`. Every `##` section after it, except a `## Workspace <name>`, goes into the campaign charter in its order: "The operator's words" (required), "The bar", "Decisions already made" and "Stop and ask" (`references/construct.md`). (The header configures the campaign; the sections become its charter.)

**milestone file** — `milestones/<id>/milestone.json`, which `construct` writes: the workflow pattern, the steps with their executor, box and tier, and the commands. Each round builds the workflow from it, and a judge's REVISE edits it and the briefs. (The milestone spec stays fixed; the milestone file is what a REVISE changes.)

**step placement** — the `box`, `harness`, `tier` and `durable` lines of a milestone spec, for the whole milestone or for one role (`review harness: claude`), from which `construct` picks each step's executor. A pair outside the valid table is refused, with the valid pairs listed. (Placement says where a step runs and with what; the workflow pattern says how the steps are arranged.)

**workflow pattern** — how a workflow arranges its agents: single agent, relay, fan-out, fan-out with consolidation, fan-out under contracts, or implement and review. `construct` builds each milestone's workflow from the pattern its milestone spec names in its `pattern:` line, `implement-and-review` by default (`patterns.py`), and a hand-written workflow follows the same six from `references/workflow-patterns.md`. One campaign may mix them. (A workflow pattern arranges the agents; a phase groups steps under one barrier.)

**pattern role** — a step's position in a workflow pattern: `agent`, `implement`, `review` or `consolidate`. A milestone spec's `<role> <field>` lines address it, such as `review harness: claude`. (A pattern role says where a step sits; an agent role is the label its history is matched by.)

**agent role** — `AgentSpec.role`: the label that estimates use, with the harness executor and the model, to match an agent's history (`estimate.py`); `construct` sets it to the step's id. The bare word *role* has no owner. (An agent role labels one agent; a pattern role is a position in a pattern.)

**piece** — one step of a relay or fan-out pattern, built from one `### <name>` part of a milestone spec and named after it. In the three fan-out patterns it is declared as a unit on the unit path `piece`, so `run --pilot` can run one piece first. The part is the spec's section, and the piece is the step; the consolidator is the agent in the `consolidate` pattern role. (A piece is one contribution; the consolidator makes the pieces fit.)

**output worktree** — a milestone's worktree on its output branch `milestone/<campaign>/<id>`, one in each workspace a step writes in. Merges land there, mechanical checks run there, and the campaign lands the milestone from it. (Each piece works on its own branch; the output worktree is where they meet.)

**command placeholder** — `{base}` and `{<workspace>}` in a milestone spec's command. `{base}` is the commit the work started from: the step's base commit in a gate or command step, or the integration branch's commit in an acceptance check. `{<workspace>}` is that workspace's output worktree, as a Git Bash path. No workspace may be named `base`. (The placeholder is filled per run; the command text stays the same.)

**rubric check** — a `- rubric:` acceptance line of a milestone spec: a condition no command decides, which the judge grades. The judge's brief tells it to pass only when every rubric check is met; the controller checks only the mechanical checks and the run (`_pass_refusal` in `campaign.py`). Judgment lives in rubric checks and reviewer steps, and a step needs neither, because many steps are chores. (The judge grades a rubric check; a command decides a mechanical check.)

**campaign charter** — the file `Campaign.charter` names: the standard a campaign's work must meet. Every judge packet contains it, and a judge may not edit it.

**campaign contracts** — the file `Campaign.contracts` names, `contracts.md` in the campaign root (`Campaign.root`) by default: the interfaces that parallel steps share, which a workflow holds as `Workflow.contracts`. Every step's position block carries it, its text is part of each step's fingerprint, and every judge packet holds it. The position block tells a step that finds a contract unworkable to stop and report it, and the judge treats that as a `spec` finding cause and an ESCALATE. A judge may not edit it. The bare word *contract* means these interfaces; other uses take a qualifier, such as the *schema contract* of structured output, a brief's *output contract* or a *contract test*. (The contracts fix the interfaces between pieces; a milestone spec fixes one milestone's target.)

**judge edit stash** — the git stash entry `judge edit to <path> on <id> rNN` in which the controller keeps a judge's edit to `contracts.md` after restoring the file, whatever the decision. ESCALATION.md names it, and a REVISE that made the edit escalates; a PASS lands with the file restored, although the judge packet says that an edit escalates (`campaign.py`). (The stash keeps the edit for the operator; the contracts stay as they were.)

**campaign controller** — the program that runs the milestones, asks for the judge and applies the decision: `CampaignController`.

**campaign lead** — the orchestrator agent or the operator, in the role of planning, watching and steering one campaign. The campaign log records the lead's milestone revision grants; the engine has no other record of the role. (A role in one campaign, not a third actor.)

**campaign status** — the operating condition reported by the campaign controller: `running` milestone work, `held` for release, `judging`, `paused`, `escalated`, stopped by a preflight failure (`preflight_failed`), or `delivered`. Individual workflow runs and steps have their own statuses. (Campaign scope; see also: workflow run status.)

**milestone** — one slice of a design with a milestone spec and acceptance checks: a `Milestone` with its `title`, its workflow, its spec and its `acceptance_checks`.

**milestone spec** — one `milestones/<id>/spec.md` in a spec bundle: one milestone's target, with a `source:` line that names the spec it was written from, its step placement, `## Scope`, `## Acceptance` and, for a pattern with pieces, `## Steps`. The judge may not change it. (The spec says what the operator wants; a milestone spec cuts out one deliverable piece of it.)

**milestone acceptance check** — a named mechanical command, `AcceptanceCheck.cmd`, that the campaign controller runs after a milestone's workflow run and before the judge decision. It has its own execution directory and timeout (`timeout_s`), and passes with exit code zero. (Checks milestone acceptance; a gate check checks a step attempt.) Its `cwd` names its workspace: `"land"` or `"repo"` means the default workspace, `"land:<workspace>"` runs in the worktree that holds the output branch there, and `"repo:<workspace>"` runs in that workspace's repository; `{base}` in its command is that workspace's integration-branch commit.

**milestone round** — one cycle of running or resuming a milestone's workflow, collecting acceptance evidence and asking for a judge decision. Its number advances after a judging outcome is recorded; an interruption before that point does not itself create another round. (A round can contain multiple step attempts.) The bare word *round* means a milestone round.

**fresh round** — a milestone round that starts a new run directory: a milestone's first round. A round that resumes the milestone's run directory is a *resumed round*, and so is every round after a judge's REVISE, because the milestone keeps one run directory (`campaign.py`). A fresh round can hold and pilot. A resumed round that a REVISE starts can hold and never pilots; a resumed round that continues an interrupted round never holds. (A fresh round starts a run; a resumed round continues one.)

**campaign hold** — `campaign run --hold`: the first fresh round waits for `ohflow go`. The first round of a later milestone, and a round that a judge's REVISE starts, wait when the estimate exceeds the first round's actual minutes by half (the `round_s` of the first `judged` event), or when there is no estimate or no recorded first round. The controller knows a REVISE round because it recorded the REVISE and committed the revision in the same `campaign run`. When a `campaign run` starts again on a milestone whose run directory holds a run log, its first round is a resume after an interruption, and that resume never holds; a judge run never holds either. While a round is held, `campaign-status.json` reads `held`, with the `go` command, and the round's run reads `held`. (A campaign hold applies held runs to a campaign's rounds; a held workflow run is one run.)

**round pilot** — `campaign run --pilot`, which implies `--hold`: a fresh round whose workflow declares units runs its pilot first and then holds; a fresh round without units only holds, and so does a round that a judge's REVISE starts, because its run resumes. (The pilot of one round; a single run's pilot is `run --pilot`.)

**campaign pid record** — `campaign.pid`: the pid that the process running the campaign writes when it starts. `campaign run --detach` prints it after waiting up to 20 s for a new one, and prints the launched pid only when none arrives, because the launched process can be a wrapper that exits. (The campaign pid names the campaign's own process; the launched pid can name a wrapper.)

**finishing milestone** — a milestone added at a campaign's end. A smoke-test milestone, added when the product has a CLI verb or MCP tool that a user drives, builds, installs and starts the product the way a user does and drives each new verb or tool once against a real target. An architecture, documents or parity milestone is added only when the operator asks (`references/campaign.md`). (A finishing milestone tests the whole product; a mechanical check tests one change.)

**milestone revision** — a judge's permitted edits to milestone inputs, committed by the controller after a valid `REVISE` decision so the workflow can resume against those inputs. `REVISE` without an actual permitted edit causes escalation. (Changes the work definition; a step retry starts another attempt.)

**milestone revision budget** — how many milestone revisions the controller may commit and continue automatically. The allowance is the milestone override (`Milestone.max_revisions`), or otherwise the campaign default (`Campaign.max_revisions`, currently 2), plus recorded revision grants. Only a revision committed for automatic continuation spends it. (Distinct from step retry and execution-start budgets.)

**milestone revision grant** — an explicit addition to a milestone's revision budget, recorded through `ohflow campaign grant --milestone ID --revisions N`. It makes the milestone eligible for continuation on a subsequent campaign run without resetting spent revision counts or step execution allowances. (Adds allowance; does not itself restart execution.)

**campaign escalation** — the controller stopping milestone progression and recording a reason requiring intervention, such as a judge's `ESCALATE`, an invalid judge result, a refused `PASS` or an exhausted revision budget. The milestone must be reopened before progression can continue. (Distinct from a paused workflow run awaiting recovery.)

**campaign estimate** — `ohflow campaign estimate`: the forecast of the milestones that have not landed, each milestone's run estimate times one plus the median number of REVISE rounds a milestone took in the campaign logs under the history directories and in the campaign's own log. A revision resumes a run and re-runs only the steps whose fingerprints changed, so the product is an upper bound. (Campaign scope; see also: estimate.)

**judge** — the fresh agent that passes a milestone, revises it or escalates one question. Each milestone round's judge runs in a workflow run of its own, under `Campaign.judge_execution_timeout_s`.

**judge packet** — `judge/rNN/packet.md`: the milestone spec, workflow evidence, acceptance check results and earlier decisions one judge reads. The bare word *packet* means a judge packet; another use carries a qualifier, such as the dashboard's *evidence packet*, a recorded run it serves as historical evidence.

**judge handover** — `judge-handover.md`: the note one judge leaves for the next milestone's judge. The judge brief carries its format: a title, a lead paragraph and the core headings of a step handover. No gate check reads its headings.

**judge decision** — the JSON the judge returns: `PASS`, `REVISE` or `ESCALATE`, under the key `decision`. The campaign controller checks it before it acts.

**finding cause** — the one word a judge gives each finding's cause, `cause` in the judge decision: `brief` (the agent was not told), `distribution` (ownership or order was wrong), `tool_policy` (wrong tools or model), `gate` (the check held the wrong thing), `product` (the code is wrong and the brief was right, so a fix step follows) or `spec` (the spec or the milestone spec is wrong), which is an ESCALATE, because the spec is not the judge's to change. (A finding cause says why a milestone fell short; finding severity sorts a reviewer's findings.)

**REVISE price** — what a judge's REVISE costs the operator: one more milestone round, which the judge's brief prices at the p50 minutes of the run's estimate, agent and checks together (`round_minutes` in `campaign.py`), or as "an unknown number of minutes" without an estimate. The judge asks for a REVISE only when a finding would cost the operator more than that to live with, and lists the rest as notes. (The price is a rule the judge applies; the milestone revision budget is a count the controller enforces.)

**milestone acceptance** — approval of a milestone's work, requiring a valid judge `PASS`, a finished workflow run with every step passed or cached, and all declared milestone acceptance checks passing. A judge `PASS` alone is insufficient. Acceptance is recorded through milestone landing, subject to any required branch checks.

**campaign integration branch** — the Git branch that accumulates accepted milestone commits across a campaign. Landing uses it as the target for branch advancement when a milestone output branch is configured. A campaign with several workspaces has one in each workspace, all under the one name `Campaign.integration_branch`, created at each workspace's base branch; the one-repository form creates it at `integration_base`. (Campaign scope; see also: milestone output branch.)

**milestone output branch** — `Milestone.output_branch`, the optional Git branch holding a milestone's work for acceptance and landing. When configured, its commit is the proposed destination of the campaign integration branch. In a campaign with several workspaces it is one name, and it exists in each workspace where the milestone's workflow has a worktree on it. (Milestone scope; see also: campaign integration branch.)

**fan-out output branch** — the branch where a hand-written fan-out under contracts (`workflows/contract_fanout.py`) merges its pieces, in its own worktree, where the review and the fix cycles work. It does the job that the output branch and the output worktree do for a constructed milestone; it is `fanout/output` unless the template's `branch_prefix` names another prefix. (The campaign integration branch is the campaign's alone.)

**transport branch** — `ohflow/<harness executor>/<attempt key>` on the `origin` of the step's workspace: the branch that carries one step's start commit to its remote workspace on an ssh box or a cloud box, and its result back. The runner deletes it after the fetch. A step on the local box has none. It is neither a milestone output branch nor the campaign integration branch.

**milestone landing** — recording a milestone as accepted and, when it has an output branch, advancing the campaign integration branch to the output commit in each workspace where the milestone's workflow has a worktree on the output branch. The output commit must contain the integration history; a missing branch or other history in any workspace escalates and leaves every integration branch where it was. Without an output branch, landing is recorded and no branch moves. (The judge decision allows a landing; the landing moves the branches.)

## The operator layer

**operator** — The person who installs ohflow and owns its settings, its accounts and the decisions of their runs. Also known as “the user” where it means the actual human person/team behind all the agents and automation. (The campaign lead is a role in one campaign, held by the operator or the orchestrator agent.)

**orchestrator agent** — the agent the operator works with. It writes the workflow or the spec bundle, starts and watches the run, writes the bill and steers the run while it runs; `references/orchestrator.md` and `references/steer-a-run.md` are its pages. The bare word *orchestrator* means this agent, and `ohflow` is the program. (The engine runs the steps it is given; the orchestrator agent decides which steps run and when one stops.)

**upper rank** — whoever may stop or change work in flight: the orchestrator agent, a judge or the operator. The kind of objective sets how far an upper rank may go (`references/campaign.md`, "Intervention by kind of objective"). (A step's own agent is never an upper rank.)

**operator settings** — the shipped base file `ohflow.settings.json`, with the operator's git-ignored `ohflow.settings.local.json` merged over it key by key. A nested object merges the same way; any other value, a list included, replaces the base value. `OHFLOW_SETTINGS` names another local file, and an empty value reads the base file alone, as the test suite does. Every read opens the files again (`settings.py`). (Operator settings configure ohflow; the Worker settings configure the Worker pair.)

**pi provider settings** — the operator settings `pi.api_key_env` and `pi.base_url`, objects keyed by provider and empty in the base file. For a `pi` step that `construct` builds, `pi.api_key_env.<provider>` names the variable that holds the provider's API key, else `<PROVIDER>_API_KEY`, and `pi.base_url.<provider>` the provider's endpoint when one is set (`patterns.model_config`). A hand-written workflow names both in the step's model configuration. (They serve constructed `pi` steps; a `durable` box and the pi-cloud Worker hold their own keys.)

**Worker settings** — `worker/pi-cloud.settings.json`, the shipped base that names the Worker `pi-cloud` and leaves every other value empty, with the operator's git-ignored `worker/pi-cloud.settings.local.json` overriding it: `name`, `account_id`, `url`, `git_owner`, `git_identity`, `skills_repo`, `skills_root_skill` and `snapshot` (`references/pi-cloud-worker.md`). The deploy, snapshot and pin scripts in `worker/scripts/` read them, and each takes `--settings <file>` in place of the local file. (Worker settings configure the Worker pair; operator settings configure ohflow.)

**house rules** — `references/local.md`: the operator's own instructions for agents. git ignores it, and `SKILL.md` tells an agent to read it when present. (House rules are text an agent reads; house checks are gate checks.)

**house checks** — the gate checks the operator settings turn on for every committing agent, appended to `clean_commit_checks`. Today there is one: `no_ai_attribution`, behind `commit_checks.no_ai_attribution`, whose base value is `false`.

**judge model** — the tier or model of the default judge, from the operator setting `campaign.judge_model`; the base value is the tier `heavy`. `default_judge` in `campaign.py` reads it when a `Campaign` names no judge, and starts that judge on the `claude` harness executor at high effort. A campaign or a milestone that names its own judge does not read it.

**escalation marker** — the heading that opens `ESCALATION.md` when a campaign escalates, from `operator.escalation_marker`; the default is "ACTION NEEDED FROM THE OPERATOR".

**escalation command** — the command the controller runs when a campaign escalates: the campaign's own `on_escalate`, else the operator setting `operator.on_escalate` when the campaign names none, with `{file}` replaced by the escalation file's path. (A campaign `construct` writes names none, so the setting is how its escalations reach the operator.)

**the four homes** — where each piece of ohflow lives: ohflow core, the operator layer, shipped examples (`examples/setups/`) or private. A piece is core when a newcomer on a clean machine needs it to run an advertised harness executor. The table is in `docs/release/boundary.md`.

**leak scan** — `tests/test_boundary_01_no_local_values.py`: it fails when a committed core file names a real home directory or a token from the operator's private list. The scanner of the release extraction, outside this repository, is the *release leak scan*: it scans the extracted package and prints `LEAK SCAN CLEAN`. (It finds a value that leaked into the core; a missing piece shows only on a clean machine.)

**recorded evidence** — `docs/`, `.impeccable/`, `references/examples/` and `tests/fixtures/`, kept as recorded. The leak scan skips them, so the release extraction reviews them by hand.

## Handovers

**step handover** — `handover.md`, written by a producer step's agent for a receiving agent, following its handover spec, `Step.handover`. The `handover_written` gate check requires it. [Contract](references/step-handover.md).

**consumes** — `Step.consumes`: the producer steps whose step handovers an agent receives. Each one is also named in `depends_on`, and the consumed content enters the receiver's step fingerprint.

**handover spec** — `HandoverSpec`: the `audience`, the `extra` headings beside the core questions, and the size limit `max_chars` that govern one step handover.

## Sessions

**session** — one named pi conversation that the orchestrator agent opens with `ohflow session open NAME --cwd DIR`, in that working directory and on an optional `--model` (a model or a model tier) and `--thinking` level, sends turns to and closes for good. At most three are open at once, each is idle, running or closed, and a name is used once. Its folder in the session record holds pi's stored conversation and its turn files. (A step's agent answers to the engine and its gate; a session answers to the orchestrator agent after every turn.)

**session controller** — `ohflow session` (`sessions.py`): the orchestrator agent keeps up to three sessions open, sends them follow-ups, and is woken when a session finishes a turn. Each turn is one process that continues the session's stored conversation, so nothing stays alive between turns. pi is its one harness today (`--harness pi`). (The engine runs steps fixed in advance; the orchestrator agent decides after each finished turn.)

**session record** — the directory the orchestrator agent names with `--dir`: `events.jsonl`, the append-only truth of the events `opened`, `sent`, `queued`, `delivered`, `interrupted` and `closed`, and one folder per session with its conversation and its turn files. Every verb derives the state from it, so a restarted orchestrator agent loses no turn and receives none twice.

**turn** — one message to a session and the process that answers it: on `open`, `--message TEXT` or `--brief FILE`; on `send`, the text as an argument or `--file`. The turn ends when that process exits, and `<n>.exit.json` records how. A turn whose process died without that record is delivered as lost.

**delivered turn** — a finished turn whose report `ohflow session wait` has handed to the orchestrator agent, recorded as a `delivered` event in the session record. `wait` hands over the finished turns one at a time, the earliest finished first, so each is delivered once, and a turn whose process died without its exit record is delivered as lost. (A delivered turn is one session turn handed over; a delivery is a kind of objective.)

**interrupt** — `ohflow session interrupt NAME`: it stops the running turn of one session and keeps the conversation. It marks the turn, waits up to 30 s for the turn's process to end, and records `interrupted` with whether the process stopped. The next `send` continues the same conversation with a new direction. (An interrupt throws away one unfinished turn; `close` ends the session for good, and `close --force` interrupts a running turn first.)

**queued message** — a message that `send` holds because the session is running a turn or already holds queued messages: it waits as `turns/queued-<id>.md`, and the session record notes `queued`. When the session controller next finds the session idle, the oldest queued message starts the next turn, one turn per message. (A queued message waits for a turn; a message to an idle session starts one at once.)
