"""D-33: generated ids do not collide and fresh runs refuse existing dirs."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

from ohflow import cli
from ohflow.engine import Engine, PreflightError, new_run_id
from support import (FakeHarnessExecutor, TempCase, AgentScript, git_repo,
                     install_fake_harness_executor, quiet, simple_workflow, stub_preflight)


class UniqueRunDirectories(TempCase):

    def test_two_ids_minted_in_one_second_are_distinct(self):
        first = new_run_id()
        second = new_run_id()
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^r-\d{8}-\d{6}-[0-9a-f]{8}$")

    def test_fresh_run_refuses_an_existing_directory(self):
        repo = git_repo(self.tmp / "repo")
        workflow = simple_workflow(repo)
        stub_preflight(self)
        install_fake_harness_executor(self, FakeHarnessExecutor(default=AgentScript()))
        out = self.tmp / "runs"
        existing = out / "r-existing"
        existing.mkdir(parents=True)
        marker = existing / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")
        original = cli._load
        cli._load = lambda ns: workflow
        self.addCleanup(setattr, cli, "_load", original)
        ns = SimpleNamespace(
            workflow="unused", args=[], max_parallel=None, auto_resume=None,
            out=str(out), resume=None, run_id="r-existing", detach=False,
            dry_run=False, only_phase=None, detached_child=False,
            harness_executors=self.harness_executors,
        )
        with quiet() as output:
            code = cli.cmd_run(ns)
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("already exists", output.out)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse((existing / "workflow.json").exists())

    def test_direct_engine_refuses_existing_directory_without_touching_it(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        run_dir = self.run_dir("r-direct-existing")
        run_dir.mkdir(parents=True)
        marker = run_dir / "keep.txt"
        marker.write_text("keep\n", encoding="utf-8")

        with self.assertRaises(PreflightError):
            Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
                   dry_run=True, verbose=False,
                   harness_executors=self.harness_executors).run()

        self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")
        self.assertEqual([p.name for p in run_dir.iterdir()], ["keep.txt"])

    def test_two_concurrent_engines_get_exactly_one_owner(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        run_dir = self.run_dir("r-concurrent")
        workflow = simple_workflow(repo)
        start = threading.Barrier(3)
        outcomes: list[str] = []
        lock = threading.Lock()

        def run_one():
            engine = Engine(workflow, run_dir, run_id=run_dir.name,
                            dry_run=True, verbose=False,
                            harness_executors=self.harness_executors)
            start.wait(timeout=5)
            try:
                engine.run()
            except PreflightError:
                outcome = "refused"
            else:
                outcome = "owner"
            with lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=run_one) for _ in range(2)]
        for thread in threads:
            thread.start()
        start.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "concurrent engine did not finish")

        self.assertEqual(sorted(outcomes), ["owner", "refused"])
        owner = json.loads((run_dir / ".ohflow-owner.json").read_text())
        self.assertEqual(owner["run_id"], run_dir.name)

    def test_detached_child_claims_one_time_handoff(self):
        repo = git_repo(self.tmp / "repo")
        stub_preflight(self)
        run_dir = self.run_dir("r-handoff")
        run_dir.mkdir(parents=True)
        token = "one-time-test-token"
        (run_dir / ".ohflow-handoff.json").write_text(json.dumps({
            "run_id": run_dir.name, "token": token,
        }), encoding="utf-8")

        Engine(simple_workflow(repo), run_dir, run_id=run_dir.name,
               dry_run=True, verbose=False,
               reservation_token=token,
               harness_executors=self.harness_executors).run()

        self.assertFalse((run_dir / ".ohflow-handoff.json").exists())
        owner = json.loads((run_dir / ".ohflow-owner.json").read_text())
        self.assertTrue(owner["detached_handoff"])
