"""`/api/workflow` carries a digest: one entry per verdict the run log wrote.

Between invocations a watcher wants the story in sentences, not events: which
attempt finished how, in how long, at what token cost, what its gate said and
what its handover opens with. The digest is derived from `attempt_finished`,
`retry_decided`, `work_excluded`, `phase_settled` and `run_finished`, in
run-log order, each entry linked to its attempt and its run-log line.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dashboard_support import T0, RunLog, agent, command, workflow_json
from support import TempCase

from ohflow import dashboard_data
from ohflow.handover import questions
from ohflow.workflow import HandoverSpec

HERE = Path(__file__).resolve().parent
PACKET = HERE / "fixtures" / "dashboard-basis"
FIRST = "01.alpha/01.first"
THIRD = "02.beta/01.third"


def handover_text(first_answer: str) -> str:
    parts = []
    for heading, _question in questions(HandoverSpec()):
        answer = first_answer if heading == "State" else "[verified] fine"
        parts.append(f"## {heading}\n{answer}")
    return "\n\n".join(parts) + "\n"


class TheDigest(TempCase):

    def setUp(self):
        super().setUp()
        self.run = self.tmp / "synthetic"
        workflow_json(self.run, [("Alpha", [agent("first", retry_max=1)], 2),
                                 ("Beta", [command("third")], 1)])
        attempt2 = (self.run / "phases" / "01.alpha" / "01.first" / "attempts"
                    / "02")
        attempt2.mkdir(parents=True)
        text = handover_text("[verified] authoritative: commit abc123 on "
                             "arch/first")
        # Bytes, not text: the recorded digest is of the bytes on disk, and a
        # text write on Windows would turn every newline into two bytes.
        (attempt2 / "handover.md").write_bytes(text.encode("utf-8"))
        (attempt2 / "result.json").write_text(json.dumps({
            "tokens": {"prompt_tokens": 30_000, "completion_tokens": 1_000}}),
            encoding="utf-8")
        log = RunLog(self.run)
        log.phase(1, "01.alpha", "Alpha", [FIRST], 2)
        log.start(2, FIRST, 1, "initial", fingerprint="fp-a")
        log.finish(12, FIRST, 1, "failed", fingerprint="fp-a", wall=10.0,
                   gate={"passed": False, "checks": [
                       {"name": "command_exit", "passed": False},
                       {"name": "tree_clean", "passed": True}]})
        log.add(12, "retry_decided", FIRST, 1,
                payload={"retry_decision": "retry start, execution 2 of 3, "
                                           "attempt 2"})
        log.start(13, FIRST, 2, "retry", fingerprint="fp-a")
        log.finish(265, FIRST, 2, "passed", fingerprint="fp-a", wall=252.0,
                   gate={"passed": True, "checks": [
                       {"name": "command_exit", "passed": True}]},
                   handover_path="phases/01.alpha/01.first/attempts/02/"
                                 "handover.md",
                   handover_sha256=hashlib.sha256(
                       text.encode("utf-8")).hexdigest())
        log.add(265, "retry_decided", FIRST, 2,
                payload={"retry_decision": "no retry: status 'passed' is not "
                                           "a failure"})
        log.settle(266, "01.alpha", "passed", 1, 1)
        log.phase(267, "02.beta", "Beta", [THIRD], 1)
        log.add(268, "attempt_finished", THIRD, 0, payload={
            "status": "cached", "step_id": "third", "kind": "command",
            "fingerprint": "fp-t", "wall_seconds": 0.0,
            "gate": {"passed": True, "checks": []}})
        log.settle(269, "02.beta", "passed", 1, 1)
        log.run_finished(270, "finished")
        self.payload = dashboard_data.workflow_data(self.run, now=T0 + 1000)
        self.digest = self.payload["digest"]

    def test_entries_come_in_run_log_order_one_per_verdict(self):
        self.assertEqual([e["kind"] for e in self.digest],
                         ["attempt_finished", "retry_decided",
                          "attempt_finished", "phase_settled",
                          "attempt_finished", "phase_settled",
                          "run_finished"])
        stamps = [e["ts"] for e in self.digest]
        self.assertEqual(stamps, sorted(stamps))
        # A decision not to retry a passed attempt tells a watcher nothing.
        self.assertFalse(any("is not a failure" in e["text"]
                             for e in self.digest))

    def test_a_passed_attempt_reads_as_one_sentence(self):
        passed = self.digest[2]
        self.assertEqual(passed["coord"], FIRST)
        self.assertEqual(passed["attempt"], 2)
        self.assertEqual(passed["id"], f"{FIRST}@2")
        self.assertEqual(passed["tokens"], 31_000)
        self.assertEqual(passed["wall_s"], 252.0)
        self.assertEqual(passed["handover_first_line"],
                         "[verified] authoritative: commit abc123 on arch/first")
        self.assertEqual(
            passed["text"],
            "role first attempt 2 passed in 4 m 12 s, 31 k tokens; gate "
            "command_exit ok; handover: [verified] authoritative: commit "
            "abc123 on arch/first")
        self.assertEqual(passed["evidence"], {"path": "run-log.jsonl",
                                              "line": 7})

    def test_a_failed_attempt_names_the_failed_check(self):
        failed = self.digest[0]
        self.assertEqual(failed["text"],
                         "role first attempt 1 failed in 10 s; gate "
                         "command_exit failed, tree_clean ok")
        self.assertIsNone(failed["tokens"])
        self.assertIsNone(failed["handover_first_line"])
        self.assertEqual(failed["tone"], "bad")

    def test_the_retry_decision_and_the_settlements_keep_their_sentences(self):
        decided = self.digest[1]
        self.assertEqual(decided["kind"], "retry_decided")
        self.assertEqual(decided["id"], f"{FIRST}@1")
        self.assertIn("retry start, execution 2 of 3", decided["text"])
        settled = self.digest[3]
        self.assertIn("settled passed", settled["text"])
        self.assertIsNone(settled["id"])
        cached = self.digest[4]
        self.assertEqual(cached["id"], f"{THIRD}@0")
        self.assertIn("cached", cached["text"])
        finished = self.digest[-1]
        self.assertEqual(finished["kind"], "run_finished")
        self.assertEqual(finished["text"], "run finished")
        self.assertEqual(finished["tone"], "ok")

    def test_a_handover_whose_bytes_changed_is_not_quoted(self):
        path = (self.run / "phases" / "01.alpha" / "01.first" / "attempts"
                / "02" / "handover.md")
        path.write_text(handover_text("[verified] rewritten"), encoding="utf-8")
        payload = dashboard_data.workflow_data(self.run, now=T0 + 1000)
        passed = payload["digest"][2]
        self.assertIsNone(passed["handover_first_line"])
        self.assertNotIn("handover:", passed["text"])
        self.assertIn("31 k tokens; gate command_exit ok", passed["text"])


class ExcludedWork(TempCase):

    def test_an_exclusion_is_a_digest_entry_of_its_own(self):
        run = self.tmp / "excluded"
        workflow_json(run, [("Alpha", [agent("first")], 1)])
        log = RunLog(run)
        log.phase(1, "01.alpha", "Alpha", [FIRST], 1)
        log.start(2, FIRST).finish(5, FIRST, 1, "failed", error="boom")
        log.start(6, FIRST, 2, "retry").finish(9, FIRST, 2, "quarantined",
                                                error="boom")
        log.add(9, "work_excluded", FIRST, payload={
            "coord": FIRST, "fingerprint": "fp",
            "reason": "excluded: 2 failed executions of unchanged work"})
        payload = dashboard_data.workflow_data(run, now=T0 + 100)
        kinds = [e["kind"] for e in payload["digest"]]
        self.assertEqual(kinds, ["attempt_finished", "attempt_finished",
                                 "work_excluded"])
        excluded = payload["digest"][-1]
        self.assertIn("excluded", excluded["text"])
        self.assertEqual(excluded["tone"], "bad")
        self.assertEqual(excluded["id"], f"{FIRST}@2")


class ThePacketDigest(TempCase):

    def test_the_recorded_run_has_a_digest_with_its_usage(self):
        payload = dashboard_data.workflow_data(PACKET, now=T0)
        digest = payload["digest"]
        self.assertTrue(digest)
        kinds = {e["kind"] for e in digest}
        self.assertIn("attempt_finished", kinds)
        self.assertIn("run_finished", kinds)
        failed = next(e for e in digest
                      if e["id"] == "01.implement/01.implement@4")
        self.assertEqual(failed["tone"], "bad")
        self.assertIn("command_exit", failed["text"])
        passed = next(e for e in digest
                      if e["id"] == "01.implement/01.implement@5")
        self.assertIsInstance(passed["tokens"], int)
        self.assertGreater(passed["tokens"], 0)
        self.assertIn("tokens", passed["text"])


if __name__ == "__main__":
    import unittest
    unittest.main()
