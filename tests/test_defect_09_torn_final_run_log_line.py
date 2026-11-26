"""D-09: only a torn final run log record is skipped and then repaired."""

from __future__ import annotations

import json

from ohflow.run_log import RunLog
from support import TempCase


class TornFinalRunLogLine(TempCase):

    def test_replay_skips_final_torn_line_and_records_recovery(self):
        run_dir = self.run_dir()
        run_log = RunLog(run_dir)
        run_log.append("run_started", payload={"run_id": run_dir.name,
                                                "workflow": "torn"})
        with run_log.path.open("a", encoding="utf-8") as fh:
            fh.write('{"event":"attempt_started"')
        state = RunLog.replay(run_dir)
        self.assertEqual(state.run_id, run_dir.name)
        self.assertTrue(state.meta["run_log_recovery"]["torn_final_line"])

    def test_next_append_truncates_torn_tail_before_writing(self):
        run_dir = self.run_dir()
        run_log = RunLog(run_dir)
        run_log.append("run_started", payload={"run_id": run_dir.name,
                                                "workflow": "torn"})
        with run_log.path.open("ab") as fh:
            fh.write(b'{"event":"attempt_started"')
        run_log.append("run_finished", payload={"status": "finished"})

        state = RunLog.replay(run_dir)
        self.assertEqual(state.status, "finished")
        self.assertEqual(state.meta["run_log_recovery"]["action"], "truncated")
        for line in run_log.path.read_text(encoding="utf-8").splitlines():
            json.loads(line)

    def test_incomplete_final_utf8_character_is_a_torn_line(self):
        run_dir = self.run_dir()
        run_log = RunLog(run_dir)
        run_log.append("run_started", payload={"run_id": run_dir.name,
                                                "workflow": "torn"})
        with run_log.path.open("ab") as fh:
            fh.write(b'{"event":"attempt_started","payload":{"note":"\xe2\x82')
        state = RunLog.replay(run_dir)
        self.assertEqual(state.run_id, run_dir.name)
        self.assertTrue(state.meta["run_log_recovery"]["torn_final_line"])

    def test_corruption_before_the_final_record_still_raises(self):
        run_dir = self.run_dir()
        run_log = RunLog(run_dir)
        run_dir.mkdir(parents=True)
        run_log.path.write_text(
            '{"event":"run_started","payload":{}}\nBROKEN\n'
            '{"event":"run_finished","payload":{"status":"finished"}}\n',
            encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            RunLog.replay(run_dir)
