"""Unit tests for Heikin Ashi calculations."""

from datetime import datetime, timedelta
import unittest

from st15_largecap.core.models import Candle
from st15_largecap.ingestion.heikin_ashi import calculate_heikin_ashi


class TestHeikinAshi(unittest.TestCase):
    def test_heikin_ashi_empty(self):
        self.assertEqual(calculate_heikin_ashi([]), [])

    def test_heikin_ashi_single_candle(self):
        now = datetime.now()
        c1 = Candle(timestamp=now, open=100.0, high=110.0, low=95.0, close=105.0, volume=1000.0)
        ha_list = calculate_heikin_ashi([c1])

        self.assertEqual(len(ha_list), 1)
        ha = ha_list[0]
        # HA_Close = (100 + 110 + 95 + 105) / 4 = 410 / 4 = 102.5
        self.assertEqual(ha.close, 102.5)
        # HA_Open (1st candle) = (100 + 105) / 2 = 102.5
        self.assertEqual(ha.open, 102.5)
        # HA_High = max(110, 102.5, 102.5) = 110.0
        self.assertEqual(ha.high, 110.0)
        # HA_Low = min(95, 102.5, 102.5) = 95.0
        self.assertEqual(ha.low, 95.0)

    def test_heikin_ashi_sequence_and_colors(self):
        now = datetime.now()
        c1 = Candle(timestamp=now, open=100.0, high=105.0, low=98.0, close=102.0)
        c2 = Candle(timestamp=now + timedelta(hours=2), open=102.0, high=112.0, low=101.0, close=110.0)

        ha_candles = calculate_heikin_ashi([c1, c2])
        self.assertEqual(len(ha_candles), 2)

        # Candle 1
        ha1 = ha_candles[0]
        expected_c1_close = (100 + 105 + 98 + 102) / 4.0 # 101.25
        expected_c1_open = (100 + 102) / 2.0 # 101.0
        self.assertEqual(ha1.close, round(expected_c1_close, 2))
        self.assertEqual(ha1.open, round(expected_c1_open, 2))

        # Candle 2
        ha2 = ha_candles[1]
        expected_c2_open = (ha1.open + ha1.close) / 2.0
        expected_c2_close = (102 + 112 + 101 + 110) / 4.0 # 106.25
        self.assertEqual(ha2.open, round(expected_c2_open, 2))
        self.assertEqual(ha2.close, round(expected_c2_close, 2))
        self.assertTrue(ha2.is_green)
        self.assertFalse(ha2.is_red)


if __name__ == "__main__":
    unittest.main()
