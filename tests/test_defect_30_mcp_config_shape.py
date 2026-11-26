"""D-30: workflows reject wrapped MCP config."""

from dataclasses import replace

from ohflow.workflow import WorkflowError, validate
from support import TempCase, simple_workflow, agent_step


class McpConfigShapeIsChecked(TempCase):

    def _workflow(self, config):
        step = agent_step("s")
        agent = replace(step.agent, mcp_config=config)
        return simple_workflow(self.tmp / "repo",
                               steps=[replace(step, agent=agent)])

    def test_mcp_servers_wrapper_is_refused(self):
        wrong = {"mcpServers": {"note-store": {
            "url": "http://127.0.0.1:8767/mcp"}}}
        with self.assertRaises(WorkflowError) as caught:
            validate(self._workflow(wrong))
        self.assertIn("flat {name: server}", str(caught.exception))

    def test_each_server_needs_command_or_url(self):
        with self.assertRaises(WorkflowError):
            validate(self._workflow({"note-store": {"transport": "http"}}))
