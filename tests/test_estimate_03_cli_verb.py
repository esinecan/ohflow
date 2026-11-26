"""`ohflow estimate`: the verb, its JSON shape and its one-line refusal.

`--history DIR` names where the finished runs are. Without the flag the verb
reads `OHFLOW_HISTORY`, and with neither it prints one line that says what to
pass and exits 0: a missing history is not a fault of the workflow.
`validate -v --history DIR` prints the same block below the step detail.
"""

from __future__ import annotations

import json
import os
import textwrap
from unittest import mock

from ohflow import estimate
from ohflow.cli import main as cli_main
from support import TempCase, quiet
from test_estimate_01_prior_from_history import attempt, summary

WORKFLOW = '''
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             Step, AgentSpec)

MODEL = ModelConfig(model="fake/deterministic",
                    base_url="http://127.0.0.1:0/never-called",
                    api_key_env="OHFLOW_TEST_FAKE_KEY")


def build(args):
    gate = GateSpec(checks=(CheckSpec("final_message_matches", {"regex": "DONE"}),))
    a = Step(id="a", kind="agent", gate=gate,
             agent=AgentSpec(role="implementer", brief="do it", model=MODEL,
                             harness_executor="pi", max_iterations=3))
    b = Step(id="b", kind="agent", gate=gate,
             agent=AgentSpec(role="reviewer", brief="check it", model=MODEL,
                             harness_executor="pi", max_iterations=3))
    return Workflow(name="two-agents", repo=Path(args["repo"]), base_branch="main",
                    max_parallel=1, transient_backoff_s=0,
                    phases=(Phase(name="Build", steps=(a,)),
                            Phase(name="Review", steps=(b,))))
'''


class EstimateVerb(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.module = self.tmp / "workflow.py"
        self.module.write_text(textwrap.dedent(WORKFLOW), encoding="utf-8")
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.history = self.tmp / "history"
        for n, (wall_a, wall_b) in enumerate([(100, 300), (200, 400), (300, 500)]):
            summary(self.history / f"r{n}", f"r{n}", [
                {"role": "implementer", "executor": "pi", "model": "fake/deterministic",
                 "attempts": [attempt(wall_a, 1000, 0.0, "unpriced")]},
                {"role": "reviewer", "executor": "pi", "model": "fake/deterministic",
                 "attempts": [attempt(wall_b, 2000, 0.0, "unpriced")]},
            ])
        self.base = ["--workflow", str(self.module), "--args", f"repo={self.repo}"]
        # The suite scrubs OHFLOW_* names at import; be explicit anyway.
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop(estimate.HISTORY_ENV, None)

    def run_cli(self, *argv: str) -> tuple[int, str]:
        with quiet() as q:
            code = cli_main(list(argv))
        return code, q.out

    def test_json_carries_the_run_phases_and_steps(self):
        code, out = self.run_cli("estimate", *self.base, "--history",
                                 str(self.history), "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["schema"], estimate.SCHEMA)
        self.assertEqual(data["workflow"], "two-agents")
        self.assertEqual([p["name"] for p in data["phases"]], ["Build", "Review"])
        self.assertEqual(data["phases"][0]["wall_s"]["p50"], 200)
        self.assertEqual(data["phases"][1]["wall_s"]["p50"], 400)
        self.assertEqual(data["run"]["wall_s"]["p50"], 600)
        self.assertEqual(data["run"]["tokens"]["p50"], 3000)
        self.assertEqual(len(data["steps"]), 2)
        self.assertEqual(data["history"]["samples"], 6)
        self.assertEqual(data["history"]["sources"], 3)

    def test_the_text_block_opens_with_the_verdict_line(self):
        code, out = self.run_cli("estimate", *self.base, "--history", str(self.history))
        self.assertEqual(code, 0, out)
        first = out.splitlines()[0]
        self.assertTrue(first.startswith("ESTIMATE two-agents:"), first)
        self.assertIn("10 min", first)
        self.assertIn("Build", out)
        self.assertIn("Review", out)

    def test_without_history_the_verb_prints_one_line_and_exits_0(self):
        code, out = self.run_cli("estimate", *self.base)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), estimate.NO_HISTORY)

    def test_the_environment_variable_names_the_default_history(self):
        os.environ[estimate.HISTORY_ENV] = str(self.history)
        code, out = self.run_cli("estimate", *self.base, "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["history"]["samples"], 6)

    def test_validate_verbose_prints_the_block_when_history_is_given(self):
        code, out = self.run_cli("validate", *self.base, "-v", "--history",
                                 str(self.history))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("VALID two-agents"))
        self.assertIn("ESTIMATE two-agents:", out)

    def test_validate_without_history_prints_no_estimate_line(self):
        code, out = self.run_cli("validate", *self.base, "-v")
        self.assertEqual(code, 0, out)
        self.assertNotIn("estimate", out.lower())

    def test_a_history_with_no_summaries_says_so(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        code, out = self.run_cli("estimate", *self.base, "--history", str(empty))
        self.assertEqual(code, 0, out)
        self.assertIn("no history", out.splitlines()[0])
