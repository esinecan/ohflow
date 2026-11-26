"""Defect 1: a non-encodable character must not raise from a console or log write.

Fixed in `9fae2dd`, "ohflow: no character can crash a console or log write".

What went wrong. The ANSI code page on this box is cp1252. An agent's output
carries box-drawing characters, em dashes and arrows, and `print` raises
`UnicodeEncodeError` on every one of them. The exception did not land on the
line, it landed on the thread that was writing the line, and a per-step thread
that dies there abandons the rest of its step.

What is asserted here. `console.say` and `Engine.say` write text containing
characters cp1252 cannot carry, to a stream that really is cp1252, and neither
raises. The text still arrives, with the unmappable characters replaced.

The characters are not invented. They come from
`fixtures.real_errors.CP1252_KILLER_LINES`, the first entry of which is a slice
of a log this orchestrator genuinely tried to print during the preserved Cortea
run.
"""

from __future__ import annotations

import io
import sys

from fixtures.real_errors import CP1252_KILLER_LINES, SCOUT1_TERMINAL_FAULT_LOG_TAIL
from ohflow import console
from ohflow.engine import Engine
from support import TempCase, simple_workflow


def cp1252_stream() -> io.TextIOWrapper:
    """A text stream that really is cp1252, so a bad character really raises.

    `errors="strict"` is the default and is what a Windows console does. No
    mock: the exception in these tests is raised by the codec, not by a stub.
    """
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict",
                            newline="")


class ConsoleSurvivesCp1252(TempCase):

    def test_say_does_not_raise_on_any_recorded_killer_line(self):
        for line in CP1252_KILLER_LINES:
            with self.subTest(line=line[:40]):
                stream = cp1252_stream()
                console.say(line, file=stream)      # must not raise

    def test_say_still_writes_the_text_with_replacements(self):
        stream = cp1252_stream()
        console.say("a │ b → c", file=stream)
        stream.flush()
        written = stream.buffer.getvalue().decode("cp1252")
        self.assertIn("a ", written)
        self.assertIn(" b ", written)
        self.assertIn(" c", written)
        # The unmappable characters became '?', they did not vanish and they did
        # not take the line with them.
        self.assertEqual(written.count("?"), 2, written)

    def test_say_survives_a_stream_that_is_closed(self):
        stream = cp1252_stream()
        stream.close()
        console.say("anything", file=stream)        # must not raise

    def test_warn_takes_the_same_path(self):
        original = sys.stderr
        stream = cp1252_stream()
        sys.stderr = stream
        try:
            console.warn("── rule ──")
        finally:
            sys.stderr = original

    def test_sanitize_round_trips_without_raising(self):
        out = console.sanitize("│→", "cp1252")
        self.assertEqual(out, "??")
        # An encoding that does not exist must not raise either.
        self.assertTrue(console.sanitize("│", "no-such-codec"))


class EngineSayCannotKillAStepThread(TempCase):
    """`Engine.say` is the funnel every console line in a run goes through."""

    def test_engine_say_writes_a_real_log_tail_without_raising(self):
        # `Engine.__init__` never touches the repository, so none is made.
        workflow = simple_workflow(self.tmp / "repo")
        engine = Engine(workflow, self.run_dir(), run_id="r-test-0001")

        original = sys.stdout
        stream = cp1252_stream()
        sys.stdout = stream
        try:
            # The whole 2021-character tail of a real killed agent's log.
            engine.say(SCOUT1_TERMINAL_FAULT_LOG_TAIL)
        finally:
            sys.stdout = original

        stream.flush()
        self.assertGreater(len(stream.buffer.getvalue()), 0,
                           "the line was dropped entirely")

    def test_engine_say_is_quiet_but_still_safe_when_not_verbose(self):
        # `Engine.__init__` never touches the repository, so none is made.
        workflow = simple_workflow(self.tmp / "repo")
        engine = Engine(workflow, self.run_dir(), run_id="r-test-0001",
                        verbose=False)
        original = sys.stdout
        sys.stdout = cp1252_stream()
        try:
            engine.say("│ nothing should be written, and nothing should raise")
        finally:
            sys.stdout = original
