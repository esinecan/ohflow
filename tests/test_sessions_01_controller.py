"""The session controller with a fake pi: one real process per turn, no model call."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from ohflow import sessions
from support import TempCase, real_process
from verb_support import call

FAKE = Path(__file__).resolve().parent / "fakes" / "fake_pi_session.py"


@real_process
class SessionControllerTest(TempCase):
    def setUp(self) -> None:
        super().setUp()
        patch = mock.patch.dict(os.environ, {"OHFLOW_PI_EXE": str(FAKE)})
        patch.start()
        self.addCleanup(patch.stop)
        self.root = self.tmp / "record"
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.addCleanup(self.stop_running)

    def stop_running(self) -> None:
        if not (self.root / sessions.EVENTS).exists():
            return
        for row in sessions.status(self.root)["sessions"]:
            if row["state"] == "running":
                sessions.interrupt(self.root, row["name"])

    def open(self, name: str, message: str) -> dict:
        return sessions.open_session(self.root, name, cwd=self.work, message=message)

    def wait(self, timeout: float = 30) -> dict:
        code, out = sessions.wait(self.root, timeout)
        self.assertEqual(code, sessions.EXIT_OK, out)
        return out

    def test_a_follow_up_continues_the_conversation_and_each_turn_is_delivered_once(self):
        def session(*argv):
            code, lines = call("session", *argv, "--dir", self.root)
            return code, json.loads(lines[-1])

        code, opened = session("open", "ada", "--cwd", self.work,
                               "--message", "remember kestrel")
        self.assertEqual((code, opened["turn"]), (0, 1))
        code, first = session("wait", "--timeout", "30")
        self.assertEqual((code, first["turn"], first["reply"]), (0, 1, "OK"))
        self.assertEqual(first["cost"], 0.001)
        session("send", "ada", "recall")
        code, second = session("wait", "--timeout", "30")
        self.assertEqual((second["turn"], second["reply"]), (2, "kestrel"))
        code, idle = session("wait", "--timeout", "1")
        self.assertEqual(code, sessions.EXIT_IDLE, idle)

    def test_messages_to_a_busy_session_wait_for_the_running_turn_in_order(self):
        self.open("ada", "sleep 1.5")
        self.assertEqual(sessions.send(self.root, "ada", "after1")["state"], "queued")
        self.assertEqual(sessions.send(self.root, "ada", "after2")["state"], "queued")
        first = self.wait()
        self.assertEqual((first["turn"], first["reply"], first["next_turn"]),
                         (1, "slept 1.5", 2))
        self.assertEqual(self.wait()["reply"], "echo: after1")
        self.assertEqual(self.wait()["reply"], "echo: after2")
        turns = self.root / "ada" / "turns"
        ended = json.loads((turns / "1.exit.json").read_text())["finished_at"]
        began = json.loads((turns / "2.exit.json").read_text())["started_at"]
        self.assertLessEqual(ended, began)

    def test_a_fourth_session_and_a_reused_name_are_refused_and_a_closed_reply_still_arrives(self):
        for name in ("a", "b", "c"):
            self.open(name, f"hello {name}")
        with self.assertRaisesRegex(sessions.Refused, "3 sessions are open"):
            self.open("d", "hello")
        deadline = time.time() + 30
        while sessions.status(self.root, "a")["state"] != "idle" and time.time() < deadline:
            time.sleep(0.1)
        sessions.close(self.root, "a")
        with self.assertRaisesRegex(sessions.Refused, "exists"):
            self.open("a", "hello")
        self.assertEqual(self.open("d", "hello d")["turn"], 1)
        replies = sorted(self.wait()["reply"] for _ in range(4))
        self.assertEqual(replies, [f"echo: hello {n}" for n in "abcd"])

    def test_an_interrupted_turn_ends_and_the_conversation_goes_on(self):
        self.open("ada", "remember heron")
        self.wait()
        sessions.send(self.root, "ada", "sleep 30")
        started = time.time()
        self.assertTrue(sessions.interrupt(self.root, "ada")["stopped"])
        self.assertLess(time.time() - started, 15)
        stopped = self.wait()
        self.assertEqual((stopped["turn"], stopped["interrupted"]), (2, True))
        sessions.send(self.root, "ada", "recall")
        self.assertEqual(self.wait()["reply"], "heron")

    def test_a_turn_whose_process_died_is_delivered_as_lost(self):
        self.open("ada", "sleep 30")
        pid_file = self.root / "ada" / "turns" / "1.pid"
        deadline = time.time() + 15
        while not pid_file.exists() and time.time() < deadline:
            time.sleep(0.1)
        pid = int(pid_file.read_text())
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGKILL)
        lost = self.wait(timeout=15)
        self.assertTrue(lost["lost"], lost)
        self.assertEqual(sessions.status(self.root)["sessions"][0]["state"], "idle")


if __name__ == "__main__":
    unittest.main()
