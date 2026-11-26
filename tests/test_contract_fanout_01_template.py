"""The contract_fanout template: named pieces in parallel, merges, one reviewer.

The template is built with two pieces and checked through workflow validation
and `render_position`, never through a live agent. The reviewer's blocking
check runs for real against a result.json on disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ohflow import gates
from ohflow.coords import render_position
from ohflow.run_log import RunState
from ohflow.workflow import WorkflowError, load_workflow, validate
from ohflow.workflows import contract_fanout as cf
from support import TempCase, git_repo

MODULE = Path(cf.__file__)
CONTRACT = "# Contracts\n\n- `parse(text) -> Tree`, owned by parser. CONTRACT-MARKER\n"


class ContractFanout(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = git_repo(self.tmp / "repo")
        self.contracts = self.tmp / "contracts.md"
        self.contracts.write_text(CONTRACT, encoding="utf-8")
        self.spec = self.tmp / "spec.md"
        self.spec.write_text("# Spec\n", encoding="utf-8")

    def build(self, pieces="parser=src/parser/**;tests/test_parser*,printer=src/printer/**",
              **extra):
        return validate(load_workflow(MODULE, {
            "repo": str(self.repo), "root": str(self.tmp / "out"),
            "spec": str(self.spec), "contracts": str(self.contracts),
            "test_cmd": "python -m unittest", "pieces": pieces, **extra}))

    def test_two_pieces_run_in_parallel_on_their_own_worktrees_and_scopes(self):
        wf = self.build()
        build = wf.phases[0]
        self.assertEqual([s.id for s in build.steps], ["parser", "printer"])
        self.assertEqual(build.max_parallel, 2)
        self.assertEqual(build.steps[0].write_scope, ("src/parser/**", "tests/test_parser*"))
        self.assertEqual(build.steps[1].write_scope, ("src/printer/**",))
        trees = [wf.worktree(s.worktree) for s in build.steps]
        self.assertEqual(len({t.path for t in trees}), 2)
        self.assertEqual([t.branch for t in trees], ["fanout/parser", "fanout/printer"])

    def test_each_child_carries_the_contracts_the_heartbeat_and_the_hand_try(self):
        wf = self.build()
        heartbeat = (self.tmp / "out" / "heartbeat.log").as_posix()
        for step in wf.phases[0].steps:
            position = render_position(wf, RunState(), step)
            self.assertIn("Contracts: ", position)
            self.assertIn("You may not change them, and you may not work around them.", position)
            self.assertIn("If a contract is unworkable, stop and say in your handover", position)
            self.assertIn("CONTRACT-MARKER", position)
            self.assertIn(heartbeat, position)
            brief = step.agent.brief
            self.assertIn(self.contracts.as_posix(), brief)
            self.assertIn(f'{step.id} start" >> "{heartbeat}"', brief)
            self.assertIn(f'{step.id} end <outcome>" >> "{heartbeat}"', brief)
            self.assertIn("Hand-try: use the piece once by hand", brief)
            handover = next(c for c in step.gate.checks if c.name == "handover_written")
            self.assertIn("Hand-try", handover.args["headings"])
            self.assertIn("Interfaces", handover.args["headings"])
            self.assertIn(cf.heartbeat_check(step.id, heartbeat), step.gate.checks)

    def test_merges_follow_the_children(self):
        wf = self.build()
        merges = wf.phases[1].steps
        self.assertEqual([(s.kind, s.merge_branch, s.depends_on, s.worktree) for s in merges],
                         [("merge", "fanout/parser", ("parser",), "output"),
                          ("merge", "fanout/printer", ("printer",), "output")])

    def test_the_reviewer_reads_every_branch_and_sorts_its_findings(self):
        wf = self.build()
        (review,) = wf.phases[2].steps
        self.assertEqual(review.worktree, "output")
        self.assertEqual(review.consumes, ("parser", "printer"))
        self.assertTrue({"parser", "printer", "merge-parser", "merge-printer"} <= set(review.depends_on))
        for key in ("blocking", "should_fix", "notes"):
            self.assertIn(key, review.schema["required"])
            self.assertEqual(review.schema["properties"][key]["type"], "array")
        self.assertEqual(review.agent.tools.only, ("terminal",))
        cmds = [c.args["cmd"] for c in review.gate.checks if c.name == "command_exit"]
        self.assertEqual(cmds, ["python -m unittest", cf.blocking_gate_cmd()])
        self.assertIn("fanout/parser", review.agent.brief)
        self.assertIn(self.spec.as_posix(), review.agent.brief)

    def gate(self, structured) -> bool:
        attempt = self.tmp / "attempt"
        attempt.mkdir(exist_ok=True)
        (attempt / "result.json").write_text(json.dumps({"structured": structured}),
                                             encoding="utf-8")
        ctx = gates.GateContext(coord="03.review/01.review", repo=self.repo,
                                worktree=self.repo, base_sha="", base_ref="main",
                                attempt_dir=attempt, log_dir=attempt / "logs")
        return gates.REGISTRY["command_exit"](ctx, cmd=cf.blocking_gate_cmd()).passed

    def test_a_child_without_both_heartbeat_lines_fails_its_gate(self):
        log = self.tmp / "out" / "heartbeat.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        check = cf.heartbeat_check("a", log.as_posix())
        ctx = gates.GateContext(coord="01.build-pieces/01.a", repo=self.repo,
                                worktree=self.repo, base_sha="", base_ref="main",
                                attempt_dir=self.tmp, log_dir=self.tmp / "logs")

        def passes(*lines: str) -> bool:
            log.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
            return gates.REGISTRY["command_exit"](ctx, **check.args).passed

        self.assertFalse(passes("2026-11-20T10:00:00Z a start"))
        self.assertFalse(passes("2026-11-20T10:00:00Z ba start", "2026-11-20T10:09:00Z ba end done"))
        self.assertTrue(passes("2026-11-20T10:00:00Z a start", "2026-11-20T10:09:00Z a end done"))

    def test_relative_paths_reach_the_briefs_absolute(self):
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        wf = validate(load_workflow(MODULE, {
            "repo": str(self.repo), "root": "out", "spec": "spec.md",
            "contracts": "contracts.md", "test_cmd": "python -m unittest",
            "pieces": "parser=src/parser/**,printer=src/printer/**"}))
        brief = wf.phases[0].steps[0].agent.brief
        for path in (self.tmp / "out" / "heartbeat.log", self.spec, self.contracts):
            self.assertIn(path.resolve().as_posix(), brief)
        self.assertEqual(wf.contracts.path, self.contracts.resolve())

    def test_the_review_gate_fails_on_a_non_empty_blocking_list(self):
        finding = {"piece": "parser", "path": "src/parser/a.py", "line": 3, "claim": "x"}
        self.assertTrue(self.gate({"blocking": [], "should_fix": [finding], "notes": []}))
        self.assertFalse(self.gate({"blocking": [finding], "should_fix": [], "notes": []}))
        self.assertFalse(self.gate(None))

    def test_overlapping_scopes_and_bad_pieces_are_refused(self):
        with self.assertRaises(WorkflowError):
            self.build("parser=src/**,printer=src/printer/**")
        for pieces in ("parser=src/**", "review=a/**,b=b/**", "a=x/**,a=y/**", "a,b=y/**"):
            with self.assertRaises(ValueError):
                self.build(pieces)

    def test_an_executor_on_another_machine_is_refused(self):
        for extra in ({"harness_executor": "pi-cloud"}, {"harness_executor": "durable"},
                      {"review_harness_executor": "durable"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError) as caught:
                self.build(**extra)
            self.assertIn("another machine", str(caught.exception))
