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

        # Timezone-aware UTC timestamp (04:00 UTC = 09:30 IST -> Bucket 1: 09:15 IST)
        from datetime import timezone
        t_utc = datetime(2025, 1, 15, 4, 0, tzinfo=timezone.utc)
        b_utc = bucket_indian_market_2h(t_utc)
        self.assertEqual(b_utc, datetime.combine(d.date(), time(9, 15)))

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
    def test_fetch_2h_candles_force_refresh_bypasses_cache_fallback(self):
        """When force_refresh=True, CandleFetcher must bypass cache and not fall back to stale cache on API error."""
        from unittest.mock import MagicMock
        from st15_largecap.ingestion.candles import CandleFetcher, Candle

        mock_dhan = MagicMock()
        # Mock intraday_minute_data returning error / failure
        mock_dhan.intraday_minute_data.return_value = {"status": "failure", "remarks": "API error"}

        fetcher = CandleFetcher(dhan_client=mock_dhan)
        # Populate cache with old candles
        old_time = datetime(2025, 1, 1, 10, 0)
        old_candles = [Candle(timestamp=old_time, open=100.0, high=105.0, low=95.0, close=102.0)]
        fetcher._cache["RELIANCE_180"] = (old_time, old_candles)

        # 1. With force_refresh=True: must NOT return old cached candles, must fail-closed and return []
        res_force = fetcher.fetch_2h_candles("2885", symbol="RELIANCE", days=180, force_refresh=True)
        self.assertEqual(res_force, [])

        # 2. Without force_refresh: within fallback window, returns cached candles
        fetcher._cache["RELIANCE_180"] = (datetime.now(), old_candles)
        res_cached = fetcher.fetch_2h_candles("2885", symbol="RELIANCE", days=180, force_refresh=False)
        self.assertEqual(res_cached, old_candles)

    def test_universe_manager_provenance(self):
        """UniverseManager must track whether security IDs are from dhan_scrip_master vs static_fallback."""
        mgr = UniverseManager(cache_path="/tmp/nonexistent_test_cache.json")
        mgr._provenance = {"RELIANCE": "static_fallback", "INFY": "dhan_scrip_master"}

        self.assertFalse(mgr.is_security_id_verified("RELIANCE"))
        self.assertTrue(mgr.is_security_id_verified("INFY"))

        sec_id, source, is_verified = mgr.get_security_id_provenance("RELIANCE")
        self.assertEqual(source, "static_fallback")
        self.assertFalse(is_verified)

        sec_id2, source2, is_verified2 = mgr.get_security_id_provenance("INFY")
        self.assertEqual(source2, "dhan_scrip_master")
        self.assertTrue(is_verified2)


if __name__ == "__main__":
    unittest.main()


