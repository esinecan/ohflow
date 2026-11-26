"""Defect 45: a hermetic claude agent still loaded the user's CLAUDE.md.

The first full roll-call matrix ran `single:claude:1:agent_profile=hermetic`. The
agent answered from the user's `~/.claude/CLAUDE.md`, so the profile did not
isolate it. `--setting-sources project,local` drops the user's settings but
does not govern instruction files. `--safe-mode` drops them but also drops the
`--mcp-config` servers, and `--bare` needs an API key, so neither can serve.
`CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` removes the instruction files, keeps the
`--mcp-config` servers and keeps the OAuth login.

The profile is hermetic when the prepared process sets that variable and keeps
the setting-source flag. A usual-setup agent sets neither.
"""

from __future__ import annotations

import os
from pathlib import Path

from ohflow.claude_runner import ClaudeAdapter
from support import TempCase

FAKE = Path(__file__).resolve().parent / "fakes" / "fake_claude.py"
DISABLE = "CLAUDE_CODE_DISABLE_CLAUDE_MDS"


class HermeticClaudeInstructionFiles(TempCase):
    def setUp(self):
        super().setUp()
        old = os.environ.get("OHFLOW_CLAUDE_EXE")
        os.environ["OHFLOW_CLAUDE_EXE"] = str(FAKE)
        self.addCleanup(lambda: os.environ.pop("OHFLOW_CLAUDE_EXE", None) if old is None
                        else os.environ.__setitem__("OHFLOW_CLAUDE_EXE", old))
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.out = self.tmp / "attempt"
        self.out.mkdir()
        (self.out / "brief.md").write_text("x\n", encoding="utf-8")

    def _prepared(self, **changes):
        spec = {"workspace": str(self.workspace), "model": {"model": "m"},
                "tools": {"only": ["terminal"]}, "mcp_config": {}}
        spec.update(changes)
        return ClaudeAdapter().prepare(spec, self.out)

    def test_hermetic_profile_disables_the_instruction_files(self):
        prepared = self._prepared(agent_profile="hermetic")
        self.assertEqual(prepared.env.get(DISABLE), "1")

    def test_hermetic_profile_keeps_the_setting_source_flag(self):
        argv = list(self._prepared(agent_profile="hermetic").argv)
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project,local")

    def test_the_usual_setup_keeps_the_instruction_files(self):
        prepared = self._prepared()
        self.assertNotIn(DISABLE, prepared.env)
        self.assertNotIn("--setting-sources", prepared.argv)
