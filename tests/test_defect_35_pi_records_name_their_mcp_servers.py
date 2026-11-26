"""Defect 35: pi records named no MCP servers.

What went wrong. The signed-in harness executors write `mcp_servers` into `result.json`, and
`rollcall_matches` reads that list as the set of servers the harness announced.
A pi record carried an empty list, so an agent that reported the one server it
really had failed with "MCP servers the harness did not announce".

What is asserted here. A pi record built from a two-server `mcp_config` names
both servers. `rollcall_matches` passes over a pi record when the agent reports
one configured server.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from ohflow import attempt_record, pi_runner
from ohflow.cli_harness_executor import CliRunOutcome
from ohflow.gates import GateContext, rollcall_matches
from ohflow.pi_runner import PiAdapter
from ohflow.workflow import ModelConfig, ToolPolicy, AgentSpec
from ohflow.harness_executor import spec_json
from support import TempCase, fake_pi_executable

MODEL = ModelConfig("zai/glm-5.3-flash", "https://example.invalid/v1", "TEST_KEY")
SERVERS = {"forum": {"url": "http://127.0.0.1:8765/mcp"},
           "note-store": {"url": "http://127.0.0.1:8767/mcp"}}


class PiRecordsNameTheirMcpServers(TempCase):

    def _pi_record(self) -> tuple[Path, dict]:
        out = self.tmp / "pi-attempt"
        out.mkdir()
        agent = AgentSpec(role="rollcall", brief="no provider is started",
                          model=MODEL, tools=ToolPolicy(only=("bash",)),
                          harness_executor="pi", mcp_config=SERVERS)
        spec = spec_json(agent, coord="01.p/01.pi", workspace=self.tmp,
                         out_dir=out, execution_timeout_s=5400, attempt=1)
        (out / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        # A fake pi: the suite runs from a fresh clone, with no pi installed.
        patch = mock.patch.dict(os.environ, {
            "TEST_KEY": "test",
            "OHFLOW_PI_EXE": str(fake_pi_executable(self.tmp))})
        patch.start()
        self.addCleanup(patch.stop)
        old_version = pi_runner.version_of
        pi_runner.version_of = lambda argv: "provider-free-test"
        self.addCleanup(setattr, pi_runner, "version_of", old_version)
        adapter = PiAdapter()
        with mock.patch("ohflow.pi_tool_policy.discover_mcp",
                        lambda tool_policy, env, out_dir: tool_policy):
            prepared = adapter.prepare(spec, out)
        outcome = CliRunOutcome(
            spec=spec, out_dir=out, prepared=prepared, events=(),
            returncode=0, started_at=1.0, finished_at=2.0, stop_error=None)
        result, final = adapter.build_result(outcome)
        attempt_record.write(out, result, final)
        return out, json.loads((out / "result.json").read_text(encoding="utf-8"))

    def test_a_pi_record_names_both_configured_servers(self):
        _, record = self._pi_record()
        self.assertEqual(record["mcp_servers"], ["forum", "note-store"])

    def test_rollcall_matches_passes_over_a_pi_record_with_one_reported_server(self):
        out, record = self._pi_record()
        ctx = GateContext(coord="01.p/01.pi", repo=self.tmp, worktree=self.tmp,
                          base_sha="x", base_ref="main", attempt_dir=out, log_dir=out,
                          structured={"tools": [], "mcp_servers": ["forum"]})
        result = rollcall_matches(ctx)
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(result.observed["announced_servers"], 2)
