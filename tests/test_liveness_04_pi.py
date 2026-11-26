"""pi's tool events feed the tool-output contract.

The fixture is the tool-event lines of a real pi run (M0 spike S1,
2026-10-10, zai/glm-5.3-flash): a command printing a tick every 5 s, one
writing to stderr, and a silent 75 s sleep.
"""

from __future__ import annotations

import json
from pathlib import Path

from support import TempCase

from ohflow import tool_output
from ohflow.pi_runner import PiAdapter
from ohflow.tool_output import ToolOutputWriter, calls

FIXTURE = Path(__file__).parent / "fixtures" / "liveness" / "pi-tool-events.jsonl"


class PiToolOutput(TempCase):

    def replay(self, upto=None):
        w = ToolOutputWriter(self.tmp)
        adapter = PiAdapter()
        events = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
        seen = []
        for e in events[:upto]:
            seen.append(e)
            for call in adapter.on_event({}, e, seen).calls:
                w.apply(call)
        return w, events

    def test_every_call_is_recorded_with_its_full_output(self):
        _, events = self.replay()
        got = calls(self.tmp)
        ends = [e for e in events if e["type"] == "tool_execution_end"]
        self.assertEqual(len(got), len(ends))
        for c, e in zip(got, ends):
            text = "".join(p.get("text", "") for p in e["result"]["content"])
            body = (tool_output.out_dir_of(self.tmp) / c["file"]).read_text(encoding="utf-8")
            self.assertEqual(body, text)
            self.assertEqual(c["ok"], not e.get("isError"))
        self.assertIn("for i in 1 2 3 4 5 6", got[0]["command"])

    def test_output_so_far_is_visible_while_the_call_is_open(self):
        events = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
        third_tick = [i for i, e in enumerate(events)
                      if e["type"] == "tool_execution_update"][3]
        w, _ = self.replay(third_tick + 1)
        [open_call] = list(w.open.values())
        lines = tool_output.tail(tool_output.out_dir_of(self.tmp) / open_call["file"])
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(line.startswith("tick ") for line in lines))
