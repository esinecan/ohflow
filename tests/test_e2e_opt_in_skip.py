"""The end-to-end test never skips in silence: every skip says why."""

from __future__ import annotations

import os
from unittest import mock

import e2e_support
from e2e_support import E2E_ENV, KEY_ENV, why_skip
from support import TempCase


class TheOptInSkipAnnouncesItself(TempCase):
    """Guards acceptance criterion 6: a silent skip is worse than no test.

    These run whether or not `--e2e` was passed, because the reasons are what
    they check, not the run. Each one sets the environment it wants and puts it
    back afterwards, so no test here changes what another test sees.
    """

    def _with_env(self, **changes) -> str:
        """`why_skip()` under a temporary environment. Restored on the way out."""
        saved = {k: os.environ.get(k) for k in changes}
        try:
            for name, value in changes.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            return why_skip() or ""
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_the_default_skip_says_how_to_opt_in(self):
        reason = self._with_env(**{E2E_ENV: None})
        self.assertIn("--e2e", reason)
        self.assertGreater(len(reason), 40,
                           "a skip reason must say what is missing and what to "
                           "do about it")

    def test_a_missing_key_names_the_variable_and_says_what_to_do(self):
        reason = self._with_env(**{E2E_ENV: "1", KEY_ENV: None})
        self.assertIn(KEY_ENV, reason,
                      "the reason must name the variable that is missing")
        self.assertIn("Set it", reason,
                      "the reason must say what to do about it")

    def test_a_missing_harness_names_the_executor_not_the_key(self):
        # The checks run in order, so the key has to look present for the
        # harness check to be reached at all. This placeholder is only ever
        # tested for emptiness; nothing sends it anywhere.
        class Missing:
            def preflight(self):
                return ["pi executable not found: no-such-pi"]

        with mock.patch.object(e2e_support, "harness_executor_for",
                               lambda name: Missing()):
            reason = self._with_env(**{E2E_ENV: "1",
                                       KEY_ENV: "placeholder-not-a-key"})
        self.assertIn("pi harness executor is not ready", reason)
        self.assertIn("no-such-pi", reason)
        self.assertIn("OHFLOW_PI_EXE", reason)
        self.assertNotIn("placeholder-not-a-key", reason,
                         "a skip reason echoed the contents of the variable")
