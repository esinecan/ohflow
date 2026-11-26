"""The shipping page has the planned-step inspector panel.

The page is static HTML served from the package. This test reads the page the
server ships and asserts the panel the hold gate adds for a step with zero
invocations.
"""

from __future__ import annotations

from ohflow import dashboard
from support import TempCase

ASSETS = dashboard.ASSET_ROOT


class PlannedViewAndHeldTone(TempCase):

    def test_the_page_has_the_planned_panel(self):
        page = (ASSETS / "dashboard.html").read_text(encoding="utf-8")
        self.assertTrue('id="panel-planned"' in page,
                        "dashboard.html has no planned panel")


if __name__ == "__main__":
    import unittest
    unittest.main()
