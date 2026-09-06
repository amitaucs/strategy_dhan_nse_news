"""Unit tests for ST15 Screener multi-gate verification and signal generation."""

from datetime import datetime, timedelta
import unittest

from st15_largecap.core.models import Candle
from st15_largecap.engine.screener import ST15Screener
from st15_largecap.ingestion.candles import generate_mock_2h_candles


class TestScreener(unittest.TestCase):
    def test_screener_empty_candles(self):
        screener = ST15Screener()
        res = screener.evaluate(symbol="TEST", sec_id="123", candles=[])
        self.assertFalse(res.is_setup_ready)
        self.assertIsNone(res.signal)

    def test_screener_bullish_pullback_trigger(self):
        # Generate 80 candles with strong bullish trend and dip + bounce at end
        candles = generate_mock_2h_candles(
            symbol="RELIANCE",
            base_price=2800.0,
            num_candles=80,
            bullish_trend=True,
            pullback_at_end=True,
        )

        screener = ST15Screener(
            ema_proximity_pct=1.5,
            risk_reward_ratio=3.0,
        )
        res = screener.evaluate(symbol="RELIANCE", sec_id="2885", candles=candles)

        self.assertEqual(res.candles_count, 80)
        self.assertEqual(res.symbol, "RELIANCE")
        self.assertTrue(res.is_ema_stacked)
        self.assertTrue(res.is_supertrend_green)
        self.assertTrue(res.is_ha_green)

        # Check setup signal if ready
        if res.is_setup_ready:
            self.assertIsNotNone(res.signal)
            self.assertGreater(res.signal.trigger_price, res.signal.stop_loss_price)
            self.assertGreater(res.signal.target_profit_price, res.signal.trigger_price)
            expected_target = round(
                res.signal.trigger_price + (res.signal.risk_per_share * 3.0), 2
            )
            self.assertEqual(res.signal.target_profit_price, expected_target)
            self.assertEqual(res.signal.risk_reward_ratio, 3.0)


if __name__ == "__main__":
    unittest.main()
