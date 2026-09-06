"""Unit tests for SQLite repository persistence."""

from datetime import datetime
import os
import tempfile
import unittest

from st15_largecap.core.models import Position, PositionStatus, ScanResult, SetupSignal, SignalStatus, TradeOrder
from st15_largecap.storage.repository import Repository


class TestRepository(unittest.TestCase):
    def setUp(self):
        self.tmp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_file.close()
        self.repo = Repository(db_path=self.tmp_file.name)

    def tearDown(self):
        if os.path.exists(self.tmp_file.name):
            os.remove(self.tmp_file.name)

    def test_save_and_get_scans(self):
        scan1 = ScanResult(
            symbol="TCS",
            sec_id="11536",
            ltp=3500.0,
            ema_20=3480.0,
            ema_50=3420.0,
            ema_200=3300.0,
            is_ema_stacked=True,
            is_in_dip=True,
            nearest_ema="EMA_20",
            nearest_ema_dist_pct=0.2,
            is_ha_green=True,
            is_supertrend_green=True,
            is_setup_ready=True,
            swing_low=3400.0,
            candles_count=60,
        )
        self.repo.save_scan_results([scan1])
        results = self.repo.get_latest_scans()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["symbol"], "TCS")
        self.assertEqual(results[0]["is_setup_ready"], 1)

    def test_save_and_get_signals(self):
        sig = SetupSignal(
            symbol="RELIANCE",
            sec_id="2885",
            setup_time=datetime.now(),
            trigger_price=2900.0,
            stop_loss_price=2820.0,
            target_profit_price=3140.0,
            risk_per_share=80.0,
            risk_reward_ratio=3.0,
            ema_20=2880.0,
            ema_50=2800.0,
            ema_200=2650.0,
            supertrend=2810.0,
            ha_close=2895.0,
            ha_open=2870.0,
            nearest_ema_name="EMA_20",
            nearest_ema_dist_pct=0.1,
            status=SignalStatus.TRIGGERED,
        )
        sig_id = self.repo.save_signal(sig)
        self.assertGreater(sig_id, 0)

        signals = self.repo.get_signals()
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["symbol"], "RELIANCE")
        self.assertEqual(signals[0]["trigger_price"], 2900.0)

    def test_save_and_get_positions(self):
        pos = Position(
            id=None,
            symbol="INFY",
            sec_id="1594",
            quantity=50,
            entry_price=1800.0,
            entry_time=datetime.now(),
            stop_loss=1750.0,
            target_price=1950.0,
            current_price=1850.0,
            product_type="CNC",
            status=PositionStatus.OPEN,
        )
        pos_id = self.repo.save_position(pos)
        self.assertGreater(pos_id, 0)

        positions = self.repo.get_positions(status="OPEN")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "INFY")


if __name__ == "__main__":
    unittest.main()
