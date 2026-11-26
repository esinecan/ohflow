All evidence is gathered. The worktree is untouched and clean; all scripts live under `%TEMP%\review-hardening-proof`.

## Findings

- BLOCKING | ohflow/scripts/ohflow/engine.py:1142-1143 (with engine.py:1166) | After a reattach sets `reuse` (engine.py:1151, or engine.py:1126 on a resume), a later judged failure sets `kind = "retry"` at engine.py:1166 but never resets `reuse = None`, so `_attempt_step(..., attempt=reuse)` launches the retry under the reattached attempt's number instead of minting a fresh one. Why it matters: the retry then calls `_prepare_step_dir` on the non-empty attempt directory and faults at engine.py:1017-1023 ("attempt directory ... is not empty"), the fault counts as a second failed execution, the exclusion fires, and the step ends failed even when its retry would have passed — R5 ("a stall, the command cap or a judged failure starts a fresh attempt under the usual retry rules, not a reattach") is broken whenever R3 has fired earlier in the same run; proved as Scenario 1 below, while the mirror order (Scenario 2) works, isolating the cause.
- MINOR | ohflow/scripts/ohflow/durable_runner.py:311 | `on_event`'s return annotation names `CliEventAction`, which the module never imports (it only works because `from __future__ import annotations` defers evaluation). Why it matters: a reader cannot resolve the name in this module and `typing.get_type_hints` would raise `NameError`.
- MINOR | ohflow/scripts/ohflow/durable_runner.py:331-333, 685-688 | The adapter reaches across the module seam for `pi_runner`'s private helpers (`_pi_messages`, `_pi_usage`, `_assistant_text`). Why it matters: the reuse the brief asked for is right, but the helpers are private to `pi_runner`, so pi can refactor them without knowing a second module depends on them; promoting them (as `event_log_usage` already was) would make the seam real.
- MINOR | ohflow/scripts/ohflow/durable_runner.py:493-530 | `_apply_event`'s assistant branch duplicates `pi_runner._entry`'s assistant branch (token fields, text/thinking pick, toolCall walk) over the same pi message shape. Why it matters: the token accounting for one message shape now lives in two places, so a change to one runner's accounting can silently diverge from the other's.

## Behaviour

1. `python ohflow/tests/run_tests.py -k durable`: exit 0 — `Ran 20 tests in 74.787s / OK` (`failures=0 errors=0 skipped=0`).
2. `python ohflow/tests/run_tests.py -k reattach`: exit 0 — `Ran 6 tests in 16.484s / OK` (`failures=0 errors=0 skipped=0`).
3. `PYTHONPATH=. python -c "...print(sorted(i('durable').caps))"` from `ohflow/scripts`: `['profile', 'qualified_mcp', 'reattach', 'stall_timeout']` — holds `reattach`, `profile`, `stall_timeout` and `qualified_mcp`; exit 0.

## Scenarios

1. **R3 and R5** (host_lost, then a stall on the reattached attempt, then a scripted success; `RetryPolicy(max=1, on=("agent_error",))`). Predicted per R3+R4+R5: starts `[(1, initial), (1, reattach), (2, retry)]`, finishes `[deferred/abort_victim/reattached, failed(stall), passed]`, step **passed**, `attempts()==3`, `failed_executions()==1`. Seen: **the retry ran as attempt 1, not attempt 2** — starts `[(1, 'initial'), (1, 'reattach'), (1, 'retry')]`; the third execution faulted `RuntimeError: ... attempt directory ... attempts\01 is not empty`, the step ended **failed**, `failed_executions()==2` and the exclusion fired, so the scripted passing answer never ran. The result goes wrong at engine.py:1142-1143, which passes the stale `reuse` set at engine.py:1151 into the retry that engine.py:1166 started.
   Script `%TEMP%\review-hardening-proof\scenario_r3_r5.py`, command `python scenario_r3_r5.py`:
   ```
   starts: [(1, 'initial'), (1, 'reattach'), (1, 'retry')]
   finishes: [('deferred', True, True, 'reattach: host_lost: ssh exited 255; the host on fakebox ended without durable_end'), ('quarantined', False, False, 'stall'), ('failed', False, False, 'RuntimeError: 01.only-phase/01.s1: attempt directory ...\attempts\01 is not empty. An attempt number was reused, and the evidence of the earlier execution would be overwritten.')]
   step status: failed
   attempts: 3
   failed_executions: 2
   exclusions: {'01.only-phase/01.s1@f26bd5...': {... 'reason': 'excluded: 2 failed executions of unchanged work (2 judged, 0 transient, ...'}}
   attempt-1 spec: attempt=1 reattach=True
   EXIT=0
   ```
2. **R5 and R3** (the mirror: stall on attempt 1, host_lost on attempt 2; same retry policy). Predicted: starts `[(1, initial), (2, retry), (2, reattach)]`, finishes `[failed(stall)→quarantined label, deferred/abort_victim/reattached, passed]`, step passed, `attempts()==3`, `failed_executions()==1`, no exclusion. Seen: exactly that (the first finish shows `quarantined`, the phase policy's documented relabelling of the judged `failed` verdict, which the retry rules read as `raw_status`).
   Script `%TEMP%\review-hardening-proof\scenario_r5_r3.py`, command `python scenario_r5_r3.py`:
   ```
   starts: [(1, 'initial'), (2, 'retry'), (2, 'reattach')]
   finishes: [('quarantined', False, False, 'stall'), ('deferred', True, True, 'reattach: host_lost: ssh exited 255; the host on fakebox ended without durable_end'), ('passed', False, False, None)]
   step status: passed
   attempts: 3
   failed_executions: 1
   exclusions: {}
   EXIT=0
   ```
3. **R6 and R5** (two host_lost reattaches, then a stall; `retry.max=1`, budget 3). Predicted per R6: the reattach closures spend total starts but no per-kind budget and no exclusion, so the stall's retry is refused by the total bound — last decision "execution budget spent", `attempts()==3 of 3`, `failed_executions()==1` (the stall only), step ends on the stall verdict (quarantined), no exclusion. Seen: exactly that.
   Script `%TEMP%\review-hardening-proof\scenario_r6_r5.py`, command `python scenario_r6_r5.py`:
   ```
   starts: [(1, 'initial'), (1, 'reattach'), (1, 'reattach')]
   finishes: [('deferred', True, True, 'reattach: host_lost: ...'), ('deferred', True, True, 'reattach: host_lost: ...'), ('quarantined', False, False, 'stall')]
   last retry decision: execution budget spent: 3 of 3 executions of this work (1 initial + 1 retries + 0 auto-resume passes + 1 manual recovery)
   step status: quarantined
   attempts: 3
   failed_executions: 1
   exclusions: {}
   EXIT=0
   ```
4. **R2 and R3 and R7** (the full engine with the real durable harness executor and transport: a real repo with a bare origin, the branch's fake ssh/scp box; execution 1 drops the connection → host_lost → the engine reattaches attempt 1 in the same directory; the host replays its session and pushes a commit). Predicted: starts `[(1, initial), (1, reattach)]`, finishes `[deferred/abort_victim/reattached(host_lost), passed]`, step passed, `attempts()==2`, `failed_executions()==0`; the reattached attempt's result `error None`, `llm_calls 5` (one replayed turn plus four), `prompt 5395 / completion 172` (the replayed turn's 945/29 included), `tool_calls 4`, `observation_errors 1`, `pushed True`; `usage(attempt_dir)` equal to those tokens; the repo HEAD fast-forwarded to the box's commit (`head != start_sha`) and the origin branch holding it; the spec in the attempt dir carrying `reattach: true, attempt: 1` and the same key (no second push). Seen: exactly that, every line.
   Scripts `%TEMP%\review-hardening-proof\scenario_r2_r3_r7.py` and `%TEMP%\review-hardening-proof\ssh_switch.py` (a fake-ssh wrapper that selects the branch fake's `killed`/`reattach` scenario from the `reattach` flag in the spec the adapter scp'd), command `python scenario_r2_r3_r7.py`:
   ```
   starts: [(1, 'initial'), (1, 'reattach')]
   finishes: [('deferred', True, True, 'reattach: host_lost: ssh exited 255; the host on fakebox ended without durable_end'), ('passed', False, False, None)]
   step status: passed
   attempts: 2 failed_executions: 0
   result error: None
   llm_calls: 5 tool_calls: 4 observation_errors: 1
   tokens: 5395 prompt / 172 completion
   usage() == result tokens: True why: None
   pushed: True head == repo HEAD: True head != start_sha: True
   origin branch holds the box commit: True
   spec: attempt=1 reattach=True key='01.only-phase-01.s1-a01-9cf041e8'
   EXIT=0
   ```

VERDICT: BLOCKED