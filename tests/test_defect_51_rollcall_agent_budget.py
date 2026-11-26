"""Defect 51: a roll-call agent could end on its iteration budget.

The roll call gave each agent `max_iterations` 15. One agent, with the
launching session's variables stripped, found no false identity in its
environment and went looking for its own harness version and model: it listed
the environment, ran `pip show`, listed its run directory and read its own
completions. It reached the limit of 15 before its final message, and its test case
failed on `schema_valid`. Earlier test cases used 5 to 9 calls.

The default is now 30 for every agent step of every scenario, and every brief
that asks for the harness line tells the agent where its facts come from:
its own system prompt, tool list and working directory, and `unknown` for a
value they do not show.
"""

from __future__ import annotations

from ohflow.workflows import rollcall
from support import TempCase

SCENARIOS = {
    "single": "pi",
    "fanout": "pi,claude,codex",
    "relay": "pi,claude",
    "merge": "pi,claude",
    "retry": "pi",
    "review": "pi",
    "campaign": "pi",
}
SENTENCE = "Write `unknown` for a value they do not show"


class RollcallAgentBudget(TempCase):

    def _agents(self, **args) -> list[tuple[str, object]]:
        found = []
        for scenario, harness_executors in SCENARIOS.items():
            workflow = rollcall.build({"repo": str(self.tmp / "repo"),
                                       "scenario": scenario, "harness_executors": harness_executors, **args})
            for phase in workflow.phases:
                for step in phase.steps:
                    if step.kind == "agent":
                        found.append((f"{scenario}/{step.id}", step.agent))
        return found

    def test_every_agent_step_of_every_scenario_gets_at_least_30_iterations(self):
        agents = self._agents()
        self.assertGreaterEqual(len(agents), len(SCENARIOS))
        for name, agent in agents:
            self.assertGreaterEqual(agent.max_iterations, 30, name)

    def test_the_judge_gets_the_default_too(self):
        judge = rollcall.judge_spec({"repo": str(self.tmp / "repo")})
        self.assertGreaterEqual(judge.max_iterations, 30)

    def test_the_argument_still_overrides_the_default(self):
        for name, agent in self._agents(max_iterations=7):
            self.assertEqual(agent.max_iterations, 7, name)

    def test_every_brief_that_asks_for_the_harness_line_says_where_facts_come_from(self):
        asking = 0
        for name, agent in self._agents():
            if "- Harness:" not in agent.brief and '"harness"' not in agent.brief:
                continue
            asking += 1
            self.assertIn(SENTENCE, agent.brief, name)
            self.assertIn("Do not search", agent.brief, name)
        self.assertGreater(asking, 0)
