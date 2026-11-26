"""`ohflow construct` turns a bundle of milestone specs into a campaign.

The bundles under `construct_bundles/` name their repositories by paths
relative to the bundle, so each test copies a bundle into its temporary
directory and makes those repositories beside it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

from ohflow import campaign as oc
from ohflow import construct as ohcon
from ohflow import patterns
from ohflow.paths import bash_exe
from ohflow.workflow import load_workflow, validate
from support import TempCase, git_repo, use_settings
from verb_support import call

BUNDLES = Path(__file__).resolve().with_name("construct_bundles")


class ConstructCase(TempCase):

    def bundle(self, name: str) -> Path:
        target = self.tmp / "bundle"
        shutil.copytree(BUNDLES / name, target)
        return target

    def construct(self, bundle: Path) -> tuple[int, list[str], Path]:
        out = self.tmp / "campaign"
        code, lines = call("construct", "--bundle", bundle, "--out", out)
        return code, lines, out

    def workflow(self, out: Path, mid: str):
        camp = oc.load_campaign(out / "campaign.py")
        m = next(m for m in camp.milestones if m.id == mid)
        return camp, m, validate(load_workflow(out / m.workflow, oc.milestone_args(camp, m)))


class SpecFolder(ConstructCase):

    def setUp(self) -> None:
        super().setUp()
        git_repo(self.tmp / "app")
        self.code, self.lines, self.out = self.construct(self.bundle("spec-folder"))

    def test_line_one_names_the_campaign_and_the_milestone_count(self) -> None:
        self.assertEqual(self.code, 0, self.lines)
        self.assertEqual(self.lines[0], f"CONSTRUCTED {self.out}: 2 milestones")

    def test_each_milestone_validates_in_its_pattern(self) -> None:
        self.assertIn("01-strict implement-and-review: VALID 01-strict: 2 phases, 2 steps; "
                      "harness executors pi:1, claude:1", self.lines)
        self.assertIn("02-docs single-agent: VALID 02-docs: 1 phase, 1 step; "
                      "harness executors codex:1", self.lines)
        self.assertIn("estimate: no history given (--history DIR or OHFLOW_HISTORY)",
                      self.lines)
        self.assertIn("CAMPAIGN OK", self.lines)

    def test_campaign_validate_passes_on_what_construct_wrote(self) -> None:
        code, lines = call("campaign", "validate", "--campaign", self.out / "campaign.py")
        self.assertEqual((code, lines[-1]), (0, "CAMPAIGN OK"), lines)

    def test_the_charter_carries_the_words_the_kind_and_each_source(self) -> None:
        charter = (self.out / "charter.md").read_text(encoding="utf-8")
        self.assertIn("Add a strict mode to the config parser, and document it.", charter)
        self.assertIn("The objective is a delivery", charter)
        self.assertIn("| `01-strict` Strict mode in the config parser | "
                      "implement-and-review | specs/strict-mode.md |", charter)

    def test_command_checks_gate_the_steps_and_run_as_acceptance_checks(self) -> None:
        camp, m, workflow = self.workflow(self.out, "01-strict")
        cmd = "python -m unittest discover -s tests"
        self.assertEqual([(c.cmd, c.cwd) for c in m.acceptance_checks], [(cmd, "land:app")])
        for step in ("implement", "review"):
            gate = workflow.step_by_id(step)[3].gate
            self.assertIn(cmd, [c.args.get("cmd") for c in gate.checks])
        review = workflow.step_by_id("review")[3]
        self.assertEqual(review.agent.tools.only, ("terminal",))
        self.assertEqual(review.agent.agent_profile, "hermetic")
        self.assertEqual([w.branch for w in workflow.worktrees],
                         ["milestone/parser-and-docs/01-strict"])

    def test_the_briefs_carry_the_spec_and_the_review_verdict(self) -> None:
        briefs = self.out / "milestones" / "01-strict" / "briefs"
        implement = (briefs / "implement.md").read_text(encoding="utf-8")
        review = (briefs / "review.md").read_text(encoding="utf-8")
        self.assertIn("Its source is specs/strict-mode.md.", implement)
        self.assertIn("`parse(text, strict=True)` refuses a key", implement)
        self.assertIn("The error message names the unknown key", implement)
        self.assertIn("`VERDICT: MERGEABLE`", review)

    def test_only_the_gate_runs_the_milestone_command(self) -> None:
        briefs = self.out / "milestones" / "01-strict" / "briefs"
        implement = (briefs / "implement.md").read_text(encoding="utf-8")
        review = " ".join((briefs / "review.md").read_text(encoding="utf-8").split())
        self.assertIn("run only the tests of the files you change", implement)
        self.assertIn("Do not run these commands or the full suite yourself.", review)
        self.assertIn("Your gate reuses that pass while the commit is unchanged.", review)
        self.assertNotIn("Run each command below once", review)

    def test_a_tier_names_no_model_in_what_construct_wrote(self) -> None:
        record = json.loads((self.out / "milestones" / "01-strict" / "milestone.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual([(s["id"], s["executor"], s["tier"]) for s in record["steps"]],
                         [("implement", "pi", "heavy"), ("review", "claude", "heavy")])
        _camp, _m, workflow = self.workflow(self.out, "01-strict")
        self.assertEqual(workflow.step_by_id("implement")[3].agent.model.model, "heavy")

    def test_an_existing_campaign_folder_is_refused(self) -> None:
        code, lines = call("construct", "--bundle", self.tmp / "bundle", "--out", self.out)
        self.assertEqual(code, 2)
        self.assertTrue(lines[0].startswith("REFUSED "), lines)
        self.assertIn("exists and is not an empty folder", lines[1])


class MixedBundle(ConstructCase):

    def setUp(self) -> None:
        super().setUp()
        git_repo(self.tmp / "api")
        git_repo(self.tmp / "client", branch="trunk")
        self.code, self.lines, self.out = self.construct(self.bundle("mixed"))

    def test_two_patterns_two_repos_and_an_owned_workspace_validate(self) -> None:
        self.assertEqual(self.code, 0, self.lines)
        self.assertIn("01-rename fan-out-under-contracts: VALID 01-rename: 4 phases, "
                      "7 steps; harness executors pi:2, claude:1; 2 units on 1 path; "
                      "2 workspaces", self.lines)
        self.assertIn("02-notes relay: VALID 02-notes: 2 phases, 2 steps; harness "
                      "executors codex:1, claude-cloud:1; 2 workspaces", self.lines)
        code, lines = call("campaign", "validate", "--campaign", self.out / "campaign.py")
        self.assertEqual((code, lines[-1]), (0, "CAMPAIGN OK"), lines)

    def test_the_campaign_declares_the_owned_workspace_under_its_root(self) -> None:
        camp = oc.load_campaign(self.out / "campaign.py")
        spaces = {w.name: w for w in camp.workspaces}
        self.assertEqual(sorted(spaces), ["api", "client", "notes"])
        self.assertTrue(spaces["notes"].owned)
        self.assertEqual(spaces["notes"].path, self.out / "workspaces" / "notes")
        self.assertEqual(spaces["client"].base_branch, "trunk")
        self.assertEqual(camp.integration_branch, "campaign/find-user")
        self.assertEqual(camp.contracts, "contracts.md")

    def test_each_written_workspace_has_a_worktree_on_the_output_branch(self) -> None:
        camp, m, workflow = self.workflow(self.out, "01-rename")
        landing = [(space.name, path.name) for space, path
                   in oc.milestone_landings(camp, m, workflow)]
        self.assertEqual(landing, [("api", "api"), ("client", "client")])
        self.assertIsNotNone(workflow.contracts)
        merges = [workflow.step_by_id(f"merge-{p}")[3] for p in ("api", "client")]
        self.assertEqual([(s.worktree, s.unit) for s in merges],
                         [("api", "api"), ("client", "client")])

    def test_a_cross_workspace_command_finds_its_sibling_worktree(self) -> None:
        _camp, _m, workflow = self.workflow(self.out, "01-rename")
        check = workflow.step_by_id("check-2")[3]
        self.assertEqual(check.worktree, "client")
        self.assertIn('"$(dirname "$PWD")/api${PWD##*/client}"/src', check.command)

    def test_the_relay_crosses_from_the_owned_workspace_to_the_cloud(self) -> None:
        _camp, _m, workflow = self.workflow(self.out, "02-notes")
        notes, shim = workflow.step_by_id("notes")[3], workflow.step_by_id("shim")[3]
        self.assertEqual((notes.worktree, notes.agent.harness_executor), ("notes", "codex"))
        self.assertEqual((shim.worktree, shim.agent.harness_executor), ("api", "claude-cloud"))
        self.assertEqual(shim.consumes, ("notes",))

    def test_campaign_run_pilots_a_round_whose_workflow_has_units(self) -> None:
        camp = oc.load_campaign(self.out / "campaign.py")
        seen = []

        def fake_run(workflow, run_dir, options):
            seen.append((workflow.name, options.pilot, options.hold))
            return None

        controller = oc.CampaignController(camp, pilot=True, say=lambda _line: None)
        with mock.patch.object(oc, "run_workflow", fake_run):
            for mid in ("01-rename", "02-notes"):
                m = next(m for m in camp.milestones if m.id == mid)
                workflow = controller._load_workflow(m, 1)
                controller._run_workflow(m, workflow, self.tmp / "runs" / mid, 1)
            resumed = self.tmp / "runs" / "resumed"
            resumed.mkdir(parents=True)
            (resumed / "run-log.jsonl").write_text("", encoding="utf-8")
            controller._run_workflow(m, workflow, resumed, 2)
        self.assertEqual(seen, [("01-rename", True, True), ("02-notes", False, True),
                                ("02-notes", False, False)])


class ExpandRunsInBash(ConstructCase):

    def test_the_sibling_path_follows_a_pilot_suffix(self) -> None:
        for suffix in ("", "-pilot"):
            here = self.tmp / "trees" / f"client{suffix}"
            here.mkdir(parents=True)
            cmd = patterns.expand("echo {api}/src", "client", {"api", "client"})
            out = subprocess.run([bash_exe(), "-c", cmd], cwd=here, capture_output=True,
                                 text=True, check=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertTrue(out.stdout.strip().endswith(f"/trees/api{suffix}/src"),
                            out.stdout)


class ExecutorFromBoxAndHarness(ConstructCase):

    def test_the_table(self) -> None:
        cases = {("local", "pi", False): ("pi", None),
                 ("local", "pi", True): ("durable", "local"),
                 ("local", "claude", False): ("claude", None),
                 ("local", "codex", False): ("codex", None),
                 ("buildbox", "pi", False): ("durable", "buildbox"),
                 ("cloud", "pi", False): ("pi-cloud", None),
                 ("cloud", "claude", False): ("claude-cloud", None),
                 ("cloud", "codex", False): ("codex-cloud", None)}
        for (box, harness, durable), want in cases.items():
            self.assertEqual(ohcon.executor_for(box, harness, durable), want)

    def test_a_pair_with_no_executor_names_the_valid_pairs(self) -> None:
        for box, harness, durable in (("buildbox", "claude", False),
                                      ("buildbox", "codex", False),
                                      ("local", "codex", True)):
            with self.assertRaises(ValueError) as caught:
                ohcon.executor_for(box, harness, durable)
            self.assertIn(ohcon.VALID_PAIRS, str(caught.exception))


class PiKeyFromTheSettings(ConstructCase):

    def test_the_provider_names_the_key_variable_by_default(self) -> None:
        model = patterns.model_config("pi", "heavy")
        self.assertEqual((model.model, model.api_key_env, model.base_url),
                         ("heavy", "ZAI_API_KEY", ""))

    def test_the_operator_settings_name_the_key_and_the_endpoint(self) -> None:
        use_settings(self, {"pi": {"api_key_env": {"zai": "OPERATOR_ZAI_KEY"},
                                   "base_url": {"zai": "https://zai.example/v4"}}})
        model = patterns.model_config("pi", "light")
        self.assertEqual((model.api_key_env, model.base_url),
                         ("OPERATOR_ZAI_KEY", "https://zai.example/v4"))


class RefusedBundles(ConstructCase):

    SPEC = "milestones/01-strict/spec.md"

    def refuse(self, old: str, new: str) -> list[str]:
        bundle = self.bundle("spec-folder")
        spec = bundle / self.SPEC
        text = spec.read_text(encoding="utf-8")
        self.assertIn(old, text)
        spec.write_text(text.replace(old, new), encoding="utf-8")
        code, lines, out = self.construct(bundle)
        self.assertEqual(code, 2, lines)
        self.assertEqual(lines[0], f"REFUSED {bundle}: 1 problem", lines)
        self.assertFalse(out.exists(), "a refused bundle writes nothing")
        return lines[1:]

    def test_an_unknown_pattern(self) -> None:
        lines = self.refuse("pattern: implement-and-review", "pattern: tree")
        self.assertTrue(lines[0].startswith("- 01-strict: pattern: 'tree' is unknown; use "
                                            "one of single-agent, relay,"), lines)

    def test_a_shape_line_is_refused_and_names_pattern(self) -> None:
        lines = self.refuse("pattern: implement-and-review", "shape: implement-and-review")
        self.assertEqual(lines, ["- 01-strict: shape: is no field; name the workflow pattern "
                                 "on a pattern: line, such as pattern: implement-and-review"])

    def test_a_box_and_harness_with_no_executor(self) -> None:
        lines = self.refuse("box: local\nharness: pi\ntier: heavy\nreview harness: claude",
                            "box: buildbox\nharness: claude\ntier: heavy")
        self.assertTrue(lines[0].startswith("- 01-strict: box and harness: box 'buildbox' "
                                            "with harness claude has no executor"), lines)
        self.assertIn(ohcon.VALID_PAIRS, lines[0])

    def test_a_tier_other_than_heavy_or_light(self) -> None:
        lines = self.refuse("tier: heavy", "tier: medium")
        self.assertEqual(lines, ["- 01-strict: tier: 'medium' must be heavy or light"])

    def test_an_undeclared_workspace(self) -> None:
        lines = self.refuse("pattern: implement-and-review",
                            "pattern: implement-and-review\nworkspaces: docs")
        self.assertEqual(lines, ["- 01-strict: workspaces: names 'docs', which bundle.md "
                                 "does not declare; declared: app"])

    def test_a_missing_source_line(self) -> None:
        lines = self.refuse("source: specs/strict-mode.md\n", "")
        self.assertEqual(lines, ["- 01-strict: no source: line; name the issue URL, the "
                                 "ticket key or the file path the milestone serves"])

    def test_every_fault_is_named_at_once(self) -> None:
        bundle = self.bundle("spec-folder")
        for rel, old, new in ((self.SPEC, "tier: heavy", "tier: medium"),
                              ("milestones/02-docs/spec.md", "source: specs/strict-mode.md\n", "")):
            spec = bundle / rel
            spec.write_text(spec.read_text(encoding="utf-8").replace(old, new),
                            encoding="utf-8")
        code, lines, _out = self.construct(bundle)
        self.assertEqual((code, lines[0]), (2, f"REFUSED {bundle}: 2 problems"))
        self.assertEqual([line.split(":")[0] for line in lines[1:]],
                         ["- 01-strict", "- 02-docs"])


class ASelectionCommandKeepsTheBasePlaceholder(ConstructCase):

    COMMAND = "python ohflow/tests/run_tests.py --changed {base}"

    def test_the_gates_and_the_acceptance_check_carry_changed_base(self) -> None:
        git_repo(self.tmp / "app")
        bundle = self.bundle("spec-folder")
        spec = bundle / "milestones" / "01-strict" / "spec.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "`python -m unittest discover -s tests`", f"`{self.COMMAND}`"), encoding="utf-8")
        code, lines, out = self.construct(bundle)
        self.assertEqual(code, 0, lines)
        camp, m, workflow = self.workflow(out, "01-strict")
        self.assertEqual([c.cmd for c in m.acceptance_checks], [self.COMMAND])
        for step in ("implement", "review"):
            checks = workflow.step_by_id(step)[3].gate.checks
            gates = [c.args for c in checks if c.name == "command_exit"]
            self.assertEqual(gates, [{"cmd": self.COMMAND, "expect": 0}])
        brief = (out / "milestones" / "01-strict" / "briefs" / "implement.md").read_text(
            encoding="utf-8")
        self.assertIn("`{base}` stands for the commit your position block names", brief)

    def test_a_workspace_named_base_is_refused(self) -> None:
        bundle = self.bundle("spec-folder")
        text = (bundle / "bundle.md").read_text(encoding="utf-8")
        (bundle / "bundle.md").write_text(text.replace("## Workspace app", "## Workspace base"),
                                          encoding="utf-8")
        code, lines, _out = self.construct(bundle)
        self.assertEqual(code, 2, lines)
        self.assertTrue(any("the name is taken" in line for line in lines), lines)
