"""Defect 77: concurrent agent steps passed a run's token cap without anyone stopping them.

What went wrong. On 19.11.2026 a research fan-out ran under a 700k-token cap
that the operator checked by polling. The last poll read 590652 tokens, and the
run settled at 782488 after it was stopped: the steps in flight kept spending
between two polls, and nothing in the engine knew the cap.

What is asserted here. With `token_budget` set, every agent attempt reserves
its grant before launch, so concurrent steps never hold more than the limit.
An attempt whose live usage reaches its grant is extended from the free
allowance or stopped. Usage that arrives too late to stop is settled as a
recorded overshoot, never silently: a `token_budget` overshoot event in the run
log, a line in the exit report, a field and an attention item on the dashboard.
In every interleaving, settled tokens stay within the limit plus the recorded
overshoot. The pi guard starts no model call past the grant.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

from ohflow import attention, budget as ohbudget, dashboard_data, exit_report
from ohflow import harness_executor as ohexecutor
from ohflow.engine import Engine
from ohflow.pi_runner import EVENT_LOG
from ohflow.workflow import WorkflowError, validate
from support import (AgentScript, FakeHarnessExecutor, TempCase, agent_step,
                     git_repo, install_fake_harness_executor, read_run_log,
                     simple_workflow, step_statuses, stub_preflight)


def usage_tokens(total: int) -> dict:
    return {"prompt_tokens": total - total // 4, "completion_tokens": total // 4,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "reasoning_tokens": 0}


class MeteredHarnessExecutor(FakeHarnessExecutor):
    """A fake agent that spends `per_poll` tokens at each poll, written to the
    pi event log the engine reads, and finishes after `total`. With `late`, it
    reports nothing live and its whole usage at the end, as codex does."""

    def __init__(self, *, per_poll: int, total: int, late: bool = False,
                 gate_at: int | None = None):
        super().__init__(default=AgentScript(final_text="DONE\n"),
                         gate_at=gate_at, gate_timeout=10.0)
        self.per_poll, self.total, self.late = per_poll, total, late
        self.peak_reserved = 0
        self.ledgers: list = []

    def launch(self, spec, out_dir):
        handle = super().launch(spec, out_dir)
        handle.spent = 0
        (Path(out_dir) / "logs").mkdir(parents=True, exist_ok=True)
        for ledger in self.ledgers:
            with ledger._turn:
                self.peak_reserved = max(self.peak_reserved,
                                         ledger.settled + sum(ledger.grants.values()))
        return handle

    def poll(self, handle):
        if handle.killed:
            handle.error = "fake child was killed"
            return ohexecutor.ERROR
        if handle.spent >= self.total:
            return ohexecutor.FINISHED
        step = min(self.per_poll, self.total - handle.spent)
        handle.spent += step
        if not self.late:
            event = {"type": "message_end", "message": {
                "role": "assistant",
                "usage": {"input": step - step // 4, "output": step // 4,
                          "cacheRead": 0, "cacheWrite": 0}}}
            with (Path(handle.out_dir) / "logs" / EVENT_LOG).open(
                    "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        return ohexecutor.RUNNING

    def collect(self, handle):
        handle.script = replace_tokens(handle.script, usage_tokens(handle.spent))
        return super().collect(handle)


def replace_tokens(script: AgentScript, tokens: dict) -> AgentScript:
    copy = AgentScript(final_text=script.final_text, error=script.error,
                       exit_status=script.exit_status, tokens=tokens)
    copy.launches = script.launches
    return copy


class LedgerInvariant(TempCase):

    def test_settled_stays_within_limit_plus_recorded_overshoot_in_any_interleaving(self):
        rng = random.Random(77)
        for trial in range(40):
            limit = rng.randint(200, 2000)
            ledger = ohbudget.Ledger(limit, rng.randint(20, limit))
            errors: list[str] = []

            def agent(n: int) -> None:
                key = f"s{n}"
                grant, _ = ledger.admit(key)
                if grant is None:
                    return
                spent = 0
                late = rng.random() < 0.4
                target = rng.randint(0, limit)
                while spent < target:
                    spent += rng.randint(1, max(1, limit // 5))
                    if not late and not ledger.observe(key, spent):
                        break
                ledger.settle(key, spent if rng.random() < 0.9 else None)
                with ledger._turn:
                    if ledger.settled + sum(ledger.grants.values()) > \
                            ledger.limit + ledger.overshoot:
                        errors.append(f"trial {trial}: invariant broken")

            threads = [threading.Thread(target=agent, args=(n,)) for n in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            snap = ledger.snapshot()
            self.assertLessEqual(snap["settled_tokens"],
                                 snap["limit_tokens"] + snap["overshoot_tokens"])
            self.assertEqual(snap["in_flight"], {})

    def test_admission_waits_for_in_flight_grants_and_refuses_when_none_are_left(self):
        ledger = ohbudget.Ledger(300, 100)
        for key in ("a", "b", "c"):
            self.assertEqual(ledger.admit(key)[0], 100)
        admitted: list = []
        waiter = threading.Thread(target=lambda: admitted.append(ledger.admit("d")),
                                  daemon=True)
        waiter.start()
        waiter.join(0.3)
        self.assertTrue(waiter.is_alive(), "d must wait while a, b, c hold grants")
        ledger.settle("a", 0)
        waiter.join(5)
        self.assertEqual(admitted[0][0], 100)
        for key in ("b", "c", "d"):
            ledger.settle(key, 100)
        grant, why = ledger.admit("e")
        self.assertIsNone(grant)
        self.assertIn("token budget spent", why)

    def test_live_usage_and_billing_estimate_are_separate_fields(self):
        ledger = ohbudget.Ledger(1000, 100)
        ledger.admit("a")
        ledger.settle("a", 80, cost=0.25, cost_source="litellm")
        ledger.admit("b")
        ledger.settle("b", 50, cost=1.5, cost_source="unpriced")
        snap = ledger.snapshot()
        self.assertEqual(snap["observed_tokens"], 130)
        self.assertEqual(snap["billing_estimate_usd"], 0.25)
        self.assertEqual(snap["billing_priced_attempts"], 1)
        self.assertEqual(snap["billing_unpriced_attempts"], 1)


class TokenBudgetInTheEngine(TempCase):

    def _run(self, harness, *, steps: int, budget: int | None, reserve: int | None,
             max_parallel: int = 3, token_budget: int | None = None,
             run_dir: Path | None = None, resume: bool = False, workflow=None):
        stub_preflight(self)
        install_fake_harness_executor(self, harness)
        if workflow is None:
            workflow = simple_workflow(
                git_repo(self.tmp / "repo"),
                steps=[agent_step(f"s{n}") for n in range(1, steps + 1)],
                max_parallel=max_parallel)
            workflow = replace(workflow, token_budget=budget, token_reserve=reserve)
        run_dir = run_dir or self.run_dir()
        engine = Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                        resume=resume, token_budget=token_budget,
                        harness_executors=self.harness_executors)
        engine.poll_interval_s = 0.01
        original = engine._open_budget

        def opened():
            original()
            if engine.budget is not None:
                harness.ledgers.append(engine.budget)
        engine._open_budget = opened
        engine.run()
        return engine, run_dir, workflow

    def events(self, run_dir: Path, kind: str) -> list[dict]:
        return [r for r in read_run_log(run_dir) if r.get("event") == "token_budget"
                and (r.get("payload") or {}).get("kind") == kind]

    def test_concurrent_steps_never_reserve_past_the_limit_and_the_rest_are_refused(self):
        harness = MeteredHarnessExecutor(per_poll=20, total=80)
        engine, run_dir, workflow = self._run(harness, steps=5, budget=300,
                                              reserve=100)
        snap = ohbudget.read_snapshot(run_dir)
        self.assertLessEqual(harness.peak_reserved, 300)
        self.assertEqual(snap["settled_tokens"], 240)
        self.assertEqual(snap["overshoot_tokens"], 0)
        statuses = step_statuses(run_dir)
        self.assertEqual(sorted(statuses.values()),
                         ["deferred", "deferred", "passed", "passed", "passed"])
        self.assertEqual(len(self.events(run_dir, "refused")), 2)
        self.assertEqual(read_run_log(run_dir)[-1]["payload"]["status"], "paused")

        engine, _, _ = self._run(harness, steps=5, budget=300, reserve=100,
                                 run_dir=run_dir, resume=True, workflow=workflow)
        self.assertEqual(engine.budget.limit, 300)
        self.assertEqual(engine.budget.settled, 240)
        self.assertEqual(sorted(step_statuses(run_dir).values()).count("deferred"), 2)

        engine, _, _ = self._run(harness, steps=5, budget=300, reserve=100,
                                 run_dir=run_dir, resume=True, workflow=workflow,
                                 token_budget=500)
        self.assertEqual(engine.budget.limit, 500)
        self.assertEqual(sorted(step_statuses(run_dir).values()),
                         ["cached", "cached", "cached", "passed", "passed"])
        self.assertEqual(ohbudget.read_snapshot(run_dir)["settled_tokens"], 400)

    def test_a_step_whose_live_usage_reaches_its_grant_with_nothing_free_is_stopped(self):
        harness = MeteredHarnessExecutor(per_poll=25, total=500, gate_at=3)
        _, run_dir, _ = self._run(harness, steps=3, budget=300, reserve=100)
        snap = ohbudget.read_snapshot(run_dir)
        self.assertEqual(sorted(harness.killed), sorted(
            c for c in step_statuses(run_dir)))
        self.assertLessEqual(snap["settled_tokens"], 300)
        self.assertEqual(snap["overshoot_tokens"], 0)
        finishes = [r for r in read_run_log(run_dir)
                    if r.get("event") == "attempt_finished"]
        self.assertEqual({r["payload"]["status"] for r in finishes}, {"quarantined"})
        for r in finishes:
            self.assertTrue(r["payload"]["error"].startswith("token budget: stopped"))
            self.assertEqual(r["payload"]["failure_class"], "structural")

    def test_late_usage_past_the_grant_is_recorded_as_overshoot_everywhere(self):
        harness = MeteredHarnessExecutor(per_poll=50, total=150, late=True,
                                         gate_at=3)
        _, run_dir, _ = self._run(harness, steps=3, budget=300, reserve=100)
        snap = ohbudget.read_snapshot(run_dir)
        overshoots = self.events(run_dir, "overshoot")
        self.assertEqual(snap["settled_tokens"], 450)
        self.assertEqual(sum(o["payload"]["overshoot_tokens"] for o in overshoots), 150)
        self.assertLessEqual(snap["settled_tokens"],
                             snap["limit_tokens"] + snap["overshoot_tokens"])

        read_out = exit_report.build(run_dir, exit_report.exit_info("finished"))
        md = exit_report.render_md(read_out)
        self.assertIn("token budget overshot by 150", read_out["report"]["verdict"])
        self.assertIn("## Token budget", md)
        self.assertTrue(any("overshot" in n["text"] for n in read_out["report"]["needs"]))

        page = dashboard_data.workflow_data(run_dir)
        self.assertEqual(page["run"]["token_budget"]["overshoot_tokens"], 150)
        kinds = [i["kind"] for i in page["attention"]]
        self.assertEqual(kinds.count("token_overshoot"), 3)

    def test_a_run_without_a_budget_writes_no_ledger(self):
        harness = MeteredHarnessExecutor(per_poll=50, total=100)
        _, run_dir, _ = self._run(harness, steps=2, budget=None, reserve=None)
        self.assertIsNone(ohbudget.read_snapshot(run_dir))
        self.assertEqual([r for r in read_run_log(run_dir)
                          if r.get("event") == "token_budget"], [])

    def test_validate_refuses_a_reserve_without_a_budget_or_above_it(self):
        workflow = simple_workflow(self.tmp / "repo")
        with self.assertRaises(WorkflowError) as caught:
            validate(replace(workflow, token_reserve=10))
        self.assertIn("token_reserve needs a token_budget", str(caught.exception))
        with self.assertRaises(WorkflowError) as caught:
            validate(replace(workflow, token_budget=10, token_reserve=20))
        self.assertIn("larger than token_budget", str(caught.exception))


class PiGuardGatesEachModelCall(TempCase):

    SCRIPT = r'''
import { pathToFileURL } from "node:url";
import fs from "node:fs";
import path from "node:path";
const hooks = {};
const pi = { on(name, handler) { hooks[name] = handler; } };
(await import(pathToFileURL(process.argv[1]).href)).default(pi);
const dir = process.env.OHFLOW_ATTEMPT_DIR;
const grant = (tokens, final) => fs.writeFileSync(path.join(dir, "budget-grant.json"),
  JSON.stringify({grant_tokens: tokens, final}));
const calls = {abort: 0, shutdown: 0};
const ctx = {abort() { calls.abort += 1; }, shutdown() { calls.shutdown += 1; }};
const spend = (n) => hooks.message_end({message: {role: "assistant",
  usage: {input: n, output: 0, cacheRead: 0, cacheWrite: 0}}});
const rows = {};
grant(100, false);
await spend(60);
await hooks.context({messages: []}, ctx);
rows.under = {...calls};
await spend(60);
setTimeout(() => grant(200, false), 300);
await hooks.context({messages: []}, ctx);
rows.extended = {...calls};
await spend(100);
grant(200, true);
await hooks.context({messages: []}, ctx);
rows.final = {...calls};
rows.stop = JSON.parse(fs.readFileSync(path.join(dir, "budget-stop.json"), "utf8"));
process.stdout.write(JSON.stringify(rows));
'''

    def test_the_guard_waits_for_an_extension_and_stops_at_a_final_grant(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is unavailable")
        original = Path(__file__).parents[1] / "scripts" / "ohflow" / "ohflow-guard.ts"
        guard = self.tmp / "guard.mjs"
        guard.write_bytes(original.read_bytes())
        attempt = self.tmp / "attempt"
        attempt.mkdir()
        proc = subprocess.run(
            [node, "--input-type=module", "-e", self.SCRIPT, str(guard)],
            check=True, capture_output=True, text=True,
            env={**os.environ, "OHFLOW_ATTEMPT_DIR": str(attempt)}, timeout=60)
        rows = json.loads(proc.stdout)
        self.assertEqual(rows["under"], {"abort": 0, "shutdown": 0})
        self.assertEqual(rows["extended"], {"abort": 0, "shutdown": 0})
        self.assertEqual(rows["final"], {"abort": 1, "shutdown": 1})
        self.assertEqual(rows["stop"], {"used_tokens": 220, "grant_tokens": 200,
                                        "final": True})
