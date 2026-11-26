"""Dashboard S4, test 10: `Step.objective` is display data and nothing more.

The objective answers "what did the workflow tell this agent to do" on its card.
`fingerprint_input` names its fields one by one and the position block feeds
the fingerprint, so an objective that reached either would invalidate every
cache the moment a workflow gained one. This test pins that it reaches neither,
that `validate` warns about a missing objective without refusing the workflow, and
the dashboard's fallback chain of spec §8.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

from dashboard_support import T0, workflow_json, agent
from ohflow import cli, live
from ohflow.coords import render_position
from ohflow.fingerprint import fingerprint, fingerprint_input
from ohflow.run_log import RunState
from ohflow.workflow import (OBJECTIVE_MAX, Phase, WorkflowError, objective_warnings,
                             validate)
from ohflow.report import render_board_md
from support import TempCase, git_repo, quiet, simple_workflow, agent_step

G1_BRIEF = (
    "# How to work here\n\n"
    "- Put `--no-pager` on every git command.\n"
    "- Never send empty input to the terminal. Redirect any possibly-long "
    "output to\n  a file and read the file instead.\n\n"
    "The first provider request is deliberately HTTP 429. Retry after the "
    "engine sweep and make no unrelated edits. End with DONE.\n")


def _two_phase_workflow(repo, *, objective: str | None):
    first = agent_step("scout", note=None)
    second = replace(agent_step("fix"), depends_on=("scout",))
    if objective is not None:
        first = replace(first, objective=objective)
        second = replace(second, objective=objective + " too")
    return simple_workflow(repo, phases=(
        Phase(name="Scout", steps=(first,)),
        Phase(name="Fix", steps=(second,)),
    ))


class TheObjectiveNeverReachesTheCacheKey(TempCase):

    def test_adding_an_objective_leaves_every_fingerprint_unchanged(self):
        repo = git_repo(self.tmp / "repo")
        bare = _two_phase_workflow(repo, objective=None)
        told = _two_phase_workflow(repo, objective="Map the parser failures")
        state = RunState()
        for (_a, _b, _c, s0), (_d, _e, _f, s1) in zip(bare.steps(),
                                                      told.steps()):
            with self.subTest(step=s0.id):
                self.assertNotEqual(s0, s1)
                self.assertEqual(fingerprint_input(bare, state, s0),
                                 fingerprint_input(told, state, s1))
                self.assertEqual(fingerprint(bare, state, s0),
                                 fingerprint(told, state, s1))
                self.assertEqual(
                    render_position(bare, state, s0, attempt=2),
                    render_position(told, state, s1, attempt=2),
                    "the position block is prepended to the brief")


class ValidateWarnsButDoesNotRefuse(TempCase):

    def test_an_agent_without_an_objective_is_a_warning(self):
        workflow = simple_workflow(self.tmp, steps=[
            agent_step("a"), replace(agent_step("b"), objective="Do b"),
            agent_step("c", note="the note")])
        validate(workflow)
        warnings = objective_warnings(workflow)
        self.assertEqual(len(warnings), 2)
        self.assertIn("01.only-phase/01.a", warnings[0])
        self.assertIn("first plain sentence of its brief", warnings[0])
        self.assertIn("01.only-phase/03.c", warnings[1])
        self.assertIn("its note", warnings[1])

    def test_the_cli_prints_the_warning_and_still_says_valid(self):
        workflow = simple_workflow(self.tmp, steps=[agent_step("a")])
        original = cli._load
        cli._load = lambda ns: workflow
        self.addCleanup(setattr, cli, "_load", original)
        with quiet() as output:
            code = cli.cmd_validate(SimpleNamespace(workflow="unused", args=[]))
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("WARNING: 01.only-phase/01.a: agent step has no "
                      "objective", output.out)
        self.assertTrue(output.out.startswith("VALID "), output.out)

    def test_an_objective_is_one_line_of_at_most_120_characters(self):
        for bad in ("x" * (OBJECTIVE_MAX + 1), "two\nlines", 42):
            with self.subTest(bad=bad):
                workflow = simple_workflow(self.tmp, steps=[
                    replace(agent_step("a"), objective=bad)])
                with self.assertRaises(WorkflowError) as caught:
                    validate(workflow)
                self.assertIn("objective", str(caught.exception))
        validate(simple_workflow(self.tmp, steps=[
            replace(agent_step("a"), objective="x" * OBJECTIVE_MAX)]))

    def test_the_board_shows_the_objective_when_there_is_no_note(self):
        workflow = simple_workflow(self.tmp, steps=[
            replace(agent_step("a"), objective="Map the parser failures")])
        self.assertIn("| Map the parser failures |",
                      render_board_md(workflow, RunState()))


class TheCardFallsBackInOrder(TempCase):

    def test_objective_then_note_then_the_first_plain_sentence(self):
        run = self.run_dir("r-objective")
        workflow_json(run, [("Map", [
            agent("a", objective="Stated outright", note="a note"),
            agent("b", note="Only a note"),
            agent("c", brief=G1_BRIEF),
            agent("d", brief="# Heading only\n\n- a list\n"),
        ], 4)])
        agents = {a["step_id"]: a for a in live.read_out(run, T0)["agents"]}
        self.assertEqual((agents["a"]["objective"],
                          agents["a"]["objective_source"]),
                         ("Stated outright", "objective"))
        self.assertEqual((agents["b"]["objective"],
                          agents["b"]["objective_source"]),
                         ("Only a note", "note"))
        self.assertEqual((agents["c"]["objective"],
                          agents["c"]["objective_source"]),
                         ("The first provider request is deliberately HTTP "
                          "429.", "brief"))
        self.assertEqual((agents["d"]["objective"],
                          agents["d"]["objective_source"]), (None, None))

    def test_workflow_json_carries_the_field(self):
        from ohflow.workflow import to_jsonable
        workflow = simple_workflow(self.tmp, steps=[
            replace(agent_step("a"), objective="Map it")])
        dumped = json.loads(json.dumps(to_jsonable(workflow)))
        self.assertEqual(dumped["phases"][0]["steps"][0]["objective"],
                         "Map it")
