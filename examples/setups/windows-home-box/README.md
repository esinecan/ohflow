# A Windows home box with a second PC and a pi-cloud Worker

This is one operator's working setup, copied from the machine that ohflow was built on, with
the host names and URLs replaced. ohflow imports nothing from this folder. Copy what fits your
setup into the two operator files at the skill root and in `references/`.

| Piece | This setup | Where it goes |
|---|---|---|
| Local box | Windows 11, Git Bash, Python 3.14, the pi, claude and codex CLIs signed in | your machine |
| ssh box | a second Windows PC on the same network, reached as `ssh buildbox`, with Node 24 and Git Bash | `durable.box` |
| Durable keys | the box's own pi holds Z.AI and DeepSeek keys | `durable.providers` |
| Cloud steps | the pi-cloud Worker deployed from the skill's `worker/` to the operator's Cloudflare account | `pi_cloud.url`, `PI_CLOUD_TOKEN` |
| Cloud MCP | six servers baked into the Worker's default snapshot, three of them from the operator's own repos | `pi_cloud.mcp_servers`, `snapshot` in `worker/pi-cloud.settings.local.json` |
| House checks | no AI attribution in commits | `commit_checks.no_ai_attribution` |
| Escalations | posted to a team board | `operator.escalation_marker`, `operator.on_escalate` |
| House rules | a memory sweep before a delivery report | `references/local.md` |

## The files

- `ohflow.settings.local.json`: this setup's settings. Copy it to the skill root as `ohflow.settings.local.json` and change the values.
- `local.md`: this setup's house rules. Copy it to `references/local.md` and keep the rules you share.

## Bring-up order

1. Install the CLIs on the supervisor and sign each one in. `ohflow preflight` names what is missing.
2. For durable steps, put an ssh key on the box, install Node 22.19 or newer and Git Bash there, and set the provider keys (`ZAI_API_KEY`, `DEEPSEEK_API_KEY`) in the box user's environment. `ssh buildbox exit` must answer without a prompt. ohflow installs its durable host on the box at the first step.
3. For cloud steps, deploy the Worker as [the pi-cloud Worker](../../../references/pi-cloud-worker.md) describes, set its `git_owner` to the GitHub account whose private repos a step may clone, give its `GITHUB_TOKEN` access to those repos, and export `PI_CLOUD_TOKEN` on the supervisor.
4. Write `ohflow.settings.local.json`, then run `ohflow preflight` again.
