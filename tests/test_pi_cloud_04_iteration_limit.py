"""The cloud executors forward `max_iterations`, and a looping agent stops at it.

The fake Worker's `loop` behaviour is an agent that calls a tool in every turn
and never answers. What is proved:

- every cloud executor posts the step's `max_iterations` in the `step` body;
- a Worker that acknowledges the limit ends the loop itself, `unanswered`,
  `turn_limit`, after that many rounds: the runner records `max iterations N
  exceeded`, counts N model calls, posts no abort and records the effective
  limit with `max_iterations_enforced_by: worker`;
- a Worker that names no limit leaves pi-cloud to ohflow's own count, which
  stops the stream at the Nth tool-use turn and aborts the object;
- `claude-cloud` and `codex-cloud` post the limit and record the Worker's
  verdict the same way.
"""

from __future__ import annotations

from ohflow import harness_executors
from pi_cloud_support import PiCloudCase

LIMIT = 3


class IterationLimit(PiCloudCase):

    def test_the_step_body_carries_the_limit(self):
        key = self.key_of(self.tmp / "body")
        self.worker.plan(key, 1, ["success"])
        _out_dir, result = self.run_attempt("body", max_iterations=17)
        posted = next(r["body"] for r in self.worker.requests
                      if r["path"].endswith("/step"))
        self.assertEqual(posted["max_iterations"], 17)
        self.assertIsNone(result["error"], result["error"])
        effective = result["settings"]["effective"]
        self.assertEqual((effective["max_iterations"],
                          effective["max_iterations_enforced_by"]), (17, "worker"))

    def test_the_worker_ends_a_loop_at_the_limit(self):
        key = self.key_of(self.tmp / "loop")
        self.worker.plan(key, 1, ["loop"])
        _out_dir, result = self.run_attempt("loop", max_iterations=LIMIT)
        self.assertEqual(result["error"], f"max iterations {LIMIT} exceeded")
        self.assertEqual(result["llm_calls"], LIMIT)
        self.assertEqual(result["tool_calls"], LIMIT)
        self.assertEqual((result["pi_cloud"]["status"], result["pi_cloud"]["reason"]),
                         ("unanswered", "turn_limit"))
        self.assertTrue(result["pi_cloud"]["pushed"])
        self.assertEqual(self.worker.aborted, [])
        effective = result["settings"]["effective"]
        self.assertEqual((effective["max_iterations"],
                          effective["max_iterations_enforced_by"]), (LIMIT, "worker"))

    def test_ohflow_counts_when_the_worker_names_no_limit(self):
        self.worker.enforces_limit = False
        key = self.key_of(self.tmp / "local")
        self.worker.plan(key, 1, ["loop"])
        _out_dir, result = self.run_attempt("local", max_iterations=LIMIT)
        self.assertEqual(result["error"], f"max iterations {LIMIT} exceeded")
        self.assertEqual(result["llm_calls"], LIMIT)
        self.assertEqual(self.worker.aborted, [key])
        effective = result["settings"]["effective"]
        self.assertEqual((effective["max_iterations"],
                          effective["max_iterations_enforced_by"]), (LIMIT, "ohflow"))

    def test_the_cli_executors_forward_the_limit_and_leave_it_to_the_worker(self):
        for name, model in (("claude-cloud", "claude-haiku-4-5-20251001"),
                            ("codex-cloud", "gpt-5.6-luna")):
            with self.subTest(harness_executor=name):
                self.executor = harness_executors.harness_executor_for(name)
                key = self.key_of(self.tmp / name)
                self.worker.plan(key, 1, ["loop"])
                _out_dir, result = self.run_attempt(
                    name, harness_executor=name, max_iterations=LIMIT,
                    model={"model": model, "base_url": "", "api_key_env": "",
                           "params": {}, "extra_body": None})
                posted = [r["body"] for r in self.worker.requests
                          if r["path"].startswith(f"/{name.split('-')[0]}/")
                          and r["path"].endswith("/step")]
                self.assertEqual(posted[-1]["max_iterations"], LIMIT)
                self.assertEqual(result["error"], f"max iterations {LIMIT} exceeded")
                effective = result["settings"]["effective"]
                self.assertEqual((effective["max_iterations"],
                                  effective["max_iterations_enforced_by"]),
                                 (LIMIT, "worker"))
