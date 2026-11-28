# ohflow

ohflow runs agent work as a plan that you can inspect, measure, resume and improve. You give the
goal and the limits. Your agent writes the plan, and ohflow runs each step with Claude Code, Codex
or pi: on this machine, on your other machines over ssh, or in containers behind a Cloudflare
Worker that you deploy. A gate checks the commit that each step leaves, and a fresh judge agent
passes, revises or escalates each milestone.

This plugin holds one skill, `ohflow`. The skill tells Claude how to write a workflow and how to
run the ohflow command-line tool in `skills/ohflow/scripts/`. The full guide, the quickstart and
the source are at https://github.com/esinecan/ohflow.

## What it needs

The command-line tool runs on your own computer, so use the skill in Claude Code. It needs
Python 3.11 or later, git with a commit identity, and bash. On Windows, use Git Bash. Each step
runs through the command-line tool of its harness, signed in: `claude`, `codex` or `pi`. The
durable and cloud executors also need Node.js. Chat on claude.ai and Cowork load the skill's text,
and its commands need a computer with these programs.

## What it runs, sends and fetches

- It runs git and the harness tools that a workflow names (`claude`, `codex`, `pi`) in the
  repositories that the workflow names. Each harness sends its prompts and the files its agent
  reads to its own model provider. The base settings give pi steps a Z.AI model.
- It serves a run's dashboard on `127.0.0.1` of your computer, and the page accepts only a
  loopback host name.
- The `durable` executor connects over ssh to the machines that you name, and it installs its
  host there with `npm ci`.
- The cloud executors (`claude-cloud`, `codex-cloud`, `pi-cloud`) send steps to the Cloudflare
  Worker that you deploy from `skills/ohflow/worker/`. The client reads the Worker's token from
  `PI_CLOUD_TOKEN` in your environment and sends it only to your Worker's URL. The Worker's
  containers pull images from ghcr.io and clone repositories from GitHub.
- The `cloud-spend` command reads `CLOUDFLARE_API_TOKEN` from your environment and asks
  api.cloudflare.com for your account's container usage.
- ohflow sends no telemetry, and it has no server of its own.

## Where this copy comes from

The release automation of https://github.com/esinecan/ohflow generates this plugin from each
validated release and writes it to the `claude-plugin` branch. `skills/ohflow/RELEASE.json` names
the release version and the source commit. Change ohflow in its main branch, never in this branch.

ohflow is licensed under the Apache License 2.0. See `LICENSE`.
