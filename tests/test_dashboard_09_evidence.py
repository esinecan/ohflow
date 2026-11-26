"""`/api/evidence`: one attempt's recorded evidence, from a whitelist only.

The packet's attempt 4 is the receipt the design was built around: five gate
checks, four passed and `command_exit` failed with `observed 1, expected 0`,
beside the agent's final message as a separate claim. The endpoints prove the
boundaries: artifact ids map to a fixed whitelist, credentials under the
attempt directory are never listed, a symlink cannot walk a file in, a cached
evaluation shows the earlier attempt's evidence and says so, and serving the
packet changes nothing on disk - same bytes, same mtimes, no `dashboard.json`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from dashboard_support import T0, RunLog, agent, command, mark_alive, stamp, \
    workflow_json
from support import TempCase

from ohflow import dashboard, dashboard_data, live
from test_dashboard_08_transcript import IMPL, PACKET, REVIEW, get, \
    make_packet

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def tree_stamp(root: Path) -> dict:
    """Every file's hash and mtime, so a read must not change either."""
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[path.relative_to(root).as_posix()] = (
                hashlib.sha256(path.read_bytes()).hexdigest(),
                stat.st_mtime_ns, stat.st_size)
    return out


class TheFailedCheck(TempCase):

    def setUp(self):
        super().setUp()
        self.evidence = dashboard_data.evidence_data(
            PACKET, IMPL, 4)

    def test_the_gate_is_the_check_result_not_the_claim(self):
        gate = self.evidence["gate"]
        self.assertFalse(gate["passed"])
        by_name = {c["name"]: c for c in gate["checks"]}
        self.assertEqual(len(gate["checks"]), 5)
        failed = by_name["command_exit"]
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["observed"], 1)
        self.assertEqual(failed["expected"], 0)
        for name in ("commits_past_base", "tree_clean", "ownership",
                     "no_ai_attribution"):
            self.assertTrue(by_name[name]["passed"])
        self.assertIn("gate_ran", self.evidence["gate_source"])

    def test_the_final_message_is_served_as_the_agents_claim(self):
        message = self.evidence["final_message"]
        self.assertIsInstance(message, str)
        self.assertTrue(message.strip())
        # The claim and the check stay apart: the gate never speaks in the
        # message and the message never declares the check's verdict fields.
        self.assertNotIn("observed", message)

    def test_the_events_name_this_attempt(self):
        events = self.evidence["events"]
        self.assertEqual([e["event"] for e in events],
                         ["attempt.started", "attempt.gate_ran",
                          "attempt.finished", "attempt.retry_decided"])
        decision = events[-1]
        self.assertEqual(decision["text"],
                         "implement attempt 4: retry start, execution 2 of "
                         "5, attempt 5")

    def test_artifacts_are_a_whitelist_with_fixed_ids(self):
        ids = [a["id"] for a in self.evidence["artifacts"]]
        self.assertEqual(ids, ["gate", "final", "position",
                               "log:gate-command-exit.out.log",
                               "log:gate-command-exit.err.log",
                               "transcript"])
        for artifact in self.evidence["artifacts"]:
            self.assertTrue(artifact["source"]["path"]
                            .startswith("transcripts/implement-att04/"))
            self.assertNotIn("content", artifact)

    def test_a_named_artifact_serves_its_content(self):
        log = dashboard_data.evidence_data(
            PACKET, IMPL, 4, artifact_id="log:gate-command-exit.out.log")
        content = log["artifacts"][0]["content"]
        self.assertIn("FAILED", content)
        self.assertLessEqual(len(content), 33000)
        gate = dashboard_data.evidence_data(PACKET, IMPL, 4,
                                            artifact_id="gate")
        self.assertEqual(gate["artifacts"][0]["kind"], "json")

    def test_an_unknown_artifact_id_is_refused(self):
        for artifact_id in ("../../case.json", "auth", "case.json",
                            "transcript.jsonl", "log:../../../.env"):
            with self.subTest(artifact_id=artifact_id):
                self.assertIsNone(dashboard_data.evidence_data(
                    PACKET, IMPL, 4, artifact_id=artifact_id))

    def test_a_cached_evaluation_shows_the_linked_attempt(self):
        evidence = dashboard_data.evidence_data(PACKET, IMPL, 0)
        joined = "\n".join(evidence["diagnostics"])
        self.assertIn("launched no agent", joined)
        self.assertIn(f"{IMPL}@5", joined)
        # The evidence is attempt 5's, and the gate it reused passed.
        self.assertTrue(evidence["gate"]["passed"])
        paths = {a["source"]["path"] for a in evidence["artifacts"]}
        self.assertTrue(all(p.startswith("transcripts/implement-att05/")
                            for p in paths))
        # A cached evaluation has no final message of its own.
        self.assertIsNone(evidence["final_message"])

    def test_unknown_attempts_are_refused(self):
        for coord, attempt in ((IMPL, 9), (IMPL, "x"), ("../../x", 1),
                               (REVIEW, 7)):
            with self.subTest(coord=coord, attempt=attempt):
                self.assertIsNone(dashboard_data.evidence_data(
                    PACKET, coord, attempt))


class WhitelistBoundaries(TempCase):

    def setUp(self):
        super().setUp()
        from test_dashboard_08_transcript import current_run
        self.run = current_run(self.tmp, harness_executor="pi")
        self.attempt = (self.run / "phases" / "01.build" / "01.worker"
                        / "attempts" / "01")
        (self.attempt / "pi-agent").mkdir(parents=True)
        self.secret = "sk-this-must-never-be-served-0123456789"
        (self.attempt / "pi-agent" / "auth.json").write_text(
            json.dumps({"zai": {"key": self.secret}}), encoding="utf-8")
        (self.run / ".env").write_text(f"ZAI_KEY={self.secret}\n",
                                       encoding="utf-8")

    def test_credentials_are_never_listed(self):
        evidence = dashboard_data.evidence_data(self.run,
                                                "01.build/01.worker", 1)
        ids = [a["id"] for a in evidence["artifacts"]]
        self.assertEqual(ids, [])
        text = json.dumps(evidence)
        self.assertNotIn("auth", text)
        self.assertNotIn(self.secret, text)

    def test_whitelisted_files_serve_and_others_do_not(self):
        (self.attempt / "final.md").write_text("all done\n", encoding="utf-8")
        (self.attempt / "secrets.txt").write_text(self.secret + "\n",
                                                  encoding="utf-8")
        evidence = dashboard_data.evidence_data(self.run,
                                                "01.build/01.worker", 1)
        ids = [a["id"] for a in evidence["artifacts"]]
        self.assertEqual(ids, ["final"])
        final = dashboard_data.evidence_data(self.run, "01.build/01.worker",
                                             1, artifact_id="final")
        self.assertEqual(
            final["artifacts"][0]["content"].replace("\r\n", "\n"),
            "all done\n")
        self.assertIsNone(dashboard_data.evidence_data(
            self.run, "01.build/01.worker", 1, artifact_id="secrets.txt"))

    def test_a_symlink_cannot_walk_out(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "final.md").write_text(self.secret + "\n",
                                          encoding="utf-8")
        (outside / "gate-evil.out.log").write_text(self.secret + "\n",
                                                   encoding="utf-8")
        link = self.attempt / "final.md"
        junction = self.attempt / "logs"
        shutil.rmtree(junction, ignore_errors=True)
        try:
            if os.name == "nt":
                # A junction needs no privilege on this box; a symlink does.
                import subprocess
                for source, target in ((link, outside), (junction, outside)):
                    done = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(source),
                         str(target)], capture_output=True, text=True)
                    if done.returncode:
                        self.skipTest("this box cannot create links: "
                                      + done.stderr.strip())
            else:
                os.symlink(outside, link)
                os.symlink(outside, junction)
        except OSError:
            self.skipTest("this box cannot create symlinks")
        evidence = dashboard_data.evidence_data(self.run,
                                                "01.build/01.worker", 1)
        text = json.dumps(evidence)
        self.assertNotIn(self.secret, text)
        self.assertNotIn("final.md", text)
        self.assertNotIn("gate-evil.out.log", text)
        self.assertIsNone(dashboard_data.evidence_data(
            self.run, "01.build/01.worker", 1, artifact_id="final"))
        self.assertIsNone(dashboard_data.evidence_data(
            self.run, "01.build/01.worker", 1,
            artifact_id="log:gate-evil.out.log"))


class ThePacketIsReadOnly(TempCase):

    def test_serving_every_endpoint_changes_nothing_on_disk(self):
        before = tree_stamp(PACKET)
        handle = dashboard.start(PACKET)
        try:
            base = handle.url.rstrip("/")
            for path in ("/", "/api/workflow",
                         "/api/transcript?coord=01.implement/01.implement"
                         "&attempt=4",
                         "/api/transcript?coord=02.review/01.review"
                         "&attempt=4",
                         "/api/evidence?coord=01.implement/01.implement"
                         "&attempt=4",
                         "/api/evidence?coord=01.implement/01.implement"
                         "&attempt=4&id=gate",
                         "/api/read-out"):
                status, body = get(base + path)
                self.assertEqual(status, 200, path)
        finally:
            handle.stop()
        self.assertEqual(tree_stamp(PACKET), before)
        self.assertFalse((PACKET / "dashboard.json").exists())


class CurrentFormatEvidence(TempCase):

    def setUp(self):
        super().setUp()
        self.run = self.tmp / "evidence-run"
        worker = agent("worker")
        compile_step = command("compile", "echo compiled")
        workflow_json(self.run, [("Build", [worker, compile_step], 2)])
        log = RunLog(self.run)
        log.phase(1, "01.build", "Build",
                  ["01.build/01.worker", "01.build/02.compile"], 2)
        log.start(2, "01.build/01.worker", 1)
        log.add(3, "gate_ran", "01.build/01.worker", 1, payload={
            "gate": {"passed": False, "checks": [
                {"name": "tree_clean", "passed": False,
                 "expected": "clean", "observed": "dirty"}]}})
        log.finish(4, "01.build/01.worker", 1, "failed", wall=9.0,
                   error="gate tree_clean failed")
        log.start(5, "01.build/02.compile", 1)
        log.finish(6, "01.build/02.compile", 1, "passed", wall=1.0)
        self.attempt = (self.run / "phases" / "01.build" / "01.worker"
                        / "attempts" / "01")
        self.attempt.mkdir(parents=True)
        (self.attempt / "gate.json").write_text(json.dumps({
            "passed": False, "checks": [
                {"name": "tree_clean", "passed": False,
                 "expected": "clean", "observed": "dirty"}]}),
            encoding="utf-8")
        (self.attempt / "final.md").write_text("I believe I am done\n",
                                               encoding="utf-8")
        logs = self.attempt / "logs"
        logs.mkdir()
        (logs / "gate-01-tree_clean.out.log").write_text(
            "M summary.json\n", encoding="utf-8")

    def test_gate_result_and_logs_are_served_from_the_attempt(self):
        evidence = dashboard_data.evidence_data(self.run,
                                                "01.build/01.worker", 1)
        self.assertFalse(evidence["gate"]["passed"])
        self.assertEqual(evidence["gate"]["checks"][0]["observed"], "dirty")
        self.assertEqual(evidence["gate_source"],
                         "phases/01.build/01.worker/attempts/01/gate.json")
        self.assertEqual(
            evidence["final_message"].replace("\r\n", "\n"),
            "I believe I am done\n")
        ids = [a["id"] for a in evidence["artifacts"]]
        self.assertEqual(ids, ["gate", "final",
                               "log:gate-01-tree_clean.out.log"])
        events = [e["event"] for e in evidence["events"]]
        self.assertIn("gate_ran", events)

    def test_a_command_step_has_no_final_message_claim(self):
        evidence = dashboard_data.evidence_data(self.run,
                                                "01.build/02.compile", 1)
        self.assertIsNone(evidence["final_message"])
        self.assertTrue(evidence["gate"]["passed"])

    def test_an_interrupted_attempt_names_its_state(self):
        log = RunLog(self.run)
        log.start(7, "01.build/01.worker", 2)
        evidence = dashboard_data.evidence_data(self.run,
                                                "01.build/01.worker", 2)
        # Current-format events carry the engine's own event names.
        self.assertEqual([e["event"] for e in evidence["events"]],
                         ["attempt_started"])

    def test_structured_gate_artifact_and_shared_read_out_redaction(self):
        secret = "value-with-no-secret-looking-shape"
        gate_path = self.attempt / "gate.json"
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        gate["details"] = {
            "CLIENT_SECRET": secret,
            "PASSWORD": "plain-password",
            "usage": {"input_tokens": 123, "output_tokens": 7},
        }
        gate_path.write_text(json.dumps(gate), encoding="utf-8")

        evidence = dashboard_data.evidence_data(
            self.run, "01.build/01.worker", 1)
        artifact = dashboard_data.evidence_data(
            self.run, "01.build/01.worker", 1, artifact_id="gate")
        for payload in (evidence, artifact):
            text = json.dumps(payload)
            self.assertNotIn(secret, text)
            self.assertNotIn("plain-password", text)
            self.assertIn("[redacted]", text)
        self.assertEqual(evidence["gate"]["details"]["usage"]["input_tokens"],
                         123)
        self.assertEqual(
            artifact["artifacts"][0]["content"]["details"]["usage"]
            ["output_tokens"], 7)

        # live.read_out uses this exact recursive final-response redactor.
        read_out_shape = {"tool": {"input": {
            "PASSWORD": "read-out-password",
            "CLIENT_SECRET": secret,
            "token_count": 9,
        }}}
        redacted = live._redact_tree(read_out_shape)
        self.assertEqual(redacted["tool"]["input"]["PASSWORD"],
                         "[redacted]")
        self.assertEqual(redacted["tool"]["input"]["token_count"], 9)
        self.assertEqual(live._redact_tree(redacted), redacted)

    def test_read_out_masks_structured_password_after_activity_shaping(self):
        run = self.run_dir("read-out-structured-secret")
        workflow_json(run, [("Build", [agent("worker")], 1)])
        (RunLog(run).phase(1, "01.build", "Build",
                           ["01.build/01.worker"])
         .start(2, "01.build/01.worker"))
        mark_alive(run)
        session = (run / "phases" / "01.build" / "01.worker" / "attempts"
                   / "01" / "session")
        session.mkdir(parents=True)
        entry = {"type": "message", "timestamp": stamp(5), "message": {
            "role": "assistant", "usage": {"input": 1, "output": 1},
            "content": [{"type": "toolCall", "id": "c1", "name": "bash",
                         "arguments": {"PASSWORD": "read-out-password",
                                       "CLIENT_SECRET": "client-value",
                                       "input_tokens": 11}}]}}
        (session / "s.jsonl").write_text(json.dumps(entry) + "\n",
                                          encoding="utf-8")
        read_out = live.read_out(run, T0 + 10)
        text = json.dumps(read_out)
        self.assertNotIn("read-out-password", text)
        self.assertNotIn("client-value", text)
        self.assertIn("[redacted]", text)


class OverHttp(TempCase):

    def setUp(self):
        super().setUp()
        self.handle = dashboard.start(PACKET)
        self.addCleanup(self.handle.stop)
        self.base = self.handle.url.rstrip("/")

    def test_the_route_answers_and_the_headers_match_the_server(self):
        status, body = get(self.base + "/api/evidence?coord="
                           "01.implement/01.implement&attempt=4")
        self.assertEqual(status, 200)
        self.assertIn(b'"command_exit"', body)
        req = urllib.request.Request(
            self.base + "/api/evidence?coord=01.implement/01.implement"
                        "&attempt=4", method="HEAD")
        try:
            OPENER.open(req, timeout=10)
            self.fail("HEAD accepted")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 405)
            self.assertEqual(e.headers["Allow"], "GET")

    def test_invalid_ids_and_coords_are_404(self):
        for path in (
            "/api/evidence?coord=01.implement/01.implement&attempt=4&id=x",
            "/api/evidence?coord=../workflow.json&attempt=1",
            "/api/evidence?coord=01.implement/01.implement&attempt=4"
            "&id=../../case.json",
        ):
            with self.subTest(path=path):
                status, body = get(self.base + path)
                self.assertEqual(status, 404, path)
                self.assertNotIn(b"schema", body)


if __name__ == "__main__":
    import unittest
    unittest.main()
