"""Unset pi-only execution knobs stay out of the cache key of a default step."""

from __future__ import annotations

from ohflow.fingerprint import fingerprint, fingerprint_input
from ohflow.run_log import RunState
from support import TempCase, git_repo, simple_workflow, agent_step


class PiFingerprint(TempCase):

    def _parts(self):
        repo = git_repo(self.tmp / "repo")
        step = agent_step("s1")
        workflow = simple_workflow(repo, steps=[step])
        return workflow, step

    def test_default_fields_pin_the_version_7_cache_key(self):
        workflow, step = self._parts()
        body = fingerprint_input(workflow, RunState(), step)
        self.assertNotIn("stall_timeout_s", body)
        self.assertNotIn("retry", body)
        self.assertEqual(
            fingerprint(workflow, RunState(), step),
            "f4f48748735d94a9d45ee26a42b72debf0024fc5a0f1485998788480228312d8",
        )
