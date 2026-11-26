"""Real pi provider strings retain retry-safe failure classification."""

from __future__ import annotations

import unittest

from fixtures.real_errors import (
    PI_PHASE0_BAD_REQUEST_ERROR,
    PI_PHASE0_RATE_LIMIT_ERROR,
    PI_PHASE0_UNAUTHORIZED_ERROR,
)
from ohflow.failure import STRUCTURAL, TRANSIENT, classify, explain, provider_structural


class PiFailureClassificationTests(unittest.TestCase):

    def test_phase0_429_is_transient(self):
        self.assertEqual(classify(error=PI_PHASE0_RATE_LIMIT_ERROR), TRANSIENT)
        self.assertEqual(explain(PI_PHASE0_RATE_LIMIT_ERROR), "429")
        self.assertIsNone(provider_structural(PI_PHASE0_RATE_LIMIT_ERROR))

    def test_phase0_401_and_400_are_structural(self):
        for error, signature in (
                (PI_PHASE0_UNAUTHORIZED_ERROR, "401"),
                (PI_PHASE0_BAD_REQUEST_ERROR, "400")):
            with self.subTest(signature=signature):
                self.assertEqual(classify(error=error), STRUCTURAL)
                self.assertEqual(provider_structural(error), signature)

    def test_structural_signature_wins_when_text_mentions_an_old_429(self):
        combined = PI_PHASE0_RATE_LIMIT_ERROR + "\n" + PI_PHASE0_UNAUTHORIZED_ERROR
        self.assertEqual(classify(error=combined), STRUCTURAL)
        self.assertEqual(provider_structural(combined), "401")

    def test_stall_is_not_mislabelled_as_a_provider_rate_limit(self):
        self.assertEqual(classify(error="stall"), STRUCTURAL)
        self.assertIsNone(explain("stall"))
        self.assertIsNone(provider_structural("stall"))


if __name__ == "__main__":
    unittest.main()
