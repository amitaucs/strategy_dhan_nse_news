"""Comprehensive unit tests for Phase 3: Order Placement, Dhan Super Orders, and 10 Shares Cap."""

import tempfile
import unittest
from unittest.mock import MagicMock, patch
from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, FilingAudit, TradeResult, TradeSignal
from news_based_strategy.engine import StrategyEngine
from news_based_strategy.execution.executor import DhanExecutor
from news_based_strategy.execution.risk import RiskManager
from news_based_strategy.storage.repository import StrategyStorage


class TestPhase3Execution(unittest.TestCase):
    """Test suite for Phase 3 Super Order placement, max 10 share cap, and trigger gates."""

    def test_max_shares_per_trade_cap(self):
        """Test that position sizing never exceeds the max_shares_per_trade cap (10 shares)."""
        # Low price stock (₹50) with ₹20,000 capital: 400 shares -> Capped to 10
        qty_low_price = RiskManager.calculate_position_size(capital=20000.0, ltp=50.0, max_quantity=10)
        self.assertEqual(qty_low_price, 10)

        # Mid price stock (₹300) with ₹20,000 capital: 66 shares -> Capped to 10
        qty_mid_price = RiskManager.calculate_position_size(capital=20000.0, ltp=300.0, max_quantity=10)
        self.assertEqual(qty_mid_price, 10)

        # High price stock (₹5,000) with ₹20,000 capital: 4 shares -> 4 shares (<= 10)
        qty_high_price = RiskManager.calculate_position_size(capital=20000.0, ltp=5000.0, max_quantity=10)
        self.assertEqual(qty_high_price, 4)

        # Very high price stock (₹25,000) with ₹20,000 capital: 0 shares -> Floored to 1 share (<= 10)
        qty_very_high_price = RiskManager.calculate_position_size(capital=20000.0, ltp=25000.0, max_quantity=10)
        self.assertEqual(qty_very_high_price, 1)

        # Custom cap (e.g. 5 shares)
        qty_custom_cap = RiskManager.calculate_position_size(capital=20000.0, ltp=100.0, max_quantity=5)
        self.assertEqual(qty_custom_cap, 5)

    def test_default_config_settings(self):
        """Test that Phase 3 default settings are properly loaded from config/env."""
        self.assertEqual(settings.max_shares_per_trade, 10)
        self.assertEqual(settings.confidence_threshold, 70)
        self.assertTrue(settings.super_order_enabled)
        self.assertEqual(settings.target_profit_pct, 3.0)
        self.assertEqual(settings.stop_loss_pct, 1.0)
        self.assertEqual(settings.trailing_jump_points, 5.0)
        self.assertEqual(settings.slippage_buffer_pct, 0.2)

    def test_executor_dry_run_super_order_with_10_shares_cap(self):
        """Test that DhanExecutor respects max 10 shares and formats bracket levels in dry-run."""
        executor = DhanExecutor(
            dry_run=True,
            capital_per_trade=20000.0,
            max_shares_per_trade=10,
            super_order_enabled=True,
            target_profit_pct=3.0,
            stop_loss_pct=1.0,
            trailing_jump_points=5.0,
            slippage_buffer_pct=0.2,
        )

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="INTRADAY",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Major defense export contract win",
        )

        result = executor.execute_order(signal, ltp=300.0)
        self.assertTrue(result.success)
        self.assertEqual(result.quantity, 10)
        self.assertEqual(result.product_type, "INTRADAY")
        self.assertTrue(result.dry_run)
        self.assertIn("Simulated Super Order: Entry Limit ₹300.60", result.remarks)
        self.assertIn("TP ₹309.00 (+3.0%)", result.remarks)
        self.assertIn("SL ₹297.00 (-1.0%)", result.remarks)
        self.assertIn("Trail 5.0 pts", result.remarks)

    def test_executor_live_super_order_call(self):
        """Test that live DhanExecutor calls place_super_order with correct capped quantity and levels."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            capital_per_trade=20000.0,
            max_shares_per_trade=10,
            super_order_enabled=True,
            target_profit_pct=3.0,
            stop_loss_pct=1.0,
            trailing_jump_points=5.0,
            slippage_buffer_pct=0.2,
        )
        mock_dhan = MagicMock()
        mock_dhan.BUY = "BUY"
        mock_dhan.NSE = "NSE_EQ"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.place_super_order.return_value = {"orderId": "LIVE_SUPER_789"}
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="INTRADAY",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Defense order",
        )

        result = executor.execute_order(signal, ltp=300.0)
        self.assertTrue(result.success)
        self.assertEqual(result.quantity, 10)
        self.assertEqual(result.order_id, "LIVE_SUPER_789")

        mock_dhan.place_super_order.assert_called_once_with(
            security_id="383",
            exchange_segment="NSE_EQ",
            transaction_type="BUY",
            quantity=10,
            order_type="LIMIT",
            product_type="INTRA",
            price=300.6,
            targetPrice=309.0,
            stopLossPrice=297.0,
            trailingJump=5.0,
            tag="news_super",
        )

    def test_strategy_engine_bullish_high_conviction_triggers_trade(self):
        """Bullish + confidence >= 70% + material_impact=True MUST trigger order execution."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            storage = StrategyStorage(db_path=tmp.name, use_mysql=False)
            mock_analyzer = MagicMock()
            mock_analyzer.audit.return_value = FilingAudit(
                sentiment="BULLISH",
                confidence=85,
                catalyst_type="ORDER_WIN",
                material_impact=True,
                summary="Secured landmark defense contract worth INR 3850 Cr",
            )
            mock_executor = MagicMock()
            mock_executor.execute_order.return_value = TradeResult(
                success=True,
                symbol="BEL",
                action="BUY",
                quantity=10,
                product_type="INTRADAY",
                order_id="DRY_BEL_383_85",
                dry_run=True,
            )

            engine = StrategyEngine(
                storage=storage,
                analyzer=mock_analyzer,
                executor=mock_executor,
            )

            item = Announcement(
                seq_id="TEST_BULLISH_001",
                symbol="BEL",
                desc="Major defense order win",
                details="Export contract worth 3850 Cr",
                an_dt="04-Sep-2026 15:00:00",
                is_fno=True,
            )

            signal = engine.process_announcement(item)
            self.assertIsNotNone(signal)
            self.assertEqual(signal.symbol, "BEL")
            self.assertEqual(signal.action, "BUY")
            self.assertEqual(signal.confidence, 85)
            mock_executor.execute_order.assert_called_once()

    def test_strategy_engine_bearish_high_conviction_skips_trade(self):
        """Bearish filing in Phase 3 should be audited and logged, but skip order placement."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            storage = StrategyStorage(db_path=tmp.name, use_mysql=False)
            mock_analyzer = MagicMock()
            mock_analyzer.audit.return_value = FilingAudit(
                sentiment="BEARISH",
                confidence=90,
                catalyst_type="PENALTY",
                material_impact=True,
                summary="RBI imposes severe monetary penalty and business halt",
            )
            mock_executor = MagicMock()

            engine = StrategyEngine(
                storage=storage,
                analyzer=mock_analyzer,
                executor=mock_executor,
            )

            item = Announcement(
                seq_id="TEST_BEARISH_001",
                symbol="BANKINDIA",
                desc="RBI regulatory penalty",
                details="Penalty of 120 Cr imposed",
                an_dt="04-Sep-2026 15:00:00",
                is_fno=True,
            )

            signal = engine.process_announcement(item)
            self.assertIsNone(signal)
            # Executor should NEVER have been called for Bearish filings in Phase 3
            self.assertFalse(mock_executor.execute_order.called)

    def test_strategy_engine_low_confidence_skips_trade(self):
        """Bullish filing with confidence < 70% must NOT trigger order placement."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            storage = StrategyStorage(db_path=tmp.name, use_mysql=False)
            mock_analyzer = MagicMock()
            mock_analyzer.audit.return_value = FilingAudit(
                sentiment="BULLISH",
                confidence=65,  # Below 70% threshold
                catalyst_type="ORDER_WIN",
                material_impact=True,
                summary="Small order received",
            )
            mock_executor = MagicMock()

            engine = StrategyEngine(
                storage=storage,
                analyzer=mock_analyzer,
                executor=mock_executor,
            )

            item = Announcement(
                seq_id="TEST_LOW_CONF_001",
                symbol="BEL",
                desc="Small order receipt",
                details="Minor contract",
                an_dt="04-Sep-2026 15:00:00",
                is_fno=True,
            )

            signal = engine.process_announcement(item)
            self.assertIsNone(signal)
            self.assertFalse(mock_executor.execute_order.called)

    def test_strategy_engine_low_material_impact_skips_trade(self):
        """Bullish filing with material_impact=False must NOT trigger order placement."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            storage = StrategyStorage(db_path=tmp.name, use_mysql=False)
            mock_analyzer = MagicMock()
            mock_analyzer.audit.return_value = FilingAudit(
                sentiment="BULLISH",
                confidence=90,
                catalyst_type="ROUTINE",
                material_impact=False,  # Not material
                summary="Routine non-material disclosure",
            )
            mock_executor = MagicMock()

            engine = StrategyEngine(
                storage=storage,
                analyzer=mock_analyzer,
                executor=mock_executor,
            )

            item = Announcement(
                seq_id="TEST_LOW_IMPACT_001",
                symbol="BEL",
                desc="Routine disclosure",
                details="Non-material",
                an_dt="04-Sep-2026 15:00:00",
                is_fno=True,
            )

            signal = engine.process_announcement(item)
            self.assertIsNone(signal)
            self.assertFalse(mock_executor.execute_order.called)

    def test_storage_trade_executions_persistence(self):
        """Test persisting and querying trade execution records."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            storage = StrategyStorage(db_path=tmp.name, use_mysql=False)
            trade = TradeResult(
                success=True,
                symbol="BEL",
                action="BUY",
                quantity=10,
                product_type="INTRADAY",
                order_id="DRY_BEL_383_95",
                remarks="Simulated Super Order: Entry Limit ₹300.60, TP ₹309.00 (+3.0%), SL ₹297.00 (-1.0%), Trail 5.0 pts",
                dry_run=True,
            )
            storage.save_trade(trade)

            cursor = storage.conn.cursor()
            cursor.execute("SELECT symbol, action, quantity, product_type, order_id, dry_run FROM trade_executions")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "BEL")
            self.assertEqual(row[1], "BUY")
            self.assertEqual(row[2], 10)
            self.assertEqual(row[3], "INTRADAY")
            self.assertEqual(row[4], "DRY_BEL_383_95")
            self.assertEqual(row[5], 1)


if __name__ == "__main__":
    unittest.main()

