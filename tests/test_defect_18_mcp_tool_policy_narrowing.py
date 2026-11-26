"""D-18: ohflow's own allow and block lists narrow MCP tools."""

import importlib
from dataclasses import replace

from ohflow.fingerprint import fingerprint, fingerprint_input
from ohflow.harness_executor import spec_json
from ohflow.pi_tool_policy import prepare_pi_tool_policy
from ohflow.run_log import RunState
from ohflow.workflow import WorkflowError, ToolPolicy, validate
from ohflow.workflow import mcp_matches_glob
from support import TempCase, simple_workflow, agent_step


MCP = {
    "note-store": {"url": "http://127.0.0.1:8767/mcp",
                     "transport": "http"},
    "forum": {"command": "node", "args": ["forum.js"]},
}


class McpToolPolicyNarrowing(TempCase):

    def _workflow(self, tool_policy):
        step = agent_step("s")
        agent = replace(step.agent, tools=tool_policy, mcp_config=MCP)
        return simple_workflow(self.tmp / "repo",
                               steps=[replace(step, agent=agent)])

    def test_ohflow_has_no_mcp_cli_module_and_no_profile_field(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("ohflow.mcp_cli")
        with self.assertRaises(TypeError):
            ToolPolicy(mcp_blocklist_profile="child")

    def test_own_lists_reach_the_spec(self):
        tool_policy = ToolPolicy(allow=("note-store.memory_search",),
                                 block=("forum.*",))
        validate(self._workflow(tool_policy))
        step = self._workflow(tool_policy).phases[0].steps[0]
        spec = spec_json(step.agent, coord="01.phase/01.step", workspace=self.tmp, out_dir=self.tmp)
        self.assertEqual(spec["tools"]["block"], ["forum.*"])
        self.assertEqual(spec["tools"]["allow"], ["note-store.memory_search"])
        self.assertNotIn("mcp_blocklist_profile", spec["tools"])

    def test_a_block_entry_must_be_a_server_tool_glob(self):
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(ToolPolicy(block=("post",))))
        self.assertIn("tools.block entry 'post' must be a server.tool glob",
                      str(caught.exception))

    def test_own_block_reaches_pi(self):
        spec = {"tools": {"block": ["forum.*", "note-store.memory_delete", "forum.*"]}}
        policy = prepare_pi_tool_policy(spec, self.tmp / "attempt")
        self.assertEqual(policy.mcp_block, ("forum.*", "note-store.memory_delete"))

    def test_block_is_part_of_the_cache_key_only_when_set(self):
        plain = self._workflow(ToolPolicy(allow=("forum.*",)))
        blocked = self._workflow(ToolPolicy(allow=("forum.*",), block=("forum.post",)))
        plain_body = fingerprint_input(plain, RunState(), plain.phases[0].steps[0])
        self.assertNotIn("block", plain_body["agent"]["mcp_tool_policy"])
        self.assertNotEqual(fingerprint(plain, RunState(), plain.phases[0].steps[0]),
                            fingerprint(blocked, RunState(), blocked.phases[0].steps[0]))

    def test_the_cache_key_keeps_its_shape_for_allow_and_block(self):
        workflow = self._workflow(ToolPolicy(allow=("forum.*",), block=("forum.post",)))
        body = fingerprint_input(workflow, RunState(), workflow.phases[0].steps[0])
        self.assertEqual(body["agent"]["mcp_tool_policy"],
                         {"allow": ["forum.*"], "mcp_blocklist_profile": None,
                          "block": ["forum.post"]})
        self.assertNotIn("resolved_mcp_blocklist_profile", body["agent"])

    def test_mcp_globs_keep_single_star_inside_one_segment(self):
        self.assertTrue(mcp_matches_glob("forum.*", "forum.post"))
        self.assertFalse(mcp_matches_glob("forum.*", "forum.admin.delete"))
        self.assertTrue(mcp_matches_glob("forum.**", "forum.admin.delete"))
        self.assertTrue(mcp_matches_glob("note-?????.memory_*",
                                        "note-store.memory_search"))
