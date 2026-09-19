"""Unit tests for EOD Multi-Scanner Daily Digest and Confluence Engine."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scanner_dhan.eod.models import (
    EODConfluenceStock,
    EODDigestReport,
    EODMatchedStrategy,
    EODStrategySummary,
)
from scanner_dhan.eod.runner import EODScanRunner
from scanner_dhan.eod.scheduler import EODScheduler
from scanner_dhan.eod.store import EODReportStore


class TestEODModelsAndStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = EODReportStore(base_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_retrieve_report(self):
        strat = EODMatchedStrategy(
            scanner_id="vcp_contraction",
            scanner_name="VCP Scanner",
            category="Chart Patterns & Breakout",
            signal="VCP Contraction Ready",
            level_desc="Pivot 7480",
            score=88.0,
        )
        stock = EODConfluenceStock(
            symbol="TRENT",
            company_name="Trent Ltd",
            security_id="1964",
            close=7450.0,
            change_pct=3.2,
            volume=1500000,
            volume_ratio=2.5,
            match_count=2,
            confluence_score=95.0,
            strategies=[strat],
        )
        report = EODDigestReport(
            date="2026-09-19",
            timestamp="2026-09-19T18:30:00+05:30",
            universe="NIFTY_500",
            total_scanners_run=12,
            total_matches=25,
            unique_stocks_count=18,
            confluence_stocks_count=5,
            bullish_count=15,
            bearish_count=3,
            top_confluence_stocks=[stock],
            all_stocks=[stock],
            strategies={
                "vcp_contraction": EODStrategySummary(
                    scanner_id="vcp_contraction",
                    scanner_name="VCP Scanner",
                    category="Chart Patterns",
                    icon="activity",
                    matches_count=1,
                    items=[stock.to_dict()],
                )
            },
        )

        saved_path = self.store.save_report(report.to_dict())
        self.assertTrue(saved_path.exists())

        # Test latest lookup
        latest = self.store.get_latest_report()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["date"], "2026-09-19")
        self.assertEqual(len(latest["top_confluence_stocks"]), 1)
        self.assertEqual(latest["top_confluence_stocks"][0]["symbol"], "TRENT")

        # Test date list
        dates = self.store.list_available_dates()
        self.assertIn("2026-09-19", dates)

        # Test date retrieval
        dated_report = self.store.get_report_by_date("2026-09-19")
        self.assertIsNotNone(dated_report)
        self.assertEqual(dated_report["unique_stocks_count"], 18)


class TestEODRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = EODReportStore(base_dir=self.temp_dir)
        self.runner = EODScanRunner(store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("scanner_dhan.eod.runner.ScannerRegistry.list_all")
    @patch("scanner_dhan.eod.runner.ScannerRegistry.run")
    def test_runner_confluence_detection(self, mock_run, mock_list_all):
        mock_list_all.return_value = [
            {"id": "vcp_contraction", "name": "VCP Scanner", "category": "Chart Patterns"},
            {"id": "order_block", "name": "Order Block", "category": "Smart Money Concepts"},
        ]

        # Mock result for scanner 1 (VCP)
        mock_item_1 = MagicMock()
        mock_item_1.symbol = "TRENT"
        mock_item_1.security_id = "1964"
        mock_item_1.company_name = "Trent Ltd"
        mock_item_1.current_price = 7450.0
        mock_item_1.change_pct = 3.2
        mock_item_1.volume = 1200000
        mock_item_1.volume_ratio = 2.4
        mock_item_1.status = "matched"
        mock_item_1.score = 85.0
        mock_item_1.level_description = "Pivot 7480"
        mock_item_1.signal = "Bullish VCP"
        mock_item_1.to_dict.return_value = {"symbol": "TRENT", "status": "matched"}

        # Mock result for scanner 2 (Order Block) - also matches TRENT and RELIANCE
        mock_item_2 = MagicMock()
        mock_item_2.symbol = "TRENT"
        mock_item_2.security_id = "1964"
        mock_item_2.company_name = "Trent Ltd"
        mock_item_2.current_price = 7450.0
        mock_item_2.change_pct = 3.2
        mock_item_2.volume = 1200000
        mock_item_2.volume_ratio = 2.4
        mock_item_2.status = "matched"
        mock_item_2.score = 90.0
        mock_item_2.level_description = "OB Zone 7350"
        mock_item_2.signal = "Demand Zone Retest"
        mock_item_2.to_dict.return_value = {"symbol": "TRENT", "status": "matched"}

        mock_item_3 = MagicMock()
        mock_item_3.symbol = "RELIANCE"
        mock_item_3.security_id = "2885"
        mock_item_3.company_name = "Reliance Ind"
        mock_item_3.current_price = 2950.0
        mock_item_3.change_pct = 1.1
        mock_item_3.volume = 3000000
        mock_item_3.volume_ratio = 1.2
        mock_item_3.status = "matched"
        mock_item_3.score = 75.0
        mock_item_3.level_description = "OB Zone 2920"
        mock_item_3.signal = "Demand Zone Retest"
        mock_item_3.to_dict.return_value = {"symbol": "RELIANCE", "status": "matched"}

        report_1 = MagicMock()
        report_1.results = [mock_item_1]

        report_2 = MagicMock()
        report_2.results = [mock_item_2, mock_item_3]

        mock_run.side_effect = [report_1, report_2]

        digest = self.runner.run_all(universe="NIFTY_500", target_date="2026-09-19")

        self.assertEqual(digest.unique_stocks_count, 2)
        self.assertEqual(digest.confluence_stocks_count, 1)  # Only TRENT matched both
        self.assertEqual(digest.top_confluence_stocks[0].symbol, "TRENT")
        self.assertEqual(digest.top_confluence_stocks[0].match_count, 2)
        self.assertGreater(digest.top_confluence_stocks[0].confluence_score, 85.0)


class TestEODScheduler(unittest.TestCase):
    def test_next_run_calculation(self):
        scheduler = EODScheduler(target_hour=18, target_minute=30)
        next_run = scheduler.get_next_run_ist()
        self.assertEqual(next_run.hour, 18)
        self.assertEqual(next_run.minute, 30)
        self.assertLess(next_run.weekday(), 5)  # Must be Monday-Friday

