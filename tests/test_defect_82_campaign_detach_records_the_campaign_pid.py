"""Defect 82: `campaign run --detach` recorded the pid of the process it launched.

`detach.launch` returns the pid of the process it started. That process runs
the campaign only when nothing wraps it. Under the `wmi` launch method it is
the `cmd.exe` that runs the campaign, and a Windows virtual environment puts a
redirector in front of the interpreter. `campaign run --detach` wrote the
launched pid to `campaign.pid` and printed it, so the pid could name a process
that had already exited while the campaign ran on.

Now the process that runs the campaign writes its own pid to `campaign.pid`
when it starts, and the launcher prints the pid of that record. Any
`campaign.pid` other than the one the launcher found before the launch is the
new record. The launched pid is the answer only when no record arrives before
the launcher stops waiting or the launched process has died.

The first class fakes `detach.launch`. The second starts a real campaign
behind a real launcher process, a Python wrapper that runs the campaign as its
child and waits for it, so the launched pid and the campaign's pid differ. The
campaign's only milestone is already escalated, so the controller writes its
pid and exits. Every process the test starts is its own, and the cleanup kills
by the recorded pids only.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import textwrap
import threading
import time
from pathlib import Path
from unittest import mock

from ohflow import campaign as oc
from ohflow import cli, detach, proc
from support import TempCase, git_repo, real_process
from verb_support import call, live_child

DEAD_PID = "2147483646"

BARE_CAMPAIGN = """
from pathlib import Path
from ohflow.campaign import Campaign, Milestone
from ohflow.workflow import AgentSpec, ModelConfig


def build(args):
    here = Path(__file__).resolve().parent
    judge = AgentSpec(harness_executor="pi", role="milestone-judge", brief="",
                      max_iterations=3,
                      model=ModelConfig(model="fake/deterministic",
                                        base_url="http://127.0.0.1:0/never-called",
                                        api_key_env="OHFLOW_TEST_FAKE_KEY"))
    milestone = Milestone(id="m1", title="first", workflow="m1/workflow.py",
                          spec="m1/spec.md", args={})
    return Campaign(name="pid-campaign", root=here, repo=here,
                    charter="charter.md", milestones=(milestone,),
                    integration_branch="integration", judge=judge,
                    auto_resume=0)
"""

ESCALATED_CAMPAIGN = """
from pathlib import Path
from ohflow.campaign import Campaign, Milestone
from ohflow.workflow import AgentSpec, ModelConfig


def build(args):
    here = Path(__file__).resolve().parent
    judge = AgentSpec(harness_executor="pi", role="milestone-judge", brief="",
                      max_iterations=3,
                      model=ModelConfig(model="fake/deterministic",
                                        base_url="http://127.0.0.1:0/never-called",
                                        api_key_env="OHFLOW_TEST_FAKE_KEY"))
    milestone = Milestone(id="m1", title="first",
                          workflow="milestones/m1/workflow.py",
                          spec="milestones/m1/spec.md",
                          args={"product": args["product"]})
    return Campaign(name="pid-campaign", root=here, repo=Path(args["product"]),
                    charter="charter.md", milestones=(milestone,),
                    integration_branch="integration", judge=judge,
                    auto_resume=0)
"""

WORKFLOW = """
from pathlib import Path
from ohflow.workflow import Phase, Step, Workflow


def build(args):
    step = Step(id="a", kind="command", command="echo DONE",
                execution_timeout_s=30)
    return Workflow(name="m1", repo=Path(args["product"]),
                    phases=(Phase(name="P", steps=(step,)),))
"""

WRAPPER = """
import json
import os
import subprocess
import sys
from pathlib import Path

child = subprocess.Popen(sys.argv[2:], stdout=sys.stdout, stderr=sys.stderr,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
Path(sys.argv[1]).write_text(json.dumps(
    {"launcher": os.getpid(), "campaign": child.pid}), encoding="utf-8")
raise SystemExit(child.wait())
"""


class FakedLaunch(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.root = self.tmp / "camp"
        self.root.mkdir()
        self.campaign_file = self.root / "campaign.py"
        self.campaign_file.write_text(BARE_CAMPAIGN, encoding="utf-8")
        self.pid_file = self.root / oc.PID_FILE
        self.launcher = live_child(self).pid
        self.campaign = live_child(self).pid

    def detach(self, launch) -> tuple[int, dict]:
        with mock.patch.object(detach, "launch", launch):
            code, lines = call("campaign", "run", "--campaign",
                               self.campaign_file, "--detach", "--no-dashboard")
        self.assertEqual(code, cli.EXIT_OK, lines)
        return code, json.loads("\n".join(lines))

    def test_the_printed_pid_and_the_pid_file_name_the_campaign(self):
        def launch(argv, **kw):
            self.pid_file.write_text(str(self.campaign), encoding="utf-8")
            return detach.Launched(pid=self.launcher, method="wmi")

        _, launched = self.detach(launch)
        self.assertEqual(launched["pid"], self.campaign)
        self.assertEqual(launched["launch_method"], "wmi")
        self.assertEqual(self.pid_file.read_text(encoding="utf-8"),
                         str(self.campaign))

    def test_a_record_written_after_the_launch_replaces_an_earlier_one(self):
        self.pid_file.write_text(DEAD_PID, encoding="utf-8")
        past = time.time() - 100
        os.utime(self.pid_file, (past, past))

        def launch(argv, **kw):
            writer = threading.Timer(0.3, lambda: self.pid_file.write_text(
                str(self.campaign), encoding="utf-8"))
            writer.start()
            self.addCleanup(writer.join)
            return detach.Launched(pid=self.launcher, method="wmi")

        with mock.patch.object(cli, "CAMPAIGN_PID_WAIT_S", 30.0):
            _, launched = self.detach(launch)
        self.assertEqual(launched["pid"], self.campaign)
        self.assertEqual(self.pid_file.read_text(encoding="utf-8"),
                         str(self.campaign))

    def test_with_no_record_the_launched_pid_is_the_answer(self):
        self.pid_file.write_text(DEAD_PID, encoding="utf-8")
        past = time.time() - 100
        os.utime(self.pid_file, (past, past))
        with mock.patch.object(cli, "CAMPAIGN_PID_WAIT_S", 0.5):
            _, launched = self.detach(lambda argv, **kw: detach.Launched(
                pid=self.launcher, method="direct"))
        self.assertEqual(launched["pid"], self.launcher)
        self.assertEqual(self.pid_file.read_text(encoding="utf-8"),
                         str(self.launcher))


@real_process
class ACampaignBehindALauncherNamesItsOwnProcess(TempCase):

    def setUp(self) -> None:
        super().setUp()
        self.product = git_repo(self.tmp / "product")
        self.root = git_repo(self.tmp / "camp")
        mdir = self.root / "milestones" / "m1"
        mdir.mkdir(parents=True)
        (self.root / "charter.md").write_text("# Charter\n", encoding="utf-8")
        (mdir / "spec.md").write_text("# m1\n", encoding="utf-8")
        (mdir / "workflow.py").write_text(WORKFLOW, encoding="utf-8")
        self.campaign_file = self.root / "campaign.py"
        self.campaign_file.write_text(textwrap.dedent(ESCALATED_CAMPAIGN),
                                      encoding="utf-8")
        oc._git(self.root, "add", "-A")
        oc._git(self.root, "commit", "-m", "campaign inputs")
        oc.CampaignLog(self.root).append("escalated", milestone="m1",
                                         reason="held for the pid test")
        self.wrapper = self.tmp / "wrapper.py"
        self.wrapper.write_text(WRAPPER, encoding="utf-8")
        self.record = self.tmp / "wrapper.json"

    def _kill(self, pid: int) -> None:
        if proc.pid_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    def _wait_for(self, done, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not done():
            time.sleep(0.05)

    def test_the_printed_pid_is_the_process_that_runs_the_campaign(self):
        real_launch = detach.launch
        launched: list[detach.Launched] = []

        def launch(argv, **kw):
            launched.append(real_launch(
                [sys.executable, str(self.wrapper), str(self.record), *argv],
                **kw))
            return launched[0]

        with mock.patch.object(detach, "launch", launch), \
                mock.patch.object(cli, "CAMPAIGN_PID_WAIT_S", 60.0):
            code, lines = call("campaign", "run", "--campaign",
                               self.campaign_file, "--detach", "--no-dashboard",
                               "--args", f"product={self.product.as_posix()}")
        self.assertEqual(code, cli.EXIT_OK, lines)
        printed = json.loads("\n".join(lines))
        self.addCleanup(self._kill, launched[0].pid)
        self.addCleanup(self._kill, printed["pid"])

        self._wait_for(self.record.exists, 30)
        wrapper = json.loads(self.record.read_text(encoding="utf-8"))
        self.addCleanup(self._kill, wrapper["launcher"])
        self.addCleanup(self._kill, wrapper["campaign"])
        self.assertNotEqual(wrapper["launcher"], wrapper["campaign"])
        self.assertEqual(printed["pid"], wrapper["campaign"],
                         "the launch record names the launcher, not the "
                         "campaign")
        self.assertNotEqual(printed["pid"], launched[0].pid)
        self.assertEqual(
            (self.root / oc.PID_FILE).read_text(encoding="utf-8"),
            str(wrapper["campaign"]))

        log = self.root / "campaign.log"
        self._wait_for(lambda: "is escalated" in log.read_text(
            encoding="utf-8", errors="replace"), 60)
        self.assertIn("m1 is escalated",
                      log.read_text(encoding="utf-8", errors="replace"),
                      "the campaign controller did not run in the child")
