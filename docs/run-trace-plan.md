# Run trace plan

ohflow gets one trace per workflow run. The trace has spans for the run, each phase, each step and each step attempt. These spans exist for every harness executor, because they come from the run log. The `durable` and `pi-cloud` executors also carry the spans that pi-durable emits inside the step, nested under the attempt span. No part of the trace depends on the model provider or on Cloudflare.

## The terms

A span is one timed piece of work: a name, a start, an end, attributes, events and a status. A trace is the tree of spans that share one trace id. A link points from a span to a span in another trace without nesting it. The export format is OTLP/JSON, OpenTelemetry's wire format, so any OpenTelemetry backend can read the file.

pi-durable's units, inside one `Harness`: a conversation holds transcript entries; a submission is one input, keyed by `operationId`; a task is a durable unit of work that a submission causes, such as a model turn; a phase is one checkpointed step of a task. pi-durable 1.4.0 emits two span types, `pi.durable.submit` and `pi.durable.phase`, with no message content. pi-durable's "phase" and "attempt" are a task checkpoint and its retry count, not ohflow's phase and step attempt.

## The span tree

The tree follows the level tree in [glossary.md](glossary.md), section 1.

| Span | Starts at | Ends at | Parent |
|---|---|---|---|
| `ohflow.run` | `run_started` | the last record of the run log | none |
| `ohflow.phase` | the first `phase_started` of the phase | the last `phase_settled` of the phase | the run |
| `ohflow.step` | the first `attempt_started` of the coordinate | the end of the coordinate's last attempt span | the phase |
| `ohflow.attempt` | the first `attempt_started` of `(coordinate, attempt)` | the last `attempt_finished` of `(coordinate, attempt)` | the step |
| `pi.durable.*` | pi-durable | pi-durable | the attempt, for `durable` and `pi-cloud` |

A run log holds one `run_started`, because a resume appends no run-level event. A phase can start and settle more than once: an auto-resume pass and every `--resume` run it again.

**A reattach stays inside one attempt span.** It keeps its attempt number, and the run log holds a `deferred` close with `reattached` between the two `attempt_started` records. Each such close becomes an `ohflow.reattach` event. The event's time is the start of the execution it closes plus that close's `wall_seconds`, which is when the old supervisor or host stopped. The resumed supervisor writes the close later, and the event keeps that time as `ohflow.recorded_at`. The attempt's `ohflow.start_kind` is the kind of its first `attempt_started`.

**A retry is a new attempt span.** It mints a new attempt number under the same step. Attempt numbers are unique per coordinate across fingerprints.

**An attempt with no finish ends where the next one starts.** An executor without reattach leaves an attempt open in the run log when its supervisor dies. That span ends at the next `attempt_started` of its coordinate and carries `ohflow.abandoned = true`. An attempt that is still open at export time, with no later attempt, ends at the export time and carries `ohflow.open = true`.

**An `attempt_finished` with attempt 0 opens no attempt span.** The engine writes attempt 0 for a cached step, a skipped step, a step deferred before it started, a refused start and a fault with no open attempt. Each such record becomes an `ohflow.step_record` event on the step span, with its status. A step whose only records carry attempt 0 gets a zero-length step span at its first record.

Run-log events that mark a moment become span events:

- `gate_ran` becomes `ohflow.gate` on the attempt, with the gate verdict and the failed check names.
- `retry_decided` and `work_excluded` become events on the step.
- `phase_resumed` becomes an event on the phase.
- A resume becomes `ohflow.resume` on the run. It sits at the first work record after a `run_finished`, or at a `phase_started` of a phase that already started when no `phase_resumed` for that phase comes before it.

The attributes use the `ohflow.` namespace: `run_id`, `workflow`, `phase`, `coord`, `step_id`, `attempt`, `start_kind`, `harness_executor`, `status`, `failure_class`, `fingerprint` and `abort_victim`. `passed`, `cached` and `skipped` map to status OK. `failed`, `timeout` and `quarantined` map to ERROR. `deferred` maps to UNSET, with `ohflow.status = deferred`. No span carries a brief, a message or a tool output.

## The ids

The ids are deterministic, so the projection rebuilds the same trace from the same run log, and the engine knows the attempt span id before the attempt ends:

- The trace id is the first 16 bytes of `sha256(run_id)`.
- A span id is the first 8 bytes of `sha256(run_id | kind | coord | attempt)`, where `kind` is `run`, `phase`, `step` or `attempt`.

## Stage 1: the projection

**The run log gets millisecond time.** `RunLog.append` adds `t_ms`, the epoch time in milliseconds, to every record. `ts` keeps its format, so `live.py`, `dashboard_data.py`, `attention.py` and `engine.py`, which read it, do not change. Neither do `compare.py` and `table.py`, which read `summary.json`. No reader compares key sets. A run log without `t_ms` projects at one-second resolution.

**`ohflow/trace.py` is a pure function of the run directory.** It reads `run-log.jsonl` and each attempt's `logs/pi-spans.jsonl`, and it returns the spans. It does not import the dashboard and makes no HTTP call, following the guardrails of the visibility verbs such as `explain` and `compare`.

**`ohflow trace --run <dir>` is the verb.** By default it prints the span tree as text, one line per span, with its status, its duration and its `run-log.jsonl:<line>` pointer, capped at 8,000 characters. A cut keeps the newest spans. `--json` prints the spans, and `--otlp <file>` writes OTLP/JSON. The engine writes `trace.otlp.json` at the run root after `run_finished`, beside `summary.json`. Like `board.md`, the file is derived, and the verb rebuilds it.

This stage alone gives the run, phase, step and attempt spans for all harness executors.

## Stage 2: propagation

**The engine gives every attempt its trace context.** `spec.json` carries `trace.traceparent`, the W3C form `00-<trace id>-<attempt span id>-01`. Every agent process gets the same value in the environment variable `TRACEPARENT`, the name OpenTelemetry uses for processes. A reattach gets the same value, because the attempt span id does not change.

**The two pi-durable executors forward it.** The `durable` executor already writes `spec.json` to the step folder, and `host/ohflow-step.mjs` reads `trace.traceparent` from there. The `pi-cloud` executor adds `traceparent` to the `ohflow` object of its `POST step` body. The Worker adds it to the `ohflow.step` record that `step()` writes to Durable Object storage.

## Stage 3: the pi-durable adapter

**`src/telemetry.mjs` in the `pi-durable-host` repository implements pi-telemetry's `TelemetryContext` with propagation.** The durable host in `ohflow/host/` and the Worker each carry a copy, as they do `src/pi-events.mjs`. Both `package.json` files add `@earendil-works/pi-telemetry` 1.4.0 as a dependency. `openHost` and the Worker's `Harness.open` pass the adapter as `telemetry`. The adapter parents its root spans under the ohflow attempt span, so a run is one trace, and it sets `ohflow.coord` and `ohflow.attempt` on each root span. Propagation is required, not optional: pi-durable stores each task's carrier in SQLite, so after a reattach the restarted tasks continue under the same parents.

**The adapter reads its parent when it starts a root span.** PiHarness's `submit` options have no `trace` field in `agents@0.33.0`, so the parent cannot come with the submission. On the durable host, `host/ohflow-step.mjs` reads the spec before `openHost`, so the parent is known at construction. On the Worker, `PiHarness` opens the Harness in `onStart`, before the first `POST step`, and opens it again after an alarm restart with no request. So the adapter holds the parent as a value that the Worker sets in two places. `step()` sets it when it writes `ohflow.step`, and that write comes before the brief's submission. The Harness factory sets it from the stored `ohflow.step` record when it opens.

**The adapter passes pi-telemetry's conformance kit.** The kit is `createTelemetryAdapterConformance` from `@earendil-works/pi-telemetry/testing`.

**Settled spans travel as event lines.** On the durable host, `host/ohflow-step.mjs` prints `{"type":"durable_span", ...}` lines. On the Worker, the `events` stream prints `pi_cloud_span` lines. The Worker also stores each settled span in the Durable Object, so every new `events` connection replays them with `replayed: true`. Both runners write the span lines to `<attempt>/logs/pi-spans.jsonl` and drop a span id they already hold. A span that was open when its process died never settles, so it is not in the file.

**The box's clock sets these spans' times.** The durable box and Cloudflare stamp pi-durable spans with their own clocks, so a nested span can sit a little outside its attempt span. The adapter marks these spans `ohflow.clock = box`.

**`pi.durable.report` events reach the orchestrator.** One example is `task_parked`, which the Worker does not log today. `ohflow trace` prints each report event on its attempt line.

## Gates

**Stage 1 gate.** `ohflow trace` runs on two recorded runs. One is the fixture `tests/fixtures/dashboard/g1-run`, which settles phase `01.sweep` twice. The other is the pi-cloud kill-test run `r-20261026-174635-74c8ab11` in the operator's runs folder, under `workflows/pi-cloud-gate3/gate/kill/runs/`, whose run log records a reattach and starts phase `01.report` twice. Each tree holds every coordinate that `table --by step` lists, and every attempt number in the run log's `attempt_started` records. The kill-test run shows one attempt span with one `ohflow.reattach` event and one `ohflow.resume` event on the run. The `trace.otlp.json` of one run is posted to a local Jaeger v2 all-in-one on OTLP/HTTP (`:4318/v1/traces`), and the Jaeger UI shows the tree.

**Stage 3 gate.** `rollcall --cases single:durable` and `rollcall --cases single:pi-cloud` each pass, and each trace shows `pi.durable.submit` and `pi.durable.phase` spans under the attempt span. The kill test from the pi-cloud gate runs again: the supervisor is killed during a 100 s silent command, `--resume` reattaches, and the phase spans after the reattach sit under the same attempt span as the ones before it.
