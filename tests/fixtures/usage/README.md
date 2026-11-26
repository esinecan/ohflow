# Token reconciliation fixtures

These are small, copied artifacts from the preserved 27 September parity runs.
Only the provider secret fields were scrubbed; the token records and event
shapes are unchanged.

| Fixture | Source path |
| --- | --- |
| `pi/result.json` | `C:\Users\<user>\ohflow-home\experiments\oh-dispatch-pi-parity-2026-09-27\runs\pi\B2-engine-fault-matrix\r-20260928-012339\work\real\plan2\ohflow\r-20260928-012649-aac0c368\phases\01.abort\01.long-worker\attempts\01\result.json` |
| `pi/spec.json` | `C:\Users\<user>\ohflow-home\experiments\oh-dispatch-pi-parity-2026-09-27\runs\pi\B2-engine-fault-matrix\r-20260928-012339\work\real\plan2\ohflow\r-20260928-012649-aac0c368\phases\01.abort\01.long-worker\attempts\01\spec.json` |
| `pi/logs/pi-events.jsonl` | `C:\Users\<user>\ohflow-home\experiments\oh-dispatch-pi-parity-2026-09-27\runs\pi\B2-engine-fault-matrix\r-20260928-012339\work\real\plan2\ohflow\r-20260928-012649-aac0c368\phases\01.abort\01.long-worker\attempts\01\logs\pi-events.jsonl` |
| `pi/session/session.jsonl` | `C:\Users\<user>\ohflow-home\experiments\oh-dispatch-pi-parity-2026-09-27\runs\pi\B2-engine-fault-matrix\r-20260928-012339\work\real\plan2\ohflow\r-20260928-012649-aac0c368\phases\01.abort\01.long-worker\attempts\01\session\2026-09-27T23-26-51-956Z_01a0e531-5a34-75d6-b602-bc7d1a540046.jsonl` |
| `pi-missing-reasoning/*` | Same preserved B2 transient attempt: `C:\Users\<user>\ohflow-home\experiments\oh-dispatch-pi-parity-2026-09-27\runs\pi\B2-engine-fault-matrix\r-20260928-012339\work\real\plan1\ohflow\r-20260928-012354-8a9130b4\phases\03.transient\01.flaky-provider\attempts\01` (its assistant usage omits optional `reasoning`). |

`pi/logs/command_caps.jsonl` and the corresponding empty transient cap log keep
the attempt-local runner layout visible; the preserved abort run produced no
cap entries because its worker was killed before a command ran.

