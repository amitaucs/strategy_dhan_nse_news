"""Unit tests for MySQL / SQLite DB persistence of EOD Multi-Scanner Daily Digest."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from news_based_strategy.storage.repository import StrategyStorage
from scanner_dhan.eod.store import EODReportStore


class TestEODDatabasePersistence(unittest.TestCase):
    """Tests for saving and recovering EOD digest reports and confluence stocks in the database."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_strategy.db"
        self.storage = StrategyStorage(db_path=str(self.db_path), use_mysql=False)
        self.store_dir = Path(self.temp_dir.name) / "eod_scans"
        self.store = EODReportStore(base_dir=self.store_dir, storage=self.storage)

        self.sample_report = {
            "date": "2026-09-19",
            "timestamp": "2026-09-19T18:30:00+05:30",
            "universe": "NIFTY_500",
            "total_scanners_run": 12,
            "total_matches": 15,
            "unique_stocks_count": 8,
            "confluence_stocks_count": 2,
            "bullish_count": 7,
            "bearish_count": 1,
            "execution_time_seconds": 12.5,
            "top_confluence_stocks": [
                {
                    "symbol": "TATAMOTORS",
                    "company_name": "Tata Motors Ltd",
                    "security_id": "3456",
                    "close": 985.50,
                    "change_pct": 3.2,
                    "volume": 5500000,
                    "volume_ratio": 2.4,
                    "match_count": 3,
                    "confluence_score": 92.5,
                    "primary_category": "Breakout",
                    "pivot_level": 990.0,
                    "stop_loss": 965.0,
                    "strategies": [
                        {"scanner_id": "vcp_breakout", "scanner_name": "VCP Breakout", "score": 90.0},
                        {"scanner_id": "momentum_52w", "scanner_name": "52W High Momentum", "score": 85.0},
                        {"scanner_id": "pivot_breakout", "scanner_name": "Pivot Breakout", "score": 88.0},
                    ],
                },
                {
                    "symbol": "RELIANCE",
                    "company_name": "Reliance Industries Ltd",
                    "security_id": "2885",
                    "close": 2980.0,
                    "change_pct": 1.8,
                    "volume": 3200000,
                    "volume_ratio": 1.6,
                    "match_count": 2,
                    "confluence_score": 81.0,
                    "primary_category": "Support",
                    "pivot_level": 3000.0,
                    "stop_loss": 2940.0,
                    "strategies": [
                        {"scanner_id": "ema_bounce", "scanner_name": "EMA 20 Bounce", "score": 80.0},
                        {"scanner_id": "volume_pocket_pivot", "scanner_name": "Pocket Pivot", "score": 82.0},
                    ],
                },
            ],
            "all_stocks": [
                {
                    "symbol": "TATAMOTORS",
                    "company_name": "Tata Motors Ltd",
                    "security_id": "3456",
                    "close": 985.50,
                    "change_pct": 3.2,
                    "volume": 5500000,
                    "volume_ratio": 2.4,
                    "match_count": 3,
                    "confluence_score": 92.5,
                    "primary_category": "Breakout",
                    "pivot_level": 990.0,
                    "stop_loss": 965.0,
                    "strategies": [
                        {"scanner_id": "vcp_breakout", "scanner_name": "VCP Breakout", "score": 90.0},
                    ],
                },
                {
                    "symbol": "RELIANCE",
                    "company_name": "Reliance Industries Ltd",
                    "security_id": "2885",
                    "close": 2980.0,
                    "change_pct": 1.8,
                    "volume": 3200000,
                    "volume_ratio": 1.6,
                    "match_count": 2,
                    "confluence_score": 81.0,
                    "primary_category": "Support",
                    "pivot_level": 3000.0,
                    "stop_loss": 2940.0,
                    "strategies": [],
                },
                {
                    "symbol": "INFY",
                    "company_name": "Infosys Ltd",
                    "security_id": "1594",
                    "close": 1820.0,
                    "change_pct": -0.5,
                    "volume": 1200000,
                    "volume_ratio": 0.9,
                    "match_count": 1,
                    "confluence_score": 65.0,
                    "primary_category": "Mean Reversion",
                    "pivot_level": None,
                    "stop_loss": None,
                    "strategies": [],
                },
            ],
            "strategies": {},
        }

    def tearDown(self):
        self.storage.close()
        self.temp_dir.cleanup()

    def test_save_and_retrieve_eod_digest_report_in_db(self):
        """Test saving report to DB and retrieving it by date and latest."""
        saved = self.storage.save_eod_digest_report(self.sample_report)
        self.assertTrue(saved)

        # Retrieve latest
        latest = self.storage.get_latest_eod_digest_report()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["date"], "2026-09-19")
        self.assertEqual(latest["universe"], "NIFTY_500")
        self.assertEqual(latest["total_scanners_run"], 12)
        self.assertEqual(len(latest["top_confluence_stocks"]), 2)

        # Retrieve by date
        dated = self.storage.get_eod_digest_report_by_date("2026-09-19")
        self.assertIsNotNone(dated)
        self.assertEqual(dated["date"], "2026-09-19")

        # Non-existent date
        non_existent = self.storage.get_eod_digest_report_by_date("2025-01-01")
        self.assertIsNone(non_existent)

    def test_list_eod_digest_dates(self):
        """Test listing dates chronologically descending."""
        report_18 = dict(self.sample_report, date="2026-09-18")
        report_19 = dict(self.sample_report, date="2026-09-19")
        report_17 = dict(self.sample_report, date="2026-09-17")

        self.storage.save_eod_digest_report(report_18)
        self.storage.save_eod_digest_report(report_19)
        self.storage.save_eod_digest_report(report_17)

        dates = self.storage.list_eod_digest_dates()
        self.assertEqual(dates, ["2026-09-19", "2026-09-18", "2026-09-17"])

    def test_eod_confluence_stocks_query(self):
        """Test relational queries against eod_confluence_stocks table."""
        self.storage.save_eod_digest_report(self.sample_report)

        # Query all stocks for date
        all_stocks = self.storage.get_eod_confluence_stocks(scan_date="2026-09-19", min_matches=1)
        self.assertEqual(len(all_stocks), 3)

        # Query only confluence stocks with min_matches >= 2
        conf_stocks = self.storage.get_eod_confluence_stocks(scan_date="2026-09-19", min_matches=2)
        self.assertEqual(len(conf_stocks), 2)
        self.assertEqual(conf_stocks[0]["symbol"], "TATAMOTORS")
        self.assertEqual(conf_stocks[0]["match_count"], 3)
        self.assertEqual(conf_stocks[0]["confluence_score"], 92.5)
        self.assertEqual(len(conf_stocks[0]["strategies"]), 1)

    def test_eod_report_upsert_same_date(self):
        """Test that re-running scan on the same date updates rows without duplicates."""
        self.storage.save_eod_digest_report(self.sample_report)

        # Modify report and save again
        updated_report = dict(self.sample_report)
        updated_report["total_matches"] = 25
        updated_report["confluence_stocks_count"] = 5
        self.storage.save_eod_digest_report(updated_report)

        dates = self.storage.list_eod_digest_dates()
        self.assertEqual(len(dates), 1)

        latest = self.storage.get_latest_eod_digest_report()
        self.assertEqual(latest["total_matches"], 25)
        self.assertEqual(latest["confluence_stocks_count"], 5)

    def test_store_dual_persistence_and_server_restart_recovery(self):
        """Test EODReportStore dual write and recovery across new store instance."""
        # 1. Save report via store
        saved_path = self.store.save_report(self.sample_report)
        self.assertTrue(saved_path.exists())

        # 2. Simulate server restart: new store instance pointing to fresh/empty file dir but same DB
        empty_cache_dir = Path(self.temp_dir.name) / "fresh_cache"
        recovered_store = EODReportStore(base_dir=empty_cache_dir, storage=self.storage)

        # 3. Verify recovered store can load from DB even with no local JSON files
        report = recovered_store.get_latest_report()
        self.assertIsNotNone(report)
        self.assertEqual(report["date"], "2026-09-19")
        self.assertEqual(report["unique_stocks_count"], 8)

        dates = recovered_store.list_available_dates()
        self.assertEqual(dates, ["2026-09-19"])

    def test_mysql_code_paths_with_mock(self):
        """Verify MySQL query execution paths with mock connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        mysql_storage = StrategyStorage(db_path=str(self.db_path), use_mysql=False)
        mysql_storage.is_mysql_active = True
        mysql_storage._mysql_conn = mock_conn

        # Test save
        success = mysql_storage.save_eod_digest_report(self.sample_report)
        self.assertTrue(success)
        self.assertTrue(mock_cursor.execute.called)

        # Test get latest
        mock_cursor.fetchone.return_value = (json.dumps(self.sample_report),)
        res = mysql_storage.get_latest_eod_digest_report()
        self.assertIsNotNone(res)
        self.assertEqual(res["date"], "2026-09-19")

        # Test list dates
        mock_cursor.fetchall.return_value = [("2026-09-19",), ("2026-09-18",)]
        dates = mysql_storage.list_eod_digest_dates()
        self.assertEqual(dates, ["2026-09-19", "2026-09-18"])

        # Test get confluence stocks
        mock_cursor.fetchall.return_value = [
            (1, "2026-09-19", "TATAMOTORS", "Tata Motors", "3456", 985.5, 3.2, 500000, 2.0, 3, 92.5, "Breakout", 990.0, 965.0, "[]", "2026-09-19 18:30:00")
        ]
        stocks = mysql_storage.get_eod_confluence_stocks("2026-09-19", min_matches=2)
        self.assertEqual(len(stocks), 1)
        self.assertEqual(stocks[0]["symbol"], "TATAMOTORS")


if __name__ == "__main__":
    unittest.main()

