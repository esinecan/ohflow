"""The cache key sees every workflow field, or says in writing why it does not.

Each field of `Step`, `AgentSpec`, `ToolPolicy`, `ModelConfig`, `RetryPolicy`,
`GateSpec` and `CheckSpec` is in exactly one of three tables below:

- HASHED: changing it must change the fingerprint.
- EXCLUDED: changing it must leave the fingerprint alone, and the table gives
  the reason.
- NESTED: the field holds another dataclass, which has its own table.

A new field fails `test_fingerprint_fields_are_all_classified` until someone
puts it in a table. Before this test, `Step.merge_message` and
`AgentSpec.skills_dir` were hashed by neither, so editing them kept a stale
step cached.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunState
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow,
                             RetryPolicy, Step, ToolPolicy, AgentSpec,
                             WorktreeSpec, HandoverSpec)
from support import FAKE_MODEL, TempCase, git_repo

CLASSES = {cls.__name__: cls for cls in (
    Step, AgentSpec, ToolPolicy, ModelConfig, RetryPolicy, GateSpec, CheckSpec, HandoverSpec)}

#: Class name -> field -> a value that differs from the base workflow's.
HASHED = {
    "Step": {
        "id": "s2", "kind": "command", "worktree": "wt", "write_scope": ("a/**",),
        "depends_on": (), "command": "echo hi", "shell": "cmd",
        "merge_branch": "feature", "merge_message": "merge it",
        "execution_timeout_s": 60, "schema": {"type": "object"},
        "stall_timeout_s": 45, "consumes": ("dep",),
    },
    "AgentSpec": {
        "role": "other-role", "brief": "another brief", "skills": ("a-skill",),
        "skills_dir": Path("elsewhere"), "mcp_config": {"srv": {"cmd": "x"}},
        "max_iterations": 7, "harness_executor": "pi", "fork_session": "session-1",
        "command_time_cap_s": 30, "agent_profile": "hermetic", "box": "buildbox",
    },
    "ToolPolicy": {
        "preset": "minimal", "enable_browser": True, "enable_sub_agents": True,
        "only": ("bash",), "allow": ("mcp__x__y",), "block": ("x.delete",),
    },
    "ModelConfig": {
        "model": "other/model", "base_url": "http://127.0.0.1:1/other",
        "api_key_env": "OTHER_KEY", "params": {"thinking": "high"},
        "extra_body": {"a": 1},
    },
    "RetryPolicy": {"carry_context": True},
    "GateSpec": {"checks": ()},
    "CheckSpec": {"name": "other_check", "args": {"regex": "OTHER"}},
    "HandoverSpec": {"audience": "reviewer", "extra": ("Another question",), "max_chars": 3000},
}

#: Class name -> field -> (a differing value, the reason the key ignores it).
EXCLUDED = {
    "Step": {
        "pool": ("p", "reserved and unused in v1; no code reads it"),
        "note": ("a note", "board text; it never reaches the agent or the gate"),
        "objective": ("an objective", "dashboard text; editing it must keep "
                                       "every cached step cached"),
        "unit": ("u1", "the pilot's grouping label; the work is the same"),
    },
    "RetryPolicy": {
        "max": (2, "how many tries; a step that passed on try 2 stays cached"),
        "on": (("transient",), "which failures retry; the work is the same"),
    },
}

#: Class name -> fields that hold another dataclass from CLASSES.
NESTED = {
    "Step": {"gate": "GateSpec", "agent": "AgentSpec", "retry": "RetryPolicy", "handover": "HandoverSpec"},
    "AgentSpec": {"model": "ModelConfig", "tools": "ToolPolicy"},
    "GateSpec": {"checks": "CheckSpec"},
}
# GateSpec.checks is in HASHED and in NESTED: the tuple is hashed as a whole,
# and its CheckSpec items are covered by CheckSpec's own table.


class FingerprintFields(TempCase):

    def _key(self, overrides: dict[str, dict] | None = None) -> str:
        ov = overrides or {}

        def build(cls_name: str, /, **base):
            return CLASSES[cls_name](**{**base, **ov.get(cls_name, {})})

        check = build("CheckSpec", name="final_message_matches",
                      args={"regex": "DONE"})
        gate = build("GateSpec", checks=(check,))
        model = build("ModelConfig", model=FAKE_MODEL.model,
                      base_url=FAKE_MODEL.base_url,
                      api_key_env=FAKE_MODEL.api_key_env)
        tools = build("ToolPolicy")
        agent = build("AgentSpec", role="role", brief="brief", model=model,
                      tools=tools)
        retry = build("RetryPolicy")
        handover = build("HandoverSpec")
        step = build("Step", id="s1", kind="agent", depends_on=("dep",),
                     gate=gate, agent=agent, retry=retry, handover=handover)
        dep = Step(id="dep", kind="command", command="true")
        self.keys = getattr(self, "keys", 0) + 1
        repo = git_repo(self.tmp / f"repo-{self.keys}")
        workflow = Workflow(
            name="fields", repo=repo, base_branch="main", transient_backoff_s=0,
            worktrees=(WorktreeSpec("wt", self.tmp / "wt", "branch", "main"),),
            phases=(Phase(name="Prep", steps=(dep,)),
                    Phase(name="Work", steps=(step,))))
        return fingerprint(workflow, RunState(), step)

    def test_fingerprint_fields_are_all_classified(self):
        for name, cls in CLASSES.items():
            fields = {f.name for f in dataclasses.fields(cls)}
            hashed = set(HASHED.get(name, {}))
            excluded = set(EXCLUDED.get(name, {}))
            nested = set(NESTED.get(name, {}))
            self.assertFalse(hashed & excluded, f"{name}: hashed and excluded")
            unclassified = fields - hashed - excluded - nested
            self.assertEqual(unclassified, set(),
                             f"{name}: fields in no table: {sorted(unclassified)}")
            unknown = (hashed | excluded | nested) - fields
            self.assertEqual(unknown, set(),
                             f"{name}: tables name fields that do not exist")
            for field, target in NESTED.get(name, {}).items():
                self.assertIn(target, CLASSES, f"{name}.{field}")

    def test_fingerprint_fields_hashed_fields_change_the_key(self):
        base = self._key()
        for name, changes in HASHED.items():
            for field, value in changes.items():
                with self.subTest(field=f"{name}.{field}"):
                    self.assertNotEqual(self._key({name: {field: value}}), base)

    def test_fingerprint_fields_excluded_fields_keep_the_key(self):
        base = self._key()
        for name, changes in EXCLUDED.items():
            for field, (value, reason) in changes.items():
                with self.subTest(field=f"{name}.{field}"):
                    self.assertTrue(reason)
                    self.assertEqual(self._key({name: {field: value}}), base)

    def test_fingerprint_fields_merge_message_and_skills_dir_are_hashed(self):
        base = self._key()
        self.assertNotEqual(
            self._key({"Step": {"merge_message": "one"}}),
            self._key({"Step": {"merge_message": "two"}}))
        self.assertNotEqual(
            self._key({"AgentSpec": {"skills_dir": Path("one")}}),
            self._key({"AgentSpec": {"skills_dir": Path("two")}}))
        self.assertEqual(self._key({"Step": {"merge_message": None}}), base)
