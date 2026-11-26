"""Defect 44: an agent inherited the variables of the session that launched ohflow.

What went wrong. Only the signed-in harness runners removed `CLAUDE*`,
`CLAUDECODE` and `ANTHROPIC_BASE_URL` from the environment they pass on. The
pi harness executor passed all of them. In the first live full roll call, run
from a Claude desktop session, an agent reported itself as "Claude Code" and
listed Claude Code's tools.

What is asserted here. For each CLI harness executor, the environment of the
agent process holds none of those variables when the launching process has
them. A variable a harness executor sets itself on purpose survives. The runner process
that `CliHarnessExecutor` starts is checked at its launch seam
(`spawn_managed`). The CLI process that the claude, codex and pi
adapters start is checked at `prepare`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest import mock

from ohflow import harness_executors, proc
from ohflow.claude_runner import ClaudeAdapter
from ohflow.codex_runner import CodexAdapter
from ohflow.pi_runner import PiAdapter
from ohflow.workflow import ModelConfig, ToolPolicy, AgentSpec
from ohflow.harness_executor import spec_json
from support import TempCase, fake_pi_executable

FAKES = Path(__file__).resolve().parent / "fakes"
PARENT = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
          "CLAUDE_AGENT_SDK_VERSION": "0.3.284",
          "ANTHROPIC_BASE_URL": "http://127.0.0.1:1/parent-proxy"}
LEAK = re.compile(r"^(CLAUDE|ANTHROPIC_BASE_URL$)")
MODEL = ModelConfig("zai/glm-5.3-flash", "https://example.invalid/v1", "TEST_KEY")


class _Captured(Exception):
    def __init__(self, env):
        self.env = env


def _capture_launch(argv, **kwargs):
    raise _Captured(dict(kwargs["env"]))


class ParentSessionVarsReachNoAgent(TempCase):

    def setUp(self):
        super().setUp()
        patch = mock.patch.dict(os.environ, {**PARENT, "TEST_KEY": "test",
                                             "OHFLOW_CLAUDE_EXE": str(FAKES / "fake_claude.py"),
                                             "OHFLOW_CODEX_EXE": str(FAKES / "fake_codex.py")})
        patch.start()
        self.addCleanup(patch.stop)

    def _leaked(self, env) -> list[str]:
        # ohflow sets CLAUDE_CODE_SHELL_PREFIX itself (tool-output capture);
        # it is the runner's own value, never a parent session's.
        return sorted(k for k in env if LEAK.match(k)
                      and k != "CLAUDE_CODE_SHELL_PREFIX")

    def _spec(self, harness_executor: str, **changes) -> dict:
        out = self.tmp / f"attempt-{harness_executor}"
        out.mkdir(exist_ok=True)
        (out / "brief.md").write_text("Report for duty.\n", encoding="utf-8")
        agent = AgentSpec(role="rollcall", brief="x", model=MODEL,
                          tools=ToolPolicy(only=("bash",)) if harness_executor == "pi"
                          else ToolPolicy(), harness_executor=harness_executor, **changes)
        workspace = self.tmp / "workspace"
        workspace.mkdir(exist_ok=True)
        spec = spec_json(agent, coord=f"01.p/01.{harness_executor}", workspace=workspace,
                         out_dir=out, execution_timeout_s=60, attempt=1)
        (out / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        return spec

    def _launch_env(self, harness_executor_name: str) -> dict:
        spec = self._spec(harness_executor_name)
        harness_executor = harness_executors.harness_executor_for(harness_executor_name)
        with mock.patch("ohflow.cli_harness_executor.spawn_managed", _capture_launch):
            try:
                harness_executor.launch(spec, self.tmp / f"attempt-{harness_executor_name}")
            except _Captured as seen:
                return seen.env
        self.fail(f"{harness_executor_name} harness executor did not reach spawn_managed")

    def test_parent_session_vars_do_not_reach_the_claude_runner_or_its_cli(self):
        self.assertEqual(self._leaked(self._launch_env("claude")), [])
        env = ClaudeAdapter().prepare(self._spec("claude"),
                                      self.tmp / "attempt-claude").env
        self.assertEqual(self._leaked(env), [])

    def test_parent_session_vars_do_not_reach_the_codex_runner_or_its_cli(self):
        self.assertEqual(self._leaked(self._launch_env("codex")), [])
        env = CodexAdapter().prepare(self._spec("codex"),
                                     self.tmp / "attempt-codex").env
        self.assertEqual(self._leaked(env), [])

    def test_parent_session_vars_do_not_reach_the_pi_runner_or_its_cli(self):
        # A fake pi: the suite runs from a fresh clone, with no pi installed.
        patch = mock.patch.dict(os.environ, {
            "OHFLOW_PI_EXE": str(fake_pi_executable(self.tmp))})
        patch.start()
        self.addCleanup(patch.stop)
        self.assertEqual(self._leaked(self._launch_env("pi")), [])
        out = self.tmp / "attempt-pi"
        spec = self._spec("pi")
        with mock.patch("ohflow.pi_tool_policy.discover_mcp",
                        lambda tool_policy, env, out_dir: tool_policy):
            env = PiAdapter().prepare(spec, out).env
        self.assertEqual(self._leaked(env), [])

    def test_parent_session_vars_are_the_only_names_the_rule_removes(self):
        env = proc.agent_env({**PARENT, "PATH": "p", "CLAUDE_X": "1",
                              "ZAI_CODING_CN_API_KEY": "k", "CODEX_HOME": "c"})
        self.assertEqual(env, {"PATH": "p", "ZAI_CODING_CN_API_KEY": "k",
                               "CODEX_HOME": "c"})
