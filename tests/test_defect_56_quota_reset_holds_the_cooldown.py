"""A provider usage window with a stated reset holds the cooldown until it.

The doubling backoff tops out at ten times the base, far below a five hour
window. When the error names the reset, the cooldown runs to that instant.
"""

from __future__ import annotations

import datetime as dt

from ohflow import engine as engine_module
from ohflow.engine import Engine
from support import TempCase, simple_workflow
from test_campaign_03_paused_run import LIMIT

ZONE = dt.timezone(dt.timedelta(hours=8))


class TheCooldownFollowsTheProviderReset(TempCase):

    def _engine(self, base: int):
        from ohflow.workflow import Workflow
        workflow = simple_workflow(self.tmp / "repo")
        workflow = Workflow(**{**{f.name: getattr(workflow, f.name)
                                  for f in workflow.__dataclass_fields__.values()},
                               "transient_backoff_s": base})
        return Engine(workflow, self.run_dir(), run_id="r-test-0001",
                      verbose=False, harness_executors=self.harness_executors)

    def test_cooldown_reads_the_zai_reset_stamp(self):
        self.assertEqual(
            engine_module._provider_reset_at(LIMIT),
            dt.datetime(2026, 10, 3, 5, 11, 59,
                        tzinfo=dt.timezone.utc).timestamp())

    def test_cooldown_holds_until_a_future_reset(self):
        engine = self._engine(10)
        stamp_dt = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
                    ).astimezone(ZONE).replace(microsecond=0)
        error = ('429: {"code":"1308","message":"Usage limit reached for 5 '
                 'hour. Your limit will reset at '
                 f'{stamp_dt:%Y-%m-%d %H:%M:%S}"}}')
        wait = engine._back_off("01.p/01.s", error)
        self.assertAlmostEqual(wait, 7260, delta=5)
        until = dt.datetime.fromtimestamp(stamp_dt.timestamp() + 60.0,
                                          dt.timezone.utc)
        self.assertEqual(engine._cooldown_record()["cooldown_until"],
                         until.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def test_cooldown_ignores_a_past_reset(self):
        engine = self._engine(10)
        self.assertEqual(engine._back_off("01.p/01.s", LIMIT), 10.0)
