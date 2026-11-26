"""A process with no stdin handle can still start children.

What went wrong. The campaign starts through `run-hidden.vbs`, so the gate
runs the suite with no console and no stdin handle. `subprocess` reads
`GetStdHandle(STD_INPUT_HANDLE)` for a child that names no stdin, finds an
invalid handle, and raises `OSError: [WinError 6] The handle is invalid`.
226 tests failed this way, and so did `ohflow`'s own `taskkill` and `git`
calls: a supervisor started windowless crashed on its first git command.

The fix. `proc.run` and `proc.popen` give a child that is fed no input the null
device for stdin, and `proc.ensure_stdin` repairs the handle of a process that
starts children through plain `subprocess`, as the suite does.

How the test reaches the fault. A child Python sets its own stdin handle to
`INVALID_HANDLE_VALUE`, the state a closed descriptor leaves. It first proves
that plain `subprocess.run` fails there, then runs the code under test.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from support import TempCase

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

NO_STDIN = """
import ctypes, subprocess, sys
from ctypes import wintypes
sys.path.insert(0, {scripts!r})
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
k.SetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF), wintypes.HANDLE(-1))
try:
    subprocess.run([sys.executable, "-c", "pass"], capture_output=True)
except OSError:
    pass
else:
    raise SystemExit("setup: plain subprocess did not fail without stdin")
{body}
print("OK")
"""


@unittest.skipUnless(sys.platform == "win32", "stdin handles are a Windows fault")
class NoStdinHandle(TempCase):
    def run_child(self, body: str) -> subprocess.CompletedProcess:
        code = NO_STDIN.format(scripts=str(SCRIPTS), body=body)
        done = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done

    def test_proc_run_starts_a_child_without_a_stdin_handle(self):
        self.run_child("""
from ohflow import proc
done = proc.run([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
                capture_output=True, text=True)
assert done.returncode == 0 and done.stdout.strip() == "''", done
""")

    def test_proc_popen_starts_a_child_without_a_stdin_handle(self):
        self.run_child("""
from ohflow import proc
p = proc.popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE)
assert p.wait(timeout=30) == 0
""")

    def test_a_command_step_runs_without_a_stdin_handle(self):
        self.run_child(f"""
from pathlib import Path
from ohflow import exec as ohexec
done = ohexec.run("echo hi", cwd=Path({str(self.tmp)!r}))
assert done.returncode == 0 and "hi" in done.stdout, done
""")

    def test_ensure_stdin_repairs_plain_subprocess(self):
        self.run_child("""
from ohflow import proc
proc.ensure_stdin()
done = subprocess.run([sys.executable, "-c", "pass"], capture_output=True)
assert done.returncode == 0, done
""")

    def test_the_wmi_detach_route_starts_its_shim_without_a_stdin_handle(self):
        shim = self.tmp / "quit.vbs"
        shim.write_text("WScript.Quit 0\r\n", encoding="ascii")
        self.run_child(f"""
import os
from pathlib import Path
from ohflow import detach
tmp = Path({str(self.tmp)!r})
log = tmp / "child.log"
try:
    detach._start_through_shim(
        Path({str(shim)!r}), [sys.executable, "-c", "pass"], str(tmp), dict(os.environ),
        log, tmp / "child.cmd", tmp / "child.ps1", tmp / "child.pid")
except detach.DetachFailed as error:
    assert "did not run" not in str(error), error
else:
    raise SystemExit("the shim wrote no pid, so the call must raise")
""")

    def test_a_caller_that_feeds_input_keeps_it(self):
        self.run_child("""
from ohflow import proc
done = proc.run([sys.executable, "-c", "import sys; print(sys.stdin.read())"],
                input="fed", capture_output=True, text=True)
assert done.stdout.strip() == "fed", done
""")


if __name__ == "__main__":
    unittest.main()
