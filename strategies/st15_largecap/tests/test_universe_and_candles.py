"""Unit tests for UniverseManager and 2H candle bucket aggregation."""

from datetime import datetime, time
import unittest

from st15_largecap.ingestion.universe import UniverseManager
from st15_largecap.ingestion.candles import bucket_indian_market_2h, aggregate_to_2h_candles


class TestUniverseAndCandles(unittest.TestCase):
    def test_universe_manager_mappings(self):
        mgr = UniverseManager()
        self.assertEqual(mgr.get_security_id("RELIANCE"), "2885")
        self.assertEqual(mgr.get_security_id("TCS"), "11536")
        self.assertEqual(mgr.get_security_id("HDFCBANK"), "1333")
        self.assertEqual(len(mgr.get_universe()), 200)

    def test_bucket_indian_market_2h(self):
        d = datetime(2025, 1, 15)
        
        # 09:30 AM -> Bucket 1: 09:15
        t1 = datetime.combine(d.date(), time(9, 30))
        b1 = bucket_indian_market_2h(t1)
        self.assertEqual(b1, datetime.combine(d.date(), time(9, 15)))

        # 12:00 PM -> Bucket 2: 11:15
        t2 = datetime.combine(d.date(), time(12, 0))
        b2 = bucket_indian_market_2h(t2)
        self.assertEqual(b2, datetime.combine(d.date(), time(11, 15)))

        # 14:30 PM -> Bucket 3: 13:15
        t3 = datetime.combine(d.date(), time(14, 30))
        b3 = bucket_indian_market_2h(t3)
        self.assertEqual(b3, datetime.combine(d.date(), time(13, 15)))

        # Pre-market / Out of session (08:30) -> None
        t4 = datetime.combine(d.date(), time(8, 30))
        self.assertIsNone(bucket_indian_market_2h(t4))

    def test_aggregate_to_2h_candles(self):
        d = datetime(2025, 1, 15)
        minute_records = [
            {"timestamp": datetime.combine(d.date(), time(9, 15)), "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 100},
            {"timestamp": datetime.combine(d.date(), time(10, 0)), "open": 102.0, "high": 108.0, "low": 101.0, "close": 107.0, "volume": 150},
            {"timestamp": datetime.combine(d.date(), time(11, 0)), "open": 107.0, "high": 107.5, "low": 104.0, "close": 106.0, "volume": 80},
        ]

        candles = aggregate_to_2h_candles(minute_records)
        self.assertEqual(len(candles), 1)
        c = candles[0]
        self.assertEqual(c.open, 100.0)
        self.assertEqual(c.high, 108.0)
        self.assertEqual(c.low, 99.0)
        self.assertEqual(c.close, 106.0)
        self.assertEqual(c.volume, 330.0)


if __name__ == "__main__":
    unittest.main()
