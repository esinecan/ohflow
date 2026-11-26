"""`rollcall_matches`: an agent's report of its tool policy against the harness record."""

from __future__ import annotations

import json

from ohflow.gates import GateContext, rollcall_matches
from support import TempCase


class RollcallGate(TempCase):

    def _ctx(self, result: dict, report) -> GateContext:
        (self.tmp / "result.json").write_text(json.dumps(result), encoding="utf-8")
        return GateContext(coord="c", repo=self.tmp, worktree=self.tmp, base_sha="x",
                           base_ref="main", attempt_dir=self.tmp, log_dir=self.tmp,
                           structured=report)

    def test_a_report_inside_the_announced_tool_policy_passes(self):
        ctx = self._ctx({"tools": ["Bash", "mcp__forum__post"], "mcp_servers": ["brave-search"]},
                        {"tools": ["Bash"], "mcp_servers": ["brave_search"]})
        self.assertTrue(rollcall_matches(ctx).passed)

    def test_an_unannounced_tool_or_server_fails(self):
        ctx = self._ctx({"tools": ["Bash"], "mcp_servers": ["forum"]},
                        {"tools": ["Bash", "WebFetch"], "mcp_servers": ["forum", "gemini"]})
        result = rollcall_matches(ctx)
        self.assertFalse(result.passed)
        self.assertIn("'WebFetch'", result.detail)
        self.assertIn("'gemini'", result.detail)

    def test_a_harness_executor_without_a_tool_list_leaves_tools_unchecked(self):
        ctx = self._ctx({"tools": [], "mcp_servers": ["forum", "codex_apps"]},
                        {"tools": ["functions.exec"], "mcp_servers": ["codex_apps"]})
        result = rollcall_matches(ctx)
        self.assertTrue(result.passed)
        self.assertEqual(result.observed["announced_tools"], "none announced; tools unchecked")

    def test_a_server_named_by_its_tool_prefix_passes(self):
        """Real 2026-09-30 R2 report: Codex named `mcp__cua_repl.js`'s server
        `mcp__cua_repl`."""
        ctx = self._ctx({"tools": [], "mcp_servers": ["cua_repl"]},
                        {"tools": [], "mcp_servers": ["mcp__cua_repl"]})
        self.assertTrue(rollcall_matches(ctx).passed)

    def test_hermetic_tool_policy_is_enforced(self):
        """A hermetic agent that reports a forum tool proves the strict MCP
        config did not hold, even when the harness announced it."""
        ctx = self._ctx({"tools": ["Bash", "mcp__forum__post"], "mcp_servers": ["forum"]},
                        {"tools": ["Bash", "mcp__forum__post"], "mcp_servers": []})
        result = rollcall_matches(ctx, tool_policy=["Bash"])
        self.assertFalse(result.passed)
        self.assertIn("outside the workflow tool policy", result.detail)

    def test_no_structured_report_fails(self):
        self.assertFalse(rollcall_matches(self._ctx({"tools": []}, None)).passed)
