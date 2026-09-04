"""Unit tests for DhanExecutor order execution and Security ID resolution."""

import unittest
from unittest.mock import MagicMock, patch
from news_based_strategy.core.models import TradeSignal
from news_based_strategy.execution.executor import DhanExecutor


class TestDhanExecutor(unittest.TestCase):
    """Test order execution, dynamic SecID resolution, and safety gates."""

    def test_dry_run_resolves_security_id_when_zero(self):
        executor = DhanExecutor(dry_run=True)
        # Signal with security_id="0" for BEL (known SecID: 383)
        signal = TradeSignal(
            symbol="BEL",
            security_id="0",
            action="BUY",
            product_type="CNC",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Major order win",
        )
        res = executor.execute_order(signal, ltp=300.0)
        self.assertTrue(res.success)
        self.assertIn("383", res.order_id)
        self.assertEqual(res.symbol, "BEL")
        self.assertGreater(res.quantity, 0)

    def test_live_mode_rejects_unresolvable_security_id(self):
        """In live mode, unresolvable security ID must be rejected defensively."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
        )
        mock_dhan = MagicMock()
        executor.dhan = mock_dhan
        executor.dry_run = False

        # Unknown symbol that cannot be resolved
        signal = TradeSignal(
            symbol="UNKNOWN_COMPANY_XYZ",
            security_id="0",
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="CONTRACT",
            summary="Test",
        )
        res = executor.execute_order(signal, ltp=100.0)
        self.assertFalse(res.success)
        self.assertEqual(res.quantity, 0)
        self.assertIn("ORDER REJECTED: Could not resolve Dhan security ID", res.remarks)
        # Verify Dhan place_order was NEVER called
        self.assertFalse(mock_dhan.place_order.called)

    def test_live_mode_places_order_with_resolved_security_id(self):
        """In live mode, valid symbol resolves SecID and passes it to Dhan API."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            super_order_enabled=False,
        )
        mock_dhan = MagicMock()
        mock_dhan.BUY = "BUY"
        mock_dhan.NSE = "NSE_EQ"
        mock_dhan.CNC = "CNC"
        mock_dhan.MARKET = "MARKET"
        mock_dhan.place_order.return_value = {"orderId": "DHAN_ORDER_9999"}
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="BEL",
            security_id="0",  # Will be resolved to "383"
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Defense order",
        )
        res = executor.execute_order(signal, ltp=300.0)
        self.assertTrue(res.success)
        self.assertEqual(res.order_id, "DHAN_ORDER_9999")

        # Verify place_order was invoked with security_id="383"
        mock_dhan.place_order.assert_called_once()
        _, kwargs = mock_dhan.place_order.call_args
        self.assertEqual(kwargs["security_id"], "383")
        self.assertEqual(kwargs["transaction_type"], "BUY")

    def test_dry_run_super_order_formatting(self):
        """Dry-run mode with Super Order enabled should format bracket order details."""
        executor = DhanExecutor(
            dry_run=True,
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
            product_type="CNC",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Major order win",
        )
        res = executor.execute_order(signal, ltp=300.0)
        self.assertTrue(res.success)
        self.assertEqual(res.product_type, "INTRADAY")
        self.assertIn("Simulated Super Order: Entry Limit ₹300.60", res.remarks)
        self.assertIn("TP ₹309.00 (+3.0%)", res.remarks)
        self.assertIn("SL ₹297.00 (-1.0%)", res.remarks)
        self.assertIn("Trail 5.0 pts", res.remarks)

    def test_live_mode_places_super_order(self):
        """Live mode with Super Order enabled should call dhan.place_super_order with bracket levels."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
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
        mock_dhan.place_super_order.return_value = {"orderId": "SUPER_ORDER_12345"}
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Major order win",
        )
        res = executor.execute_order(signal, ltp=300.0)
        self.assertTrue(res.success)
        self.assertEqual(res.order_id, "SUPER_ORDER_12345")
        self.assertEqual(res.product_type, "INTRADAY")

        mock_dhan.place_super_order.assert_called_once()
        _, kwargs = mock_dhan.place_super_order.call_args
        self.assertEqual(kwargs["security_id"], "383")
        self.assertEqual(kwargs["exchange_segment"], "NSE_EQ")
        self.assertEqual(kwargs["transaction_type"], "BUY")
        self.assertEqual(kwargs["order_type"], "LIMIT")
        self.assertEqual(kwargs["product_type"], "INTRA")
        self.assertEqual(kwargs["price"], 300.6)
        self.assertEqual(kwargs["targetPrice"], 309.0)
        self.assertEqual(kwargs["stopLossPrice"], 297.0)
        self.assertEqual(kwargs["trailingJump"], 5.0)


if __name__ == "__main__":
    unittest.main()
