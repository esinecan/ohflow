"""Pi tool policy construction is hermetic, narrow, and uses pi's built-in MCP."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

from ohflow.pi_tool_policy import (discover_mcp, prepare_pi_tool_policy,
                                   qualified_tool_name, write_pi_agent_dir)
from support import TempCase


def _spec(**changes):
    spec = {
        "model": {
            "model": "zai/glm-5.3-flash",
            "base_url": "https://api.z.ai/api/coding/paas/v4",
            "api_key_env": "OHFLOW_TEST_FAKE_KEY",
            "params": {"thinking": "high"},
            "extra_body": {},
        },
        "tools": {
            "preset": "default", "only": (), "allow": (),
        },
        "skills": [],
        "skills_dir": None,
        "mcp_config": None,
    }
    spec.update(changes)
    return spec


def _listing(tools_by_server, failed=None):
    servers = [{"name": name, "state": "connected", "tools": list(tools)}
               for name, tools in tools_by_server.items()]
    for name, error in (failed or {}).items():
        servers.append({"name": name, "state": "failed", "tools": [], "error": error})
    return {"servers": servers, "errors": []}


class PiToolPolicyTests(TempCase):

    def _fake_pi(self, listing, exit_code=0):
        script = self.tmp / f"fake-pi-{len(list(self.tmp.glob('fake-pi-*.py')))}.py"
        self.invocation = self.tmp / "invocation.json"
        script.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            f"Path({str(self.invocation)!r}).write_text(json.dumps({{"
            "'argv': sys.argv[1:], 'agent_dir': os.environ['PI_CODING_AGENT_DIR'],"
            "'config': json.loads((Path(os.environ['PI_CODING_AGENT_DIR']) / 'mcp.json')"
            ".read_text(encoding='utf-8'))}))\n"
            f"print(json.dumps({listing!r}))\n"
            f"sys.exit({exit_code})\n", encoding="utf-8")
        patch = mock.patch.dict(os.environ, {"OHFLOW_PI_EXE": str(script)})
        patch.start()
        self.addCleanup(patch.stop)

    def _discover(self, attempt, spec):
        tool_policy = prepare_pi_tool_policy(spec, attempt)
        return discover_mcp(tool_policy, dict(os.environ), attempt)

    def _config(self, tool_policy):
        return json.loads(tool_policy.mcp_config_path.read_text(encoding="utf-8"))

    def test_default_and_named_tool_rows_map_deterministically(self):
        default = prepare_pi_tool_policy(_spec(), self.tmp / "default")
        self.assertEqual(default.tools,
                         ("read", "bash", "edit", "write", "grep", "find", "ls"))

        spec = _spec(tools={
            "preset": "default",
            "only": ("terminal", "file_editor", "task_tracker", "powershell"),
            "allow": (),
        })
        narrowed = prepare_pi_tool_policy(spec, self.tmp / "narrow")
        self.assertEqual(narrowed.tools,
                         ("bash", "read", "edit", "write", "powershell"))
        self.assertEqual(narrowed.offered_tools, narrowed.tools)

    def test_skills_are_explicit_paths_and_guard_is_always_loaded(self):
        skills = self.tmp / "skills"
        (skills / "review" ).mkdir(parents=True)
        (skills / "review" / "SKILL.md").write_text("# review\n", encoding="utf-8")
        tool_policy = prepare_pi_tool_policy(
            _spec(skills=["review"], skills_dir=str(skills)), self.tmp / "attempt")
        self.assertEqual(tool_policy.skill_paths, (skills / "review",))
        self.assertEqual(tool_policy.extension_paths[0].name, "ohflow-guard.ts")
        self.assertEqual(tool_policy.builtin_extensions, ())
        self.assertIsNone(tool_policy.mcp_config_path)

    def test_mcp_config_is_attempt_local_hidden_and_names_are_qualified(self):
        attempt = self.tmp / "attempt"
        spec = _spec(
            mcp_config={
                "note-store": {"url": "http://127.0.0.1:8767/mcp"},
                "code": {"command": "node", "args": ["server.js"]},
            },
            tools={
                "preset": "default", "only": ("read",),
                "allow": ("note-store.memory_search", "code.lookup"),
                "block": ["note-store.memory_delete"],
            },
        )
        tool_policy = prepare_pi_tool_policy(spec, attempt)
        self.assertEqual(tool_policy.mcp_config_path, attempt / "pi-agent" / "mcp.json")
        self.assertEqual(tool_policy.tools, ("read",))
        self.assertEqual(tool_policy.exclude_tools, ())
        self.assertEqual(tool_policy.builtin_extensions, ("builtin:mcp",))
        self.assertEqual(tool_policy.mcp_allow,
                         ("note-store.memory_search", "code.lookup"))
        self.assertEqual(tool_policy.mcp_block, ("note-store.memory_delete",))
        self.assertEqual(self._config(tool_policy), {"mcpServers": {
            "note-store": {"url": "http://127.0.0.1:8767/mcp", "exposure": "hidden"},
            "code": {"command": "node", "args": ["server.js"], "exposure": "hidden"},
        }})

        self.assertEqual(qualified_tool_name("note-store.memory_search"),
                         "mcp__note_store__memory_search")
        self.assertEqual(
            qualified_tool_name("google-workspace.get_gmail_threads_content_batch_for.every-label"),
            "mcp__google_workspace__get_gmail_threads_content_batch__fa6d99f7")

    def test_agent_dir_pins_git_bash_and_only_writes_models_for_custom_route(self):
        old_bash = os.environ.get("OHFLOW_BASH")
        fake_bash = self.tmp / "Git" / "bin" / "bash.exe"
        fake_bash.parent.mkdir(parents=True)
        fake_bash.write_bytes(b"")
        os.environ["OHFLOW_BASH"] = str(fake_bash)
        self.addCleanup(
            lambda: os.environ.pop("OHFLOW_BASH", None) if old_bash is None
            else os.environ.__setitem__("OHFLOW_BASH", old_bash))

        built_in = write_pi_agent_dir(_spec(), self.tmp / "built-in")
        settings = json.loads((built_in / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["defaultProvider"], "zai")
        self.assertEqual(settings["defaultModel"], "glm-5.3-flash")
        self.assertEqual(settings["defaultThinkingLevel"], "high")
        self.assertEqual(settings["shellPath"], str(fake_bash).replace("\\", "/"))
        self.assertFalse((built_in / "models.json").exists())
        self.assertFalse(settings["retry"]["enabled"])
        self.assertEqual(settings["retry"]["provider"]["maxRetries"], 0)

        custom_spec = _spec(model={**_spec()["model"],
                                  "base_url": "http://127.0.0.1:9876/v1"})
        custom = write_pi_agent_dir(custom_spec, self.tmp / "custom")
        models = json.loads((custom / "models.json").read_text(encoding="utf-8"))
        provider = models["providers"]["zai"]
        self.assertEqual(provider["baseUrl"], "http://127.0.0.1:9876/v1")
        self.assertEqual(provider["apiKey"], "$OHFLOW_TEST_FAKE_KEY")
        model = provider["models"][0]
        self.assertNotIn("contextWindow", model)
        self.assertNotIn("maxTokens", model)
        self.assertNotIn("cost", model)
        marker = json.loads((custom / "ohflow-model.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["cost_source"], "unpriced")
        self.assertNotIn("not-a-key", (custom / "models.json").read_text(encoding="utf-8"))

    def test_discovery_gives_only_the_allowed_tool_direct_exposure(self):
        attempt = self.tmp / "attempt"
        self._fake_pi(_listing({"note-store": ["memory_search", "memory_delete"]}))
        tool_policy = self._discover(attempt, _spec(
            mcp_config={"note-store": {"command": sys.executable,
                                         "args": ["unused.py"]}},
            tools={"preset": "default", "only": ("read",),
                   "allow": ("note-store.memory_search",)}))
        self.assertEqual(tool_policy.tools, ("read", "mcp__note_store__memory_search"))
        self.assertEqual(tool_policy.offered_tools, tool_policy.tools)
        self.assertEqual(tool_policy.exclude_tools, ("mcp__note_store__memory_delete",))
        server = self._config(tool_policy)["mcpServers"]["note-store"]
        self.assertEqual(server["exposure"], "hidden")
        self.assertEqual(server["toolExposure"], {"memory_search": "direct"})
        self.assertNotIn("enabled", server)
        seen = json.loads(self.invocation.read_text(encoding="utf-8"))
        self.assertEqual(seen["argv"], ["mcp", "list", "--json"])
        self.assertEqual(Path(seen["agent_dir"]), attempt / "pi-agent")
        self.assertEqual(seen["config"]["mcpServers"]["note-store"]["exposure"], "hidden")
        self.assertTrue((attempt / "logs" / "mcp-list.json").is_file())

    def test_default_mcp_tool_policy_exposes_every_listed_tool(self):
        attempt = self.tmp / "default-mcp"
        self._fake_pi(_listing({"note-store": ["memory_search", "memory_delete"]}))
        selected = self._discover(attempt, _spec(
            mcp_config={"note-store": {"command": "unused"}}))
        self.assertEqual(selected.offered_tools[-2:],
                         ("mcp__note_store__memory_search",
                          "mcp__note_store__memory_delete"))
        self.assertEqual(selected.exclude_tools, ())
        self.assertEqual(self._config(selected)["mcpServers"]["note-store"]["toolExposure"],
                         {"memory_search": "direct", "memory_delete": "direct"})

    def test_discovery_expands_block_globs_and_refuses_canonical_collisions(self):
        self._fake_pi(_listing({
            "note-store": ["memory_search", "memory_delete", "other_delete"],
            "forum": ["post"]}))
        selected = self._discover(self.tmp / "glob", _spec(
            mcp_config={"note-store": {"command": "unused"},
                        "forum": {"url": "http://127.0.0.1:8765/mcp"}},
            tools={"preset": "default", "only": ("read",), "allow": (),
                   "block": ["note-store.*_delete", "forum.*"]}))
        self.assertEqual(selected.offered_tools,
                         ("read", "mcp__note_store__memory_search"))
        self.assertEqual(set(selected.exclude_tools), {
            "mcp__note_store__memory_delete", "mcp__note_store__other_delete",
            "mcp__forum__post"})
        servers = self._config(selected)["mcpServers"]
        self.assertEqual(servers["note-store"]["toolExposure"], {"memory_search": "direct"})
        self.assertEqual(servers["forum"]["toolExposure"], {})
        self.assertIs(servers["forum"]["enabled"], False)

        self._fake_pi(_listing({"code": ["get-item", "get_item"]}))
        with self.assertRaisesRegex(ValueError, "collision"):
            self._discover(self.tmp / "collision", _spec(
                mcp_config={"code": {"command": "unused"}},
                tools={"preset": "default", "only": ("read",), "allow": ("**",)}))

    def test_discovery_refuses_a_server_that_did_not_connect(self):
        self._fake_pi(_listing({"note-store": ["memory_search"]},
                               failed={"code": "MCP connection closed\nstack"}),
                      exit_code=1)
        with self.assertRaises(RuntimeError) as raised:
            self._discover(self.tmp / "failed", _spec(
                mcp_config={"note-store": {"command": "unused"},
                            "code": {"command": "unused"}}))
        self.assertIn("server 'code' is failed: MCP connection closed", str(raised.exception))
        self.assertNotIn("stack", str(raised.exception))


if __name__ == "__main__":
    import unittest
    unittest.main()
