"""The claude and codex harness executors run a real child process and read it back.

Each fake executable under `tests/fakes/` runs as a real descendant and
replays a stream recorded from the real CLI on 2026-09-30 where one exists:
Claude logged out, the Codex roll call and a Codex model refusal.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ohflow import harness_executors
from ohflow.harness_executor import ERROR, FINISHED, RUNNING
from support import TempCase
from test_pi_05_runner_harness_executor import _alive

FAKES = Path(__file__).resolve().parent / "fakes"
SCHEMA = {"type": "object", "required": ["answer", "count"],
          "properties": {"answer": {"type": "string"}, "count": {"type": "integer"}}}


class SignedInHarnessExecutorCase(TempCase):
    harness_executor_name = ""
    exe_var = ""

    def setUp(self):
        super().setUp()
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.state = self.tmp / "fake-state"
        self._set_env(self.exe_var, str(FAKES / f"fake_{self.harness_executor_name}.py"))
        self._set_env("OHFLOW_FAKE_SIGNED_IN_STATE", str(self.state))
        self._set_env("OHFLOW_FAKE_SIGNED_IN_SCENARIO", "success")
        self.harness_executor = harness_executors.harness_executor_for(self.harness_executor_name)

    def _set_env(self, name: str, value: str) -> None:
        old = os.environ.get(name)
        os.environ[name] = value
        self.addCleanup(lambda: os.environ.pop(name, None) if old is None
                        else os.environ.__setitem__(name, old))

    def _spec(self, **changes) -> dict:
        spec = {"coord": f"01.only/01.{self.harness_executor_name}", "attempt": 1,
                "role": "rollcall", "harness_executor": self.harness_executor_name,
                "workspace": str(self.workspace),
                "model": {"model": "m", "base_url": "", "api_key_env": "",
                          "params": {}, "extra_body": {}},
                "tools": {"preset": "default", "only": [], "allow": []},
                "skills": [], "skills_dir": None, "mcp_config": None,
                "max_iterations": 5, "execution_timeout_s": 30, "stall_timeout_s": None,
                "write_scope": [], "fork_session": None, "brief_path": "brief.md",
                "schema_path": None, "out_dir": "."}
        spec.update(changes)
        return spec

    def _run(self, scenario: str, name: str | None = None, *, schema: dict | None = None,
             timeout: float = 20.0, **changes) -> dict:
        os.environ["OHFLOW_FAKE_SIGNED_IN_SCENARIO"] = scenario
        attempt = self.tmp / (name or scenario)
        attempt.mkdir()
        (attempt / "brief.md").write_text("Report for duty.\n", encoding="utf-8")
        if schema is not None:
            (attempt / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
            changes.setdefault("schema_path", "schema.json")
        handle = self.harness_executor.launch(self._spec(**changes), attempt)
        self.handle = handle
        deadline = time.monotonic() + timeout
        state = RUNNING
        while state == RUNNING and time.monotonic() < deadline:
            state = self.harness_executor.poll(handle)
            time.sleep(0.05)
        if state == RUNNING:
            self.harness_executor.kill(handle)
            self.fail(f"{self.harness_executor_name} runner did not finish in {timeout}s")
        self.assertEqual(state, FINISHED, (attempt / "logs").iterdir())
        return self.harness_executor.collect(handle)

    def _argv(self) -> list[str]:
        return json.loads((self.state / "argv.json").read_text(encoding="utf-8"))

    def _kill_tree(self, scenario: str = "grandchild") -> None:
        os.environ["OHFLOW_FAKE_SIGNED_IN_SCENARIO"] = scenario
        attempt = self.tmp / "tree"
        attempt.mkdir()
        (attempt / "brief.md").write_text("x\n", encoding="utf-8")
        handle = self.harness_executor.launch(self._spec(), attempt)
        pid_file = self.state / "grandchild.pid"
        deadline = time.monotonic() + 15
        # The fake creates the file, then writes the number: wait for both.
        while time.monotonic() < deadline and not (
                pid_file.exists() and pid_file.read_text(encoding="ascii").strip()):
            time.sleep(0.05)
        grandchild = int(pid_file.read_text(encoding="ascii"))
        self.assertTrue(_alive(grandchild))
        self.harness_executor.kill(handle)
        deadline = time.monotonic() + 10
        while _alive(grandchild) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(_alive(grandchild), "the harness executor left a grandchild alive")
        self.assertIn(self.harness_executor.poll(handle), (ERROR, FINISHED))


class ClaudeHarnessExecutor(SignedInHarnessExecutorCase):
    harness_executor_name = "claude"
    exe_var = "OHFLOW_CLAUDE_EXE"

    def test_success_records_the_announced_tool_policy_and_usage(self):
        self._set_env("CLAUDECODE", "1")
        self._set_env("ANTHROPIC_BASE_URL", "http://127.0.0.1:1/parent-proxy")
        result = self._run("success")
        self.assertEqual(result["execution_status"], "finished", result["error"])
        self.assertEqual(result["tools"][0], "Bash")
        self.assertEqual(result["mcp_servers"], ["forum", "cortex"])
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["llm_calls"], 2)
        self.assertEqual(result["tokens"], {"prompt_tokens": 70, "completion_tokens": 14,
                                            "cache_read_tokens": 40, "cache_write_tokens": 10,
                                            "reasoning_tokens": 3})
        self.assertEqual(result["cost"], 0.0042)
        self.assertEqual((self.tmp / "success" / "final.md").read_text(encoding="utf-8"), "DONE")
        argv = self._argv()
        for flag in ("-p", "--verbose", "bypassPermissions", "--session-id", "--model"):
            self.assertIn(flag, argv)
        self.assertIn("brief.md", argv[-1])
        self.assertEqual(result["conversation_id"], argv[argv.index("--session-id") + 1])
        # ohflow sets the shell prefix itself: every Bash command's output is
        # copied to the tool-output contract while it runs.
        self.assertEqual([k for k in json.loads((self.state / "env.json").read_text())
                          if k != "CLAUDE_CODE_SHELL_PREFIX"], [],
                         "a parent Claude session's variables reached the agent")

    def test_native_schema_output_is_the_structured_result(self):
        result = self._run("schema", schema=SCHEMA)
        self.assertEqual(result["structured"], {"answer": "ok", "count": 2})
        self.assertEqual(result["observation_errors"], 1)
        argv = self._argv()
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), SCHEMA)

    def test_a_logged_out_cli_is_an_error_with_its_own_words(self):
        result = self._run("logged-out")
        self.assertEqual(result["execution_status"], "error")
        self.assertIn("OAuth session expired", result["error"])
        self.assertEqual(self.harness_executor.preflight(), [
            "claude harness executor: the Claude CLI is not logged in; run `claude auth login`"])

    def test_iteration_cap_stops_the_agent(self):
        result = self._run("tool-loop", max_iterations=3)
        self.assertEqual(result["error"], "max iterations 3 exceeded")

    def test_stall_deadline(self):
        result = self._run("slow", stall_timeout_s=1)
        self.assertEqual(result["error"], "stall")

    def test_hermetic_flags(self):
        self._run("success", agent_profile="hermetic",
                  tools={"preset": "default", "only": ["terminal"], "allow": []},
                  mcp_config={"forum": {"command": "node"}})
        argv = self._argv()
        self.assertEqual(argv[argv.index("--tools") + 1], "Bash")
        self.assertIn("--strict-mcp-config", argv)
        mcp = json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text())
        self.assertEqual(mcp, {"mcpServers": {"forum": {"command": "node"}}})
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project,local")

    def test_recovery_after_the_runner_dies(self):
        os.environ["OHFLOW_FAKE_SIGNED_IN_SCENARIO"] = "torn-tail"
        attempt = self.tmp / "torn"
        attempt.mkdir()
        (attempt / "brief.md").write_text("x\n", encoding="utf-8")
        handle = self.harness_executor.launch(self._spec(), attempt)
        log = attempt / "logs" / "claude-events.jsonl"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and (not log.exists() or
                                                log.read_text().count("\n") < 3):
            time.sleep(0.05)
        self.harness_executor.kill(handle)
        self.assertEqual(self.harness_executor.poll(handle), ERROR)
        result = self.harness_executor.collect(handle)
        self.assertEqual(result["execution_status"], "error")
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["tools"][0], "Bash")

    def test_kill_takes_the_tree(self):
        self._kill_tree()


class CodexHarnessExecutor(SignedInHarnessExecutorCase):
    harness_executor_name = "codex"
    exe_var = "OHFLOW_CODEX_EXE"

    def setUp(self):
        super().setUp()
        home = self.tmp / "real-codex-home"
        home.mkdir()
        (home / "auth.json").write_text('{"fake": true}', encoding="utf-8")
        (home / "config.toml").write_text(
            '[mcp_servers.brave-search]\ncommand = "x"\n[mcp_servers.off]\n'
            'command = "y"\nenabled = false\n', encoding="utf-8")
        plugin = home / "plugins" / "cache" / "openai-bundled" / "unified-computer-use" / "1.0"
        plugin.mkdir(parents=True)
        (plugin / ".mcp.json").write_text(
            '{"mcpServers": {"cua_repl": {"command": "node", "enabled": true}}}',
            encoding="utf-8")
        self._set_env("CODEX_HOME", str(home))
        self.real_home = home

    def test_the_real_roll_call_stream(self):
        result = self._run("success", schema=SCHEMA, max_iterations=100)
        self.assertEqual(result["execution_status"], "finished", result["error"])
        self.assertEqual(result["conversation_id"], "01a0f387-29cd-79d1-be1e-480c6b01b49c")
        self.assertEqual(result["tokens"]["prompt_tokens"], 1103792)
        self.assertEqual(result["tokens"]["cache_read_tokens"], 1050624)
        self.assertEqual(result["tokens"]["reasoning_tokens"], 4467)
        self.assertEqual((result["cost"], result["cost_source"]), (0.0, "subscription"))
        self.assertEqual(result["tools"], [])
        self.assertEqual(result["mcp_servers"], ["brave-search", "codex_apps", "cua_repl"])
        self.assertEqual(result["structured"]["status"], "PRESENT")
        self.assertGreater(result["tool_calls"], 10)
        self.assertEqual(self._argv(), ["app-server", "--listen", "stdio://"])
        thread = self._request("thread/start")
        self.assertEqual(thread["sandbox"], "danger-full-access")
        self.assertEqual(thread["approvalPolicy"], "never")
        self.assertEqual(thread["cwd"], str(self.workspace))
        turn = self._request("turn/start")
        self.assertEqual(turn["sandboxPolicy"], {"type": "dangerFullAccess"})
        self.assertEqual(turn["outputSchema"], SCHEMA)

    def _request(self, method: str) -> dict:
        path = self.state / "requests.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            msg = json.loads(line)
            if msg.get("method") == method:
                return msg.get("params") or {}
        self.fail(f"no {method} request")

    def test_command_output_reaches_the_tool_output_contract(self):
        from ohflow.tool_output import calls, out_dir_of
        result = self._run("output")
        self.assertEqual(result["execution_status"], "finished", result["error"])
        [call] = calls(self.tmp / "output")
        self.assertEqual(call["command"], "pytest")
        body = (out_dir_of(self.tmp / "output") / call["file"]).read_text(encoding="utf-8")
        self.assertEqual(body, "line 0\nline 1\nline 2\n")

    def test_a_refused_model_is_an_error_with_its_own_words(self):
        result = self._run("refused")
        self.assertEqual(result["execution_status"], "error")
        self.assertIn("is not supported when using Codex with a ChatGPT account",
                      result["error"])

    def test_schema_and_failed_commands(self):
        result = self._run("schema", schema=SCHEMA,
                           model={"model": "gpt-5.6-luna", "base_url": "", "api_key_env": "",
                                  "params": {"reasoning_effort": "low"}, "extra_body": {}})
        self.assertEqual(result["structured"], {"answer": "ok", "count": 2})
        self.assertEqual(result["observation_errors"], 1)
        turn = self._request("turn/start")
        self.assertEqual(turn["effort"], "low")
        self.assertEqual(turn["model"], "gpt-5.6-luna")
        self.assertEqual(turn["outputSchema"], SCHEMA)

    def test_hermetic_home_links_the_real_auth_file(self):
        result = self._run("schema", schema=SCHEMA, agent_profile="hermetic",
                           mcp_config={"forum": {"command": "node", "args": ["f.js"]}})
        home = Path((self.state / "codex_home.txt").read_text(encoding="utf-8"))
        self.assertEqual(home, self.tmp / "schema" / "codex-home")
        self.assertTrue(os.path.samefile(home / "auth.json", self.real_home / "auth.json"))
        config = (home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('[mcp_servers."forum"]', config)
        self.assertIn('default_tools_approval_mode = "approve"', config)
        self.assertEqual(result["mcp_servers"], ["forum"])

    def test_iteration_cap_stops_the_agent(self):
        result = self._run("tool-loop", max_iterations=3)
        self.assertEqual(result["error"], "max iterations 3 exceeded")

    def test_kill_takes_the_tree(self):
        self._kill_tree()
