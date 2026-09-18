"""Unit tests for ST-14 Bullish CE Strategy execution engine."""

from __future__ import annotations

from datetime import datetime
import tempfile
import unittest
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from st14_bullish_ce.models import (
    ExecutionMode,
    OrderStatus,
    ProductType,
    St14OptionContract,
    St14Position,
    St14StrategyConfig,
    St14TradeSignal,
)
from st14_bullish_ce.strategy import St14BullishCeStrategy


class TestSt14Strategy(unittest.TestCase):
    """Test suite for ST-14 Bullish CE Strategy orchestrator."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.config = St14StrategyConfig(
            mode=ExecutionMode.VIRTUAL,
            product_type=ProductType.INTRADAY,
            capital_per_trade=30000.0,
            target_profit_pct=40.0,
            stop_loss_pct=20.0,
            trailing_jump_pts=2.0,
            trade_cutoff_time="14:00",
            square_off_time="15:00",
        )
        setattr(self.config, "data_dir", self._tmp_dir.name)
        self.strategy = St14BullishCeStrategy(config=self.config)

    def tearDown(self):
        self._tmp_dir.cleanup()

    def test_entry_timing_window(self):
        """Validates 10:15 AM start and 14:00 PM cutoff."""
        ist = ZoneInfo("Asia/Kolkata")

        # 09:45 AM -> Blocked (early)
        dt_0945 = datetime(2026, 9, 17, 9, 45, tzinfo=ist)
        is_valid_0945, _ = self.strategy.is_within_entry_window(dt_0945)
        self.assertFalse(is_valid_0945)

        # 11:30 AM -> Valid
        dt_1130 = datetime(2026, 9, 17, 11, 30, tzinfo=ist)
        is_valid_1130, _ = self.strategy.is_within_entry_window(dt_1130)
        self.assertTrue(is_valid_1130)

        # 14:15 PM -> Blocked (cutoff reached)
        dt_1415 = datetime(2026, 9, 17, 14, 15, tzinfo=ist)
        is_valid_1415, _ = self.strategy.is_within_entry_window(dt_1415)
        self.assertFalse(is_valid_1415)

    def test_square_off_time(self):
        """Enforces 15:00 (3:00 PM IST) auto square-off for Intraday mode."""
        ist = ZoneInfo("Asia/Kolkata")

        # 14:45 PM -> Not square-off
        dt_1445 = datetime(2026, 9, 17, 14, 45, tzinfo=ist)
        self.assertFalse(self.strategy.is_square_off_time(dt_1445))

        # 15:00 PM -> Trigger square-off
        dt_1500 = datetime(2026, 9, 17, 15, 0, tzinfo=ist)
        self.assertTrue(self.strategy.is_square_off_time(dt_1500))

        # 15:10 PM -> Trigger square-off
        dt_1510 = datetime(2026, 9, 17, 15, 10, tzinfo=ist)
        self.assertTrue(self.strategy.is_square_off_time(dt_1510))

    def test_super_order_level_calculations(self):
        """Calculates correct Entry, Target (+40%), and SL (-20%) prices."""
        levels = self.strategy.calculate_super_order_levels(option_ltp=100.0)
        # Entry with 0.5% slippage = ₹100.50
        self.assertEqual(levels.entry_price, 100.50)
        # Target +40% on 100.50 = 100.50 * 1.4 = ₹140.70
        self.assertEqual(levels.target_price, 140.70)
        # SL -20% on 100.50 = 100.50 * 0.8 = ₹80.40
        self.assertEqual(levels.stop_loss_price, 80.40)
        self.assertEqual(levels.trailing_jump, 2.0)

    def test_order_quantity_sizing(self):
        """Calculates lot-aligned position sizing based on capital per trade."""
        # Capital = 30,000, Option Entry = ₹50, Lot Size = 250 -> Cost/lot = 12,500
        # 30,000 / 12,500 = 2 lots -> 500 shares
        qty = self.strategy.calculate_order_quantity(option_entry_price=50.0, lot_size=250)
        self.assertEqual(qty, 500)

    def test_virtual_order_execution_and_square_off(self):
        """Simulates placing a virtual Super Order and auto-closing at 3 PM."""
        opt = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="OPT_INFY_1900_CE",
            lot_size=300,
            ltp=45.0,
            is_next_month=True,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=45.0)

        signal = St14TradeSignal(
            signal_id="SIG_INFY_001",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertTrue(success)
        self.assertIsNotNone(pos)
        self.assertIn("VIRTUAL SUPER ORDER", remarks)
        self.assertEqual(len(self.strategy.active_positions), 1)

        # Update live PnL: price moved up to ₹55.0 (+22%)
        pos.update_pnl(live_ltp=55.0)
        self.assertGreater(pos.unrealized_pnl, 0)

        # Trigger 3:00 PM Square-off
        ist = ZoneInfo("Asia/Kolkata")
        dt_1500 = datetime(2026, 9, 17, 15, 0, tzinfo=ist)
        closed = self.strategy.square_off_intraday_positions(dt_1500)
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(self.strategy.active_positions), 0)
        self.assertEqual(len(self.strategy.closed_positions), 1)
        self.assertEqual(closed[0].status, "CLOSED")

        # Telemetry
        telemetry = self.strategy.get_strategy_telemetry()
        self.assertEqual(telemetry["active_positions_count"], 0)
        self.assertEqual(len(telemetry["closed_positions"]), 1)

    def test_dual_frequency_discovery_and_trigger_monitoring(self):
        """Validates Tier 1 hourly discovery scan followed by Tier 2 5-min price breach trigger."""
        from unittest.mock import patch
        from scanner_dhan.scanner.st14_scanner import St14ScanResult, St14Status

        ist = ZoneInfo("Asia/Kolkata")
        dt_1100 = datetime(2026, 9, 17, 11, 0, tzinfo=ist)

        mock_candidate = St14ScanResult(
            symbol="TATAMOTORS",
            security_id="3456",
            ltp=980.0,
            status=St14Status.QUALIFIED,
            is_at_support=True,
            daily_close=975.0,
            daily_ema20=940.0,
            five_day_high=970.0,
            is_5d_breakout=True,
            is_daily_bullish=True,
            hourly_close=978.0,
            hourly_ema20=965.0,
            five_hour_high=985.0,
            is_5h_breakout=False,
            is_hourly_bullish=True,
            vwap=975.0,
            vwap_dist_pct=0.51,
            vwap_angle_deg=48.0,
            is_vwap_near=True,
            is_vwap_rising=True,
            timing_valid=True,
            timing_message="OK",
            dist_to_5d_high_pct=1.0,
            dist_to_5h_high_pct=-0.5,
            analysis_time_ist="11:00:00",
        )

        mock_report = MagicMock()
        mock_report.results = [mock_candidate]
        mock_report.total_scanned = 1

        mock_opt = St14OptionContract(
            symbol="TATAMOTORS 29OCT26 1000 CE",
            underlying_symbol="TATAMOTORS",
            strike_price=1000.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="OPT_TATA_1000_CE",
            lot_size=500,
            ltp=22.0,
            is_next_month=True,
        )

        self.strategy.scanner = MagicMock()
        self.strategy.scanner.run.return_value = mock_report

        with patch("st14_bullish_ce.strategy.check_market_breadth") as mock_breadth, \
             patch("st14_bullish_ce.strategy.resolve_1otm_ce_contract", return_value=mock_opt), \
             patch("st14_bullish_ce.strategy.check_breakout_candle_cross") as mock_cross:

            mock_breadth.return_value = (True, {"nifty50_green": True, "banknifty_green": True, "message": "OK"})

            # 1. Tier 1 Hourly Discovery Scan -> Adds candidate to watchlist
            hourly_res = self.strategy.run_hourly_discovery_scan(target_dt=dt_1100)
            self.assertEqual(hourly_res["discovered_count"], 1)
            self.assertEqual(len(hourly_res["candidates"]), 1)
            self.assertIn("TATAMOTORS", self.strategy.breakout_watchlist)
            watch_item = self.strategy.breakout_watchlist["TATAMOTORS"]
            self.assertEqual(watch_item.breakout_candle_high, 985.0)
            self.assertEqual(watch_item.status, OrderStatus.WAITING_TRIGGER)

            # 2. Tier 2 5-Min Monitor Check - Price still at 982.0 (< 985.0) -> No order
            mock_cross.return_value = (False, 982.0, "Monitoring below high")
            check1 = self.strategy.run_5min_trigger_monitor(target_dt=dt_1100)
            self.assertEqual(check1["triggered_count"], 0)
            self.assertEqual(check1["orders_placed"], 0)
            self.assertEqual(watch_item.status, OrderStatus.WAITING_TRIGGER)

            # 3. Tier 2 5-Min Monitor Check - Price breaches high to 987.0 (> 985.0) -> Triggers Super Order!
            mock_cross.return_value = (True, 987.0, "Breached high")
            check2 = self.strategy.run_5min_trigger_monitor(target_dt=dt_1100)
            self.assertEqual(check2["triggered_count"], 1)
            self.assertEqual(check2["orders_placed"], 1)
            self.assertEqual(watch_item.status, OrderStatus.ORDER_PLACED)
            self.assertEqual(len(self.strategy.active_positions), 1)

            # 4. Verify Telemetry
            telemetry = self.strategy.get_strategy_telemetry()
            self.assertEqual(telemetry["last_hourly_candidates_count"], 1)
            self.assertEqual(telemetry["active_positions_count"], 1)
            self.assertEqual(len(telemetry["breakout_watchlist"]), 1)
            self.assertEqual(telemetry["breakout_watchlist"][0]["symbol"], "TATAMOTORS")

    def test_live_mode_rejects_synthetic_option(self):
        """Live mode must reject synthetic / unverified option contracts."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        self.strategy.provider.dhan = mock_dhan

        opt_synthetic = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="OPT_INFY_1900_CE",
            lot_size=300,
            ltp=45.0,
            is_synthetic=True,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=45.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_LIVE_01",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt_synthetic,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertIn("Option contract is synthetic", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)

    def test_live_mode_rejects_non_numeric_security_id(self):
        """Live mode must reject contracts without valid numeric security IDs."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        self.strategy.provider.dhan = mock_dhan

        opt_non_numeric = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="INVALID_NON_NUMERIC_ID",
            lot_size=300,
            ltp=45.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=45.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_LIVE_02",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt_non_numeric,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertIn("Invalid non-numeric security ID", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)

    def test_idempotency_prevents_duplicate_executions(self):
        """Re-executing the same signal or placing duplicate orders for the same contract must be rejected."""
        opt = St14OptionContract(
            symbol="TCS 29OCT26 4000 CE",
            underlying_symbol="TCS",
            strike_price=4000.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="OPT_TCS_4000_CE",
            lot_size=175,
            ltp=80.0,
            is_next_month=True,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=80.0)
        signal = St14TradeSignal(
            signal_id="SIG_TCS_IDEMPOTENT_01",
            symbol="TCS",
            underlying_sec_id="11536",
            underlying_ltp=3980.0,
            breakout_candle_high=3975.0,
            daily_ema20=3900.0,
            hourly_ema20=3950.0,
            vwap=3960.0,
            vwap_dist_pct=0.5,
            vwap_angle_deg=45.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        # 1. First execution succeeds
        success1, remarks1, pos1 = self.strategy.execute_order(signal)
        self.assertTrue(success1)
        self.assertIsNotNone(pos1)
        self.assertEqual(signal.status, OrderStatus.ORDER_PLACED)

        # 2. Second execution with the same signal is blocked
        success2, remarks2, pos2 = self.strategy.execute_order(signal)
        self.assertFalse(success2)
        self.assertIsNone(pos2)
        self.assertIn("already placed", remarks2.lower())

        # 3. Another signal with a new ID for the same active stock is also blocked
        signal2 = St14TradeSignal(
            signal_id="SIG_TCS_IDEMPOTENT_02",
            symbol="TCS",
            underlying_sec_id="11536",
            underlying_ltp=3990.0,
            breakout_candle_high=3975.0,
            daily_ema20=3900.0,
            hourly_ema20=3950.0,
            vwap=3960.0,
            vwap_dist_pct=0.5,
            vwap_angle_deg=45.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )
        success3, remarks3, pos3 = self.strategy.execute_order(signal2)
        self.assertFalse(success3)
        self.assertIsNone(pos3)
        self.assertIn("active position already open", remarks3.lower())

    def test_capital_limit_rejects_oversized_option_lot(self):
        """When 1 lot cost exceeds allocated capital, calculate_order_quantity must return 0 and execute_order must reject."""
        # Capital = ₹30,000. Option Entry = ₹200, Lot Size = 250 -> 1 lot cost = ₹50,000 (> ₹30,000)
        qty = self.strategy.calculate_order_quantity(option_entry_price=200.0, lot_size=250)
        self.assertEqual(qty, 0)

        opt_expensive = St14OptionContract(
            symbol="BAJFINANCE 29OCT26 7500 CE",
            underlying_symbol="BAJFINANCE",
            strike_price=7500.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="OPT_BAJ_7500_CE",
            lot_size=250,
            ltp=200.0,
            is_next_month=True,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=200.0)
        signal = St14TradeSignal(
            signal_id="SIG_BAJ_001",
            symbol="BAJFINANCE",
            underlying_sec_id="317",
            underlying_ltp=7400.0,
            breakout_candle_high=7380.0,
            daily_ema20=7200.0,
            hourly_ema20=7300.0,
            vwap=7350.0,
            vwap_dist_pct=0.5,
            vwap_angle_deg=45.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt_expensive,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertEqual(signal.status, OrderStatus.ORDER_REJECTED)
        self.assertIn("exceeds allocated capital", remarks)

    def test_live_mode_checks_broker_margin(self):
        """Live mode must query broker fund limits and reject if available margin is insufficient."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.margin_calculator.return_value = {
            "status": "success",
            "data": {"totalMargin": 15075.0},
        }
        mock_dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {
                "availabelBalance": 5000.0,  # Available ₹5,000 only
                "sodLimit": 5000.0,
            },
        }
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="12345",  # Valid numeric ID
            lot_size=300,
            ltp=50.0,  # 1 lot = 300 * 50.25 ≈ ₹15,075 (exceeds ₹5,000 available balance)
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=50.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_MARGIN_01",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertIn("Insufficient broker margin", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)
        mock_dhan.margin_calculator.assert_called_once()

    def test_live_margin_check_rejects_zero_balance(self):
        """Live mode must fail closed and reject if available balance is zero."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.margin_calculator.return_value = {
            "status": "success",
            "data": {"totalMargin": 15075.0},
        }
        mock_dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {
                "availabelBalance": 0.0,  # Zero balance
            },
        }
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="12345",
            lot_size=300,
            ltp=50.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=50.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_ZERO_BAL",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertIn("Available broker balance is zero or unavailable", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)

    def test_live_margin_check_rejects_margin_calculator_failure(self):
        """Live mode must fail closed if margin_calculator returns non-success or error."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.margin_calculator.return_value = {
            "status": "failure",
            "remarks": "Invalid security ID",
        }
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="12345",
            lot_size=300,
            ltp=50.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=50.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_MC_FAIL",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertIn("Broker margin calculation failed", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)

    def test_live_margin_check_fails_closed_on_exception(self):
        """If broker fund check raises exception in LIVE mode, fail-closed and reject order."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.margin_calculator.side_effect = ConnectionError("Broker timeout")
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="12345",
            lot_size=300,
            ltp=50.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=50.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_EXC_01",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertEqual(signal.status, OrderStatus.ORDER_REJECTED)
        self.assertIn("Broker fund limit check exception", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)

    def test_live_margin_check_approves_when_funds_sufficient(self):
        """When margin_calculator and get_fund_limits succeed and balance >= margin, order is dispatched."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.margin_calculator.return_value = {
            "status": "success",
            "data": {"totalMargin": 15075.0},
        }
        mock_dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {"availabelBalance": 50000.0},
        }
        mock_dhan.place_super_order.return_value = {
            "status": "success",
            "data": {"orderId": "LIVE_SUP_1001"},
        }
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="INFY 29OCT26 1900 CE",
            underlying_symbol="INFY",
            strike_price=1900.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="12345",
            lot_size=300,
            ltp=50.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=50.0)
        signal = St14TradeSignal(
            signal_id="SIG_INFY_SUFF_01",
            symbol="INFY",
            underlying_sec_id="1594",
            underlying_ltp=1880.0,
            breakout_candle_high=1875.0,
            daily_ema20=1820.0,
            hourly_ema20=1860.0,
            vwap=1870.0,
            vwap_dist_pct=0.53,
            vwap_angle_deg=44.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertTrue(success)
        self.assertIsNotNone(pos)
        self.assertEqual(pos.position_id, "LIVE_SUP_1001")
        self.assertEqual(mock_dhan.place_super_order.call_count, 1)

    def test_live_square_off_dispatches_broker_exit_orders(self):
        """Square-off in Live mode cancels target/SL legs, checks broker netQty, and places MARKET exit with price=0.0."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.SELL = "SELL"
        mock_dhan.MARKET = "MARKET"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderStatus": "TRADED"},
        }
        mock_dhan.cancel_super_order.return_value = {"status": "success"}
        mock_dhan.get_positions.return_value = {
            "status": "success",
            "data": [{"securityId": "12345", "netQty": 300}],
        }
        mock_dhan.place_order.return_value = {
            "status": "success",
            "data": {"orderId": "EXIT_ORD_777"},
        }
        self.strategy.provider.dhan = mock_dhan

        pos = St14Position(
            position_id="DHAN_ORD_999",
            symbol="INFY",
            option_symbol="INFY 29OCT26 1900 CE",
            security_id="12345",
            quantity=300,
            entry_price=50.0,
            current_ltp=55.0,
            target_price=70.0,
            stop_loss_price=40.0,
            product_type=ProductType.INTRADAY,
            mode=ExecutionMode.LIVE,
            entry_time_ist="2026-09-17 11:30:00",
        )
        self.strategy.active_positions["DHAN_ORD_999"] = pos

        closed = self.strategy.emergency_square_off_all()
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(self.strategy.active_positions), 0)

        # Verified that TARGET_LEG and STOP_LOSS_LEG cancellations were called
        mock_dhan.cancel_super_order.assert_any_call("DHAN_ORD_999", "TARGET_LEG")
        mock_dhan.cancel_super_order.assert_any_call("DHAN_ORD_999", "STOP_LOSS_LEG")

        # Verified that place_order was invoked with required positional price=0.0
        mock_dhan.place_order.assert_called_once_with(
            security_id="12345",
            exchange_segment="NSE_FNO",
            transaction_type="SELL",
            quantity=300,
            order_type="MARKET",
            product_type="INTRA",
            price=0.0,
            tag="st14_sqoff",
        )

    def test_live_square_off_pending_entry_cancels_without_selling(self):
        """When entry leg is pending, square-off cancels ENTRY_LEG and does NOT place market sell order."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderStatus": "PENDING"},
        }
        mock_dhan.cancel_super_order.return_value = {"status": "success"}
        mock_dhan.get_positions.return_value = {
            "status": "success",
            "data": [{"securityId": "12345", "netQty": 0}],
        }
        self.strategy.provider.dhan = mock_dhan

        pos = St14Position(
            position_id="DHAN_PENDING_01",
            symbol="INFY",
            option_symbol="INFY 29OCT26 1900 CE",
            security_id="12345",
            quantity=300,
            entry_price=50.0,
            current_ltp=50.0,
            target_price=70.0,
            stop_loss_price=40.0,
            product_type=ProductType.INTRADAY,
            mode=ExecutionMode.LIVE,
            entry_time_ist="2026-09-17 11:30:00",
        )
        self.strategy.active_positions["DHAN_PENDING_01"] = pos

        closed = self.strategy.emergency_square_off_all()
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(self.strategy.active_positions), 0)

        # Verified ENTRY_LEG cancellation
        mock_dhan.cancel_super_order.assert_called_once_with("DHAN_PENDING_01", "ENTRY_LEG")
        # Verified NO sell order was placed since netQty is 0
        self.assertEqual(mock_dhan.place_order.call_count, 0)

    def test_live_square_off_partial_fill_sells_only_net_qty(self):
        """When position was partially filled (e.g. 100 out of 300), exit only confirmed netQty."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.SELL = "SELL"
        mock_dhan.MARKET = "MARKET"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderStatus": "TRADED"},
        }
        mock_dhan.cancel_super_order.return_value = {"status": "success"}
        mock_dhan.get_positions.return_value = {
            "status": "success",
            "data": [{"securityId": "12345", "netQty": 100}],  # Only 100 filled
        }
        mock_dhan.place_order.return_value = {
            "status": "success",
            "data": {"orderId": "EXIT_PARTIAL_100"},
        }
        self.strategy.provider.dhan = mock_dhan

        pos = St14Position(
            position_id="DHAN_PARTIAL_01",
            symbol="INFY",
            option_symbol="INFY 29OCT26 1900 CE",
            security_id="12345",
            quantity=300,
            entry_price=50.0,
            current_ltp=52.0,
            target_price=70.0,
            stop_loss_price=40.0,
            product_type=ProductType.INTRADAY,
            mode=ExecutionMode.LIVE,
            entry_time_ist="2026-09-17 11:30:00",
        )
        self.strategy.active_positions["DHAN_PARTIAL_01"] = pos

        closed = self.strategy.emergency_square_off_all()
        self.assertEqual(len(closed), 1)

        # Verified place_order quantity was 100 (not 300)
        mock_dhan.place_order.assert_called_once_with(
            security_id="12345",
            exchange_segment="NSE_FNO",
            transaction_type="SELL",
            quantity=100,
            order_type="MARKET",
            product_type="INTRA",
            price=0.0,
            tag="st14_sqoff",
        )

    def test_live_square_off_failure_retains_position_with_exit_failed(self):
        """When broker exit order fails, position must NOT be removed from active positions and marked EXIT_FAILED."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.SELL = "SELL"
        mock_dhan.MARKET = "MARKET"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.get_order_by_id.return_value = {
            "status": "success",
            "data": {"orderStatus": "TRADED"},
        }
        mock_dhan.cancel_super_order.return_value = {"status": "success"}
        mock_dhan.get_positions.return_value = {
            "status": "success",
            "data": [{"securityId": "12345", "netQty": 300}],
        }
        mock_dhan.place_order.return_value = {
            "status": "failure",
            "remarks": "RMS: Margin/Order blocked",
        }
        self.strategy.provider.dhan = mock_dhan

        pos = St14Position(
            position_id="DHAN_FAIL_01",
            symbol="INFY",
            option_symbol="INFY 29OCT26 1900 CE",
            security_id="12345",
            quantity=300,
            entry_price=50.0,
            current_ltp=45.0,
            target_price=70.0,
            stop_loss_price=40.0,
            product_type=ProductType.INTRADAY,
            mode=ExecutionMode.LIVE,
            entry_time_ist="2026-09-17 11:30:00",
        )
        self.strategy.active_positions["DHAN_FAIL_01"] = pos

        closed = self.strategy.emergency_square_off_all()
        self.assertEqual(len(closed), 0)
        self.assertEqual(len(self.strategy.active_positions), 1)
        self.assertEqual(self.strategy.active_positions["DHAN_FAIL_01"].status, "EXIT_FAILED")
        self.assertIn("RMS: Margin/Order blocked", self.strategy.active_positions["DHAN_FAIL_01"].close_reason)

    def test_journal_persistence_and_reload(self):
        """Executed orders are saved to disk journal and reloaded upon restart."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = St14StrategyConfig(mode=ExecutionMode.VIRTUAL)
            setattr(cfg, "data_dir", tmp_dir)
            strat = St14BullishCeStrategy(config=cfg)

            opt = St14OptionContract(
                symbol="INFY 29OCT26 1900 CE",
                underlying_symbol="INFY",
                strike_price=1900.0,
                option_type="CE",
                expiry_date="2026-10-29",
                security_id="12345",
                lot_size=300,
                ltp=50.0,
                is_synthetic=False,
            )
            levels = strat.calculate_super_order_levels(option_ltp=50.0)
            signal = St14TradeSignal(
                signal_id="SIG_JOURNAL_01",
                symbol="INFY",
                underlying_sec_id="1594",
                underlying_ltp=1880.0,
                breakout_candle_high=1875.0,
                daily_ema20=1820.0,
                hourly_ema20=1860.0,
                vwap=1870.0,
                vwap_dist_pct=0.53,
                vwap_angle_deg=44.0,
                status=OrderStatus.TRIGGERED,
                nifty_green=True,
                banknifty_green=True,
                is_confirmed=True,
                option_contract=opt,
                order_levels=levels,
            )

            success, remarks, pos = strat.execute_order(signal)
            self.assertTrue(success)

            # Re-instantiate strategy pointing to same journal directory
            strat2 = St14BullishCeStrategy(config=cfg)
            self.assertIn("SIG_JOURNAL_01", strat2._executed_signal_ids)

            # Attempt duplicate execution with fresh signal object having same signal_id
            signal2 = St14TradeSignal(
                signal_id="SIG_JOURNAL_01",
                symbol="INFY",
                underlying_sec_id="1594",
                underlying_ltp=1880.0,
                breakout_candle_high=1875.0,
                daily_ema20=1820.0,
                hourly_ema20=1860.0,
                vwap=1870.0,
                vwap_dist_pct=0.53,
                vwap_angle_deg=44.0,
                status=OrderStatus.TRIGGERED,
                nifty_green=True,
                banknifty_green=True,
                is_confirmed=True,
                option_contract=opt,
                order_levels=levels,
            )
            success2, remarks2, _ = strat2.execute_order(signal2)
            self.assertFalse(success2)
            self.assertIn("already been executed", remarks2)

    def test_deterministic_order_tag_passed_to_broker(self):
        """When placing live Super Order, deterministic tag (<=20 alphanumeric chars) is supplied."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.margin_calculator.return_value = {
            "status": "success",
            "data": {"totalMargin": 15075.0},
        }
        mock_dhan.get_fund_limits.return_value = {
            "status": "success",
            "data": {"availabelBalance": 50000.0},
        }
        mock_dhan.place_super_order.return_value = {
            "status": "success",
            "data": {"orderId": "LIVE_SUP_2001"},
        }
        mock_dhan.get_order_list.return_value = {"status": "success", "data": []}
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="TCS 29OCT26 4000 CE",
            underlying_symbol="TCS",
            strike_price=4000.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="11536",
            lot_size=175,
            ltp=80.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=80.0)
        signal = St14TradeSignal(
            signal_id="SIG_TCS_DET_TAG_01",
            symbol="TCS",
            underlying_sec_id="11536",
            underlying_ltp=3980.0,
            breakout_candle_high=3975.0,
            daily_ema20=3900.0,
            hourly_ema20=3950.0,
            vwap=3960.0,
            vwap_dist_pct=0.5,
            vwap_angle_deg=45.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertTrue(success)
        mock_dhan.place_super_order.assert_called_once()
        _, kwargs = mock_dhan.place_super_order.call_args
        order_tag = kwargs.get("tag")
        self.assertIsNotNone(order_tag)
        self.assertTrue(order_tag.startswith("ST14_"))
        self.assertLessEqual(len(order_tag), 20)

    def test_pre_order_broker_reconciliation_blocks_duplicate(self):
        """If broker order book already contains a matching active/traded order today, order is blocked without placing a duplicate."""
        self.strategy.config.mode = ExecutionMode.LIVE
        mock_dhan = MagicMock()
        mock_dhan.NSE_FNO = "NSE_FNO"
        mock_dhan.BUY = "BUY"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.get_order_list.return_value = {
            "status": "success",
            "data": [
                {
                    "orderId": "DHAN_EXISTING_999",
                    "orderStatus": "TRADED",
                    "securityId": "11536",
                    "tradingSymbol": "TCS 29OCT26 4000 CE",
                    "tag": "ST14_SOMEHASH",
                }
            ],
        }
        self.strategy.provider.dhan = mock_dhan

        opt = St14OptionContract(
            symbol="TCS 29OCT26 4000 CE",
            underlying_symbol="TCS",
            strike_price=4000.0,
            option_type="CE",
            expiry_date="2026-10-29",
            security_id="11536",
            lot_size=175,
            ltp=80.0,
            is_synthetic=False,
        )
        levels = self.strategy.calculate_super_order_levels(option_ltp=80.0)
        signal = St14TradeSignal(
            signal_id="SIG_TCS_RECON_01",
            symbol="TCS",
            underlying_sec_id="11536",
            underlying_ltp=3980.0,
            breakout_candle_high=3975.0,
            daily_ema20=3900.0,
            hourly_ema20=3950.0,
            vwap=3960.0,
            vwap_dist_pct=0.5,
            vwap_angle_deg=45.0,
            status=OrderStatus.TRIGGERED,
            nifty_green=True,
            banknifty_green=True,
            is_confirmed=True,
            option_contract=opt,
            order_levels=levels,
        )

        success, remarks, pos = self.strategy.execute_order(signal)
        self.assertFalse(success)
        self.assertIsNone(pos)
        self.assertIn("Broker order already exists", remarks)
        self.assertEqual(mock_dhan.place_super_order.call_count, 0)
        self.assertIn("SIG_TCS_RECON_01", self.strategy._executed_signal_ids)

    def test_corrupt_journal_backup_and_live_broker_recovery(self):
        """Corrupt journal JSON file is backed up and re-populated via broker order reconciliation in LIVE mode."""
        import json, os, tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = St14StrategyConfig(mode=ExecutionMode.LIVE)
            setattr(cfg, "data_dir", tmp_dir)
            journal_path = os.path.join(tmp_dir, "st14_executed_orders.json")

            # Write broken / corrupted JSON to journal file
            with open(journal_path, "w", encoding="utf-8") as f:
                f.write("{ INVALID JSON DATA CORRUPTED !!!")

            mock_dhan = MagicMock()
            mock_dhan.get_order_list.return_value = {
                "status": "success",
                "data": [
                    {
                        "orderId": "BROKER_RECOVERED_1",
                        "orderStatus": "TRADED",
                        "securityId": "12345",
                        "tradingSymbol": "INFY 29OCT26 1900 CE",
                        "tag": "ST14_RECOVERED",
                    }
                ],
            }
            mock_provider = MagicMock()
            mock_provider.dhan = mock_dhan

            strat = St14BullishCeStrategy(config=cfg, provider=mock_provider)
            # Reconciled from broker order book
            self.assertIn("ST14_RECOVERED", strat._executed_order_keys)


if __name__ == "__main__":
    unittest.main()





