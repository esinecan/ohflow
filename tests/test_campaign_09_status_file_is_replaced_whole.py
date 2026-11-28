"""A reader of `campaign-status.json` reads a whole record, never a half-written one.

Before: the controller rewrote the file in place, so a reader that came in
between the truncation and the write got empty or cut JSON. A campaign hold
test failed on it in CI on 27.11.2026.

Now: the controller writes the record to a file beside it and swaps it in, so
a reader sees the old record or the new one. On Windows the swap waits while a
reader holds the file open, and a reader that opens the file during the swap
is refused for a moment, so `campaign.read_status` waits that moment out.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

from ohflow import campaign as oc  # noqa: E402
from test_campaign_01_loop import CampaignCase  # noqa: E402

PADDING = "x" * 200_000


class TheStatusFileIsReplacedWhole(CampaignCase):

    def controller(self) -> oc.CampaignController:
        return oc.CampaignController(self.campaign(), no_dashboard=True,
                                     say=lambda _m: None)

    def test_a_reader_that_opened_the_file_before_a_write_reads_the_old_record(self):
        controller = self.controller()
        controller._status(state="running", round=1, problems=[PADDING])
        path = self.root / oc.STATUS
        old = path.read_bytes()
        errors: list[BaseException] = []

        def write() -> None:
            try:
                controller._status(state="held", round=2, problems=[PADDING])
            except BaseException as exc:
                errors.append(exc)

        with path.open("rb") as reader:
            writer = threading.Thread(target=write)
            writer.start()
            writer.join(0.3)
            seen = reader.read()
        writer.join(10)

        self.assertFalse(writer.is_alive(), "the write never finished")
        self.assertEqual(errors, [])
        self.assertEqual(seen, old, "the record was rewritten in place")
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((record["state"], record["round"]), ("held", 2))
        self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_a_reader_polling_during_writes_always_reads_a_whole_record(self):
        controller = self.controller()
        controller._status(state="running", round=0, problems=[PADDING])
        stop = threading.Event()
        errors: list[BaseException] = []
        missing = [0]
        reads = [0]

        def poll() -> None:
            while not stop.is_set():
                try:
                    record = oc.read_status(self.root)
                except BaseException as exc:
                    errors.append(exc)
                    continue
                if record is None:
                    missing[0] += 1
                reads[0] += 1

        reader = threading.Thread(target=poll)
        reader.start()
        try:
            for round_no in range(1, 101):
                controller._status(state="running", round=round_no,
                                   problems=[PADDING])
        finally:
            stop.set()
            reader.join(10)

        self.assertGreater(reads[0], 0)
        self.assertEqual(errors[:3], [], f"{len(errors)} of {reads[0]} reads failed")
        self.assertEqual(missing[0], 0)
        self.assertEqual(oc.read_status(self.root)["round"], 100)


if __name__ == "__main__":
    unittest.main()
