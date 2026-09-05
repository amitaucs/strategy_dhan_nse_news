"""Unit tests for SQLite persistent storage."""

import os
import tempfile
import unittest
from news_based_strategy.core.models import FilingAudit, TradeResult
from news_based_strategy.storage.repository import StrategyStorage


class TestStrategyStorage(unittest.TestCase):
    """Test deduplication and logging in SQLite."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_strategy.db")
        self.storage = StrategyStorage(self.db_path)

    def tearDown(self):
        self.storage.close()
        self.temp_dir.cleanup()

    def test_deduplication(self):
        self.assertFalse(self.storage.is_processed("SEQ_101"))

        self.storage.mark_processed("SEQ_101", "TATAMOTORS", "04-Sep-2026")
        self.assertTrue(self.storage.is_processed("SEQ_101"))

        # Re-marking the same sequence ID should be ignored gracefully
        self.storage.mark_processed("SEQ_101", "TATAMOTORS", "04-Sep-2026")
        self.assertEqual(self.storage.get_processed_count(), 1)

    def test_audit_and_trade_logging(self):
        audit = FilingAudit(
            sentiment="BULLISH",
            confidence=90,
            catalyst_type="ORDER_WIN",
            material_impact=True,
            summary="New project won",
        )
        self.storage.save_audit("SEQ_102", "BEL", audit)

        trade = TradeResult(
            success=True,
            symbol="BEL",
            action="BUY",
            quantity=50,
            product_type="INTRADAY",
            order_id="DRY_12345",
            dry_run=True,
        )
        self.storage.save_trade(trade)

        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT sentiment, confidence FROM audit_logs WHERE seq_id = 'SEQ_102'")
        row = cursor.fetchone()
        self.assertEqual(row[0], "BULLISH")
        self.assertEqual(row[1], 90)

        cursor.execute("SELECT action, quantity, dry_run FROM trade_executions WHERE symbol = 'BEL'")
        trade_row = cursor.fetchone()
        self.assertEqual(trade_row[0], "BUY")
        self.assertEqual(trade_row[1], 50)
        self.assertEqual(trade_row[2], 1)

    def test_get_processed_seq_ids(self):
        """Test preloading sequence IDs into a Python set."""
        self.storage.mark_processed("SEQ_201", "INFY")
        self.storage.mark_processed("SEQ_202", "TCS")
        self.storage.mark_processed("SEQ_203", "RELIANCE")

        ids = self.storage.get_processed_seq_ids()
        self.assertIn("SEQ_201", ids)
        self.assertIn("SEQ_202", ids)
        self.assertIn("SEQ_203", ids)
        self.assertEqual(len(ids), 3)

    def test_status_description(self):
        """Test human readable status string."""
        desc = self.storage.get_status_description()
        self.assertIn("SQLite", desc)
        self.assertIn("0 stored filings", desc)

    def test_mysql_fallback_when_unreachable(self):
        """Verify storage falls back to SQLite when MySQL is unreachable."""
        fallback_storage = StrategyStorage(
            db_path=os.path.join(self.temp_dir.name, "fallback.db"),
            use_mysql=True,
            host="invalid-host-999.example.com",
            port=3306,
            user="bad_user",
            password="bad_password",
            database="bad_db",
        )
        try:
            self.assertFalse(fallback_storage.is_mysql_active)
            self.assertIsNotNone(fallback_storage._sqlite_conn)
            # Should still function properly on SQLite
            fallback_storage.mark_processed("FALLBACK_01", "BEL")
            self.assertTrue(fallback_storage.is_processed("FALLBACK_01"))
        finally:
            fallback_storage.close()

    def test_monitor_warmup_and_marking(self):
        """Verify NSEFilingMonitor warms up seen_seq_ids and marks new filings."""
        from news_based_strategy.ingestion.monitor import NSEFilingMonitor
        import json

        self.storage.mark_processed("OLD_SEQ_99", "HAL")

        monitor = NSEFilingMonitor(storage=self.storage, auto_refresh=False)
        self.assertIn("OLD_SEQ_99", monitor.seen_seq_ids)

        payload = [
            {
                "seq_id": "NEW_SEQ_100",
                "symbol": "BEL",
                "desc": "Receipt of Order",
                "an_dt": "04-Sep-2026 12:00:00",
            }
        ]
        with unittest.mock.patch.object(monitor, "_do_get", return_value=(200, json.dumps(payload))):
            items = monitor.get_new_announcements(fno_only=False, filter_noise=False)
            self.assertEqual(len(items), 1)
            self.assertIn("NEW_SEQ_100", monitor.seen_seq_ids)
            # Storage should now also have NEW_SEQ_100
            self.assertTrue(self.storage.is_processed("NEW_SEQ_100"))

    def test_settings_persistence(self):
        """Test setting, getting, upserting, and deleting key-value configuration in DB."""
        # Non-existent setting returns default
        self.assertIsNone(self.storage.get_setting("non_existent_key"))
        self.assertEqual(self.storage.get_setting("non_existent_key", default="fallback"), "fallback")

        # Set and get settings
        self.storage.set_setting("dhan_app_id", "APP_12345")
        self.storage.set_setting("dhan_app_secret", "SEC_98765")
        self.storage.set_setting("dhan_client_id", "CLIENT_555")

        self.assertEqual(self.storage.get_setting("dhan_app_id"), "APP_12345")
        self.assertEqual(self.storage.get_setting("dhan_app_secret"), "SEC_98765")
        self.assertEqual(self.storage.get_setting("dhan_client_id"), "CLIENT_555")

        # Upsert (update existing key)
        self.storage.set_setting("dhan_app_id", "APP_99999_UPDATED")
        self.assertEqual(self.storage.get_setting("dhan_app_id"), "APP_99999_UPDATED")

        # Get all settings dictionary
        all_settings = self.storage.get_all_settings()
        self.assertIn("dhan_app_id", all_settings)
        self.assertEqual(all_settings["dhan_app_id"], "APP_99999_UPDATED")
        self.assertEqual(all_settings["dhan_app_secret"], "SEC_98765")

        # Delete setting
        deleted = self.storage.delete_setting("dhan_app_secret")
        self.assertTrue(deleted)
        self.assertIsNone(self.storage.get_setting("dhan_app_secret"))


if __name__ == "__main__":
    unittest.main()


