"""D-39: one detach helper, with a launch method that survives a restrictive job.

Before: `run --detach` and `campaign run --detach` each started their child
inline. A launcher inside a restrictive Windows Job Object got WinError 5 from
`run --detach`, which refused, and an uncaught traceback from `campaign run
--detach`.
Now: both call `detach.launch`. It breaks away from the job when the job allows
it, starts the child through WMI `Win32_Process.Create` (wrapped in
`run-hidden.vbs`) when the job denies breakaway, and raises `DetachFailed`
when neither works. The CLI prints which launch method started the child. On failure
it prints guidance, exits 1, and prints no traceback.

The child process is faked: `proc.popen` stands in for the direct start and
`proc.run` stands in for the `run-hidden.vbs` call. The real WMI launch method is
exercised in `test_defect_07_detached_run_survives`.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ohflow import IMPORT_ROOT, cli, detach
from support import TempCase, git_repo, quiet

WORKFLOW_MODULE = '''
from pathlib import Path
from ohflow.workflow import (CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
                             AgentSpec)


def build(args):
    return Workflow(
        name="detach-workflow", repo=Path(args["repo"]), base_branch="main",
        max_parallel=1, transient_backoff_s=0,
        phases=(Phase(name="Only phase", steps=(Step(
            id="only", kind="agent",
            gate=GateSpec(checks=(CheckSpec("final_message_matches",
                                            {"regex": "DONE"}),)),
            agent=AgentSpec(harness_executor="pi", 
                role="only", brief="do the trivial thing",
                model=ModelConfig(model="fake/deterministic",
                                  base_url="http://127.0.0.1:0/never-called",
                                  api_key_env="OHFLOW_TEST_FAKE_KEY"),
                max_iterations=3),
        ),)),),
    )
'''

CAMPAIGN_MODULE = '''
from pathlib import Path
from ohflow.campaign import Campaign, Milestone
from ohflow.workflow import ModelConfig, AgentSpec


def build(args):
    here = Path(__file__).resolve().parent
    judge = AgentSpec(harness_executor="pi", 
        role="milestone-judge", brief="", max_iterations=3,
        model=ModelConfig(model="fake/deterministic",
                          base_url="http://127.0.0.1:0/never-called",
                          api_key_env="OHFLOW_TEST_FAKE_KEY"))
    milestone = Milestone(id="m1", title="first", workflow="m1/workflow.py",
                          spec="m1/spec.md", args={})
    return Campaign(name="detach-campaign", root=here, repo=here,
                    charter="charter.md", milestones=(milestone,),
                    integration_branch="integration_branch", judge=judge, auto_resume=0)
'''

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BREAKAWAY = CREATE_NO_WINDOW | getattr(
    subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)


def denied() -> OSError:
    error = OSError(13, "access denied")
    error.winerror = 5
    return error


class DetachLaunchMethods(TempCase):

    def setUp(self) -> None:
        super().setUp()
        repo = git_repo(self.tmp / "repo")
        self.workflow = self.tmp / "workflow.py"
        self.workflow.write_text(WORKFLOW_MODULE, encoding="utf-8")
        self.camp_dir = self.tmp / "camp"
        self.camp_dir.mkdir()
        self.campaign_file = self.camp_dir / "campaign.py"
        self.campaign_file.write_text(CAMPAIGN_MODULE, encoding="utf-8")
        self.out_root = self.tmp / "runs"
        self.shim = self.tmp / "run-hidden.vbs"
        self.shim.write_text("' stand-in\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ,
                                  {"OHFLOW_RUN_HIDDEN": str(self.shim)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = repo
        self.shim_calls: list[list[str]] = []
        self.shim_envs: list[dict] = []
        self.direct_calls: list[dict] = []

    # The two commands that detach. Each returns (exit code, output, log path,
    # pid file, the directory that must be gone after a failed launch or None).
    def start(self, kind: str):
        with quiet() as output:
            if kind == "run":
                code = cli.main(["run", "--workflow", str(self.workflow), "--out",
                                 str(self.out_root), "--run-id", "r-detach",
                                 "--detach", "--json", "--args",
                                 f"repo={self.repo}"],
                                harness_executors=self.harness_executors)
            else:
                code = cli.main(["campaign", "run", "--campaign",
                                 str(self.campaign_file), "--detach",
                                 "--no-dashboard"])
        run_dir = self.out_root / "r-detach"
        if kind == "run":
            return code, output.out, run_dir / "supervisor.log", \
                run_dir / "supervisor.pid", run_dir
        return code, output.out, self.camp_dir / "campaign.log", \
            self.camp_dir / "campaign.pid", None

    def shim_answers(self, *, code: int, pid: int | None):
        def fake_run(argv, **kw):
            self.shim_calls.append(list(argv))
            self.shim_envs.append(dict(kw["env"]))
            ps1 = Path(argv[-1])
            if pid is not None:
                ps1.with_name(ps1.name.replace(".ps1", ".pid")).write_text(
                    str(pid), encoding="ascii")
            return subprocess.CompletedProcess(argv, code, b"", b"")
        return mock.patch.object(detach.proc, "run", fake_run)

    @staticmethod
    def printed_json(text: str) -> dict:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])

    def test_detach_when_the_job_allows_breakaway_the_child_breaks_away(self):
        for kind in ("run", "campaign"):
            with self.subTest(kind=kind):
                self.direct_calls.clear()
                with mock.patch.object(detach, "creationflags",
                                       return_value=(BREAKAWAY, True)), \
                     mock.patch.object(detach.proc, "popen",
                                       side_effect=self._record_popen):
                    code, out, log, pid_file, _ = self.start(kind)
                self.assertEqual(code, cli.EXIT_OK, out)
                self.assertEqual(self.printed_json(out)["launch_method"], "breakaway")
                self.assertEqual(self.direct_calls[0]["creationflags"],
                                 BREAKAWAY)
                self.assertEqual(pid_file.read_text(), "4242")
                self.assertEqual(self.shim_calls, [])
                self._reset(kind)

    def test_detach_when_the_job_denies_breakaway_wmi_starts_the_child(self):
        for kind in ("run", "campaign"):
            with self.subTest(kind=kind):
                self.shim_calls.clear()
                with mock.patch.object(detach, "creationflags",
                                       return_value=(BREAKAWAY, True)), \
                     mock.patch.object(detach.proc, "popen",
                                       side_effect=lambda *a, **k: _raise()), \
                     self.shim_answers(code=0, pid=777):
                    code, out, log, pid_file, _ = self.start(kind)
                self.assertEqual(code, cli.EXIT_OK, out)
                launched = self.printed_json(out)
                self.assertEqual(launched["launch_method"], "wmi")
                self.assertEqual(launched["pid"], 777)
                self.assertEqual(pid_file.read_text(), "777")

                shim_argv = self.shim_calls[0]
                self.assertEqual(shim_argv[0], "wscript.exe")
                self.assertIn(str(self.shim), shim_argv)
                self.assertEqual(shim_argv[shim_argv.index(str(self.shim)) + 1],
                                 "powershell.exe")
                cmd_text = Path(str(log) + ".launch.cmd").read_text(
                    encoding="utf-8")
                self.assertIn(f'cd /d "{IMPORT_ROOT}"', cmd_text)
                self.assertIn("-m ohflow.cli", cmd_text)
                self.assertIn(f'>> "{log}" 2>&1', cmd_text)
                self.assertEqual(self.shim_envs[0]["PYTHONIOENCODING"],
                                 "utf-8:replace")
                self.assertIn("PYTHONPATH", self.shim_envs[0])
                self.assertNotIn("PYTHONIOENCODING", cmd_text)
                ps1_text = Path(str(log) + ".launch.ps1").read_text(
                    encoding="utf-8-sig")
                self.assertIn("Win32_Process", ps1_text)
                self.assertIn("EnvironmentVariables", ps1_text)
                self.assertIn(f"CurrentDirectory = '{IMPORT_ROOT}'", ps1_text)
                self._reset(kind)

    def test_detach_when_both_launch_methods_fail_the_guidance_has_no_traceback(self):
        for kind in ("run", "campaign"):
            with self.subTest(kind=kind):
                with mock.patch.object(detach, "creationflags",
                                       return_value=(BREAKAWAY, True)), \
                     mock.patch.object(detach.proc, "popen",
                                       side_effect=lambda *a, **k: _raise()), \
                     self.shim_answers(code=1, pid=None):
                    code, out, log, pid_file, reservation = self.start(kind)
                self.assertEqual(code, cli.EXIT_FAIL, out)
                self.assertIn("restrictive Windows Job Object", out)
                self.assertIn("WMI launch method failed", out)
                self.assertIn("outside that job", out)
                self.assertIn("independent broker", out)
                self.assertNotIn("Traceback", out)
                self.assertFalse(pid_file.exists())
                if reservation is not None:
                    self.assertFalse(reservation.exists(),
                                     "the failed launch kept its reservation")
                self._reset(kind)

    def test_detach_without_the_shim_names_the_missing_file(self):
        self.shim.unlink()
        with mock.patch.object(detach, "creationflags",
                               return_value=(BREAKAWAY, True)), \
             mock.patch.object(detach.proc, "popen",
                               side_effect=lambda *a, **k: _raise()):
            code, out, *_ = self.start("campaign")
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertIn("the hidden-launch shim is missing", out)
        self.assertNotIn("Traceback", out)

    def test_detach_outside_a_job_starts_the_child_directly(self):
        with mock.patch.object(detach, "creationflags",
                               return_value=(CREATE_NO_WINDOW,
                                             False)), \
             mock.patch.object(detach.proc, "popen",
                               side_effect=self._record_popen):
            code, out, *_ = self.start("campaign")
        self.assertEqual(code, cli.EXIT_OK, out)
        self.assertEqual(self.printed_json(out)["launch_method"], "direct")

    def test_detach_an_error_that_is_not_a_denied_breakaway_is_not_retried(self):
        def broken(*a, **k):
            raise OSError(2, "no such file")
        with mock.patch.object(detach, "creationflags",
                               return_value=(BREAKAWAY, True)), \
             mock.patch.object(detach.proc, "popen", broken), \
             self.shim_answers(code=0, pid=1):
            code, out, *_ = self.start("campaign")
        self.assertEqual(code, cli.EXIT_FAIL)
        self.assertEqual(self.shim_calls, [])
        self.assertIn("no such file", out)

    def _record_popen(self, argv, **kw):
        self.direct_calls.append({"argv": list(argv), **kw})
        return mock.Mock(pid=4242)

    def _reset(self, kind: str) -> None:
        for path in list(self.out_root.glob("*")):
            for child in path.glob("*"):
                child.unlink()
            path.rmdir()
        for name in ("campaign.log", "campaign.pid", "campaign.log.launch.cmd",
                     "campaign.log.launch.ps1"):
            (self.camp_dir / name).unlink(missing_ok=True)


def _raise():
    raise denied()


if __name__ == "__main__":
    unittest.main()
