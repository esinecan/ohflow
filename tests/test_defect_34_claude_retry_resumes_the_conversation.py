"""Defect 34: a claude retry with `carry_context` resumed the wrong thing.

What went wrong. The engine chose the next attempt's `fork_session` by taking
the newest `*.jsonl` file in the prior attempt's `transcript_dir`. That is a pi
rule: pi keeps one session file per conversation there. For claude the folder
holds `claude-events.jsonl`, the runner's event log, so the second launch got
`--resume <path to the event log>` and the CLI found no such conversation.

What is asserted here. A claude step with `retry.carry_context` runs twice
through the real claude harness executor (a fake CLI stands in for the binary). The second
launch resumes the first attempt's `conversation_id` from its `result.json`,
forks it, and is never handed a path.
"""

from __future__ import annotations

import json
import os

from ohflow import harness_executors
from ohflow.engine import Engine
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, RetryPolicy,
                             Step, AgentSpec)
from support import TempCase, git_repo, simple_workflow, stub_preflight

FAKE = os.path.join(os.path.dirname(__file__), "fakes", "fake_claude.py")
COORD = "01.only-phase/01.claude-step"
NEVER = GateSpec(checks=(CheckSpec("final_message_matches", {"regex": r"NEVER"}),))


class ClaudeCarryContext(TempCase):

    def _set_env(self, name: str, value: str) -> None:
        old = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(lambda: os.environ.pop(name, None) if old is None
                        else os.environ.__setitem__(name, old))

    def _run(self, *, carry: bool):
        state = self.tmp / "fake-state"
        self._set_env("OHFLOW_CLAUDE_EXE", FAKE)
        self._set_env("OHFLOW_FAKE_SIGNED_IN_STATE", str(state))
        self._set_env("OHFLOW_FAKE_SIGNED_IN_SCENARIO", "success")
        stub_preflight(self)
        repo = git_repo(self.tmp / "repo")
        agent = AgentSpec(
            role="rollcall", brief="report for duty", harness_executor="claude",
            model=ModelConfig(model="m", base_url="", api_key_env=""),
            max_iterations=5)
        step = Step(id="claude-step", kind="agent", worktree=None,
                    execution_timeout_s=60, agent=agent, gate=NEVER,
                    retry=RetryPolicy(max=1, on=("gate:final_message_matches",),
                                      carry_context=carry))
        workflow = simple_workflow(repo, phases=(
            Phase(name="Only phase", on_step_failure="continue",
                  min_success="all", steps=(step,)),))
        run_dir = self.run_dir()
        Engine(workflow, run_dir, run_id=run_dir.name, verbose=False).run()
        attempts = run_dir / "phases" / "01.only-phase" / "01.claude-step" / "attempts"
        history = [json.loads(line) for line in (state / "argv-history.jsonl")
                   .read_text(encoding="utf-8").splitlines()]
        return attempts, history

    @staticmethod
    def _after(argv: list[str], flag: str) -> str:
        return argv[argv.index(flag) + 1]

    def test_carry_context_resumes_the_first_attempts_conversation(self):
        attempts, history = self._run(carry=True)
        self.assertEqual(len(history), 2, "the gate failure must buy one retry")
        first = json.loads((attempts / "01" / "result.json").read_text(encoding="utf-8"))
        self.assertTrue(first["conversation_id"])
        self.assertNotIn("--resume", history[0])
        self.assertEqual(self._after(history[1], "--resume"), first["conversation_id"])
        self.assertIn("--fork-session", history[1])

    def test_a_retry_without_carry_context_starts_a_fresh_conversation(self):
        _attempts, history = self._run(carry=False)
        self.assertEqual(len(history), 2)
        self.assertNotIn("--resume", history[1])

    def test_the_claude_row_answers_the_resume_question_from_the_record(self):
        module = harness_executors.harness_executor_module("claude")
        self.assertEqual(module.resume_target({"conversation_id": "abc"}, self.tmp), "abc")
        self.assertIsNone(module.resume_target({}, self.tmp))
