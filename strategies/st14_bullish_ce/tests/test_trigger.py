"""Unit tests for next-candle breakout trigger cross verification."""

from __future__ import annotations

import unittest

from st14_bullish_ce.trigger import check_breakout_candle_cross


class TestTriggerConfirmation(unittest.TestCase):
    """Test suite for breakout trigger cross evaluation."""

    def test_trigger_crossed_above_high(self):
        """When live LTP > Breakout High, trigger fires successfully."""
        is_crossed, ltp, msg = check_breakout_candle_cross(
            symbol="TCS",
            sec_id="11536",
            breakout_candle_high=4250.0,
            current_ltp=4255.0,
        )
        self.assertTrue(is_crossed)
        self.assertEqual(ltp, 4255.0)
        self.assertIn("Breakout Confirmed", msg)

    def test_trigger_pending_below_high(self):
        """When live LTP <= Breakout High, trigger remains pending."""
        is_crossed, ltp, msg = check_breakout_candle_cross(
            symbol="TCS",
            sec_id="11536",
            breakout_candle_high=4250.0,
            current_ltp=4248.0,
        )
        self.assertFalse(is_crossed)
        self.assertEqual(ltp, 4248.0)
        self.assertIn("Pending Trigger", msg)


if __name__ == "__main__":
    unittest.main()

