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

    def test_check_ema_proximity_positive_tolerance(self):
        # Low is 2505 when EMA is 2500 -> +0.2% distance
        in_dip, name, dist = check_ema_proximity(
            low=2505.0, high=2530.0, close=2520.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.5
        )
        self.assertTrue(in_dip)
        self.assertEqual(name, "EMA_20")
        self.assertEqual(dist, 0.2)

        # Low is 2600 when EMA is 2500 -> +4.0% distance > +0.5%
        in_dip_far, _, dist_far = check_ema_proximity(
            low=2600.0, high=2650.0, close=2620.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.5
        )
        self.assertFalse(in_dip_far)
        self.assertEqual(dist_far, 4.0)

    def test_check_ema_proximity_zero_tolerance(self):
        # 0.0% tolerance requires exact touch or lower (Low <= EMA)
        # Low = 2500 -> 0.0%
        in_dip_touch, _, dist_touch = check_ema_proximity(
            low=2500.0, high=2520.0, close=2510.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.0
        )
        self.assertTrue(in_dip_touch)
        self.assertEqual(dist_touch, 0.0)

        # Low = 2502 (+0.08% above) -> fails 0.0% tolerance
        in_dip_above, _, _ = check_ema_proximity(
            low=2502.0, high=2520.0, close=2510.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=0.0
        )
        self.assertFalse(in_dip_above)

    def test_check_ema_proximity_negative_tolerance(self):
        # -0.2% tolerance requires price to have dipped at least 0.2% below EMA (Low <= 2500 * 0.998 = 2495)
        # Low = 2492 -> dist = (2492-2500)/2500 = -0.32% <= -0.2% -> True
        in_dip_neg, name, dist_neg = check_ema_proximity(
            low=2492.0, high=2515.0, close=2505.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=-0.2
        )
        self.assertTrue(in_dip_neg)
        self.assertEqual(dist_neg, -0.32)

        # Low = 2498 -> dist = -0.08% > -0.2% -> False (did not penetrate enough)
        in_dip_shallow, _, _ = check_ema_proximity(
            low=2498.0, high=2515.0, close=2505.0,
            ema_20=2500.0, ema_50=2400.0, ema_200=2200.0,
            tolerance_pct=-0.2
        )
        self.assertFalse(in_dip_shallow)

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
