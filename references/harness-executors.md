# Harness executors: pi, claude, codex, durable, pi-cloud, claude-cloud, codex-cloud

A harness executor launches, monitors, collects results from and stops one kind of harness for an agent step. `harness_executors.py` is the registry. Outside the harness executor modules, these places name every harness executor: `HARNESS_EXECUTOR_FIX` in `preflight.py`, the fix hint for a failed harness executor check; `executor_for` in `construct.py`; `MODELS` and `STALL_S` in `workflows/rollcall.py`; and `tiers` in `ohflow.settings.json`. `_READERS` and `JOINS` in `actions.py` and `_NORMALIZERS` in `dashboard_data.py` name every harness executor except `durable`. The engine talks to the `HarnessExecutor` protocol in `harness_executor.py`. For `carry_context` it also calls `harness_executor_module(harness_executor).resume_target` directly, and before restarting a step whose execution is still open it calls `reattach_target` on the harness executors that have it. Test fixtures and live checks: [CONTRIBUTING](../CONTRIBUTING.md#add-a-harness-executor).

Every agent step names its harness executor in `AgentSpec.harness_executor`. ohflow has no default: `validate` refuses an agent step that names none.

| Harness executor | Starts | Setup the agent sees | Pick it for |
|---|---|---|---|
| `pi` | a hermetic pi CLI child | only what the workflow names | new workflows |
| `claude` | the Claude Code CLI | the signed-in harness's own setup; the agent profile `hermetic` strips it | a step that needs that harness's model, memory or fleet |
| `codex` | the Codex CLI | the same | the same |
| `durable` | the durable host that ships in `host/`, as a `node` child on this machine (box `local`) or over `ssh` on an ssh box | only what the workflow names, on the box | a step that must survive the death of its supervisor, or of this machine |
| `pi-cloud` | `pi_cloud_client.py` streaming a Cloudflare Durable Object | only what the workflow names, in `/workspace` | a step that must survive this machine being off |
| `claude-cloud`, `codex-cloud` | the same client, streaming a `ContainerHarness` object of the same Worker | the CLI's own tools and the box's MCP servers, in `/workspace` | a Claude Code or Codex step that must survive this machine being off |

A local harness executor (`pi`, `claude`, `codex`) sees this machine's real filesystem and starts in the step's worktree. None of them confines its agent with a sandbox: Codex runs with `danger-full-access`. The worktree and the `ownership` gate are their isolation. A cloud step, and a `durable` step on an ssh box, runs on that box, so its agent sees the box and its remote workspace, not this machine. A `durable` step on `local` works in its worktree on this machine, as `pi` does.

In a workflow with several [workspaces](ohflow.md#workspaces), a local step reads every workspace on this machine and writes in its own. A step on an ssh box or a cloud box gets its own workspace alone: the transport carries one branch of that workspace's `origin` out and back, so the agent there cannot read the other workspaces. A step on an ssh box or a cloud box that writes in an owned workspace needs the `remote` of that workspace; `validate` refuses the workflow without one.

Every harness executor starts its runner through `proc.spawn_managed`, with the environment from `proc.agent_env`. On Windows the runner and its descendants enter a kill-on-close Job Object. On Linux and macOS the runner leads its own process group, and its descendants stay in that group. Cancelling a run therefore removes the agent and its MCP children together.

Every harness executor takes a stall limit. `CliAgentRuntime` applies `Step.stall_timeout_s` and stops an agent whose event stream goes silent while no tool call is open. The attempt then records `stall`, which ends as an `agent_error` ([retry tokens](ohflow.md#retry)).

## Liveness and tool output

An agent that waits on its own command is working, not hung. Every harness executor reports its tool calls to the tool-output contract, `logs/tool-output/` in the attempt directory, and the runtime keeps the set of open calls from it.

- While a call is open, the stall clock waits. The command time cap (`command_time_cap_s`, or the default from `execution_timeout_s`, plus 60 s) applies; past it the attempt records `command_time_cap`.
- Once an agent has answered, the exit grace governs its shutdown and the stall clock stops.
- `result.json` and the `attempt_finished` payload carry `open_tool_call` when a call was open at the end.
- `result.json` names what built it in `record_source`. `runner` means the runner wrote it. When a runner is killed or dies, `collect` rebuilds the record: `event_log` means from the runner's event log, and `attempt_files` means the runner died before it opened that log, so the record comes from the attempt's other files, such as `remote.json` and `kill-abort.json` of a cloud attempt. `none` means nothing could be read, and the `error` then holds the fault of a rebuild that failed. A rebuilt record carries the attempt's wall time and, from the tool-output index, the call that was still open; both end at the moment `recovery.ended_at` names. `recovery.ended_basis` says how that moment is known: `kill` is the time the executor's `kill` wrote to `kill.json`, `last_write` is the newest write in the attempt directory (the runner lived at least that long), and `recovery_time` is the moment of the rebuild (an upper bound). `recovery.event_log` is `read`, `absent`, `empty` or `unreadable`, with the skipped lines in `unparsed_lines`. A cloud record adds `recovery.tokens`: `event_log`, `abort_answer`, or `unknown` when nothing counted them, which is not a count of zero.
- The dashboard shows a running call's output in the peek and every call's output in the inspector; the exit report shows the call open when an attempt failed.

| Harness executor | Open calls | Output while the command runs |
|---|---|---|
| `pi` | `tool_execution_start` / `_end` | yes, from `tool_execution_update` |
| `claude` | `tool_use` / `tool_result` | Bash: yes, through `CLAUDE_CODE_SHELL_PREFIX` = `shell_tee.sh`, which copies Bash tool lines only and leaves MCP servers and hooks untouched. PowerShell: at the end |
| `codex` | app-server `item/started` / `item/completed` | yes, from `outputDelta` |
| `durable` | pi's `tool_execution_start` / `_end`, over ssh | yes, from `tool_execution_update` |
| `pi-cloud` | pi's `tool_execution_start` / `_end`, over the Worker's event stream | yes, from `tool_execution_update` |
| `claude-cloud`, `codex-cloud` | pi's `tool_execution_start` / `_end`, which the Worker builds from the CLI's messages | at the end |

codex runs over `codex app-server` through `ohflow.codex_appserver`, which prints the `codex exec --json` shapes plus `item.output_delta`.

## Model tiers

A step names the rung of the inference ladder it needs in `ModelConfig.model`: `heavy` or `light`. The operator settings name the model. `tiers.heavy.<harness executor>` and `tiers.light.<harness executor>` in `ohflow.settings.json` map both tiers for every harness executor, and `ohflow.settings.local.json` overrides any of them. Validation checks the model a tier resolves to against the harness executor's own model rules, and an unmapped tier fails validation naming the setting. The step's `spec.json` carries the resolved model with `tier` beside it, and `validate -v` prints `model=<model> tier=<tier>`. A model id in `ModelConfig.model` passes through untouched. Give `heavy` to the implementer and the judge, and `light` to scouts and reviewers.

## Tool policies

A tool policy is the tool set an agent is built with. Set it in the workflow, never in the brief. Narrowest first:

1. `terminal` alone.
2. `terminal` and `file_editor`.
3. The default set: `terminal`, `file_editor`, `task_tracker`.
4. The default set plus skills.
5. Plus MCP servers.

A `pi` step reaches MCP servers through `mcp_config`. The `mcp_config` shape and the narrowing fields are in [ohflow](ohflow.md#narrow-an-mcp-tool-policy). The implement and review tool policies are in [implement-review](implement-review.md).

## Tool policy in a workflow

```python
AgentSpec(role="implementer", brief="...", harness_executor="pi",
           model=ModelConfig(model="heavy",
                           base_url="https://api.z.ai/api/coding/paas/v4",
                           api_key_env="ZAI_CODING_CN_API_KEY",
                           params={"thinking": "high"}),
           tools=ToolPolicy(only=("terminal", "file_editor")))
AgentSpec(role="rollcall", brief="...", harness_executor="claude",
           model=ModelConfig(model="light", base_url="", api_key_env=""))
AgentSpec(role="rollcall", brief="...", harness_executor="codex",
           model=ModelConfig(model="light", base_url="", api_key_env="",
                           params={"reasoning_effort": "low"}))
```

The signed-in harnesses (`claude` and `codex`) sign in with their own login, so `api_key_env` is empty. In the usual setup, validation refuses every field that would claim a tool policy the signed-in harness controls: `tools.only`, `tools.allow`, `tools.block`, `skills`, `mcp_config`, `enable_browser`, `enable_sub_agents`. With `agent_profile="hermetic"`, `claude` accepts `tools.only`; `codex` refuses it, because only `claude`'s registry row carries `CAP_TOOLS_ONLY`.

| | pi | claude | codex | durable | pi-cloud |
|---|---|---|---|---|---|
| Executable | pi CLI | `OHFLOW_CLAUDE_EXE`; else on Windows the npm `claude.cmd` target `claude.exe`, on Linux and macOS the first `claude` on PATH | `OHFLOW_CODEX_EXE`; else on Windows the npm `codex.cmd` target, `node` + `codex.js`, on Linux and macOS the first `codex` on PATH | an ssh box: `OHFLOW_DURABLE_SSH`, else `C:\Windows\System32\OpenSSH\ssh.exe` on Windows and the first `ssh` on PATH on Linux and macOS, then `node` + the host on the box; `local`: `OHFLOW_DURABLE_NODE`, else `node` | this Python + `ohflow/pi_cloud_client.py` over HTTPS |
| Model params | `thinking` | `effort` | `reasoning_effort` | `thinking` | `thinking` |
| `AgentSpec.agent_profile` | none | `None` or `"hermetic"` | `None` or `"hermetic"` | none; must be empty | none; must be empty |
| `AgentSpec.box` | none | none | none | the box's ssh host alias, such as `buildbox`, or `local` for this machine; required | none |
| `retry.carry_context` | yes | yes (`--resume --fork-session`) | no | no; a reattach continues the attempt instead | no; a reattach continues the attempt instead |
| Schema | the final message | native `--json-schema` | native `outputSchema` on `turn/start` | the final message, from the box | the final message, from the Worker |
| Announced tool policy | offered tools | the `system` `init` event | none; servers from `config.toml` plus `codex_apps` | the offered list from `tools.only` | the `tools` of the `pi_cloud_start` line |

Each harness executor accepts only the model params in its row. Its `agent_errors` refuses any other param and a non-empty `ModelConfig.extra_body`.

## What `agent_profile="hermetic"` removes and keeps

A hermetic agent starts from nothing the signed-in harness owns, except its login. Every harness executor also drops the launching session's variables (`CLAUDE*`, `CLAUDECODE`, `ANTHROPIC_BASE_URL`), hermetic or not.

| Harness executor | Removes | Keeps |
|---|---|---|
| `pi` | has no profile; it is always hermetic: no ambient extensions, skills, prompts, context files or themes | only what the workflow names |
| `claude` | every `CLAUDE.md` instruction file, the user's and the project's (`CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules`), by `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`; the user's settings (`--setting-sources project,local`); every built-in tool the workflow does not name (`--tools`); every MCP server the workflow does not name (`--strict-mcp-config`) | the OAuth login, the workflow's `--mcp-config` servers, the project's and local settings files (`.claude/settings.json`, `.claude/settings.local.json`) |
| `codex` | the real `~/.codex` configuration, its hooks and its MCP servers (the agent gets its own `CODEX_HOME`) | the login (`auth.json` is a hard link to the real file), the workflow's MCP servers |

`claude` offers two other switches, and neither serves: `--safe-mode` drops the `--mcp-config` servers, and `--bare` needs an API key.

Command time caps follow one rule on every harness executor that runs a terminal: [ohflow](ohflow.md#command-time-caps). Structured results and `schema_error`: [ohflow](ohflow.md#structured-results-and-dimensional-review). Pricing, `cost_source` and token reconcile: [transcripts](transcripts.md).

## pi

Install the pi CLI with `npm install -g @earendil-works/pi-coding-agent`; the binary is `pi`. Off Windows ohflow takes the first `pi` on PATH, and `OHFLOW_PI_EXE` overrides it. The step's `api_key_env` names the variable that holds the provider key, such as `ZAI_CODING_CN_API_KEY`.

`thinking` takes `off`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`. Browser and sub-agent tool policies are refused. `task_tracker` has no pi equivalent; validation drops it with a warning.

Each attempt gets its own `pi-agent/` and `session/`. The runner turns off ambient extensions, skills, prompts, context files and themes. It loads only what the workflow names. It pins Git Bash through `OHFLOW_BASH` and leaves stdin closed.

MCP servers run on pi's built-in MCP support, which needs pi 1.4 or later. The runner writes the step's `mcp_config` servers to `pi-agent/mcp.json` and loads `-e builtin:mcp`. `--no-extensions` keeps `codemode` and `tool_search` off. Before the first model turn, `pi mcp list --json` connects each server and lists its tools. The listing goes to `logs/mcp-list.json`. A server that does not connect fails the attempt. The runner expands the `allow` globs and the block globs over the listed `server.tool` addresses. The block globs are the step's own `tools.block`. An `allow` glob that matches no tool fails the attempt, and so does a canonical-name collision. Each selected tool gets `direct` exposure through `toolExposure`. Every other tool stays `hidden`, and a server with no selected tool gets `enabled: false`. `--tools` names the selected tools in pi's spelling, such as `mcp__note_store__memory_search`, and `--exclude-tools` names the blocked ones. A blocked tool is therefore unreachable.

The in-flight guard applies the step's `write_scope` globs to `edit` and `write`, caps each bash timeout, and sets `GIT_PAGER=cat`. It narrows cooperative pi tools. It is not a shell sandbox.

`max_iterations` caps assistant tool-use turns. Provider and agent retries are off inside pi, so ohflow owns the retry budget and the execution-start budget. `RetryPolicy(carry_context=True)` forks the previous attempt's session, which the harness executor module names through `resume_target`.

## claude

`-p --output-format stream-json --verbose --permission-mode bypassPermissions --session-id <uuid> --model <m>`. Without `bypassPermissions` a headless MCP call blocks.

The `init` event and the model name some things differently. `Task` is `Agent`. Connector `claude.ai Gmail` is server `claude_ai_Gmail`. The harness executor records both forms. The last `result` event carries the final text, usage and `total_cost_usd`. A failed login arrives as a `<synthetic>` assistant reply, and the harness executor records that text as the error.

Hermetic: `--tools <mapped list> --strict-mcp-config --mcp-config <file> --setting-sources project,local`, and the environment variable `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1`, which drops every `CLAUDE.md` instruction file. `tools.only` maps `terminal` to `Bash`, `file_editor` to `Read,Edit,Write,Glob,Grep`, `task_tracker` to `TodoWrite`. Preflight runs `claude auth status` and refuses a logged-out CLI.

## codex

`python -m ohflow.codex_appserver --codex <argv> --cwd <worktree> --final <out>/final.md --model <m> [--effort <e>] [--schema <file>] --prompt <bootstrap prompt>`. The bridge starts `codex app-server --listen stdio://` in the worktree and speaks JSON-RPC on its stdin. It opens one thread with `approvalPolicy` `never` and `sandbox` `danger-full-access`, and sends the bootstrap prompt as one `turn/start`. It passes the step's model to `thread/start` and `turn/start`, so the agent runs the workflow's model and not the `config.toml` default. It writes the `final_answer` message, else the last agent message, to `final.md`. The base `tiers.heavy.codex` model at `reasoning_effort` `high` runs on the signed-in ChatGPT account with codex-cli 0.160.0; 0.157.1 gets a `model_not_found` 400 for it (both tried 2026-11-04). The result's `codex_version` is the `--version` of the CLI that the [launch rules](#launch-rules-for-the-cli-harness-executors) resolve.

A step `schema` reaches Codex as a strict `outputSchema`. The API refuses it with `invalid_json_schema` unless every object in it sets `additionalProperties: false` and lists all its properties as required. For open-ended report objects, leave `schema` off and gate the report file with a `command_exit` check.

Why `danger-full-access`: under `workspace-write` every write under `.git` is denied, and `--add-dir <repo>/.git` does not lift that. A worktree keeps its index and HEAD under `<repo>/.git/worktrees/<name>`, so `git add` and `git commit` fail.

Hermetic: `CODEX_HOME=<attempt>/codex-home` with a generated `config.toml` (the workflow's MCP servers, each with `default_tools_approval_mode = "approve"`) and `auth.json` as a hard link to `~/.codex/auth.json`, so a token refresh writes the one real file.

Codex announces no tool list, so `rollcall_matches` checks its servers only. Its MCP tools are deferred: a low-effort roll call reported no servers. Installed plugins add servers of their own (`cua_repl`), and Codex spells their tools `mcp__<server>.<tool>`; the harness executor announces them.

## durable

The step runs through the durable host, a Node program that ships in
[`host/`](../host/) and opens a pi-durable `Harness` over the step's
`session.sqlite`, so the step outlives the process that drives it.
`AgentSpec.box` names where: `local` is this machine, and any other name is the
ssh host alias of an ssh box. `durable` refuses an `agent_profile`; the roll call
and implement-review default `box` to the `durable.box` setting. A machine
needs Node 22.19 or newer, Git Bash on Windows (`OHFLOW_BASH` or
`CLAUDE_CODE_GIT_BASH_PATH` names it, else the usual install path) and bash
elsewhere, and its own provider keys (`ZAI_API_KEY`, `DEEPSEEK_API_KEY`) for
the providers the `durable.providers` setting lists.

**The install.** ohflow installs the host on the machine that runs the step,
at the step's launch (`durable_host.py`). It feeds `host/install.cjs`, with
the host's files embedded, to that machine's `node` on stdin (`ssh <box> node`
for a box). The installer writes the files to
`~/.pi-durable/ohflow-host/<version>/`, runs `npm ci` there (the dependencies
are the public npm packages `@earendil-works/pi-durable`, `pi-ai` and `chord`;
on Windows `postinstall` compiles `bin/winjob.exe` with the .NET Framework's
`csc.exe`) and prints one `durable_host` line naming the folder. The version is
the first 16 hex digits of the SHA-256 of the host's files with LF line
endings, so a changed host installs beside the old one and a running step
keeps its own; a folder that already holds the version answers at once.
`OHFLOW_DURABLE_NODE` overrides this machine's `node`, and `OHFLOW_DURABLE_SSH`
and `OHFLOW_DURABLE_SCP` the two OpenSSH executables; ssh always gets `-T -o
BatchMode=yes -o ServerAliveInterval=15`.

**The host's commands**, `node <host>/ohflow-step.mjs <mode> <arg>`:

- `prepare <key>` makes `~/.pi-durable/ohflow/<key>` on the box and prints
  one `durable_prepared` line naming the dir and whether a session file is
  already there.
- `run <key>` clones `spec.durable.remote_url` at `spec.durable.start_sha` into
  `<dir>/work` on the box, force-pushes the clone's HEAD to
  `spec.durable.branch` at the end, and writes `.` to stderr every 2 s,
  exiting when that write fails, so it stops within seconds when the ssh
  connection drops, and its commands stop with it.
- `local <step folder>` works in the worktree `spec.durable.work` names on
  this machine, pushes nothing, and ends when its stdout closes. The step
  folder is `<attempt dir>/durable`.

`run` and `local` send the brief to `spec.model.model` with the thinking level
`spec.model.params.thinking`, print pi's `--mode json` event shapes on stdout
(`message_end`, `tool_execution_start`, `tool_execution_update`,
`tool_execution_end`) and end with one `durable_end` line naming the head
commit, the uncommitted paths and the session file. Their own log lines carry
`ev` instead of `type`, such as `{"ev":"command_cap",...}`; a fault is a
`durable_error` line and exit 1. They write `transcript.md` and `usage.json`
beside `spec.json`, and keep the conversation in `session.sqlite` there.

**The transport, on an ssh box.** The run's worktree sits on this machine and the
work happens on the box, so git carries the step ([remote_git](../scripts/ohflow/remote_git.py)):
the executor's `launch` pushes the step's start commit to the project's own
remote `origin` on `ohflow/durable/<key>` (refusing a dirty tree, because
uncommitted work would not reach the box), the box clones from that branch,
the step pushes its result to it, and after `durable_end` the runner fetches
the branch back into the run's worktree with a fast-forward from the start
commit, then deletes the branch from origin (`branch_deleted` in the result's
`durable` block says whether origin accepted; a refused delete is no error,
and a reattach after the fetch pushes the branch again). A fault in the
fetch is the `fetch_back` error. A repository without `origin`
refuses to launch. A step on `local` has no transport: it needs no remote, and
its commits are in the worktree when it ends. The `pi-cloud` harness executor uses the same transport
and the same `attempt_key`, and every transport branch sits under `ohflow/`.

**The attempt key.** The coordinate with every character outside `[A-Za-z0-9._-]`
turned into `-`, then `-a<NN>` for the attempt, then `-` and the first 8 hex
digits of the SHA-1 of the resolved attempt directory; the branch is
`ohflow/durable/<key>`.

**The brief and the spec.** On an ssh box, the adapter sends `spec.json` (the spec plus
`durable: box, remote_url, branch, start_sha, command_cap_s`, where the box's
protocol key `command_cap_s` carries the command time cap from
`effective_command_time_cap`) and `brief.md` with every occurrence of the worktree
path and of the attempt directory replaced by `<dir>\work` and `<dir>`, in both
the backslash and the forward-slash form. Its position block names the transport
branch `ohflow/durable/<key>` as the current branch and the worktree's branch as
the branch its commits are fetched onto. A handover the agent writes lands at
`<dir>/handover.md` for the same reason, and the runner copies it back with the
transcript and the usage. On `local`, the adapter writes `spec.json` (the spec
plus `durable: box, key, work, command_cap_s`) and the brief unchanged to the
step folder, and copies the transcript and the usage out of it.

**Tools.** `tools.only` maps `terminal` to `bash` and `file_editor` to `read`,
`write`, `edit`; empty means all four. The host offers no MCP servers, so
`mcp_config`, `tools.allow`, `tools.block`, `skills_dir`, `extra_body`,
`enable_browser` and `enable_sub_agents` are refused. `skills` is accepted: the host resolves each
name on the box, as `~/.agents/skills/<name>/SKILL.md` in the box's own copy
of the skills tree, lists the skills in a prompt section, and a name with no
`SKILL.md` there, or a name made only of dots, ends the step with a
`durable_error`. The box's copy of the skills tree is a clone that nothing
pulls by itself, so a skill change reaches a step after a pull on the box. An empty `api_key_env`
is right: the host holds its keys on its own box, for the providers the `durable.providers` setting lists. `write_scope`
guards `edit` and `write`, and `durable.command_cap_s` applies the command time
cap to every command on the box.

**Reattach.** A supervisor death or a host reboot reattaches the attempt: the
same attempt number, the same attempt directory, `start_kind: "reattach"` in
the run log. `reattach_target` answers `<box>:<step folder>` from
`remote.json`. The host finds `session.sqlite`, replays the saved transcript as
the same events with `"replayed": true`, and continues; a tool call the stop
interrupted comes back to the model as "Tool bash was interrupted and may have
partially run". Replayed `message_end` events carry their usage, so a reattached
attempt counts all its usage. A host that ends with no `durable_end`, such as one behind a dropped
connection, ends the runner with `host_lost: ssh exited <rc>; the host on <box>
ended without durable_end` (`node exited <rc>` on `local`), and the engine
answers that with a reattach, not a fresh attempt. A stall, the
command time cap or a judged failure is an ordinary failure under the usual retry
rules. A reattach spends a start from the total-execution bound and no
per-kind budget, and it does not advance the two-failure exclusion
([retry](ohflow.md#retry)); a step whose own work keeps killing its supervisor
stops when its starts run out. On a reattach to a box the adapter first waits for the
box (`ssh <box> exit` every 15 s, at most `OHFLOW_DURABLE_BOX_WAIT_S`, 900 by
default).

**A kill ends the host's step.** On `local`, the host is a child in the
runner's kill-on-close job (a process group elsewhere), so a kill or the
supervisor's death ends it with its commands. On an ssh box, the execution timeout,
a phase abort and `ohflow kill` kill the local ssh client, so the connection drops. The
host's tether (`host/src/tether.mjs`) writes one byte to stderr every 2 s and
exits when the write fails, so the host and the command it runs end within
seconds. Live check, 19.11.2026: the engine killed a roll-call step in the
middle of a 20-minute `python -c "time.sleep(1210)"` command. `Get-Process
python*,node*,bash*` on the box, 40 s after the kill, listed no process that
started after the step began, and the step's `session.sqlite-wal` was last
written 16 s before the kill.

**Preflight** checks that the box runs Node 22.19 or newer: this machine's
`node --version` for `local`, else `ssh <box> exit` and `ssh <box> node
--version`. The box comes from `OHFLOW_DURABLE_BOX`, else the `durable.box`
setting. The install happens at launch, not in the preflight.

## pi-cloud

The step runs in one Cloudflare Durable Object of the operator's own pi-cloud
Worker, at `OHFLOW_PI_CLOUD_URL`, else the `pi_cloud.url` setting. One
object runs one attempt; the object's name and the operation id are both
the attempt's key, so each attempt number gets its own object.

**Transport.** The same git transport as `durable` ([remote_git](../scripts/ohflow/remote_git.py)):
`launch` pushes the step's start commit to the project's own `origin` on
`ohflow/pi-cloud/<key>` (the key is the shared `attempt_key`), the Worker clones
the branch and checks that HEAD equals the posted `start_sha`, and after a
`pi_cloud_end` with `pushed: true` the runner fetches the branch back with a
fast-forward and deletes it. `pushed: false` is the error `push_failed`, or
`clone_failed` or `skills_failed` when the `push_error` names the box's clone or
skills fetch; any end status other than `done` is `unanswered`.

The box checks out the transport branch `ohflow/pi-cloud/<key>`. The posted brief's
position block names it as the current branch, cloned at the start commit, and names the
worktree's branch, where the executor fetches the returned
commits (`remote_git.transport_position`). The `claude-cloud`, `codex-cloud` and
`durable` briefs carry the same two lines with their own transport branch.

**Routes and headers.** Every route is
`<url>/attempts/<name>/<action>` with `<name>` percent-encoded, and needs
`Authorization: Bearer <token>` and `User-Agent: ohflow-pi-cloud/1` -
Cloudflare answers error 1010 with HTTP 403 to Python's default `User-Agent`,
so every request sets its own. `POST step` carries the rewritten brief, the
model (`provider/id`), the thinking level, `max_iterations`, the remote URL,
the branch, the start commit and the ohflow coordinate; a
repeat with the same operation id answers `accepted: false, reattach: true`
and changes nothing. The model's provider must be one that the
`pi_cloud.providers` setting lists, the providers whose keys the Worker holds.
`ohflow.settings.json` ships that list empty, so validation refuses every
`pi-cloud` model until `ohflow.settings.local.json` names a provider.
`GET events` is NDJSON: a `pi_cloud_start` line, the transcript replayed
with `"replayed": true`, then live pi event shapes, a
`pi_cloud_beat` every 15 s, and `pi_cloud_end` when the operation settles.
`POST abort` stops the operation. `GET transcript` and `GET out/<file>` serve
the agent's text. `GET /` answers 404 with both headers and 401 with a wrong
token, which is what the preflight reads. The token variable is
`PI_CLOUD_TOKEN`; `OHFLOW_PI_CLOUD_URL` overrides the Worker's URL.

**Iteration limit.** The Worker enforces `max_iterations` and echoes it in the
`step` answer. pi-durable's `maxTurns` ends the run after that many tool
rounds, the last round's tools included, and the end line says `unanswered`,
`turn_limit`. The runner records `max iterations N exceeded`, and the result's
`settings.effective` carries `max_iterations` and
`max_iterations_enforced_by: "worker"`. A Worker whose answer names no limit
predates the field; ohflow then counts the tool-use turns on the stream itself,
stops at the limit as `pi` does, and records `max_iterations_enforced_by:
"ohflow"`.

**The client.** `ohflow/pi_cloud_client.py`, standard library only, run by
path under the same interpreter as the runner. It copies the stream to stdout
flushed per line, never prints a beat, drops a `message_end` or
`tool_execution_end` whose `entryId` it already printed and a
`tool_execution_start` whose `toolCallId` it already printed, and reconnects
inside one process when the stream drops, the connection fails, the read
times out, or the Worker answers 408, 429 or 5xx (`OHFLOW_PI_CLOUD_RETRY_S`,
5 s between tries). The lost-Worker clock counts from the last contact - a
response opening, and every line read, beats included - so a stream that
stays healthy for longer than the bound and then drops reconnects like any
other drop. When neither a line nor an opened response has arrived for
`OHFLOW_PI_CLOUD_LOST_S` seconds (900 by default) it exits 3, and the runner
records `host_lost: the event stream of <url>/attempts/<key> ended without
pi_cloud_end (client exited 3)`. Any other 4xx is a verdict: the client
prints one `pi_cloud_error` line naming the status and the body, exits 1, and
the engine does not reattach the attempt.

**Reattach.** The same rule as `durable`: a `host_lost` closes the attempt
`deferred` and the engine continues it in the same directory under the same
attempt number. The reattach keeps `remote.json`, pushes nothing, and posts
`step` again with the same operation id; the Worker replays the transcript it
holds, and the replayed `message_end` events carry their usage, so the
reattached attempt counts its conversation once. A reconnect or a reattach
that arrives while a tool call is still running ends the replay with a
`tool_execution_start` for that call (Worker `4bf4a32`), without an
`entryId`, so the stall clock waits on the open command instead of firing at
the silence. A stall or the command time cap ends the attempt - the runner posts
`abort` for the attempt's key - and the
retry is a fresh attempt with a new number, key, object and branch, so a
retry never meets the old object's 409. The execution timeout, a phase
abort and `ohflow kill` kill the runner instead, and the executor's `kill` posts the same
`abort` and keeps the answer in `kill-abort.json`, so no container runs on
for an attempt that is over. This holds for `pi-cloud`, `claude-cloud` and
`codex-cloud`. A supervisor death never calls `kill`, so its reattach still
finds the object.

**The agent's world.** The Worker's agent sees `/workspace/repo` and
`/workspace/out`, never this machine's paths: the adapter rewrites both
renderings of the worktree path and of the attempt directory in the brief
before it posts. Its tools are fixed - `read`, `ls`, `find`, `grep`, `write`,
`edit`, `delete`, `exec` and four git tools - plus `codemode` and the MCP
servers of the box. `agent_errors` refuses a non-empty `agent_profile`, a
provider outside the `pi_cloud.providers` setting, a model param other than `thinking`,
a non-empty `extra_body`, `api_key_env` (the Worker holds its keys),
`tools.only`, `mcp_config`, `skills_dir`, `enable_browser`,
`enable_sub_agents` and a `tools.preset` other than `default` - no workflow
MCP servers, no browser, no second machine.

**Skills.** `skills` names folders of the skills repository the Worker mirrors. When a step
that names skills starts, the Worker's `SkillsMirror` object asks GitHub for the
head of that repo's `main`, copies that commit into its own SQLite when it is
new, and the step pins it. The first step after a push therefore pins the
pushed commit. The step's workspace mounts only the named skills, read-only,
at `/workspace/.agents/skills/<name>`. Cloudflare's `skills()` extension lists
them in the prompt and adds the tools `activate_skill` and
`read_skill_resource`. The model runs a skill's scripts with `exec` from that
folder. A name the mirror does not hold fails the step with HTTP 400 before
any work starts. The `pi_cloud_start` event and the step answer carry
`skills: {sha, names}`.

**MCP.** The box serves its MCP servers through one gateway in the
container (the table `worker/snapshot/box/mcp-servers.json` and the operator's
`snapshot.mcp_servers`, [the pi-cloud Worker](pi-cloud-worker.md#mcp-in-the-box)).
The `pi_cloud.mcp_servers` setting lists the same servers for validation, so
change both together. `tools.allow` and
`tools.block` narrow them with the same `server.tool` globs as `pi`:
validation accepts an `allow` entry that names one of those servers, and
`POST step` carries both lists as `tools`, which the Worker applies to the
gateway's tool list. An `allow` glob that matches no tool answers 400. The
model calls an MCP tool from a `codemode` script as
`tools.mcp__<server>__<tool>(args)`, and the `pi_cloud_start` line lists each
offered MCP function beside `codemode`. A call that the container's stop cuts
off returns `interrupted: ...` to the script. brave-search runs with a
placeholder key; the Worker writes the real `BRAVE_API_KEY` into the request
header on the way out, so the box holds no key.

For a source-only agent that needs no MCP server, `ToolPolicy(block=("*.*",))`
removes every `server.tool` address. A bare `"*"` is not a valid address glob.
The cloud executor still offers its fixed built-in file, command and git tools;
this policy does not restrict their filesystem reach. Confirm `mcp_servers: []`
in `pi_cloud_start` before describing the agent as having no MCP access.

**The box.** The step's container starts from the Worker's default snapshot,
built on `cloudflare/debian-trixie`, so the step installs nothing. The
snapshot holds git, gh, ripgrep, jq, uv, Python 3, Node 24, pnpm, pandoc,
ffmpeg, sqlite3, curl, the CLIs `pi`, `codex` and `claude`, the operator's
skills repo and MCP server programs when its settings name them, the MCP gateway and Playwright MCP with headless
Chromium, and no credential. Outbound traffic reaches only the hosts the MCP
servers need, through the Worker. The agent reads the box rules in its system prompt, and
`box-versions` in the box prints every version. `pi_cloud_start` names the
key of the snapshot the attempt started from. While the Worker's current
snapshot key has no built snapshot, a step starts from the newest snapshot
already built, and a `POST step` answers 503 only when none is built. The
recipe and the build commands are in [the pi-cloud Worker](pi-cloud-worker.md#the-default-snapshot).

**Container cost.** The container is `standard-1` (4 GiB memory, 8 GB disk),
and Cloudflare bills its memory and disk for every second it runs, busy or
idle; CPU bills for active use only. The Worker stops the container when the
step settles or is aborted, because the container backend sets no inactivity
timeout. `pi_cloud_end` and the abort answer carry the container's meter:
`durable_object_id`, `instance`, `seconds` over every launch, and `launches`.
The result's `infra` block holds that meter, and `infra_cost` prices it at the
list rates in `cloud_spend.py`, memory and disk only; `table` shows it as
`Infra cost` beside `Cost`. At run end the supervisor compares it with
Cloudflare's own meters per object (`cloudflare.json`, see
[ohflow](ohflow.md)).

**Preflight** checks that `PI_CLOUD_TOKEN` is set and that `GET <url>/`
answers 404 with both headers, naming the fault in words - unset, refused
(401) or unreachable, with the URL.

On Windows, a desktop process started before a user environment variable was set
can miss an existing token. If preflight says it is unset, check presence in the
process and user scopes without printing the value. When the user scope holds the
configured token, load it into the launching PowerShell process and repeat preflight:

```powershell
$env:PI_CLOUD_TOKEN = [Environment]::GetEnvironmentVariable('PI_CLOUD_TOKEN', 'User')
```

The cloud snapshot provides `python3`; use that spelling in cloud agent briefs.
Local command and gate steps run on the local box, so choose their
interpreter separately. The container's outbound-host policy is described under
**The box** above; arrange local capture and git transport when a source is outside it.

**Where it lives.** The Worker is `worker/` in this skill, and
[the pi-cloud Worker](pi-cloud-worker.md) deploys it to the operator's own
Cloudflare account and lists its routes. A step may clone a private repo of the Worker's `GIT_OWNER` that its `GITHUB_TOKEN` reaches;
the token's repository access on github.com is the list, and a step pushes only
`ohflow/` branches. So a `pi-cloud` test case needs `--repo` with such a repo as `origin`.

## claude-cloud and codex-cloud

These two executors run Claude Code or Codex in the same pi-cloud Worker,
in a `CliAgent` Durable Object that drives the CLI through Cloudflare's
`ContainerHarness` (`ohflow/cli_cloud_runner.py`, bound per kind by
`claude_cloud_runner.py` and `codex_cloud_runner.py`). Everything in the
pi-cloud section holds - the transport, the client, the reattach rule, the
`/workspace/repo` and `/workspace/out` rewrite, the container chronometer and the
preflight - with these differences:

- **Routes and branch.** The routes are `<url>/claude/attempts/<name>/<action>`
  and `<url>/codex/attempts/<name>/<action>`, and the transport branch is
  `ohflow/claude-cloud/<key>` or `ohflow/codex-cloud/<key>`.
- **Model.** `claude-cloud` takes a Claude model id or an alias of the
  Claude CLI; `codex-cloud` takes a Codex model id. A tier resolves through
  `tiers.<tier>.claude-cloud` or `tiers.<tier>.codex-cloud`. Neither takes a
  model param, a `base_url` or an `api_key_env`.
- **Login.** The CLI signs in with the operator's subscription. The Worker
  holds the Claude Code token (the secret `CLAUDE_CODE_OAUTH_TOKEN`) and a
  Codex login made for the Worker alone, and writes them into the request
  headers outside the container. The `codex-cloud` preflight also checks that
  the Worker holds that login; `node scripts/codex-login.mjs`, run from
  `worker/`, makes it.
- **Tools.** The CLI keeps its own tools and reaches the MCP servers of
  the box over HTTP. The object announces no tool list, so the rollcall gate
  leaves tools unchecked and checks the servers. `agent_errors` refuses
  `tools.allow`, `tools.block`, `tools.only`, `mcp_config`,
  `skills_dir`, `enable_browser`, `enable_sub_agents` and a non-empty
  `agent_profile`.
- **Skills.** `skills` names folders of the skills repository the Worker
  mirrors, as for pi-cloud: the step syncs the mirror when it starts and pins
  `{sha, names}`, which the step answer and the `pi_cloud_start` line carry.
  When the container starts, the box fetches the named skills of that commit
  into `/opt/agent-skills`, which then holds only those skills.
  `~/.claude/skills` and `~/.agents/skills` link to that folder, so Claude Code
  and Codex load them as their own skills. `/etc/agent-box/skills.json` in the
  box records the commit and the names. `pinSkills` in
  `worker/src/skills-feed.mjs` answers HTTP 400 for a name that the pinned
  commit lacks, before any work starts. A fetch that fails twice ends
  the step with `skills_failed: ...`. A step that names no skill
  reads the copy of the skills repo that the default snapshot holds, at the
  commit of the operator's `snapshot.skills` setting. Live check, 22.11.2026:
  a `claude-cloud` step that named `handover` and `prune-file` pinned the head
  of the skills repo's `main`, and `ls /opt/agent-skills` in its box printed
  those two folders alone, 16 files by `/etc/agent-box/skills.json`.
- **Liveness.** A tool call reaches the stream as `tool_execution_start` and
  `tool_execution_end` once the CLI reports it; no output arrives while a
  command runs. Claude Code reported its calls when they started; Codex
  reported some at their start and others only at their end. A container restored from a freshly built snapshot took 100 s
  to answer, so the rollcall gives both executors a 600 s stall limit.
- **Iteration limit.** The Worker enforces `max_iterations`. For Claude Code it
  passes `--max-turns`; for Codex, which has no such flag, it counts the tool
  calls and aborts the operation at the first call past the limit, as the
  local `codex` runner does. Either way the end line says `unanswered`,
  `turn_limit`, and the result records it as for pi-cloud. The tool-use turns
  reach ohflow only when the step settles, so ohflow does not count them: a
  Worker whose answer names no limit runs the CLI unbounded, and the result
  records `max_iterations_enforced_by: null`.
- **Reattach.** The pi-cloud rule holds. A repeat `step` post answers
  `accepted: false, reattach: true`, and the CLI object replays the
  conversation when the step settles, not on connection. Live check,
  21.11.2026, on both executors: the roll call's `silent` scenario with a
  600 s stall limit, the supervisor's process tree killed with `taskkill /F /T`
  while the 100 s command ran, then `--resume`. Attempt 1 closed `deferred`
  `reattached`, attempt 1 started again with `start_kind: reattach` in the
  same directory, the Durable Object ran its container through the gap
  (`launches: 1`), and the step passed every gate as one attempt.
- **Container loss.** A container that stops during a step settles it
  `unanswered`, `container_lost`, and the runner records that error.
- **Usage.** Tokens come from the CLI's own report, input and output without
  the cache split; `cost` is 0 with `cost_source` `subscription`, because a
  subscription bills no tokens.

The Worker side is [the pi-cloud Worker](pi-cloud-worker.md#claude-code-and-codex-steps).

## Launch rules for the CLI harness executors

- **On Windows the npm shim resolves to its target.** ohflow reads `%APPDATA%\npm\<name>.cmd`, else the first `<name>.cmd` on PATH, and starts the `.exe` or the `node` script that the shim names. No argument passes through `cmd.exe`, so quotes and `&` arrive intact and the 8191-character limit does not apply. On Linux and macOS ohflow starts the first `<name>` on PATH. An `OHFLOW_CLAUDE_EXE` or `OHFLOW_CODEX_EXE` override comes first on every OS.
- **One bootstrap prompt.** `Your brief is at <abs>/brief.md. Read it and follow it.`
- **A clean environment.** Every `CLAUDE*` variable and `ANTHROPIC_BASE_URL` is removed. A desktop-app session exports 25 `CLAUDE*` names and an `ANTHROPIC_BASE_URL` that points at the app's own proxy.
