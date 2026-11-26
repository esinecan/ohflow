# The pi-cloud Worker

The `pi-cloud`, `claude-cloud` and `codex-cloud` harness executors drive one Cloudflare Worker,
named `pi-cloud` unless the setting `name` says otherwise, which runs each step in a container in
your own Cloudflare account. Its source is `worker/` in this skill. Its code mode scripts run in a
second Worker, `<name>-codemode` (`worker/sandbox/`), which keeps pi-codemode's class name `CodemodeSandbox`. The executors are described in [harness executors](harness-executors.md#pi-cloud);
this page deploys the Worker and describes its side.

## Deploy it to your Cloudflare account

You need a Cloudflare account on the Workers Paid plan, because the Worker runs Containers, and
Node 22.19 or newer. Containers bill their memory and disk for every second they run.

1. **Install.** From `worker/`, run `npm ci`.
2. **Sign in.** Run `node node_modules/wrangler/bin/wrangler.js login`, or export
   `CLOUDFLARE_API_TOKEN` with the Workers and Containers permissions.
3. **Write your settings.** Create `worker/pi-cloud.settings.local.json`, which git ignores, with the
   keys of the table below that you need. Your values override the shipped
   `worker/pi-cloud.settings.json`, which names the Worker `pi-cloud` and leaves every other value
   empty. Every Node script here takes `--settings <file>` to read another file in place of
   `pi-cloud.settings.local.json`. `set-secrets.ps1` takes no such flag and always reads
   `pi-cloud.settings.local.json`.
4. **Deploy.** From `worker/`, run `node scripts/deploy.mjs`. It deploys `<name>-codemode` first and
   then `<name>`, with your settings as the Worker's vars and your snapshot settings bundled into
   the recipe, and records the address the deploy prints under your `name` in the git-ignored
   `worker/.pi-cloud-urls.json`. `--dry-run` bundles both into `dist/` and uploads nothing.
5. **Set the secrets.** For each of `OHFLOW_TOKEN` (a random string the supervisor sends as
   `PI_CLOUD_TOKEN`), `GITHUB_TOKEN` and `ZAI_API_KEY`, which serves the default model, run
   `node node_modules/wrangler/bin/wrangler.js secret put <NAME> --name <name>` from `worker/`.
   `DEEPSEEK_API_KEY` serves the DeepSeek models and `BRAVE_API_KEY` the brave-search server; set them
   when you use those. On Windows, `scripts/set-secrets.ps1` sets all of them at once on the Worker
   your local settings name, from your User environment (`PI_CLOUD_GITHUB_TOKEN` there becomes
   `GITHUB_TOKEN`), and makes `PI_CLOUD_TOKEN` when it is unset.
6. **Build the default snapshot.** Run `node scripts/snapshot.mjs build`, then
   `node scripts/snapshot.mjs verify`. Both reach the Worker at `PI_CLOUD_URL`, else at `url`, else
   at the address the deploy recorded for your `name`, and send the token from `PI_CLOUD_TOKEN`. When your settings clone repos, the build takes
   `gh auth token` as its setup token, and verify checks that the token left no trace in the box.
7. **Point ohflow at it.** Set `pi_cloud.url` in `ohflow.settings.local.json` and export
   `PI_CLOUD_TOKEN` on the supervisor. List the box's MCP servers in `pi_cloud.mcp_servers`.
   `ohflow preflight` then checks the route.
8. **For `claude-cloud`,** run `claude setup-token`, which prints a token that lasts one year, and store
   it with `wrangler secret put CLAUDE_CODE_OAUTH_TOKEN`. **For `codex-cloud`,** run
   `node scripts/codex-login.mjs` (section [Claude Code and Codex steps](#claude-code-and-codex-steps)).

A GitHub token for `GITHUB_TOKEN` is best a fine-grained token with read and write on Contents of
the repos your steps work in, and read on your skills repo.

### Settings

| Key | What it sets | Empty value |
|---|---|---|
| `name` | the Worker's name, shipped as `pi-cloud`: lowercase letters, digits and inner dashes, at most 54 characters. The code mode Worker is `<name>-codemode`, and the Worker's `CODEMODE_SANDBOX` binding names it | `pi-cloud` |
| `account_id` | the Cloudflare account the deploy and `set-secrets.ps1` use | wrangler uses the account of its login |
| `url` | the Worker's address for `snapshot.mjs` and `codex-login.mjs`; `PI_CLOUD_URL` wins | the address the deploy recorded for `name`; with none, both scripts stop and say so |
| `git_owner` | the var `GIT_OWNER`: the GitHub account whose private repos a step may clone | every step's repo is refused |
| `git_identity` | `{name, email}`: the default commit author and committer for cloud steps, installed as system Git config for both users and used by the pi workspace; repository config can override it | `ohflow <ohflow@users.noreply.github.com>` |
| `skills_repo` | the var `SKILLS_REPO`, `<owner>/<name>`: a repo you control whose skills the steps mount; the Worker follows its `main` branch | the checkout's `origin` remote when `git_owner` owns it, as in your own fork; otherwise no skills repo |
| `skills_root_skill` | the var `SKILLS_ROOT_SKILL`: the skill name when the repo root is one skill | read from `SKILL.md` when the checkout is that repo's root |
| `snapshot.skills` | `{repo, sha}`: a skills repo the snapshot clones to `/opt/agent-skills`, which a Claude Code or Codex step that names no skill reads | `/opt/agent-skills` is an empty folder in the snapshot |
| `snapshot.repos` | a list of `{repo, sha, name?, build?}`: repos the snapshot clones to `/opt/mcp/<name>` and builds with the `build` shell lines | no repo is cloned |
| `snapshot.mcp_servers` | MCP server entries added to the box's server table, in the shape of `worker/snapshot/box/mcp-servers.json` | the shipped table: sequential-thinking, brave-search, Playwright MCP |

`sha` is a full commit id. A box rules file of your own, `worker/snapshot/AGENTS.local.md`, which git
ignores, is appended to the shipped `worker/snapshot/AGENTS.md` when it exists. Your snapshot
settings and that file are part of the recipe, so a change to either gives a new snapshot key and
needs a snapshot build.

Changing `git_identity` also needs a deploy and snapshot build. It controls commit metadata;
the existing GitHub token still controls access. Snapshot verification creates a temporary
repository and checks a real commit's author and committer as both root and the agent user.

`node scripts/pins.mjs` moves the `sha` of `snapshot.skills` and of each `snapshot.repos` entry in
your settings file to the head of that repo's `main`, and prints each snapshot pin with the number of commits
it moved over. It reads the heads through `gh api`. `--dry-run` prints the same lines and leaves the
file as it is. The moved snapshot pins take effect with the next deploy and snapshot build.

### A second Worker in the same account

A `name` other than `pi-cloud` deploys a second pair of Workers, with their own Durable Objects,
snapshot, secrets and address, beside the first. The deploy writes the two configs with that name
to `wrangler.generated.json` beside `wrangler.jsonc` and `sandbox/wrangler.jsonc` and removes them
when it ends; the Durable Object classes and migrations are those of the checked-in configs. With
the name `pi-cloud` the deploy uses the checked-in configs as they are. A second Worker builds or
tests a snapshot without touching the Worker your steps use, whose steps would start from its
earlier snapshot from the deploy until the build ends. Give the test its own settings file,
for example the shipped values with `name` and `account_id`:

```
node scripts/deploy.mjs --settings <test settings>
node node_modules/wrangler/bin/wrangler.js secret put OHFLOW_TOKEN --name <name>
node scripts/snapshot.mjs build --settings <test settings>
node scripts/snapshot.mjs verify --settings <test settings>
node node_modules/wrangler/bin/wrangler.js delete --name <name>
node node_modules/wrangler/bin/wrangler.js delete --name <name>-codemode
```

With the shipped settings the build needs only `OHFLOW_TOKEN`. On 21.11.2026 this built the
shipped-settings snapshot on `ohflow-newcomer-test` while `pi-cloud` kept its version and key.

## Routes

One Durable Object `StepAgent` runs one ohflow step attempt, named `<attempt>` in each route
`/attempts/<attempt>/<action>`. Every route needs `Authorization: Bearer <OHFLOW_TOKEN>`, and
Cloudflare answers error 1010 to a client that sends Python's default `User-Agent`, so a client
names its own.

- `POST step` with `{operationId, brief, model, thinking?, remote_url, branch, start_sha, ohflow?, tools?, skills?, max_iterations?}`:
  clones `branch` of an allowed repo into `/workspace/repo`, checks that HEAD is `start_sha`, sets the
  session's model and thinking level, makes `/workspace/out` and submits the brief as an
  `ohflow.brief` entry. A repeat with the same `operationId` changes nothing and answers
  `accepted: false, reattach: true`; another `operationId` gets 409. `tools` is
  `{allow?, block?}`, two lists of `server.tool` globs over the box's MCP tools (`*` stays inside one
  segment, `**` crosses the dot); an `allow` glob that matches no tool gets 400. The answer lists the
  offered tools, with `codemode` and each MCP function, and `mcp_errors` names a server whose tool
  list failed. `skills` names skill folders of the skills repo (section [Skills](#skills)); a name the
  mirror does not hold gets 400, and the answer carries `skills: {sha, names}`. `max_iterations`, an
  integer 1 or more, becomes the session's `maxTurns`: the run ends after that many model calls, the
  tool calls of the last one included, and the operation settles `unanswered`, `turn_limit`. The answer and
  the `pi_cloud_start` line carry the limit the object enforces, or null.
- `GET events?operationId=<op>`: NDJSON. A `pi_cloud_start` line (with the object's
  `durable_object_id` and the container `instance`), the transcript so far as pi's
  `--mode json` events with `replayed: true`, then live events, and a `pi_cloud_beat` line every 15 s.
  `message_end` and `tool_execution_end` lines carry the entry's `entryId`, and a tool call still running
  when the request arrives gets a `tool_execution_start` after the replay. When the operation settles,
  the Worker pushes HEAD to `branch` without force, stops the object's container and ends with
  `pi_cloud_end` (`status`, `reason`, `start`, `head`, `dirty`, `pushed`, `push_error`, `usage`,
  `container`). A fault ends with `pi_cloud_error`. A dropped connection loses nothing: the next
  request replays from the start.
- `POST abort` with `{operationId}`: stops the operation, which then settles `unanswered`, `aborted`,
  and stops the object's container. The answer carries `container` and `last_look`: the box as it
  was just before the stop, `{at, took_ms, exit, text, truncated}` (`worker/src/last-look.mjs`), with `text` cut at 8000 characters.
  `text` reads without a second sample: the uptime, the load, the cores and the box's first
  process; whether a lookup of the box's own hostname answers within 2 s, and whether the hosts
  file names it; the machine's CPU shares since boot and over the look's own second, with the steal
  share; the container's cgroup CPU use and throttling since boot and over that second, and its
  limit; the memory; the count of live processes, of zombies and of processes blocked in the
  kernel; the zombies by parent; and the live processes, oldest first. `last_look` is null when
  the container was not running, and `{at, took_ms, error}` when the look failed. The whole look
  ends after 10 s at most, also when `exec` or the command's output never answers, and the stop
  follows in every case. ohflow writes `text` to `logs/box-last-look.txt` of the attempt, and
  `pi_cloud.last_look` in `result.json` points at it; its `absent` says why an abort left no
  look.
- `container` is the object's container chronometer: `durable_object_id`, `instance`, `seconds` (the
  container's running time summed over every launch in this object), `launches`, and `stopped` (the
  container was still running and this call stopped it). Containers bill the instance's memory and
  disk for every running second, and the backend sets no inactivity timeout, so a container left
  running after its step is billed until the object is evicted.
- `GET transcript`: the transcript as markdown. `GET out/<file>`: a file the agent wrote to
  `/workspace/out`, or 404.
- `POST submit`, `POST wait`, `GET messages`, `GET pending`: the raw session. `crash`,
  `stop-container`, `files`, `secret-scan` and `probe` answer only while `TEST_HOOKS` is `on`, which a
  test deploy sets with `--var TEST_HOOKS:on`. `secret-scan` greps the running container's files,
  every process environment and every command line for each placeholder and each real secret value,
  which it passes to `grep -f -` on standard input, so the value reaches no argv, file or environment.
  `probe` prints the container's processes, the CA directory and the gateway logs.

`MODEL` sets the default model. A step may clone a repo when `GIT_OWNER` owns it, GitHub reports it
private, and `GITHUB_TOKEN` reaches it; the Worker asks `GET /repos/<repo>` with the token and keeps
each answer for 60 seconds. The token's repository access on github.com is therefore the list of
repos, and a change there needs no redeploy. `GITHUB_TOKEN` stays in the Durable Object. A step
container has no general Internet: its outbound HTTP and HTTPS go through the Worker, which serves
only the hosts named under `secrets` in the box's server table and answers 403 to every other host.

## The default snapshot

Every step's container starts from one default snapshot, with `computerd` as its entrypoint, so a
step installs nothing. The recipe is `worker/snapshot/recipe.mjs`: setup steps run on the managed
image `cloudflare/debian-trixie` (Node 24). The CLIs, the npm MCP servers and the repo commits
are pinned; the image and the APT packages are not. The snapshot key is the first 16 bytes of
the SHA-256 of the image name and the steps, so the same recipe gives the same key, and a new snapshot pin or CLI version gives a new one. The box's rules file is `worker/snapshot/AGENTS.md` with your
`AGENTS.local.md` appended: the snapshot links it into `~/.pi/agent`, `~/.codex` and
`~/.claude/CLAUDE.md`, and `StepAgent` renders it as a system prompt section. `box-versions` prints
the version of each program in the box, and `box-chromium` renders a `data:` URL with headless
Chromium.

With the shipped settings the snapshot clones no repo: it holds the Debian tools, the document tools,
the `pi`, `codex` and `claude` CLIs, the npm MCP servers and headless Chromium. `snapshot.skills` and
`snapshot.repos` add your own repos, cloned at their pinned commits.

The Durable Object `SnapshotBuilder` (object `default`) builds the snapshot and stores its id under
the key. While the current key has no snapshot, `SnapshotBuilder.current()` answers the newest
snapshot built under an earlier key, so steps keep starting from that one, and a `POST step` refuses
with 503 only when the object stores no snapshot. Each attempt records the key of the snapshot it
started from and keeps that snapshot. `GET /snapshot` answers the current key, the record a step
would start from, and `built`, which is false while that record belongs to an earlier key. The
commands run from `worker/`:

- `node scripts/snapshot.mjs build [--force] [--log <file>]` streams the build. The setup
  token is the output of `gh auth token`, sent in the request body and given only to the setup steps
  that clone repos, as an environment variable of that one process. Git takes it as a
  command-line header, so no credential helper, credential file or remote URL keeps it.
- `node scripts/snapshot.mjs verify` starts a container from the snapshot without Internet,
  greps its filesystem for the token, and runs `box-versions` and `box-chromium`.
- `node scripts/snapshot.mjs status` prints the answer of `GET /snapshot`, and `key` prints the key
  the local recipe gives.
- `node scripts/try-recipe.mjs [--distro <name>] [--from <step>]` runs the recipe on a Windows
  machine in a WSL distro (default `boxtest`), which costs no Cloudflare build. Make the distro with
  `wsl --import` from the first layer of `node:24-trixie-slim`, untar the later layers into it, and
  set `appendWindowsPath=false` in its `/etc/wsl.conf`. Cloudflare documents
  `cloudflare/debian-trixie` as built from that image; on 14.11.2026 it carried Node 24.22.1.

A Claude Code or Codex step starts from the same snapshot through `ContainerHarness` (section
[Claude Code and Codex steps](#claude-code-and-codex-steps)), so the snapshot also holds the user
`agent` (uid 10001), `/workspace`, both CLI configs, and the `ContainerHarness` daemon
`d45c6a8182ef9070`, the same in `agents` 0.30.1 and 0.33.0, at `/opt/harness/harness-daemon.mjs`
behind the boot wrapper `/opt/harness/daemon.mjs` and its skills module `/opt/harness/box-skills.mjs`.
`/opt/agent-skills` exists in every snapshot, and `~/.claude/skills` and `~/.agents/skills` of both
homes link to it.

## Skills

A pi step gets the skills of the skills repo (`SKILLS_REPO`) through Cloudflare's `skills()`
extension from `agents/harness/pi`, with the source `workspace()` from `agents/skills`. The extension
lists each skill's name and description in a prompt section and adds the tools `activate_skill` and
`read_skill_resource`. A skill whose front matter sets `disable-model-invocation: true` is left out of
the list. The model runs a skill's scripts with `exec`, because the box sees the same files.

- **The mirror.** The Durable Object `SkillsMirror` (`worker/src/skills.mjs`), named `agent-skills`,
  holds commits of the skills repo's `main` in its SQLite. `sync()` asks GitHub for the head of
  `main` with the Worker's `GITHUB_TOKEN`, streams that commit's tarball into the SQLite when the
  commit is new to the mirror, and answers once the copy is complete. A step that names skills calls
  `sync()` when `POST step` first runs, so it pins the head of `main` of that moment. `current()`
  answers the stored commit, checks the head at most once a minute and leaves a new head to an
  alarm; `GET /skills` and a Worker that only reads the mirror call it. The mirror keeps each
  top-level folder that holds a `SKILL.md`, or, with `SKILLS_ROOT_SKILL` set, the whole repo as that
  one skill. It leaves out every path with a segment that starts with a dot and every file above
  512 KB, and keeps the newest three commits. On 15.11.2026 one commit of a repo of 49 skills was
  1049 files and 15.8 MB, copied in 2.5 s.
- **The mount.** Each `Workspace` mounts the mirror read-only at `/workspace/.agents/skills`, with the
  commit as the mount's version. `@cloudflare/computer` checks the version once per object wake and
  copies the files again when it changed. A step pins the commit when `POST step` first runs, and its
  mount holds only the named skills. A step that names none gets an empty folder and no skill tools.
- **Routes.** `GET /skills` answers the mirrored commit and its skill names, and `POST /skills/sync`
  mirrors the head of `main` now.
- **Failure.** A step whose mirror cannot be reached on `POST step` fails before any work starts.

`skillsMirror`, `skillsMount` and `keepMkdirOfExistingDirs` are exported for another Worker that binds
`SkillsMirror` with `script_name` set to this Worker's name (`pi-cloud` by default), and `src/mcp-front.mjs` for one that serves MCP tools
the same way. `src/skills.mjs` imports `cloudflare:workers` and its sibling `src/skills-feed.mjs`,
`src/mcp-front.mjs` imports no module, and the folder's package
name is `ohflow-pi-cloud`, so such a Worker depends on it with `"ohflow-pi-cloud": "file:<path to worker/>"`.

## MCP in the box

`box-mcp-gateway` (`worker/snapshot/box/mcp-gateway.mjs`, at `/usr/local/lib/box/mcp-gateway.mjs` in
the box) serves every server of `/etc/agent-box/mcp-servers.json` on port 8800: `POST /mcp/<server>`
takes MCP JSON-RPC (one message or a batch) and answers with JSON, and `GET /health` lists the
servers and the running ones. It starts each server as its own child on first use and keeps that
child for the life of the container, so a server that holds state in memory keeps it between calls.
The shipped table serves sequential-thinking, brave-search and Playwright MCP
(`--browser chromium --headless --isolated`); `snapshot.mcp_servers` adds yours.

`StepAgent` starts the gateway with `ctx.container.exec` on the first MCP request of a container,
with the box `PATH` and `NODE_EXTRA_CA_CERTS`, and reaches it through
`ctx.container.getTcpPort(8800).fetch()`. The first start from a freshly built snapshot can take
longer than the backend's default 30 s connect deadline, so `StepAgent` sets `connectTimeoutMs` to
120 s. On the first step of a snapshot key, `POST step` starts the container, lists every
server's tools and keeps the list in `SnapshotBuilder` under `mcp-tools:<key>`; later steps reuse
it. The step applies `tools.allow` and `tools.block`, keeps the selection with the step, and
installs each selected tool as a pi-durable tool named `mcp__<server>__<tool>` with
`replay: "unsafe"` and `callers: ["tools"]`. The model reaches them through the `codemode` tool,
whose scripts run in `RemoteCodemodeSandbox` objects of `<name>-codemode`. A call whose
connection breaks while the container stops returns `interrupted: ...` to the script. The tool
front is `createMcpExtensions` in `worker/src/mcp-front.mjs`: it takes a
`call(server, tool, args, signal)` function, a summary text and a codemode factory, and
`worker/src/mcp.mjs` supplies the gateway call and the box summary.

A server that needs a key gets a placeholder in its environment from the table, such as
`BRAVE_API_KEY=pi-cloud-placeholder-BRAVE_API_KEY`. The backend runs in `http-gateway` egress mode:
the container trusts `/etc/cloudflare/certs/cloudflare-containers-ca.crt` through
`NODE_EXTRA_CA_CERTS`, Cloudflare hands every outbound request to `StepAgent`, and `boxEgress`
writes the Worker secret into the named header (`x-subscription-token` for brave-search) only for
the hosts named with that secret. The real key never enters the container. A Node program trusts
the intercepted HTTPS through `NODE_EXTRA_CA_CERTS`. The system trust store does not hold that CA,
so a server written in another language that needs HTTPS needs its own CA setting first.

## Claude Code and Codex steps

The Durable Object `CliAgent` (`worker/src/cli.mjs`) runs one Claude Code or Codex step attempt
through `ContainerHarness` from `agents` 0.33.0. Its name is `<kind>:<attempt>`, and its routes are
`/claude/attempts/<attempt>/<action>` and `/codex/attempts/<attempt>/<action>`: `step`, `events`,
`abort`, `transcript` and `out/<file>` as for `StepAgent`, plus `stop-container` and `probe` while
`TEST_HOOKS` is `on`. `POST step` takes `{operationId, brief, model, remote_url, branch, start_sha, skills?, max_iterations?}`.
`skills` names skill folders of the skills repo, and the answer and the `pi_cloud_start` line carry
the skills pin `skills: {sha, names}`.
`max_iterations` reaches Claude Code as `--max-turns`. Codex has no such flag, so `CliAgent` counts
the tool calls and aborts the operation at the first call past the limit. Either way the end line
says `unanswered`, `turn_limit`, and the answer and the `pi_cloud_start` line carry the limit.
The events are pi's shapes: a `tool_execution_start` and a `tool_execution_end` per tool call while
the CLI runs, the transcript as `message_end` lines without `replayed` when the operation settles, the token counts the
CLI reports on the last one, then `pi_cloud_end`. The object announces no tool list, because the
CLIs keep their own tools, and it announces the MCP servers of the box.

- **Start from the default snapshot.** `ContainerHarness` keeps its snapshot record in the object's
  storage under `container-harness:snapshot`, keyed by its setup steps, and has no option to start
  from a given snapshot. Before the first start, `CliAgent` writes that record with the key of its
  setup steps (the CLI install pinned in the recipe) and the default snapshot's id. The harness then
  restores the snapshot instead of running setup. The record format is internal to `agents`; the code
  that writes and reads it is the same in 0.30.1 and 0.33.0, and an echo probe on 0.33.0 started from
  the default snapshot.
  The first start from a freshly built snapshot took 100 s, a warm one about 30 s.
- **Boot.** The harness entrypoint runs `/opt/harness/daemon.mjs`, which is
  `worker/snapshot/box/harness-boot.mjs`. It starts `box-mcp-gateway`, clones `branch` into
  `/workspace/repo` as the user `agent` when the object's step names one, checks that HEAD is
  `start_sha`, fetches the step's skills, and then imports the real daemon. A failed clone writes
  `/workspace/out/.box-clone-error`, and the step ends with `push_error: clone_failed: ...`, which
  the runner records as the error `clone_failed: ...`.
- **MCP.** `/home/agent/.claude.json` and `/home/agent/.codex/config.toml` name each server of the
  table as an HTTP MCP server at `http://127.0.0.1:8800/mcp/<server>`. Every session home starts as a
  copy of `/home/agent/`.
- **Skills.** The CLIs read `/opt/agent-skills` through `~/.claude/skills` and `~/.agents/skills`.
  `CliAgent.step` syncs the skills mirror and keeps the skills pin `{sha, names}` in its step record, as
  `StepAgent` does, and hands the box `OHFLOW_SKILLS_URL`,
  `http://skills.harness.internal/<sha>?names=<name>,<name>`. `CliEgress` serves that host from
  `SkillsMirror`: one NDJSON line per file with its path and base64 data, then a last line with the
  file count. The boot wrapper's module `worker/snapshot/box/box-skills.mjs` writes the files to a
  staging folder, puts it in place of `/opt/agent-skills` when the last line's count matches, and
  records the skills pin in `/etc/agent-box/skills.json`. A file that starts with `#!` gets mode 755. A
  container that starts again during the step reads the same URL from the step record, so it
  fetches the same commit. A fetch that fails twice leaves `/opt/agent-skills` as the snapshot
  holds it and writes `/workspace/out/.box-skills-error`, and the step ends with
  `push_error: skills_failed: ...`, which the runner records as the error `skills_failed: ...`.
  The mirror keeps three commits, and the route answers 404 for
  a commit it has dropped. A step that names no skill gets no URL and reads the snapshot's own
  copy, which `snapshot.skills` clones, and which is an empty folder while `snapshot.skills` is `null`,
  its shipped value. An attempt that started from a snapshot of an earlier
  recipe, whose boot wrapper fetches nothing, keeps its skills pin in the step record and reads that
  snapshot's copy.
- **Credentials.** The CLI signs in with the operator's subscription, and the box holds only
  placeholders. Claude Code gets `CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-harness-egress-placeholder`
  and `ANTHROPIC_BASE_URL=http://anthropic.harness.internal`. Codex reads a placeholder ChatGPT
  login from `/home/agent/.codex/auth.json` and calls `http://chatgpt.harness.internal/backend-api/codex`
  through the provider `box` with `requires_openai_auth = true` and `supports_websockets = false`.
  `ContainerHarness` intercepts these plain-HTTP hosts, and the entrypoint `CliEgress` forwards each
  request over HTTPS. For Anthropic it sets `Authorization: Bearer` with the Worker secret
  `CLAUDE_CODE_OAUTH_TOKEN`, all whitespace removed, because a pasted token can carry a line break.
  For ChatGPT it sets `Authorization: Bearer` and the ChatGPT account id header from the Durable Object
  `CodexLogin`. Git uses `http://github.harness.internal/<repo>.git`, and `CliEgress` adds
  `GITHUB_TOKEN` only for a repo that passes the same check. It reads the commands of each push and
  refuses a push to any ref outside `refs/heads/ohflow/`. brave-search goes through `boxEgress` as for a pi
  step. The container has no other Internet.
- **The Codex login.** `node scripts/codex-login.mjs` runs `codex login` in a temporary
  `CODEX_HOME`, posts its `auth.json` to `POST /codex/login`, and deletes the folder. That login
  belongs to the Worker alone, so the refresh token rotates in one place. `CodexLogin` refreshes the
  access token at `https://auth.openai.com/oauth/token` with the Codex CLI's client id when it has
  less than three days left. `node scripts/codex-login.mjs status` prints its expiry.
- **The Claude token.** `claude setup-token` prints a token that lasts one year;
  `wrangler secret put CLAUDE_CODE_OAUTH_TOKEN` stores it.
- **The end of a step.** When the operation settles, `CliAgent` pushes HEAD of `/workspace/repo` to
  `branch` as the user `agent`, keeps the files of `/workspace/out` in its storage for
  `GET out/<file>`, and destroys the container. A container that stops during a step settles the
  operation `unanswered`, `container_lost`. The harness starts a new container to reconcile, so the
  push then carries the start commit.
- **Usage.** The token counts come from the CLI's own `usage` event, which carries input and output
  tokens without the cache split. Claude Code also reports a notional API price, which the end line
  keeps as `notional_cost_usd`; a subscription bills none of it. The object adds up the counts as
  they arrive, and the answer of `POST abort` carries the sum so far as `usage`. `agents` 0.33.0
  passes a usage event only when the CLI ends, Codex on `turn.completed` and Claude Code on its
  result message, so the sum is empty for a step that is stopped while it runs, and `usage` is
  then null. ohflow records those tokens as unknown, and `ohflow table --reconcile` names the
  attempt.

## Tests

`node --test worker/test/*.test.mjs` checks the recipe, the settings, the skills feed and the pin
script with no network and no secret: the shipped settings clone no repo, Worker settings add
their repos, servers and rules, a `name` renames both Workers and the code mode binding while the
name `pi-cloud` gives the checked-in configs unchanged, a skills pin syncs the mirror before it reads the
commit, the box module writes exactly the named skills that the skills route sends and keeps the
earlier folder when the feed is refused, the fallback snapshot is the newest one built, and
`pins.mjs` rewrites only a snapshot pin whose head moved.
CI runs it beside the suite.
