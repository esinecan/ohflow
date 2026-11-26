"""CONTEXT.md is the one source of the glossary definitions, and the check notices drift.

Asserted here, on temporary copies of the documents:

- An edited map definition or glossary row fails the check, and `--write` restores it.
- A map node that is not a CONTEXT.md term fails the check.
- A node or edge that cites a function its file does not define fails the check.
- A changed public vocabulary surface fails the check until it is accepted.
- Each of these is part of that surface, so a change in one of them fails the
  check and names it: a CLI flag, a key of `ohflow.settings.json` (an empty
  object included), a key of `worker/pi-cloud.settings.json`, an executor
  capability, a `cost_source` value and a cloud end error.
- A surface entry that no CONTEXT.md backtick span names, alone or after a
  qualifier, fails the check and names both ways out, until a definition names
  it or `docs/vocabulary-unnamed.json` lists it with a reason; a listed entry
  that CONTEXT.md names, or that the surface lacks, fails too.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "docs"))

from support import TempCase  # noqa: E402

import glossary_sync as gs  # noqa: E402


class GlossarySync(TempCase):

    def setUp(self) -> None:
        super().setUp()
        for name in ("CONTEXT", "GLOSSARY", "MAP", "SURFACE", "UNNAMED"):
            src = getattr(gs, name)
            dst = self.tmp / src.name
            shutil.copyfile(src, dst)
            patcher = mock.patch.object(gs, name, dst)
            patcher.start()
            self.addCleanup(patcher.stop)

    def edit(self, path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_an_edited_map_definition_fails_and_write_restores_it(self):
        self.edit(gs.MAP, "One numbered try at executing a step.", "One recorded start of a step.")
        self.assertTrue(any("glossary-map.html" in e for e in gs.run(write=False)))
        gs.run(write=True)
        self.assertEqual(gs.run(write=False), [])

    def test_an_edited_glossary_row_fails(self):
        self.edit(gs.GLOSSARY, "One numbered try at executing a step.", "One recorded start of a step.")
        self.assertTrue(any("glossary.md" in e for e in gs.run(write=False)))

    def test_a_map_node_without_a_context_term_fails(self):
        self.edit(gs.MAP, '"name": "Attempt"', '"name": "Step attempt"')
        self.assertTrue(any("'Step attempt' is not a CONTEXT.md term" in e for e in gs.run(write=False)))

    def test_a_cited_function_that_does_not_exist_fails(self):
        self.edit(gs.MAP, "engine.py:Engine._auto_resumable", "engine.py:Engine._prepare_attempt")
        self.assertTrue(any("_prepare_attempt" in e for e in gs.run(write=False)))

    def test_a_wrong_owner_of_an_existing_method_fails(self):
        data = {"nodes": [{"name": "probe", "code": "engine.py:MissingOwner._run_phase"}], "edges": []}
        self.assertTrue(gs.anchor_errors(data))

    def test_imports_and_comments_are_not_local_definitions(self):
        code = self.tmp / "code"
        code.mkdir()
        (code / "probe.py").write_text("from elsewhere import borrowed\n# ghost is mentioned only here\n", encoding="utf-8")
        with mock.patch.object(gs, "CODE", code):
            for symbol in ("borrowed", "ghost"):
                with self.subTest(symbol=symbol):
                    data = {"nodes": [{"name": "probe", "code": f"probe.py:{symbol}"}], "edges": []}
                    self.assertTrue(gs.anchor_errors(data))

    def test_instance_fields_and_inherited_members_are_valid(self):
        code = self.tmp / "code"
        code.mkdir()
        (code / "probe.py").write_text(
            "class Base:\n    field: str\n    def method(self):\n        self.assigned = 1\n"
            "class Child(Base):\n    pass\n", encoding="utf-8")
        with mock.patch.object(gs, "CODE", code):
            data = {"nodes": [{"name": name, "code": f"probe.py:Child.{name}"}
                              for name in ("field", "method", "assigned")], "edges": []}
            self.assertEqual(gs.anchor_errors(data), [])

    def test_a_held_state_change_through_expanded_keywords_requires_review(self):
        self.assertIn("held", gs.surface()["campaign states"])
        code = self.tmp / "code"
        package = code / "ohflow"
        package.mkdir(parents=True)
        for name in ("campaign.py", "cli.py"):
            shutil.copyfile(gs.CODE / "ohflow" / name, package / name)
        self.edit(package / "campaign.py", '"state": "held"', '"state": "awaiting_release"')
        with mock.patch.object(gs, "CODE", code):
            self.assertTrue(any("campaign states" in e for e in gs.surface_errors()))

    def test_a_changed_vocabulary_surface_fails_until_accepted(self):
        recorded = json.loads(gs.SURFACE.read_text(encoding="utf-8"))
        recorded["attempts.EXCLUSION_THRESHOLD"] = [3]
        gs.SURFACE.write_text(json.dumps(recorded), encoding="utf-8")
        errors = gs.run(write=False)
        self.assertTrue(any("attempts.EXCLUSION_THRESHOLD" in e for e in errors))
        gs.SURFACE.write_text(json.dumps(gs.surface()), encoding="utf-8")
        self.assertEqual(gs.run(write=False), [])

    def changed_parts(self) -> list[str]:
        """The surface parts that differ from the recorded ones, and proof
        that the check reports each of them."""
        recorded = json.loads(gs.SURFACE.read_text(encoding="utf-8"))
        current = gs.surface()
        changed = sorted(k for k in current.keys() | recorded.keys()
                         if current.get(k) != recorded.get(k))
        errors = gs.surface_errors()
        for part in changed:
            self.assertTrue(any(part in e for e in errors), (part, errors))
        return changed

    def code_copy(self) -> Path:
        """A copy of the whole package, so an edit to one file is the only change."""
        code = self.tmp / "code"
        shutil.copytree(gs.CODE / "ohflow", code / "ohflow",
                        ignore=shutil.ignore_patterns("__pycache__"))
        patcher = mock.patch.object(gs, "CODE", code)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(self.changed_parts(), [])
        return code / "ohflow"

    def test_a_new_cli_flag_requires_review(self):
        from ohflow import cli
        build = cli.build_parser

        def with_a_new_flag():
            parser = build()
            verbs = next(a for a in parser._actions
                         if isinstance(a, argparse._SubParsersAction))
            verbs.choices["status"].add_argument("--brief", action="store_true")
            return parser

        self.assertIn("--run", gs.surface()["cli flags: status"])
        self.assertIn("--milestone", gs.surface()["cli flags: campaign grant"])
        with mock.patch.object(cli, "build_parser", with_a_new_flag):
            self.assertEqual(self.changed_parts(), ["cli flags: status"])

    def test_a_new_settings_key_requires_review(self):
        self.assertIn("durable.box", gs.surface()["settings keys"])
        settings = self.tmp / "ohflow.settings.json"
        data = json.loads(gs.SETTINGS.read_text(encoding="utf-8"))
        data["durable"]["port"] = None
        settings.write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(gs, "SETTINGS", settings):
            self.assertEqual(self.changed_parts(), ["settings keys"])
            self.assertIn("durable.port", gs.surface()["settings keys"])

    def test_a_renamed_executor_capability_requires_review(self):
        from ohflow import harness_executors
        self.assertIn("signed_in", gs.surface()["executor capabilities"])
        with mock.patch.object(harness_executors, "CAP_SIGNED_IN", "logged_in"):
            self.assertEqual(self.changed_parts(), ["executor capabilities"])

    def test_a_new_cost_source_requires_review(self):
        self.assertEqual(gs.surface()["cost sources"],
                         ["claude-cli", "durable-host", "pi-catalog", "pi-cloud-worker",
                          "subscription", "unpriced"])
        package = self.code_copy()
        self.edit(package / "codex_runner.py", '"cost_source": "subscription"',
                  '"cost_source": "flat-rate"')
        self.assertEqual(self.changed_parts(), ["cost sources"])
        self.assertIn("flat-rate", gs.surface()["cost sources"])

    def test_a_renamed_cloud_end_error_requires_review(self):
        self.assertEqual(gs.surface()["cloud end errors"],
                         ["clone_failed", "fetch_back", "host_lost", "push_failed",
                          "skills_failed", "unanswered"])
        package = self.code_copy()
        self.edit(package / "pi_cloud_runner.py", 'f"push_failed: ', 'f"push_refused: ')
        self.assertEqual(self.changed_parts(), ["cloud end errors"])

    def test_an_empty_settings_object_is_a_key_of_its_own(self):
        self.assertEqual(gs.settings_keys({"a": {}, "b": {"c": None}}), ["a", "b.c"])
        keys = gs.surface()["settings keys"]
        self.assertIn("pi.api_key_env", keys)
        self.assertIn("pi.base_url", keys)

    def test_a_new_worker_settings_key_requires_review(self):
        self.assertIn("snapshot.skills", gs.surface()["worker settings keys"])
        settings = self.tmp / "pi-cloud.settings.json"
        data = json.loads(gs.WORKER_SETTINGS.read_text(encoding="utf-8"))
        data["region"] = None
        settings.write_text(json.dumps(data), encoding="utf-8")
        with mock.patch.object(gs, "WORKER_SETTINGS", settings):
            self.assertEqual(self.changed_parts(), ["worker settings keys"])

    def test_a_name_counts_alone_or_after_a_qualifier(self):
        spans = "\n".join(["AgentSpec.max_iterations", "run --hold", "notes.md",
                           "run-log.jsonl", "max_iterations_enforced_by"])
        for name, named in (("max_iterations", True), ("--hold", True), ("run", True),
                            ("notes", False), ("max_iterations_enforced_by", True),
                            ("hold", False), ("max", False)):
            with self.subTest(name=name):
                self.assertIs(gs.named_in_context(name, spans), named)
        self.assertEqual(gs.surface_entries({"attempts.EXCLUSION_THRESHOLD": [2]}),
                         [("attempts.EXCLUSION_THRESHOLD", "EXCLUSION_THRESHOLD")])

    def test_an_unnamed_surface_entry_fails_until_it_is_listed_with_a_reason(self):
        self.assertEqual(gs.unnamed_errors(), [])
        listed = json.loads(gs.UNNAMED.read_text(encoding="utf-8"))
        del listed["workflow.Step"]["pool"]
        gs.UNNAMED.write_text(json.dumps(listed), encoding="utf-8")
        errors = gs.unnamed_errors()
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("surface entry workflow.Step: pool has no CONTEXT.md name", errors[0])
        self.assertIn("add `pool` to a definition in CONTEXT.md", errors[0])
        self.assertIn('list it under "workflow.Step" in docs/vocabulary-unnamed.json', errors[0])
        listed["workflow.Step"]["pool"] = " "
        gs.UNNAMED.write_text(json.dumps(listed), encoding="utf-8")
        self.assertEqual(len(gs.unnamed_errors()), 1)
        listed["workflow.Step"]["pool"] = "reserved and unused"
        gs.UNNAMED.write_text(json.dumps(listed), encoding="utf-8")
        self.assertEqual(gs.unnamed_errors(), [])

    def test_a_listed_entry_that_is_named_or_gone_fails(self):
        self.edit(gs.CONTEXT, "a named piece of work within a workflow phase",
                  "a named piece of work within a workflow phase (`Step.pool` is reserved)")
        listed = json.loads(gs.UNNAMED.read_text(encoding="utf-8"))
        listed["workflow.Step"]["queue"] = "no such field"
        gs.UNNAMED.write_text(json.dumps(listed), encoding="utf-8")
        self.assertEqual(sorted(gs.unnamed_errors()), [
            "vocabulary-unnamed.json lists workflow.Step: pool, which CONTEXT.md names: "
            "remove it from the list",
            "vocabulary-unnamed.json lists workflow.Step: queue, which the recorded surface "
            "does not hold: remove it from the list"])
