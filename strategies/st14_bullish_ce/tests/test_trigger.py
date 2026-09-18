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
    def test_trigger_fail_closed_on_missing_quote(self):
        """When provider is connected to Dhan and live quote is unavailable, fail closed."""
        from unittest.mock import MagicMock
        mock_prov = MagicMock()
        mock_prov.dhan = MagicMock()
        mock_prov.fetch_ltp_batch.return_value = {"11536": 0.0}

        is_crossed, ltp, msg = check_breakout_candle_cross(
            symbol="TCS",
            sec_id="11536",
            breakout_candle_high=4250.0,
            current_ltp=4260.0,  # Stale discovery price
            provider=mock_prov,
        )
        self.assertFalse(is_crossed)
        self.assertEqual(ltp, 0.0)
        self.assertIn("Live real-time price unavailable", msg)


if __name__ == "__main__":
    unittest.main()

