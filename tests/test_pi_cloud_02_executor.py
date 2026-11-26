"""The pi-cloud harness executor: launch, adapter and the three end outcomes.

The real `PiCloudHarnessExecutor` runs against the fake Worker, over a real
repository with a real bare `origin`, so the transport - `push_start`, the
Worker clone, `fetch_result`, `delete_branch` - is the real git path. What is
proved:

- R1: a fresh attempt pushes its start commit to `ohflow/pi-cloud/<key>` on
  origin before it posts `step`, and the post names that commit;
- R2: the Durable Object's name and the operation id are both the attempt
  key, and the branch sits under the executor's own prefix;
- R7: a pushed end fetches the head and deletes the branch, an unpushed end
  is `push_failed` and fetches nothing, a failed clone is `clone_failed`, and
  any status other than `done` is `unanswered`;
- the posted brief names only the Worker's folders, and the transcript, the
  usage and the handover are copied into the attempt directory;
- F3: every request the fake records - the preflight's root probe included -
  carries both headers, which one function builds;
- F4: both remote executors rewrite one brief and word their model errors
  through the shared rules (`remote_git.rewrite_paths`,
  `pi_runner.model_errors`), unchanged apart from each executor's own name;
- `agent_errors` refuses every field that would configure a tool, a server or
  a second machine the Worker does not offer;
- R9: the token appears in no file the attempt directory holds.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import replace
from pathlib import Path

from ohflow.workflow import AgentSpec, ModelConfig, ToolPolicy
from pi_cloud_support import TOKEN, PiCloudCase, git

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pi_cloud"


def _model(**changes) -> ModelConfig:
    base = ModelConfig(model="zai/glm-5.3-flash", base_url="", api_key_env="",
                       params={"thinking": "low"})
    return replace(base, **changes) if changes else base


def _agent(**changes) -> AgentSpec:
    base = AgentSpec(role="rollcall", brief="do the trivial thing",
                     model=_model(), harness_executor="pi-cloud")
    return replace(base, **changes) if changes else base


class ExecutorCase(PiCloudCase):

    def test_a_fresh_attempt_pushes_its_start_before_it_posts_step(self):
        key = self.key_of(self.tmp / "r1")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("r1")
        remote = json.loads((out_dir / "remote.json").read_text(encoding="utf-8"))
        self.assertTrue(remote["branch"].startswith("ohflow/pi-cloud/"))
        self.assertEqual(remote["branch"], self.branch_for(key))
        # The branch sat at the start commit on origin when the post arrived,
        # and the post named that same commit (R1).
        seen = self.worker.transport_at_step[key]
        self.assertEqual(seen["branch"], remote["branch"])
        self.assertEqual(seen["on_origin"], remote["start_sha"])
        self.assertEqual(seen["start_sha"], remote["start_sha"])
        # The launch's own push is the only one: HEAD had not moved yet.
        self.assertEqual(remote["start_sha"], seen["on_origin"])
        self.assertIsNone(result["error"], result["error"])

    def test_the_object_name_and_operation_id_are_both_the_key(self):
        key = self.key_of(self.tmp / "r2")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("r2")
        quoted = urllib.parse.quote(key, safe="")
        steps = [r for r in self.worker.requests if r["path"].endswith("/step")]
        self.assertEqual([r["path"] for r in steps],
                         [f"/attempts/{quoted}/step"])
        self.assertEqual(steps[0]["body"]["operationId"], key)
        events = [r for r in self.worker.requests if "/events" in r["path"]]
        self.assertTrue(events)
        for request in events:
            self.assertEqual(request["path"],
                             f"/attempts/{quoted}/events"
                             f"?operationId={quoted}")
        self.assertEqual(result["conversation_id"], key)
        self.assertEqual(result["pi_cloud"]["key"], key)

    def test_a_pushed_end_fetches_the_head_and_deletes_the_branch(self):
        key = self.key_of(self.tmp / "pushed")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("pushed")
        self.assertIsNone(result["error"], result["error"])
        self.assertEqual(result["execution_status"], "finished")
        cloud = result["pi_cloud"]
        self.assertEqual(cloud["status"], "done")
        self.assertTrue(cloud["pushed"])
        self.assertTrue(cloud["branch_deleted"])
        self.assertEqual(cloud["dirty"], ["?? __pycache__/calc.cpython-313.pyc",
                                          "?? __pycache__/test_calc.cpython-313.pyc"])
        self.assertEqual(cloud["head"], git(self.repo, "rev-parse", "HEAD"))
        self.assertNotEqual(cloud["head"], cloud["start_sha"])
        listed = git(self.tmp, "ls-remote", self.origin.as_posix(),
                     f"refs/heads/{cloud['branch']}")
        self.assertEqual(listed, "")

    def test_an_unpushed_end_is_the_push_failed_error(self):
        key = self.key_of(self.tmp / "pushfail")
        self.worker.plan(key, 1, ["pushfail"])
        out_dir, result = self.run_attempt("pushfail")
        self.assertEqual(result["error"],
                         "push_failed: origin refused the push")
        cloud = result["pi_cloud"]
        self.assertFalse(cloud["pushed"])
        self.assertFalse(cloud["branch_deleted"])
        # Nothing was fetched: the worktree is still on its own start commit.
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), cloud["start_sha"])
        listed = git(self.tmp, "ls-remote", self.origin.as_posix(),
                     f"refs/heads/{cloud['branch']}")
        self.assertEqual(listed.split()[0], cloud["start_sha"])

    def test_a_failed_clone_is_the_clone_failed_error(self):
        key = self.key_of(self.tmp / "clonefail")
        self.worker.plan(key, 1, ["clonefail"])
        _out_dir, result = self.run_attempt("clonefail")
        self.assertEqual(result["error"], "clone_failed: repository not found")

    def test_an_unanswered_end_is_the_unanswered_error(self):
        key = self.key_of(self.tmp / "aborted")
        self.worker.plan(key, 1, ["aborted"])
        out_dir, result = self.run_attempt("aborted")
        self.assertEqual(result["error"], "unanswered: aborted")
        self.assertEqual(result["execution_status"], "error")
        cloud = result["pi_cloud"]
        self.assertEqual(cloud["status"], "unanswered")
        self.assertEqual(cloud["reason"], "aborted")

    def test_the_posted_brief_names_only_the_workers_folders(self):
        key = self.key_of(self.tmp / "brief")
        out_dir = self.tmp / "brief"
        self.worker.plan(key, 1, ["success"])
        _out_dir, result = self.run_attempt("brief")
        posted = next(r["body"] for r in self.worker.requests
                      if r["path"].endswith("/step"))
        brief = posted["brief"]
        self.assertIn("/workspace/repo", brief)
        self.assertIn("/workspace/out", brief)
        self.assertNotIn(str(self.repo), brief)
        self.assertNotIn(self.repo.as_posix(), brief)
        self.assertNotIn(str(out_dir), brief)
        self.assertNotIn(out_dir.as_posix(), brief)
        # The staged copy the adapter wrote is the same text.
        staged = (out_dir / "remote" / "brief.md").read_text(encoding="utf-8")
        self.assertEqual(staged, brief)
        self.assertEqual(posted["model"], "zai/glm-5.3-flash")
        self.assertEqual(posted["thinking"], "low")
        self.assertEqual(posted["ohflow"], {"coord": "01.report/01.s1",
                                            "attempt": 1, "key": key})
        self.assertEqual(posted["tools"], {"allow": [], "block": []})

    def test_the_step_post_carries_the_mcp_tool_policy(self):
        key = self.key_of(self.tmp / "policy")
        self.worker.plan(key, 1, ["success"])
        tools = {"preset": "default", "enable_browser": False,
                 "enable_sub_agents": False, "only": [],
                 "allow": ["brave-search.*"], "block": ["brave-search.brave_image_*"]}
        self.run_attempt("policy", tools=tools)
        posted = next(r["body"] for r in self.worker.requests
                      if r["path"].endswith("/step"))
        self.assertEqual(posted["tools"], {"allow": ["brave-search.*"],
                                           "block": ["brave-search.brave_image_*"]})

    def test_the_step_post_carries_the_named_skills(self):
        key = self.key_of(self.tmp / "skills")
        self.worker.plan(key, 1, ["success"])
        self.run_attempt("skills", skills=["codebase-design"])
        posted = next(r["body"] for r in self.worker.requests
                      if r["path"].endswith("/step"))
        self.assertEqual(posted["skills"], ["codebase-design"])

    def test_the_transcript_usage_and_handover_are_copied(self):
        key = self.key_of(self.tmp / "copies")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("copies")
        self.assertEqual(
            (out_dir / "transcript.md").read_text(encoding="utf-8"),
            (FIXTURES / "transcript.md").read_text(encoding="utf-8"))
        self.assertEqual(
            (out_dir / "handover.md").read_text(encoding="utf-8"),
            (FIXTURES / "handover.md").read_text(encoding="utf-8"))
        end = next(json.loads(line) for line in
                   (out_dir / "logs" / "pi-cloud-events.jsonl")
                   .read_text(encoding="utf-8").splitlines()
                   if '"pi_cloud_end"' in line)
        usage = json.loads((out_dir / "usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage, end["usage"])
        # The saved step answer and the announced tools agree.
        answer = json.loads(
            (out_dir / "pi-cloud-step.json").read_text(encoding="utf-8"))
        self.assertEqual(result["tools"], answer["tools"])

    def test_f3_the_preflight_and_every_runner_request_carry_both_headers(self):
        # The preflight's own root probe first, then a whole attempt: the
        # step post, the events stream and the two text routes.
        self.assertEqual(self.module.preflight(), [])
        self.assertEqual(self.worker.requests[0]["method"], "GET")
        self.assertEqual(self.worker.requests[0]["path"], "/")
        key = self.key_of(self.tmp / "headers")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("headers")
        self.assertIsNone(result["error"], result["error"])
        paths = [r["path"] for r in self.worker.requests]
        self.assertIn("/", paths)
        self.assertTrue(any(p.endswith("/step") for p in paths))
        self.assertTrue(any("/events" in p for p in paths))
        self.assertGreaterEqual(len(self.worker.requests), 5)
        for request in self.worker.requests:
            self.assertTrue(request["auth"], request)
            self.assertEqual(request["user_agent"], "ohflow-pi-cloud/1")

    def test_f4_both_executors_rewrite_one_brief_through_the_shared_rule(self):
        from ohflow import durable_runner
        brief = ("# Task\n\nThe repo is at C:\\wt\\repo (or C:/wt/repo); "
                 "the run dir is C:\\runs\\r\\a1 (or C:/runs/r/a1).\n")
        self.assertEqual(
            self.module._rewrite_brief(brief, "C:\\wt\\repo", "C:\\runs\\r\\a1"),
            "# Task\n\nThe repo is at /workspace/repo (or /workspace/repo); "
            "the run dir is /workspace/out (or /workspace/out).\n")
        self.assertEqual(
            durable_runner._rewrite_brief(brief, "C:\\wt\\repo",
                                          "C:\\runs\\r\\a1",
                                          Path("C:\\box\\pi\\k1")),
            "# Task\n\nThe repo is at C:\\box\\pi\\k1\\work "
            "(or C:\\box\\pi\\k1\\work); "
            "the run dir is C:\\box\\pi\\k1 (or C:\\box\\pi\\k1).\n")

    def test_f4_both_executors_word_one_model_check_in_their_own_name(self):
        from ohflow import durable_runner
        where = "01.report/01.s1"
        bad = _agent(model=_model(
            model="openai/glm-5.3-flash",
            params={"temperature": 0.2, "thinking": "ultra"},
            extra_body={"x": 1}, api_key_env="ZAI_KEY"))
        # A durable agent names its box; a pi-cloud agent has none to name.
        # The model faults are the same five either way, each in the
        # executor's name.
        box_bad = replace(bad, box="buildbox")
        self.assertEqual(
            self.module.agent_errors(where, bad),
            [f"{where}: pi-cloud model must be provider/id with the provider "
             f"one of ['deepseek', 'zai'], got 'openai/glm-5.3-flash'",
             f"{where}: pi-cloud model params are closed; "
             f"unsupported [\"'temperature'\"]. Known: ['thinking']",
             f"{where}: pi-cloud model param 'thinking' must be one of "
             f"['high', 'low', 'max', 'medium', 'minimal', 'off', 'xhigh'], "
             f"got 'ultra'",
             f"{where}: pi-cloud refuses ModelConfig.extra_body; use a "
             "supported model param",
             f"{where}: pi-cloud model api_key_env must be empty; "
             "the Worker holds its keys"])
        self.assertEqual(
            durable_runner.agent_errors(where, box_bad),
            [f"{where}: durable model must be provider/id with the provider "
             f"one of ['deepseek', 'zai'], got 'openai/glm-5.3-flash'",
             f"{where}: durable model params are closed; "
             f"unsupported [\"'temperature'\"]. Known: ['thinking']",
             f"{where}: durable model param 'thinking' must be one of "
             f"['high', 'low', 'max', 'medium', 'minimal', 'off', 'xhigh'], "
             f"got 'ultra'",
             f"{where}: durable refuses ModelConfig.extra_body; use a "
             "supported model param",
             f"{where}: durable model api_key_env must be empty; "
             "the host holds its keys on its own box"])

    def test_agent_errors_accepts_the_worker_plain_spec_and_refuses_the_rest(self):
        where = "01.report/01.s1"
        self.assertEqual(self.module.agent_errors(where, _agent()), [])
        refusals = [
            (_agent(agent_profile="hermetic"), "agent_profile"),
            (_agent(model=_model(model="openai/glm-5.3-flash")), "provider"),
            (_agent(model=_model(params={"temperature": 0.2})), "params are closed"),
            (_agent(model=_model(params={"thinking": "ultra"})), "thinking"),
            (_agent(model=_model(extra_body={"x": 1})), "extra_body"),
            (_agent(model=_model(api_key_env="ZAI_KEY")), "api_key_env"),
            (_agent(tools=ToolPolicy(only=("terminal",))), "tools.only"),
            (_agent(tools=ToolPolicy(preset="minimal")), "preset"),
            (_agent(tools=ToolPolicy(enable_browser=True)), "browser"),
            (_agent(tools=ToolPolicy(enable_sub_agents=True)), "sub_agents"),
            (_agent(mcp_config={"cortex": {}}), "mcp_config"),
            (_agent(skills_dir=Path("/x")), "skills_dir"),
        ]
        for agent, why in refusals:
            with self.subTest(why=why):
                [fault] = self.module.agent_errors(where, agent)
                self.assertIn("pi-cloud", fault)
                self.assertIn(why, fault)
        policy = ToolPolicy(allow=("brave-search.*",), block=("brave-search.brave_image_*",))
        self.assertEqual(self.module.agent_errors(where, _agent(tools=policy)), [])
        self.assertEqual(self.module.agent_errors(where, _agent(skills=("codebase-design",))), [])

    def test_the_announced_mcp_servers_come_from_pi_cloud_start(self):
        events = [{"type": "pi_cloud_start", "tools": ["exec", "codemode"],
                   "mcp_servers": ["brave-search", "deepthink"]}]
        self.assertEqual(self.module._announced(events, self.tmp, "mcp_servers"),
                         ["brave-search", "deepthink"])
        self.assertEqual(self.module._announced([], self.tmp, "mcp_servers"), [])

    def test_tools_allow_names_only_the_servers_of_the_box(self):
        from ohflow.workflow import _mcp_tool_policy_errors
        where = "01.report/01.s1"
        ok = _agent(tools=ToolPolicy(allow=("sequential-thinking.*",)))
        self.assertEqual(_mcp_tool_policy_errors(where, ok), [])
        [fault] = _mcp_tool_policy_errors(
            where, _agent(tools=ToolPolicy(allow=("forum.post",))))
        self.assertIn("unconfigured server 'forum'", fault)

    def test_resume_target_is_none_and_reattach_target_names_the_object(self):
        key = self.key_of(self.tmp / "target")
        self.worker.plan(key, 1, ["success"])
        out_dir, result = self.run_attempt("target")
        self.assertIsNone(self.module.resume_target(result, out_dir))
        quoted = urllib.parse.quote(key, safe="")
        self.assertEqual(self.module.reattach_target(out_dir),
                         f"{self.worker.url}/attempts/{quoted}")
        self.assertIsNone(self.module.reattach_target(self.tmp / "nowhere"))
        bare = self.tmp / "bare"
        bare.mkdir()
        (bare / "remote.json").write_text('{"url": "http://x", "branch": "b"}',
                                          encoding="utf-8")
        self.assertIsNone(self.module.reattach_target(bare))

    def test_preflight_names_the_unset_refused_and_unreachable_faults(self):
        from pi_cloud_support import override_env
        self.assertEqual(self.module.preflight(), [])
        with override_env("PI_CLOUD_TOKEN", ""):
            faults = self.module.preflight()
            self.assertEqual(len(faults), 1)
            self.assertIn("PI_CLOUD_TOKEN", faults[0])
            self.assertIn(self.worker.url, faults[0])
        with override_env("PI_CLOUD_TOKEN", "a-wrong-token"):
            faults = self.module.preflight()
            self.assertEqual(faults, [f"the pi-cloud Worker at "
                                      f"{self.worker.url} refused "
                                      f"PI_CLOUD_TOKEN (HTTP 401); check the "
                                      f"token"])
        with override_env("OHFLOW_PI_CLOUD_URL", "http://127.0.0.1:1"):
            faults = self.module.preflight()
            self.assertEqual(len(faults), 1)
            self.assertIn("unreachable", faults[0])
            self.assertIn("http://127.0.0.1:1", faults[0])
        # The fake still accepts the test's own token after all that.
        self.assertEqual(self.module.preflight(), [])

    def test_the_token_is_in_no_file_of_the_attempt_directory(self):
        key = self.key_of(self.tmp / "r9")
        self.worker.plan(key, 1, ["success"])
        out_dir, _result = self.run_attempt("r9")
        files = [p for p in out_dir.rglob("*") if p.is_file()]
        self.assertGreater(len(files), 6)
        for path in files:
            self.assertNotIn(TOKEN, path.read_text(encoding="utf-8",
                                                   errors="replace"),
                             f"{path.name} holds the token")
