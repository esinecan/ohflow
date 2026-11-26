from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ohflow import pilot
from ohflow.workflow import Phase, Unit, UnitPath, WorkflowError, validate
from pilot_support import two_paths, write_module
from support import TempCase
from verb_support import call


class Declaration(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()

    def problems(self, workflow) -> list[str]:
        with self.assertRaises(WorkflowError) as caught:
            validate(workflow)
        return caught.exception.problems

    def test_a_two_path_workflow_validates(self):
        validate(two_paths(self.repo))

    def test_validate_names_units_and_paths_and_the_pilot_units(self):
        module = write_module(self.tmp / "wf.py")
        code, lines = call("validate", "--workflow", module, "--args",
                           f"repo={self.repo}", "-v")
        self.assertEqual(code, 0, lines)
        self.assertIn("; 5 units on 2 paths", lines[0])
        self.assertIn("path single: 3 units, pilot unit s2", lines)
        self.assertIn("path probe: 2 units, pilot unit p2", lines)

    def test_a_unit_on_an_undeclared_path_is_refused(self):
        workflow = two_paths(self.repo)
        workflow = replace(workflow, units=workflow.units[:-1]
                           + (Unit("p2", "reopened", 1),))
        self.assertIn("unit 'p2': path 'reopened' is not declared in "
                      "Workflow.paths", self.problems(workflow))

    def test_a_step_naming_an_undeclared_unit_is_refused(self):
        workflow = two_paths(self.repo)
        workflow = replace(workflow, units=workflow.units[1:])
        problems = self.problems(workflow)
        self.assertTrue(any("unit 's1' is not declared in Workflow.units" in p
                            for p in problems), problems)

    def test_a_unit_without_a_step_is_refused(self):
        workflow = two_paths(self.repo)
        workflow = replace(workflow, units=workflow.units + (Unit("p9", "probe"),))
        self.assertIn("unit 'p9' has no step; set Step.unit='p9' on the steps "
                      "that do its work", self.problems(workflow))

    def test_a_duplicate_unit_and_a_bad_size_are_refused(self):
        workflow = two_paths(self.repo)
        workflow = replace(workflow, units=workflow.units
                           + (Unit("s1", "single", 0),))
        problems = self.problems(workflow)
        self.assertIn("unit 's1' is declared twice", problems)
        self.assertIn("unit 's1': size must be a positive number, got 0", problems)

    def test_a_duplicate_path_is_refused(self):
        workflow = two_paths(self.repo)
        workflow = replace(workflow, paths=workflow.paths + (UnitPath("probe"),))
        self.assertIn("path 'probe' is declared twice", self.problems(workflow))


class PilotSelection(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()

    def test_the_smallest_unit_of_each_path_is_picked(self):
        self.assertEqual([u.id for u in pilot.pick(two_paths(self.repo))],
                         ["s2", "p2"])

    def test_a_tie_goes_to_the_unit_declared_first(self):
        units = [("a", "single", 1), ("b", "single", 1), ("c", "probe", 1)]
        self.assertEqual([u.id for u in pilot.pick(two_paths(self.repo, units))],
                         ["a", "c"])

    def test_a_path_with_no_unit_is_not_piloted(self):
        units = [("a", "single", 1), ("b", "single", 2)]
        self.assertEqual([u.id for u in pilot.pick(two_paths(self.repo, units))],
                         ["a"])

    def test_the_pilot_workflow_keeps_the_picked_units_and_the_shared_steps(self):
        small = validate(pilot.pilot_workflow(two_paths(self.repo)))
        ids = [step.id for _pi, _phase, _si, step in small.steps()]
        self.assertEqual(ids, ["fix-s2", "fix-p2", "report"])
        self.assertEqual([u.id for u in small.units], ["s2", "p2"])
        self.assertEqual(small.step_by_id("report")[3].depends_on,
                         ("fix-s2", "fix-p2"))

    def test_an_empty_phase_is_dropped_and_min_success_is_clamped(self):
        workflow = two_paths(self.repo)
        fix, report = workflow.phases
        workflow = validate(replace(workflow, phases=(
            replace(fix, steps=fix.steps[1:], min_success=4),
            Phase(name="Only s1", steps=(fix.steps[0],)),
            report)))
        small = validate(pilot.pilot_workflow(workflow))
        self.assertEqual([p.name for p in small.phases], ["Fix", "Report"])
        self.assertEqual(small.phases[0].min_success, 2)

    def test_the_pilot_runs_on_its_own_worktrees(self):
        workflow = two_paths(self.repo, worktrees=True)
        merge = replace(workflow.phases[1].steps[0], id="merge", kind="merge",
                        agent=None, gate=None, objective=None,
                        merge_branch="atlas/work", depends_on=())
        workflow = replace(workflow, phases=workflow.phases
                           + (Phase(name="Merge", steps=(merge,)),))
        small = pilot.pilot_workflow(workflow)
        tree = small.worktree("work")
        self.assertEqual(tree.path, Path(str(workflow.worktree("work").path)
                                         + pilot.SUFFIX))
        self.assertEqual(tree.branch, "atlas/work-pilot")
        self.assertEqual(tree.base, "main")
        self.assertEqual(small.step_by_id("merge")[3].merge_branch,
                         "atlas/work-pilot")


if __name__ == "__main__":
    import unittest
    unittest.main()
