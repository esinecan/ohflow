# The boundary between ohflow and one operator's setup

Every piece of ohflow has one of four homes. A piece belongs to ohflow core when a newcomer on a
clean machine needs it to run an executor that ohflow advertises.

| Home | What lives there | Where |
|---|---|---|
| ohflow core | code, the base settings, the skill and its references | the shipped tree |
| Operator layer | one operator's values and house rules | `ohflow.settings.local.json` at the skill root, `references/local.md`, and the Worker's `worker/pi-cloud.settings.local.json` and `worker/snapshot/AGENTS.local.md`, all git-ignored |
| Shipped examples | one operator's real setup with the names replaced; ohflow imports none of it | `examples/setups/` |
| Private | what only this operator's machines need | outside the shipped tree |

## The settings

`ohflow.settings.json` names every setting and its newcomer value. `scripts/ohflow/settings.py`
merges the local file over it; `OHFLOW_SETTINGS` names another local file, and an empty value
reads the base alone. The test suite runs on the base alone.

| Setting | Base value | Read by |
|---|---|---|
| `operator.escalation_marker` | `ACTION NEEDED FROM THE OPERATOR` | the campaign's `ESCALATION.md` heading |
| `operator.on_escalate` | none | the campaign controller, which runs this command on an escalation of a campaign that names no `on_escalate`, with `{file}` replaced by the path of `ESCALATION.md` |
| `tiers.heavy.<harness executor>`, `tiers.light.<harness executor>` | a model for each of the seven harness executors | `tiers.resolve`, so validation, the step's `spec.json`, `estimate` and `validate -v`; a step or the judge whose model names a tier runs the model mapped here. An unmapped tier stops `validate` naming the setting |
| `campaign.judge_model` | `heavy` | `campaign.default_judge`, the judge of a campaign that names none; it runs on the `claude` harness executor, and a tier resolves through `tiers.<tier>.claude`. A value that is not a non-empty string stops `campaign validate` and `campaign run` with `WORKFLOW INVALID` before anything runs |
| `pi.api_key_env.<provider>`, `pi.base_url.<provider>` | none; the key variable is then `<PROVIDER>_API_KEY`, and pi's own endpoint for the provider | `patterns.model_config`, so every `pi` step that `construct` builds |
| `commit_checks.no_ai_attribution` | `false` | `workflow.house_checks`, so `clean_commit_checks`, the roll call and the evidence atlas |
| `durable.box` | none | durable preflight, implement-review `box`, roll call `durable_box`; `local` is this machine |
| `durable.providers` | none | durable model validation |
| `pi_cloud.url` | none | the pi-cloud executor; `OHFLOW_PI_CLOUD_URL` wins |
| `pi_cloud.providers` | none | pi-cloud model validation |
| `pi_cloud.mcp_servers` | none | `tools.allow` validation for pi-cloud steps |

## Pieces outside the core today

| Piece | Home | State |
|---|---|---|
| `run-hidden.vbs` | core | ships beside `detach.py` |
| `host/` | core, as the durable executor's host side | ships in ohflow; `durable_host.py` installs it on each machine that runs a durable step |
| `worker/` | core, as the pi-cloud Worker each operator deploys | ships in ohflow; `worker/pi-cloud.settings.json` holds its empty base settings and `references/pi-cloud-worker.md` deploys it |
| `docs/`, `.impeccable/`, `references/examples/`, `tests/fixtures/` | recorded evidence | the release extraction reviews each one; the leak scan skips them |

## The leak scan

`tests/test_boundary_01_no_local_values.py` reads every file git would commit under ohflow,
outside the recorded evidence. It fails on a path that names a real home directory, and on a
token from the operator's private list (`OHFLOW_LEAK_TOKENS`, else
`~/.config/ohflow/leak-tokens.txt`). A machine with no list skips the token half and says so.
The scan finds a value that leaked into the core. A piece missing from the core shows only on a
clean machine, so the install rehearsal in `macos-install-rehearsal.md` covers that direction.
