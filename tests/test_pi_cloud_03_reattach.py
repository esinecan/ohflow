"""The reattach rule over the real pi-cloud executor: the Worker, the engine.

Unlike `test_durable_03_reattach`, which drives an in-process fake executor,
these tests drive the real `PiCloudHarnessExecutor` - a real runner process,
the real client script, the fake Worker of `tests/fakes/fake_pi_cloud.py` -
so every `host_lost` verdict the engine answers comes from the client's own
exit code and every abort from the runner's own POST. What is proved, from
the run log and the attempt directories:

- R4 and R5: a host loss reattaches attempt 1 in its own directory, the
  reattach posts `step` again with the same operation id and pushes nothing,
  and the step passes as one attempt that counts its conversation once;
- R4 and R6: a host loss, then a stall, then success - the pair that broke
  the `durable` executor. The stall's runner posts `abort` for attempt 1's
  key, and the retry is attempt 2 with a new key, object and branch;
- R3 and R5: a reattached attempt whose stream also drops once. The event
  log holds no `entryId` twice, and the attempt's usage equals the sum over
  the distinct assistant messages of the recording;
- R5 and R7: a supervisor death after the Worker settled and pushed. The
  dead supervisor's own `step` post was the object's first; the resume's post
  is the repeat with the same operation id, answered as a reattach, the
  replay ends with `pi_cloud_end` at once, the worktree fast-forwards to its
  head, the branch is deleted, and the step passes as one attempt;
- F2 and R5: a first connection that streams beats for longer than the lost
  bound and then drops reconnects and ends `done`, with attempt 1 started
  once and no reattach at all;
- R4 and R8: a reconnect answered 401 ends the attempt with an `HTTPError`
  error, not `host_lost`, and no reattach follows;
- R6 and R2: after a stall's abort, the retry posts `step` to a new object
  and never gets 409.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

from ohflow import attempts as ohattempts
from ohflow.engine import Engine
from ohflow.fingerprint import fingerprint
from ohflow.run_log import RunLog, RunState
from ohflow.workflow import ModelConfig, RetryPolicy
from pi_cloud_support import PiCloudCase, git
from support import (agent_step, quiet, read_run_log, simple_workflow,
                     step_statuses, stub_preflight)
from fakes.fake_pi_cloud import CUT

COORD = "01.only-phase/01.s1"
PI_CLOUD_MODEL = ModelConfig(model="zai/glm-5.3-flash", base_url="",
                             api_key_env="", params={"thinking": "low"})


def pi_cloud_step(**changes):
    """One agent step on the pi-cloud harness executor, gated on the
    recording's own final message.

    `max_iterations` sits above every recording's message count, so the
    scenarios under test - a replay that goes quiet, a stream that drops -
    are what stops the attempt, not the iteration cap.
    """
    from support import GateSpec, CheckSpec
    step = agent_step("s1", gate=GateSpec(
        checks=(CheckSpec("final_message_matches",
                          {"regex": "(?i)tests pass"}),)))
    step = replace(step, agent=replace(step.agent, harness_executor="pi-cloud",
                                       model=PI_CLOUD_MODEL,
                                       max_iterations=30))
    return replace(step, **changes) if changes else step


class Reattach(PiCloudCase):

    def _engine(self, workflow, run_dir, resume=False):
        return Engine(workflow, run_dir, run_id=run_dir.name, verbose=False,
                      resume=resume)

    def attempt_dir(self, run_dir: Path, attempt: int) -> Path:
        return (run_dir / "phases" / "01.only-phase" / "01.s1" / "attempts"
                / f"{attempt:02d}")

    def key_of(self, run_dir: Path, attempt: int) -> str:
        from ohflow import remote_git
        return remote_git.attempt_key(COORD, attempt,
                                      self.attempt_dir(run_dir, attempt).resolve())

    def _plan(self, run_dir: Path, attempt: int, post: int,
              behaviours: list[str]) -> str:
        key = self.key_of(run_dir, attempt)
        self.worker.plan(key, post, behaviours)
        return key

    def _events(self, run_dir, name):
        return [r for r in read_run_log(run_dir)
                if r["event"] == name and r.get("coord") == COORD]

    def _run(self, workflow, run_dir, *, resume=False):
        with quiet():
            self._engine(workflow, run_dir, resume=resume).run()

    def _fast_reconnect(self):
        self._set_env("OHFLOW_PI_CLOUD_LOST_S", "2")
        self._set_env("OHFLOW_PI_CLOUD_RETRY_S", "0.2")

    # ------------------------------------------------------------- R4 and R5

    def test_r4_and_r5_a_host_loss_reattaches_the_same_attempt_and_passes(self):
        self._fast_reconnect()
        stub_preflight(self)
        run_dir = self.run_dir()
        key1 = self._plan(run_dir, 1, 1, ["refuse"])
        self._plan(run_dir, 1, 2, ["success"])
        workflow = simple_workflow(self.repo, steps=[pi_cloud_step()])
        self._run(workflow, run_dir)

        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts], [(1, "initial"), (1, "reattach")])
        finishes = self._events(run_dir, "attempt_finished")
        self.assertEqual(len(finishes), 2)
        closed = finishes[0]["payload"]
        self.assertEqual(closed["status"], "deferred")
        self.assertTrue(closed["abort_victim"])
        self.assertTrue(closed["reattached"])
        # The client's own lost bound, not a guessed transport error.
        self.assertIn("host_lost", closed["error"])
        self.assertIn("client exited 3", closed["error"])
        self.assertIn(key1, closed["error"])
        state = RunLog.replay(run_dir)
        self.assertEqual(ohattempts.attempts(state, COORD), 2)
        self.assertEqual(ohattempts.failed_executions(state, COORD), 0)
        # The reattach posts step again with the same operation id and no
        # second push: the transport the first launch pushed is the one the
        # fetch came back on, and the Worker answered a reattach.
        answers = self.worker.step_answers[key1]
        self.assertEqual([a["reattach"] for a in answers], [False, True])
        self.assertEqual([a["accepted"] for a in answers], [True, False])
        remote = json.loads((self.attempt_dir(run_dir, 1) / "remote.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(remote["key"], key1)
        self.assertEqual(remote["start_sha"],
                         self.worker.transport_at_step[key1]["on_origin"])
        result = json.loads((self.attempt_dir(run_dir, 1) / "result.json")
                            .read_text(encoding="utf-8"))
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["llm_calls"], 6)
        tokens, why = self.module.usage(self.attempt_dir(run_dir, 1))
        self.assertIsNone(why)
        self.assertEqual(tokens, result["tokens"])

    # ------------------------------------------------------------- R4 and R6

    def test_r4_and_r6_host_loss_then_a_stall_then_success(self):
        self._fast_reconnect()
        stub_preflight(self)
        run_dir = self.run_dir()
        key1 = self._plan(run_dir, 1, 1, ["refuse"])
        self._plan(run_dir, 1, 2, ["silent"])
        key2 = self._plan(run_dir, 2, 1, ["success"])
        self.assertNotEqual(key1, key2)
        workflow = simple_workflow(self.repo, steps=[pi_cloud_step(
            stall_timeout_s=6, retry=RetryPolicy(max=1, on=("agent_error",)))])
        self._run(workflow, run_dir)

        # The run log has attempt 1 started twice - fresh, then reattach -
        # and attempt 2 once, and the step passes on attempt 2's commit.
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts],
                         [(1, "initial"), (1, "reattach"), (2, "retry")])
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        # The stall's runner aborted attempt 1's object and no other.
        self.assertEqual(self.worker.aborted, [key1])
        result1 = json.loads((self.attempt_dir(run_dir, 1) / "result.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(result1["error"], "stall")
        self.assertTrue(result1["pi_cloud"]["aborted"])
        result2 = json.loads((self.attempt_dir(run_dir, 2) / "result.json")
                             .read_text(encoding="utf-8"))
        self.assertIsNone(result2["error"], result2["error"])
        self.assertEqual(result2["pi_cloud"]["key"], key2)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"),
                         result2["pi_cloud"]["head"])

    # ------------------------------------------------------------- R3 and R5

    def test_r3_and_r5_a_reattached_attempt_whose_stream_also_drops(self):
        self._fast_reconnect()
        stub_preflight(self)
        run_dir = self.run_dir()
        key1 = self._plan(run_dir, 1, 1, ["refuse"])
        self._plan(run_dir, 1, 2, CUT)
        workflow = simple_workflow(self.repo, steps=[pi_cloud_step()])
        self._run(workflow, run_dir)

        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts], [(1, "initial"), (1, "reattach")])
        # The reattached client reconnected once inside its own process, and
        # no entry and no tool-call start reached the log twice.
        log = (self.attempt_dir(run_dir, 1) / "logs" / "pi-cloud-events.jsonl")
        events = [json.loads(line) for line in
                  log.read_text(encoding="utf-8").splitlines() if line.strip()]
        entries = [e.get("entryId") for e in events
                   if e.get("type") in ("message_end", "tool_execution_end")
                   and e.get("entryId") is not None]
        self.assertEqual(len(entries), len(set(entries)), entries)
        starts_printed = [e.get("toolCallId") for e in events
                          if e.get("type") == "tool_execution_start"]
        self.assertEqual(len(starts_printed), len(set(starts_printed)))
        kinds = [e.get("type") for e in events]
        self.assertEqual(kinds.count("pi_cloud_start"), 2)
        # Every distinct assistant message of the recording, counted once.
        self.assertEqual(kinds.count("message_end"), 9)
        result = json.loads((self.attempt_dir(run_dir, 1) / "result.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(result["llm_calls"], 9)
        tokens, why = self.module.usage(self.attempt_dir(run_dir, 1))
        self.assertIsNone(why)
        self.assertEqual(tokens, result["tokens"])

    # --------------------------------------------------------- F2 and R5

    def test_f2_and_r5_a_stream_past_the_bound_drops_and_the_reconnect_ends_done(self):
        self._fast_reconnect()
        stub_preflight(self)
        run_dir = self.run_dir()
        key1 = self._plan(run_dir, 1, 1,
                          [{"hold_s": 3, "beat_s": 0.5}, "success"])
        workflow = simple_workflow(self.repo, steps=[pi_cloud_step()])
        self._run(workflow, run_dir)

        # The first connection was quiet-but-healthy for 3 s - longer than
        # the 2 s lost bound - and then dropped; the client reconnected in
        # the same process and the step finished on attempt 1's own run.
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts], [(1, "initial")])
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        result = json.loads((self.attempt_dir(run_dir, 1) / "result.json")
                            .read_text(encoding="utf-8"))
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["pi_cloud"]["key"], key1)
        [answer] = self.worker.step_answers[key1]
        self.assertEqual((answer["accepted"], answer["reattach"]),
                         (True, False))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"),
                         result["pi_cloud"]["head"])
        listed = git(self.tmp, "ls-remote", self.origin.as_posix(),
                     f"refs/heads/{result['pi_cloud']['branch']}")
        self.assertEqual(listed, "")

    # ------------------------------------------------------------- R5 and R7

    def test_r5_and_r7_a_supervisor_death_after_the_worker_settled(self):
        stub_preflight(self)
        run_dir = self.run_dir()
        key1 = self._plan(run_dir, 1, 1, ["success"])
        self._plan(run_dir, 1, 2, ["settled"])
        workflow = simple_workflow(self.repo, steps=[pi_cloud_step()])
        self._open_attempt(workflow, run_dir)

        self._run(workflow, run_dir, resume=True)

        # One attempt, started by the dead supervisor and continued by the
        # resume; the worktree fast-forwarded and the branch was deleted.
        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts], [(1, "initial"), (1, "reattach")])
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        result = json.loads((self.attempt_dir(run_dir, 1) / "result.json")
                            .read_text(encoding="utf-8"))
        self.assertIsNone(result["error"], result["error"])
        cloud = result["pi_cloud"]
        self.assertTrue(cloud["pushed"])
        self.assertTrue(cloud["branch_deleted"])
        self.assertEqual(cloud["key"], key1)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), cloud["head"])
        listed = git(self.tmp, "ls-remote", self.origin.as_posix(),
                     f"refs/heads/{cloud['branch']}")
        self.assertEqual(listed, "")
        # The dead supervisor's post was the object's first (accepted); the
        # resume's post is the repeat with the same operation id, answered as
        # a reattach, and the replay ended with `pi_cloud_end` at once.
        answers = self.worker.step_answers[key1]
        self.assertEqual([(a["accepted"], a["reattach"]) for a in answers],
                         [(True, False), (False, True)])
        state = RunLog.replay(run_dir)
        self.assertEqual(ohattempts.attempts(state, COORD), 2)
        self.assertEqual(ohattempts.failed_executions(state, COORD), 0)

    # ------------------------------------------------------------- R4 and R8

    def test_r4_and_r8_a_401_during_a_reconnect_is_an_http_error_not_a_reattach(self):
        self._set_env("OHFLOW_PI_CLOUD_RETRY_S", "0.2")
        stub_preflight(self)
        run_dir = self.run_dir()
        self._plan(run_dir, 1, 1, ["refuse", "unauthorized"])
        workflow = simple_workflow(self.repo, on_step_failure="continue",
                                   steps=[pi_cloud_step()])
        self._run(workflow, run_dir)

        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts], [(1, "initial")])
        self.assertEqual(step_statuses(run_dir)[COORD], "failed")
        result = json.loads((self.attempt_dir(run_dir, 1) / "result.json")
                            .read_text(encoding="utf-8"))
        self.assertTrue(result["error"].startswith("HTTPError: HTTP 401"),
                        result["error"])
        self.assertFalse(result["error"].startswith("host_lost"))
        self.assertEqual(result["pi_cloud"]["aborted"], False)

    # ------------------------------------------------------------- R6 and R2

    def test_r6_and_r2_after_a_stalls_abort_the_retry_gets_a_new_object(self):
        stub_preflight(self)
        run_dir = self.run_dir()
        key1 = self._plan(run_dir, 1, 1, ["silent"])
        key2 = self._plan(run_dir, 2, 1, ["success"])
        workflow = simple_workflow(self.repo, steps=[pi_cloud_step(
            stall_timeout_s=6, retry=RetryPolicy(max=1, on=("agent_error",)))])
        self._run(workflow, run_dir)

        starts = self._events(run_dir, "attempt_started")
        self.assertEqual([(r["attempt"], r["payload"]["start_kind"])
                          for r in starts], [(1, "initial"), (2, "retry")])
        self.assertEqual(step_statuses(run_dir)[COORD], "passed")
        # The stall's abort named attempt 1's object, and the retry's step
        # post went to attempt 2's own object, accepted, with no 409.
        self.assertEqual(self.worker.aborted, [key1])
        [answer1] = self.worker.step_answers[key1]
        [answer2] = self.worker.step_answers[key2]
        self.assertEqual((answer1["accepted"], answer1["reattach"]),
                         (True, False))
        self.assertEqual((answer2["accepted"], answer2["reattach"]),
                         (True, False))
        self.assertNotEqual(self.worker.step_answers[key1][0]["branch"],
                            answer2["branch"])
        posted = [r for r in self.worker.requests if r["path"].endswith("/step")]
        self.assertEqual(len(posted), 2)

    # ------------------------------------------------------------- the open attempt

    def _open_attempt(self, workflow, run_dir: Path) -> Path:
        """The run log and attempt directory a dead supervisor leaves behind.

        Attempt 1 started and never closed; its runner had already pushed the
        start commit and posted `step` - the object's first post - and the
        Worker settled and pushed while the supervisor was dying, so the
        resume's reattach finds the whole answer on the branch.
        """
        fp = fingerprint(workflow, RunState(), workflow.phases[0].steps[0])
        opener = self._engine(workflow, run_dir)
        opener._transition("run_started", payload={
            "run_id": run_dir.name, "workflow": workflow.name, "meta": {}})
        opener._transition("attempt_started", coord_=COORD, attempt=1, payload={
            "step_id": "s1", "kind": "agent", "fingerprint": fp,
            "start_kind": "initial"})
        attempt_dir = self.attempt_dir(run_dir, 1)
        attempt_dir.mkdir(parents=True)
        key = self.key_of(run_dir, 1)
        branch = self.branch_for(key)
        from ohflow import remote_git
        start_sha = remote_git.push_start(self.repo, branch)
        # The dead supervisor's runner had already posted `step`: the post
        # the adapter makes, accepted, and then the Worker settled and pushed
        # the answer onto the branch while the supervisor was dying.
        answer = self.post_step(key, branch, start_sha)
        self.assertEqual(answer["accepted"], True)
        self.worker.head_for(key, self.worker.step_body(key))
        (attempt_dir / "spec.json").write_text(json.dumps(
            {"coord": COORD, "attempt": 1, "role": "role-s1",
             "harness_executor": "pi-cloud", "workspace": str(self.repo),
             "model": {"model": "zai/glm-5.3-flash", "base_url": "",
                       "api_key_env": "", "params": {"thinking": "low"},
                       "extra_body": {}},
             "tools": {"preset": "default", "enable_browser": False,
                       "enable_sub_agents": False, "only": [], "allow": []},
             "skills": [], "skills_dir": None, "mcp_config": None,
             "max_iterations": 30, "command_time_cap_s": None,
             "execution_timeout_s": 5400, "stall_timeout_s": None,
             "write_scope": [], "fork_session": None,
             "brief_path": "brief.md", "schema_path": None,
             "out_dir": "."}, indent=2), encoding="utf-8")
        (attempt_dir / "brief.md").write_text(
            "# Task\ndo the trivial thing\n", encoding="utf-8")
        (attempt_dir / "remote.json").write_text(json.dumps({
            "url": self.worker.url, "key": key, "branch": branch,
            "remote_url": self.origin.as_posix(),
            "start_sha": start_sha}, indent=2), encoding="utf-8")
        logs = attempt_dir / "logs"
        logs.mkdir()
        seen = logs / "pi-cloud-events.jsonl"
        seen.write_text("", encoding="utf-8")
        at = time.time() + 30
        import os
        os.utime(seen, (at, at))
        return attempt_dir
