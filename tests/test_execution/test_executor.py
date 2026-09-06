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
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
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
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
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
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
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

    def test_jwt_expiry_check_valid_and_expired(self):
        """Test parse_jwt_claims and check_token_expiry with future and past timestamps."""
        import base64
        import json
        import time
        from news_based_strategy.execution.executor import check_token_expiry, parse_jwt_claims

        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")

        # Future token (Valid)
        future_ts = int(time.time()) + 3600
        future_payload = base64.urlsafe_b64encode(json.dumps({"exp": future_ts, "dhanClientId": "12345"}).encode()).decode().rstrip("=")
        future_token = f"{header}.{future_payload}.signature"

        claims = parse_jwt_claims(future_token)
        self.assertEqual(claims["dhanClientId"], "12345")

        is_exp, msg, exp_ts = check_token_expiry(future_token)
        self.assertFalse(is_exp)
        self.assertIn("Valid until", msg)
        self.assertEqual(exp_ts, future_ts)

        # Past token (Expired)
        past_ts = int(time.time()) - 3600
        past_payload = base64.urlsafe_b64encode(json.dumps({"exp": past_ts, "dhanClientId": "12345"}).encode()).decode().rstrip("=")
        past_token = f"{header}.{past_payload}.signature"

        is_exp_past, msg_past, exp_ts_past = check_token_expiry(past_token)
        self.assertTrue(is_exp_past)
        self.assertIn("Token expired on", msg_past)
        self.assertEqual(exp_ts_past, past_ts)

        # DhanExecutor.validate_token rejects expired token
        executor = DhanExecutor(client_id="12345", access_token=past_token, dry_run=False)
        val = executor.validate_token()
        self.assertFalse(val["valid"])
        self.assertTrue(val["is_expired"])
        self.assertIn("EXPIRED", val["message"])

    def test_cutoff_time_order_rejection(self):
        """Orders placed after trade cutoff time (14:45 IST) must be rejected defensively."""
        executor = DhanExecutor(dry_run=False, trade_cutoff_time="14:45", max_news_age_seconds=0)
        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Major order win",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(False, "Trade cutoff reached (14:45 IST). No new trades permitted.")):
            res = executor.execute_order(signal, ltp=300.0)
            self.assertFalse(res.success)
            self.assertEqual(res.quantity, 0)
            self.assertIn("ORDER REJECTED: Trade cutoff reached", res.remarks)

    def test_square_off_all_positions_dry_run(self):
        """In dry-run mode, square_off_all_positions should return simulated square-off summary."""
        executor = DhanExecutor(dry_run=True)
        res = executor.square_off_all_positions()
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["orders_cancelled"], 0)
        self.assertEqual(res["positions_squared_off"], 0)

    def test_square_off_all_positions_live(self):
        """In live mode, square_off_all_positions must cancel open orders and close positions."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
        )
        mock_dhan = MagicMock()
        mock_dhan.BUY = "BUY"
        mock_dhan.SELL = "SELL"
        mock_dhan.NSE = "NSE_EQ"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.MARKET = "MARKET"

        # Mock open orders (2 regular orders)
        mock_dhan.get_order_list.return_value = {
            "status": "success",
            "data": [
                {"orderId": "ORD_101", "orderStatus": "PENDING", "legName": "ENTRY_LEG", "superOrderId": None},
                {"orderId": "ORD_102", "orderStatus": "TRANSIT", "legName": "STOP_LOSS_LEG", "superOrderId": None},
            ]
        }
        mock_dhan.cancel_order.return_value = {"status": "success"}
        # Mock open super orders (1 super order)
        mock_dhan.get_super_order_list.return_value = {
            "status": "success",
            "data": [
                {"orderId": "SO_201", "orderStatus": "PENDING"},
            ]
        }
        mock_dhan.cancel_super_order.return_value = {"status": "success"}

        # Mock open positions: 1 Long (BEL: +10), 1 Short (TATAMOTORS: -5), 1 Closed (INFY: 0)
        mock_dhan.get_positions.return_value = {
            "status": "success",
            "data": [
                {
                    "tradingSymbol": "BEL",
                    "securityId": "383",
                    "exchangeSegment": "NSE_EQ",
                    "positionType": "INTRADAY",
                    "netQty": 10,
                },
                {
                    "tradingSymbol": "TATAMOTORS",
                    "securityId": "3456",
                    "exchangeSegment": "NSE_EQ",
                    "positionType": "INTRADAY",
                    "netQty": -5,
                },
                {
                    "tradingSymbol": "INFY",
                    "securityId": "1594",
                    "exchangeSegment": "NSE_EQ",
                    "positionType": "INTRADAY",
                    "netQty": 0,
                },
            ]
        }
        mock_dhan.place_order.return_value = {"orderId": "CLOSE_ORD_999"}
        executor.dhan = mock_dhan
        executor.dry_run = False

        res = executor.square_off_all_positions()
        self.assertTrue(res["success"])
        self.assertEqual(len(res["cancelled_orders"]), 3)
        self.assertEqual(len(res["closed_positions"]), 2)
        self.assertEqual(len(res["closed_positions"]), 2)

        # Verify regular order cancellation
        mock_dhan.cancel_order.assert_any_call(order_id="ORD_101")
        # Verify super order cancellation
        mock_dhan.cancel_super_order.assert_called_with(order_id="SO_201")

        # Verify counter orders placed (2 calls: 1 SELL for BEL, 1 BUY for TATAMOTORS)
        self.assertEqual(mock_dhan.place_order.call_count, 2)
        call1_kwargs = mock_dhan.place_order.call_args_list[0][1]
        self.assertEqual(call1_kwargs["security_id"], "383")
        self.assertEqual(call1_kwargs["transaction_type"], "SELL")
        self.assertEqual(call1_kwargs["quantity"], 10)
        self.assertEqual(call1_kwargs["product_type"], "INTRA")

        call2_kwargs = mock_dhan.place_order.call_args_list[1][1]
        self.assertEqual(call2_kwargs["security_id"], "3456")
        self.assertEqual(call2_kwargs["transaction_type"], "BUY")
        self.assertEqual(call2_kwargs["quantity"], 5)
        self.assertEqual(call2_kwargs["product_type"], "INTRA")


if __name__ == "__main__":
    unittest.main()

