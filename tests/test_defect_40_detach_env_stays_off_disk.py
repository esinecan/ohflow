"""D-40: the WMI launch method kept every environment value in a file on disk.

What went wrong. WMI cannot set the environment of the process it creates, so
the launch method wrote one `set "KEY=value"` line per variable into `<log>.launch.cmd`
and kept the file after the launch. For `campaign run --detach` that file sat
in the campaign root, a git repository that did not ignore it, and held every
API key of the caller.

What the module promises now. The child gets the environment that the caller
passed to `detach.launch`, and when `launch` returns no file in the log
directory holds an environment value. The PowerShell script reads the
environment that it inherited from the shim and hands it to WMI as
`Win32_ProcessStartup.EnvironmentVariables`.

The first test is a real WMI start. It runs only where `run-hidden.vbs`
exists. The first start is denied breakaway so that `launch` takes the WMI
launch method. The second test checks that a campaign root ignores the files the launch method
leaves behind.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
import unittest
from unittest import mock

from ohflow import campaign, detach
from support import TempCase, git_repo

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BREAKAWAY = CREATE_NO_WINDOW | getattr(
    subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)


def denied() -> OSError:
    error = OSError(13, "access denied")
    error.winerror = 5
    return error


@unittest.skipUnless(sys.platform == "win32"
                     and detach.run_hidden_shim().is_file(),
                     "the run-hidden.vbs shim is required for the WMI launch method")
class WmiLaunchMethodKeepsTheEnvironmentOffDisk(TempCase):

    def test_the_child_sees_the_environment_and_no_file_holds_it(self):
        secret = secrets.token_hex(16)
        logs = self.tmp / "logs"
        seen = self.tmp / "seen"
        logs.mkdir()
        seen.mkdir()
        seen_file = seen / "value.txt"
        child = [sys.executable, "-c",
                 "import os, pathlib; pathlib.Path(r'%s').write_text("
                 "os.environ['OHFLOW_TEST_SECRET'], encoding='ascii')"
                 % seen_file]
        env = dict(os.environ, OHFLOW_TEST_SECRET=secret)

        with mock.patch.object(detach, "creationflags",
                               return_value=(BREAKAWAY, True)), \
             mock.patch.object(detach.proc, "popen",
                               side_effect=lambda *a, **k: _raise()):
            launched = detach.launch(child, cwd=self.tmp, env=env,
                                     log_path=logs / "child.log")
        self.assertEqual(launched.method, "wmi")

        holders = [path.name for path in logs.iterdir()
                   if secret.encode("ascii") in path.read_bytes()]
        self.assertEqual(holders, [],
                         "a file the WMI launch method wrote holds an environment value")

        deadline = time.monotonic() + 30
        while not seen_file.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertTrue(seen_file.exists(), "the child never ran")
        self.assertEqual(seen_file.read_text(encoding="ascii"), secret)


class CampaignRootIgnoresTheLaunchFiles(TempCase):

    def test_campaign_ignores_cover_the_launch_files(self):
        root = git_repo(self.tmp / "camp")
        campaign.ensure_ignores(root)
        for name in ("campaign.log.launch.cmd", "campaign.log.launch.ps1",
                     "campaign.log.launch.pid"):
            checked = subprocess.run(["git", "check-ignore", "-q", name],
                                     cwd=root, stdin=subprocess.DEVNULL)
            self.assertEqual(checked.returncode, 0, f"{name} is not ignored")


def _raise():
    raise denied()


if __name__ == "__main__":
    unittest.main()
