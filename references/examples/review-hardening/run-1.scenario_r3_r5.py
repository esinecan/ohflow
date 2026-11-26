"""Scenario: R3 then R5 in one run (R4 fires on the way).

Sequence, one step with retry.max=1 on agent_error:
  execution 1 (attempt 1, initial)  -> host_lost -> R3: same attempt number,
      same attempt directory, closed deferred with abort_victim+reattached
      (R4), restarted with start_kind "reattach";
  execution 2 (attempt 1, reattach) -> "stall"   -> R5: an ordinary judged
      failure under the retry rules, not a reattach;
  execution 3 (attempt 2, retry)    -> success.

Predicted: starts [(1, initial), (1, reattach), (2, retry)]; finishes
[deferred/abort_victim/reattached, failed, passed]; step passed;
attempts() == 3; failed_executions() == 1; no exclusion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WT = Path(r"C:\Users\<user>\ohflow-home\workflows\review-hardening\wt")
sys.path[:0] = [str(WT / "ohflow" / "tests"),
                str(WT / "ohflow" / "scripts")]

from ohflow import attempts as ohattempts           # noqa: E402
from ohflow.engine import Engine                    # noqa: E402
from ohflow.run_log import RunLog                   # noqa: E402
from ohflow.workflow import RetryPolicy             # noqa: E402
from support import (AgentScript, TempCase, git_repo,         # noqa: E402
                     install_fake_harness_executor, quiet, simple_workflow,
                     step_statuses, stub_preflight)
from test_durable_03_reattach import (COORD, HOST_LOST, DurableFake,  # noqa: E402
                                      durable_step)


class Case(TempCase):
    def run_scenario(self):
        pass


case = Case("run_scenario")
case.setUp()
stub_preflight(case)
install_fake_harness_executor(case, DurableFake(default=AgentScript(
    sequence=[{"error": HOST_LOST}, {"error": "stall"}, {"error": None}])))
workflow = simple_workflow(git_repo(case.tmp / "repo"),
                           steps=[durable_step(
                               retry=RetryPolicy(max=1, on=("agent_error",)))])
run_dir = case.run_dir()
with quiet():
    Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
           resume=False, harness_executors=case.harness_executors).run()

records = [json.loads(line) for line
           in (run_dir / "run-log.jsonl").read_text(encoding="utf-8").splitlines()
           if line.strip()]
starts = [(r["attempt"], r["payload"]["start_kind"]) for r in records
          if r["event"] == "attempt_started" and r.get("coord") == COORD]
finishes = [(p["status"], bool(p.get("abort_victim")), bool(p.get("reattached")),
             p.get("error")) for r in records
            if r["event"] == "attempt_finished" and r.get("coord") == COORD
            for p in [r["payload"]]]
state = RunLog.replay(run_dir)
spec1 = json.loads((run_dir / "phases" / "01.only-phase" / "01.s1"
                    / "attempts" / "01" / "spec.json").read_text(encoding="utf-8"))
print("starts:", starts)
print("finishes:", finishes)
print("step status:", step_statuses(run_dir)[COORD])
print("attempts:", ohattempts.attempts(state, COORD))
print("failed_executions:", ohattempts.failed_executions(state, COORD))
print("exclusions:", dict(state.exclusions))
print("attempt-1 spec: attempt=%r reattach=%r"
      % (spec1.get("attempt"), spec1.get("reattach")))
case.doCleanups()
