# Sessions: steer pi sessions turn by turn

`ohflow session` keeps up to three sessions open for you, the orchestrator agent. After each finished turn you decide what happens next: a follow-up, a correction, another session, a workflow, or acceptance. Use it when nobody can plan the work in full at the start. When the steps can be fixed in advance, a workflow costs less attention. Code: [sessions.py](../scripts/ohflow/sessions.py).

## How a turn runs

Each turn is one process. A small wrapper starts `pi -p --mode json --session-dir <session>/session --session-id <id>` with the message, so the session keeps its conversation between turns and nothing stays alive in between. The turn ends when that process exits, and the reply is the last assistant message it printed. pi is the one harness. The session gets the operator's own pi configuration and pi's default model, unless `--model` names a model or the tier `heavy` or `light`.

## The verbs

Run each from `~/.agents/skills/ohflow/scripts` as `PYTHONPATH=. python -m ohflow.cli session <verb> ... --dir <record dir>`. Every verb prints one JSON object, and exit code 2 means refused, with the reason in `refused`.

| Verb | What it does |
|---|---|
| `open NAME --cwd C (--brief F \| --message T)` | starts a session and its first turn; refuses a fourth open session and a name used before |
| `send NAME (TEXT \| --file F)` | starts the next turn; a message to a running session waits in the record and starts when that turn ends |
| `wait [--timeout S]` | blocks until a turn finishes and prints it once: `reply`, `error`, `interrupted`, `lost`, `tokens`, `cost`, `next_turn`. Exit 3 on timeout, exit 4 when no turn runs and every finished turn is delivered |
| `status [NAME]` | each session's state, turn, undelivered and queued counts, age and cost; with a name, its last finished turn, not marked delivered |
| `interrupt NAME` | ends the running turn's process tree; `wait` then delivers the turn with `interrupted: true`. A turn takes no message while it runs, so interrupt, then send |
| `close NAME [--force]` | closes the session for good; `--force` interrupts a running turn first. `wait` still delivers a finished turn of a closed session |

## Be woken, do not poll

In Claude Code, run `session wait` as a background command: its exit starts your next turn. An orchestrator agent on pi or Codex runs `wait` in the foreground. Read the reply, then check the artifact it names, because the reply is a claim and the commit or file is the evidence. A reviewer's verdict covers only the commit it read, so ask the reviewer to name that commit, and before you land a branch whose tip has moved since, send the reviewer the diff from that commit to the tip. Your moves on a session that goes wrong, and when to make them: [steer-a-run](steer-a-run.md).

## The record

`--dir` holds `events.jsonl`, the append-only truth, and one folder per session with `session/`, pi's conversation, and `turns/<n>.md`, `.jsonl`, `.err` and `.exit.json`. Every verb reads the record again, so a restarted orchestrator agent loses no turn and receives none twice. A turn whose process died without its exit record is delivered with `lost: true`, and a follow-up still continues the conversation.
