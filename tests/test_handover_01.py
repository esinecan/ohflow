"""Handovers cross a real engine boundary, including retry and cached resume."""
from dataclasses import replace
from ohflow.workflow import HandoverSpec, Phase, RetryPolicy, validate, WorkflowError
from ohflow.engine import Engine
from ohflow.handover import questions, check_text
from ohflow import rundir
from support import TempCase, git_repo, simple_workflow, agent_step, AgentScript, FakeHarnessExecutor, quiet


def report(marker="source finding", audience="next"):
    return "\n\n".join(f"## {h}\n[verified] {marker}" for h, _ in questions(HandoverSpec(audience=audience)))


class Handovers(TempCase):
    def workflow(self, **kwargs):
        repo = git_repo(self.tmp / "repo")
        producer = agent_step("producer")
        consumer = replace(agent_step("consumer"), depends_on=("producer",), consumes=("producer",))
        return validate(simple_workflow(repo, phases=(Phase("Produce", (producer,)), Phase("Consume", (consumer,))), **kwargs))

    def test_validation_normalizes_once_and_refuses_non_dependencies(self):
        wf = self.workflow()
        p = wf.step_by_id("producer")[3]
        self.assertEqual(p.handover, HandoverSpec())
        self.assertEqual(p.gate.names().count("handover_written"), 1)
        self.assertEqual(validate(wf), wf)
        c = wf.step_by_id("consumer")[3]
        with self.assertRaisesRegex(WorkflowError, "must also depend"):
            validate(replace(wf, phases=(wf.phases[0], Phase("Consume", (replace(c, depends_on=()),)))))

    def test_gate_rejects_missing_empty_duplicate_and_oversize_answers(self):
        spec = HandoverSpec()
        self.assertIsNone(check_text(report(), spec))
        for bad in ("", report().replace("## Next", "## Wrong"), report()+"\n## State\nagain", report()+"x"*6000,
                    "```markdown\n"+report(), "~~~markdown\n"+report()+"\n~~~"):
            self.assertIsNotNone(check_text(bad, spec))

    def test_crlf_limit_is_the_same_in_the_gate_and_received_text(self):
        from ohflow.gates import GateContext, handover_written
        limit = 1200
        text = report()
        text += "x" * (limit-len(text))
        self.assertIsNone(check_text(text, HandoverSpec(max_chars=limit)))
        attempt = self.tmp / "attempt"
        attempt.mkdir()
        (attempt / "handover.md").write_bytes(text.replace("\n", "\r\n").encode())
        ctx = GateContext("p/s", self.tmp, self.tmp, "", "", attempt, attempt)
        self.assertFalse(handover_written(ctx, max_chars=limit).passed)

    def test_relay_receives_authoritative_handover_and_cached_resume(self):
        wf = self.workflow()
        fake = FakeHarnessExecutor({"producer": AgentScript(files={"handover.md": report("TOKEN-73")})})
        root = self.tmp / "run"
        with quiet():
            Engine(wf, root, harness_executors=lambda _: fake).run()
        run = rundir.open_run(root)
        c = next(s for s in run.steps() if s.step_id == "consumer")
        text = (run.step_dir(c.coord) / "brief.md").read_text(encoding="utf-8")
        self.assertIn("TOKEN-73", text)
        self.assertIn("Handed to you", text)
        p = next(s for s in run.steps() if s.step_id == "producer")
        self.assertIn("TOKEN-73", run.handover(p.coord))
        with quiet():
            Engine(wf, root, resume=True, harness_executors=lambda _: fake).run()
        self.assertEqual(len(fake.launched), 2)
        self.assertEqual(rundir.open_run(root).state.steps[p.coord].status, "cached")

    def test_missing_handover_fails_producer_and_skips_consumer(self):
        wf = self.workflow()
        fake = FakeHarnessExecutor()
        root = self.tmp / "run"
        with quiet():
            Engine(wf, root, harness_executors=lambda _: fake).run()
        run = rundir.open_run(root)
        self.assertEqual(len(fake.launched), 1)
        self.assertEqual([s.status for s in run.steps()], ["quarantined", "skipped"])

    def test_modified_or_deleted_handover_forces_producer_to_run_again(self):
        for mode in ("delete", "modify"):
            with self.subTest(mode=mode):
                wf = self.workflow() if mode == "delete" else self.saved_wf
                self.saved_wf = wf
                fake = FakeHarnessExecutor({"producer": AgentScript(files={"handover.md": report("ORIGINAL")})})
                root = self.tmp / mode
                with quiet():
                    Engine(wf, root, harness_executors=lambda _: fake).run()
                run = rundir.open_run(root)
                p = next(s for s in run.steps() if s.step_id == "producer")
                path = root / run.state.steps[p.coord].handover_path
                if mode == "delete":
                    path.unlink()
                else:
                    path.write_text(report("TAMPERED"), encoding="utf-8")
                with quiet():
                    Engine(wf, root, resume=True, harness_executors=lambda _: fake).run()
                self.assertEqual(fake.scripts["producer"].launches, 2)
                self.assertNotIn("TAMPERED", rundir.open_run(root).handover(p.coord))

    def test_changed_handover_digest_reruns_consumer_with_same_producer_inputs(self):
        wf = self.workflow()
        fake = FakeHarnessExecutor({"producer": AgentScript(sequence=[
            {"files": {"handover.md": report("OLD-MARKER")}},
            {"files": {"handover.md": report("NEW-MARKER")}}])})
        root = self.tmp / "run"
        with quiet():
            Engine(wf, root, harness_executors=lambda _: fake).run()
        run = rundir.open_run(root)
        producer, consumer = run.steps()
        before = {c: r.fingerprint for c, r in run.state.steps.items()}
        (root / run.state.steps[producer.coord].handover_path).unlink()
        with quiet():
            Engine(wf, root, resume=True, harness_executors=lambda _: fake).run()
        run = rundir.open_run(root)
        self.assertEqual(len(fake.launched), 4)
        self.assertEqual(before[producer.coord], run.state.steps[producer.coord].fingerprint)
        self.assertNotEqual(before[consumer.coord], run.state.steps[consumer.coord].fingerprint)
        brief = run.latest_attempt_dir(consumer.coord) / "brief.md"
        self.assertIn("NEW-MARKER", brief.read_text(encoding="utf-8"))

    def test_retry_receives_previous_handover_and_failed_check(self):
        repo = git_repo(self.tmp / "repo")
        p = replace(agent_step("producer"), handover=HandoverSpec(), retry=RetryPolicy(max=1, on=("gate:handover_written",)))
        wf = validate(simple_workflow(repo, steps=[p]))
        fake = FakeHarnessExecutor({"producer": AgentScript(sequence=[{"files":{"handover.md":"## State\nPARTIAL-91"}}, {"files":{"handover.md":report()}}])})
        root = self.tmp / "run"
        with quiet():
            Engine(wf, root, harness_executors=lambda _: fake).run()
        p = rundir.open_run(root).steps()[0]
        text = (rundir.open_run(root).step_dir(p.coord) / "attempts" / "02" / "brief.md").read_text(encoding="utf-8")
        self.assertIn("PARTIAL-91", text)
        self.assertIn("handover_written", text)
