# Agent transcripts, tokens and cost

Every agent attempt leaves a record on disk. Each harness executor writes its own format. All formats join the agent's tool calls to the run, step and attempt that paid for them. That record lets you compare two workflow designs instead of arguing about them. The attempt layout is in [ohflow](ohflow.md#every-execution-owns-a-directory).

## Export an agent transcript

```powershell
python -m ohflow.cli transcript --run <run-dir> --step <step-id> --html
```

Each harness executor module answers `transcript` for its own steps:

| Harness executor | `transcript` gives |
|---|---|
| pi | runs `pi --export` as a windowless child and writes `<run-dir>/<step-id>.transcript.html`; `--out <file>` picks the path |
| claude, codex | the path of the attempt's event log under `logs/` |
| pi-cloud, claude-cloud, codex-cloud | the path of `transcript.md`, the Worker's transcript the runner copies down when the attempt settles; before that, and on a killed attempt that never copies it, the path of the attempt's event log under `logs/` |

A short step id must identify one step. Use the full coordinate, such as `02.review/01.review`, when ids repeat. The command opens the run through `rundir.open_run`, so the run needs `run-log.jsonl`. It does not read `summary.json`. The newest attempt that really started decides which session is exported, so retries and cached finishes never export stale work.

## One line per model call and action

```powershell
python -m ohflow.cli actions --run <run-dir> --step <step-id>
```

`actions` joins each action to the model call that launched it and to its result, in every harness executor's format. The tokens and the latency sit on the call line once. Each harness executor's call key and what its format leaves out: [ohflow](ohflow.md#run-it).

## Run-level accounting

```powershell
python -m ohflow.cli table --runs <run-dir> --by step
```

The table sums every real attempt, failed ones included. A priced attempt shows a number, and a `subscription` attempt shows its known zero. An attempt with no known price shows `unpriced`. A measurement no agent recorded shows `-`.

### Token reconcile

```powershell
python -m ohflow.cli table --runs <runs-root> --reconcile
```

`--reconcile` compares each agent attempt's `result.json.tokens` with the harness executor's own usage record:

- pi totals come from `logs/pi-events.jsonl`, assistant `message_end` usage. Pi prompt tokens are input + cacheRead + cacheWrite.

It fails closed on missing or malformed usage. A mismatch prints the run, coordinate, attempt, result totals and usage-record totals. Command, merge and gate steps have no provider usage record and are skipped.

## Tokens and cost

`result.json` records `conversation_id`, `transcript_dir`, tool-call and LLM-call counts, `cost`, `cost_source` and five token fields: prompt, completion, cache read, cache write and reasoning. `prompt_tokens` includes cache-read and cache-write counts.

**`cost_source` names where the price came from:**

| `cost_source` | Meaning |
|---|---|
| `pi-catalog` | exact Z.AI provider and model pairs, priced from pi's discovered catalog chunks |
| `claude-cli` | Claude Code's own figure, which is notional on a subscription |
| `subscription` | `codex`, `claude-cloud` and `codex-cloud`: a subscription bills no tokens, so `cost` is a known `0.0` |
| `unpriced` | a model with no known price; `cost` is `0.0` |

A pi model behind a custom `base_url` reads `unpriced`, because `ModelConfig` carries no price. Token counts stay real. This costs nothing on the Z.AI flat quota. It matters on DeepSeek, which bills per token.

Command time cap evidence sits in `logs/command_time_caps.jsonl`. The rule is in [ohflow](ohflow.md#command-time-caps).
