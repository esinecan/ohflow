"""A Codex usage limit defers the step and holds the cooldown until the stated reset.

Codex on a ChatGPT account ends the turn with a message that names only a local
clock time. The classifier must call it transient, and the reset parser must
turn the clock time into the next instant it occurs.
"""

from __future__ import annotations

import datetime as dt
import unittest

from ohflow import engine as engine_module
from ohflow import failure

CODEX_LIMIT = ("You’ve hit your usage limit. Upgrade to Pro "
               "(https://chatgpt.com/explore/pro), visit "
               "https://chatgpt.com/codex/settings/usage to purchase more credits "
               "or try again at 3:23 AM.")

ZONE = dt.timezone(dt.timedelta(hours=1))


class CodexUsageLimit(unittest.TestCase):

    def test_classified_transient(self):
        self.assertEqual(failure.classify(error=CODEX_LIMIT), failure.TRANSIENT)

    def test_reset_later_today(self):
        now = dt.datetime(2026, 11, 5, 0, 38, tzinfo=ZONE)
        self.assertEqual(engine_module._provider_reset_at(CODEX_LIMIT, now),
                         dt.datetime(2026, 11, 5, 3, 24, tzinfo=ZONE).timestamp())

    def test_reset_tomorrow_when_the_time_has_passed(self):
        now = dt.datetime(2026, 11, 5, 4, 0, tzinfo=ZONE)
        self.assertEqual(engine_module._provider_reset_at(CODEX_LIMIT, now),
                         dt.datetime(2026, 11, 6, 3, 24, tzinfo=ZONE).timestamp())

    def test_pm_reset(self):
        now = dt.datetime(2026, 11, 5, 9, 0, tzinfo=ZONE)
        error = CODEX_LIMIT.replace("3:23 AM", "12:05 PM")
        self.assertEqual(engine_module._provider_reset_at(error, now),
                         dt.datetime(2026, 11, 5, 12, 6, tzinfo=ZONE).timestamp())


if __name__ == "__main__":
    unittest.main()
