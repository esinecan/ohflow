# Quickstart: a source install

This takes a new operator from a clone to a first live roll call. ohflow installs no package: it runs from the clone on the Python standard library. A fresh clone followed this page on macOS in the install rehearsal ([the rehearsal note](../docs/release/macos-install-rehearsal.md)) and on Ubuntu 24.04 under WSL, to a passing `pi` and `durable` roll call. Git Bash on Windows takes the same commands.

## 1. Check the prerequisites

```bash
python3 --version
git --version
bash --version
```

- **Python 3.11 or later.** Check which interpreter `python3` is: on a machine with several, the first one on PATH may be an old system Python or an unrelated virtual environment. Every command below works with any 3.11+ interpreter in place of `python3`.
- **git**, with a commit identity (`git config user.name` and `git config user.email`).
- **bash** on PATH. On Windows that is Git Bash.
- **One agent CLI, signed in.** ohflow starts agents through a harness executor and has no default one, so a live run needs at least one of these:

| Harness executor | What it needs |
|---|---|
| `claude` | the Claude CLI on PATH and `claude auth login` |
| `codex` | the Codex CLI on PATH and its login |
| `pi` | the pi CLI, `npm install -g @earendil-works/pi-coding-agent`, and a provider key in its variable (`ZAI_CODING_CN_API_KEY` for the roll call's `pi` cases, and `ZAI_API_KEY` for a `pi` step that `construct` builds on the default model) |

`npm install -g` writes to Node's own prefix. A Node from the Linux distribution's packages has its prefix in `/usr`, and the install fails there with `EACCES`. Install Node 22.19 or newer through [nvm](https://github.com/nvm-sh/nvm) or from [nodejs.org](https://nodejs.org) instead, so the prefix is yours. That Node also serves `durable`.

`durable` needs Node 22.19 or newer and a Z.AI key in `ZAI_API_KEY`: with `durable.box` set to `local` its steps run on this machine and survive a restart of the supervisor, and with a box's ssh host alias they run on that machine. ohflow installs the host from `host/` on that machine at the first step. `pi-cloud` needs a deployed Worker, which [the pi-cloud Worker](pi-cloud-worker.md) deploys to your Cloudflare account. Leave a second machine and the Worker for later. [The example setup](../examples/setups/windows-home-box/README.md) shows both.

## 2. Clone

```bash
git clone https://github.com/esinecan/ohflow
cd ohflow
```

Every later path is relative to `ohflow`, the skill root.

## 3. Local settings

`ohflow.settings.json` at the skill root names every setting with the value a new operator starts with. The local harness executors (`pi`, `claude`, `codex`) run on it as it is, so this step is optional for a first roll call.

Your own values go in `ohflow.settings.local.json` beside it. git ignores that file, and ohflow merges it over the base file key by key, so it holds only the keys you change:

```json
{
  "commit_checks": {
    "no_ai_attribution": true
  }
}
```

[The boundary](../docs/release/boundary.md#the-settings) lists each setting and what reads it. `examples/setups/windows-home-box/ohflow.settings.local.json` is a full file to copy the layout from. Leave `pi_cloud` out until you have a Worker. For `durable` on this machine, the file needs both keys below: `durable.box` names the machine, and `durable.providers` names the providers whose keys that machine holds. Without `durable.providers` the preflight passes, but every `durable` workflow fails to build with `durable model must be provider/id with the provider one of []`.

```json
{
  "durable": {
    "box": "local",
    "providers": ["zai"]
  }
}
```

House rules for your agents go in `references/local.md`, which git also ignores.

## 4. Preflight

```bash
cd scripts
PYTHONPATH=. python3 -m ohflow.cli preflight
```

Line one is the verdict. The verb checks bash and every harness executor, and each `FAIL` line names its fix. On a new machine it reads `PREFLIGHT FAIL` and exits 1, because `durable`, `pi-cloud`, `claude-cloud` and `codex-cloud` are not set up. That is expected. Check the harness executor you will use on its own:

```bash
PYTHONPATH=. python3 -m ohflow.cli preflight --harness-executors claude -v
```

This must read `PREFLIGHT PASS: 2 checks`, with one `PASS` line for the bash check, which is named `Git Bash` on every system, and one for the harness executor. A missing sign-in shows here, so fix it as the line says before you go on.

## 5. A first roll call

A roll call is a trivial task: one agent writes who it is, commits that file and reports. Pick an output directory outside the clone and pass it as `--out` every time: without it the verb makes a `rollcall-<id>` directory under `TEMP`, or in the current directory when `TEMP` is unset.

Check first that the workflows build. This starts no agent and spends nothing:

```bash
PYTHONPATH=. python3 -m ohflow.cli rollcall --matrix smoke --dry-run --out <dir>
```

It prints one `WORKFLOW` line per test case and ends with `ROLLCALL DRY: 3 test cases valid`.

Then run one live test case on your harness executor:

```bash
PYTHONPATH=. python3 -m ohflow.cli rollcall --cases single:claude:agent_profile=hermetic --out <dir>
```

The agent profile `hermetic` runs the agent without your own Claude setup, and it exists for `claude` and `codex` only. For pi the test case is `single:pi`, and for durable it is `single:durable`. The run makes a throwaway git repository under `<dir>`, so it touches no repository of yours. It spends a little of the subscription or key behind the harness executor: on the rehearsal Mac this test case took 31 s.

The verdict is one line, then the total:

    PASS single claude count=1 agent_profile=hermetic  0m31s  97.9 k tokens  <dir>/01-single-claude-1/run
    ROLLCALL PASS: 1 of 1 test cases

A `FAIL` line ends with the first failing step and check, and a `SKIP` line says what the harness executor's preflight missed. Read a run with:

```bash
PYTHONPATH=. python3 -m ohflow.cli status --run <dir>/01-single-claude-1/run
```

## Where to go next

- [The README](../README.md#quickstart-from-a-spec-bundle-to-a-finished-change) runs a two-milestone campaign
  from the example spec bundle in `examples/quickstart/`.
- [CONTRIBUTING](../CONTRIBUTING.md#testing-with-live-agents) has every test scenario, the test matrices and how to read a matrix result.
- [SKILL.md](../SKILL.md) routes a task to a workflow pattern or another route, and [operate-a-run](operate-a-run.md) is the procedure for every real run.
- [CONTEXT.md](../CONTEXT.md) defines the terms used here.
