"""Unit tests for EMA, SuperTrend, and Swing Low indicators."""

from datetime import datetime, timedelta
import unittest

from st15_largecap.core.models import Candle
from st15_largecap.indicators.ema import (
    calculate_ema,
    calculate_triple_ema,
    check_ema_proximity,
    is_ema_stacked_bullish,
)
from st15_largecap.indicators.supertrend import calculate_supertrend
from st15_largecap.indicators.swing import calculate_swing_low


class TestIndicators(unittest.TestCase):
    def test_ema_calculations(self):
        prices = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0]
        ema_5 = calculate_ema(prices, span=5)
        self.assertEqual(len(ema_5), len(prices))
        self.assertGreater(ema_5[-1], ema_5[0])

        triple = calculate_triple_ema(prices, fast_span=2, mid_span=4, slow_span=6)
        self.assertIn("ema_20", triple)
        self.assertIn("ema_50", triple)
        self.assertIn("ema_200", triple)

    def test_is_ema_stacked_bullish(self):
        # 20 > 50 > 200 is True
        self.assertTrue(is_ema_stacked_bullish(ema_20=2500.0, ema_50=2400.0, ema_200=2200.0))
        # 20 < 50 is False
        self.assertFalse(is_ema_stacked_bullish(ema_20=2300.0, ema_50=2400.0, ema_200=2200.0))
        # 50 < 200 is False
        self.assertFalse(is_ema_stacked_bullish(ema_20=2500.0, ema_50=2100.0, ema_200=2200.0))

    def test_check_ema_proximity(self):
        # Exact touch: low <= 2500 <= high
        in_dip, name, dist = check_ema_proximity(
            low=2490.0, high=2520.0, close=2510.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.5
        )
        self.assertTrue(in_dip)
        self.assertEqual(name, "EMA_20")
        self.assertEqual(dist, 0.0)

        # Near dip: low is 2505 when EMA is 2500 -> diff 5 / 2500 = 0.2% <= 0.5%
        in_dip2, name2, dist2 = check_ema_proximity(
            low=2505.0, high=2530.0, close=2520.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.5
        )
        self.assertTrue(in_dip2)
        self.assertEqual(name2, "EMA_20")
        self.assertEqual(dist2, 0.2)

        # Far away: low is 2600 when EMA is 2500 -> diff 100 / 2500 = 4% > 0.5%
        in_dip3, _, dist3 = check_ema_proximity(
            low=2600.0, high=2650.0, close=2620.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.5
        )
        self.assertFalse(in_dip3)
        self.assertEqual(dist3, 4.0)

    def test_supertrend_bullish_bearish(self):
        base_time = datetime(2025, 1, 1, 9, 15)
        candles = []
        # Upward trending candles
        for i in range(25):
            p = 1000.0 + (i * 10.0)
            candles.append(
                Candle(
                    timestamp=base_time + timedelta(hours=i*2),
                    open=p - 2.0,
                    high=p + 5.0,
                    low=p - 3.0,
                    close=p + 4.0,
                )
            )

        st_values, is_green = calculate_supertrend(candles, period=10, multiplier=3.0)
        self.assertEqual(len(st_values), 25)
        self.assertEqual(len(is_green), 25)
        self.assertTrue(is_green[-1])

    def test_swing_low(self):
        base_time = datetime(2025, 1, 1, 9, 15)
        lows = [100.0, 98.0, 95.0, 97.0, 99.0, 102.0]
        candles = [
            Candle(timestamp=base_time + timedelta(hours=i*2), open=l+2, high=l+5, low=l, close=l+3)
            for i, l in enumerate(lows)
        ]
        # Lowest low is 95.0, buffer 0.1% = 95.0 * 0.999 = 94.905 -> 94.91
        sl = calculate_swing_low(candles, lookback=6, buffer_pct=0.1)
        self.assertEqual(sl, 94.91)


if __name__ == "__main__":
    unittest.main()
