"""Unit tests for DhanExecutor order execution and Security ID resolution."""

from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import MagicMock, patch
from news_based_strategy.core.models import TradeSignal
from news_based_strategy.execution.executor import DhanExecutor
from news_based_strategy.execution.quote import PriceQuote


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
        from datetime import timezone
        from news_based_strategy.execution.quote import PriceQuote
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
        valid_quote = PriceQuote(
            price=300.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=datetime.now(timezone.utc),
            security_id="383",
            exchange_segment="NSE_EQ",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")), \
             patch("news_based_strategy.execution.executor.get_live_market_quote", return_value=valid_quote):
            res = executor.execute_order(signal, quote=valid_quote)
            self.assertTrue(res.success)
            self.assertEqual(res.order_id, "DHAN_ORDER_9999")

            # Verify place_order was invoked with security_id="383"
            mock_dhan.place_order.assert_called_once()
            call_kwargs = mock_dhan.place_order.call_args[1]
            self.assertEqual(call_kwargs["security_id"], "383")

    def test_live_mode_resolves_alkem_security_id(self):
        """Verify ALKEM specifically resolves SecID 11703 and places live order without rejection."""
        from datetime import timezone
        from news_based_strategy.execution.quote import PriceQuote
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
        mock_dhan.place_order.return_value = {"orderId": "ALKEM_ORDER_12345"}
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="ALKEM",
            security_id="0",  # Specifically test resolution of ALKEM
            action="BUY",
            product_type="CNC",
            confidence=95,
            catalyst_type="FDA_APPROVAL",
            summary="USFDA Approval received",
        )
        valid_quote = PriceQuote(
            price=5400.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=datetime.now(timezone.utc),
            security_id="11703",
            exchange_segment="NSE_EQ",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")), \
             patch("news_based_strategy.execution.executor.get_live_market_quote", return_value=valid_quote):
            res = executor.execute_order(signal, quote=valid_quote)
            self.assertTrue(res.success)
            self.assertEqual(res.order_id, "ALKEM_ORDER_12345")

            # Verify place_order was invoked with ALKEM security_id="11703"
            mock_dhan.place_order.assert_called_once()
            call_kwargs = mock_dhan.place_order.call_args[1]
            self.assertEqual(call_kwargs["security_id"], "11703")
            self.assertEqual(call_kwargs["transaction_type"], "BUY")

    def test_live_mode_rejects_non_dhan_or_unverified_quote(self):
        """In live mode, non-dhan or unverified source must be rejected."""
        from datetime import timezone, timedelta
        from news_based_strategy.execution.quote import PriceQuote
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            super_order_enabled=False,
        )
        mock_dhan = MagicMock()
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Defense order",
        )

        # 1. Non-Dhan quote (e.g. manual / market_feed)
        non_dhan_quote = PriceQuote(price=300.0, is_real_time=True, source="market_feed", last_trade_time=datetime.now(timezone.utc), security_id="383")
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
            res = executor.execute_order(signal, quote=non_dhan_quote)
            self.assertFalse(res.success)
            self.assertIn("ORDER REJECTED: Unverified quote", res.remarks)

        # 2. Missing last_trade_time
        no_ltt_quote = PriceQuote(price=300.0, is_real_time=True, source="dhan", last_trade_time=None, security_id="383")
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
            res2 = executor.execute_order(signal, quote=no_ltt_quote)
            self.assertFalse(res2.success)
            self.assertIn("lacks verified exchange last_trade_time", res2.remarks)

        # 3. Stale quote (> 60s)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        stale_quote = PriceQuote(price=300.0, is_real_time=True, source="dhan", last_trade_time=stale_time, security_id="383")
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
            res3 = executor.execute_order(signal, quote=stale_quote)
            self.assertFalse(res3.success)
            self.assertIn("Live quote for BEL is stale", res3.remarks)

    def test_live_mode_rejects_fallback_price_quote(self):
        """In live mode, if real-time price cannot be resolved (fallback used), order must be rejected."""
        from news_based_strategy.execution.quote import PriceQuote
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            super_order_enabled=False,
        )
        mock_dhan = MagicMock()
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Defense order",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")), \
             patch("news_based_strategy.execution.executor.get_live_market_quote", return_value=PriceQuote(price=300.0, is_real_time=False, source="fallback")):
            res = executor.execute_order(signal, ltp=None)
            self.assertFalse(res.success)
            self.assertIn("ORDER REJECTED: Unverified quote", res.remarks)
            self.assertFalse(mock_dhan.place_order.called)

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
        from datetime import timezone
        from news_based_strategy.execution.quote import PriceQuote
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
        valid_quote = PriceQuote(
            price=300.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=datetime.now(timezone.utc),
            security_id="383",
            exchange_segment="NSE_EQ",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")), \
             patch("news_based_strategy.execution.executor.get_live_market_quote", return_value=valid_quote):
            res = executor.execute_order(signal, quote=valid_quote)
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

    def test_parse_dhan_order_response_formats(self):
        """Test _parse_dhan_order_response with various success and failure shapes from DhanHQ API."""
        # 1. Nested data with orderId
        s1, id1, m1 = DhanExecutor._parse_dhan_order_response(
            {"status": "success", "data": {"orderId": "11223344", "orderStatus": "PENDING"}},
            order_type_label="Super Order"
        )
        self.assertTrue(s1)
        self.assertEqual(id1, "11223344")
        self.assertIn("11223344", m1)

        # 2. Nested data with superOrderId
        s2, id2, m2 = DhanExecutor._parse_dhan_order_response(
            {"status": "success", "data": {"superOrderId": "SO_9988", "orderStatus": "PENDING"}},
            order_type_label="Super Order"
        )
        self.assertTrue(s2)
        self.assertEqual(id2, "SO_9988")

        # 3. Direct top-level orderId
        s3, id3, m3 = DhanExecutor._parse_dhan_order_response(
            {"status": "success", "orderId": "ORD_5544"},
            order_type_label="Regular Order"
        )
        self.assertTrue(s3)
        self.assertEqual(id3, "ORD_5544")

        # 4. Dhan Failure with error dict
        s4, id4, m4 = DhanExecutor._parse_dhan_order_response(
            {
                "status": "failure",
                "remarks": {
                    "errorType": "BusinessException",
                    "errorCode": "DH-902",
                    "errorMessage": "Access Token expired"
                }
            },
            order_type_label="Super Order"
        )
        self.assertFalse(s4)
        self.assertEqual(id4, "")
        self.assertIn("DH-902", m4)
        self.assertIn("Access Token expired", m4)
        self.assertNotIn("UNKNOWN_SUPER_ID", m4)

        # 5. Dhan Failure with plain string remarks
        s5, id5, m5 = DhanExecutor._parse_dhan_order_response(
            {"status": "failure", "remarks": "Static IP not whitelisted on Dhan"},
            order_type_label="Super Order"
        )
        self.assertFalse(s5)
        self.assertEqual(id5, "")
        self.assertIn("Static IP not whitelisted", m5)
        self.assertNotIn("UNKNOWN_SUPER_ID", m5)

        # 6. Raw order ID
        s6, id6, m6 = DhanExecutor._parse_dhan_order_response(987654321, order_type_label="Order")
        self.assertTrue(s6)
        self.assertEqual(id6, "987654321")

    def test_live_mode_handles_dhan_rejection_gracefully(self):
        """When Dhan rejects super order, execute_order must return success=False with rejection reason."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            super_order_enabled=True,
        )
        mock_dhan = MagicMock()
        mock_dhan.BUY = "BUY"
        mock_dhan.NSE = "NSE_EQ"
        mock_dhan.LIMIT = "LIMIT"
        mock_dhan.INTRA = "INTRA"
        mock_dhan.place_super_order.return_value = {
            "status": "failure",
            "remarks": {
                "errorCode": "DH-911",
                "errorMessage": "Static IP not whitelisted"
            }
        }
        executor.dhan = mock_dhan
        executor.dry_run = False

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Defense order",
        )
        valid_quote = PriceQuote(
            price=300.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=datetime.now(timezone.utc),
            security_id="383",
            exchange_segment="NSE_EQ",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
            res = executor.execute_order(signal, quote=valid_quote)
            self.assertFalse(res.success)
            self.assertIn("DH-911", res.remarks)
            self.assertIn("Static IP not whitelisted", res.remarks)
            self.assertNotIn("UNKNOWN_SUPER_ID", res.remarks)

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
        valid_quote = PriceQuote(
            price=300.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=datetime.now(timezone.utc),
            security_id="383",
            exchange_segment="NSE_EQ",
        )
        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(False, "Trade cutoff reached (14:45 IST). No new trades permitted.")):
            res = executor.execute_order(signal, quote=valid_quote)
            self.assertFalse(res.success)
            self.assertEqual(res.quantity, 0)
            self.assertIn("ORDER REJECTED: Trade cutoff reached", res.remarks)

    def test_trade_cutoff_evaluates_wall_clock_time_not_announcement_time(self):
        """Execution cutoff check must evaluate current wall-clock time, not the morning announcement timestamp."""
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            trade_cutoff_time="14:45",
        )
        # Signal with early morning announcement timestamp (10:30 AM)
        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="INTRADAY",
            confidence=95,
            catalyst_type="ORDER_WIN",
            summary="Major order win",
            exchange_time="04-Sep-2026 10:30:00",
        )
        valid_quote = PriceQuote(
            price=300.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=datetime.now(timezone.utc),
            security_id="383",
            exchange_segment="NSE_EQ",
        )
        # Wall clock is at 15:05 PM (after cutoff)
        wall_clock_after_cutoff = datetime(2026, 9, 4, 15, 5, 0)

        with patch("news_based_strategy.execution.risk.RiskManager.get_ist_now", return_value=wall_clock_after_cutoff), \
             patch("news_based_strategy.execution.risk.RiskManager.is_news_fresh", return_value=(True, 30.0)):
            res = executor.execute_order(signal, quote=valid_quote)
            self.assertFalse(res.success)
            self.assertEqual(res.quantity, 0)
            self.assertIn("Trade cutoff reached", res.remarks)

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



class TestLiveMarketLTP(unittest.TestCase):
    """Test suite for get_live_market_ltp multi-tier resolution."""

    def test_dhan_broker_quote_success(self):
        """Tier 1: When Dhan client returns valid ticker data, use it."""
        from news_based_strategy.execution.quote import get_live_market_ltp, _LTP_CACHE
        _LTP_CACHE.clear()

        mock_dhan = MagicMock()
        mock_dhan.ticker_data.return_value = {
            "status": "success",
            "data": {
                "NSE_EQ": {
                    "18652": {"last_price": 464.85}
                }
            }
        }
        price = get_live_market_ltp("ICICIPRULI", security_id="18652", dhan_client=mock_dhan)
        self.assertEqual(price, 464.85)

    def test_market_feed_fallback_when_dhan_fails(self):
        """Tier 2: When Dhan fails, fall back to market feed."""
        from news_based_strategy.execution.quote import get_live_market_ltp, _LTP_CACHE
        _LTP_CACHE.clear()

        mock_dhan = MagicMock()
        mock_dhan.ticker_data.return_value = {"status": "failure"}

        with patch("news_based_strategy.execution.quote._fetch_from_market_feed", return_value=462.50):
            price = get_live_market_ltp("ICICIPRULI", security_id="18652", dhan_client=mock_dhan)
            self.assertEqual(price, 462.50)

    def test_reference_fallback_when_all_fail(self):
        """Tier 3: When all live sources fail, use reference fallback."""
        from news_based_strategy.execution.quote import get_live_market_ltp, _LTP_CACHE
        _LTP_CACHE.clear()

        with patch("news_based_strategy.execution.quote._fetch_from_market_feed", return_value=None):
            price = get_live_market_ltp("ICICIPRULI", security_id="18652", dhan_client=None)
            self.assertEqual(price, 465.0)

    def test_ttl_caching(self):
        """Test that cached price is returned without calling Dhan or feed repeatedly."""
        from news_based_strategy.execution.quote import get_live_market_ltp, _LTP_CACHE
        _LTP_CACHE.clear()

        mock_dhan = MagicMock()
        mock_dhan.ticker_data.return_value = {
            "status": "success",
            "data": {"NSE_EQ": {"18652": {"last_price": 460.0}}}
        }
        price1 = get_live_market_ltp("ICICIPRULI", security_id="18652", dhan_client=mock_dhan)
        self.assertEqual(price1, 460.0)
        self.assertEqual(mock_dhan.ticker_data.call_count, 1)

        # Second call should use cache
        price2 = get_live_market_ltp("ICICIPRULI", security_id="18652", dhan_client=mock_dhan)
        self.assertEqual(price2, 460.0)
        self.assertEqual(mock_dhan.ticker_data.call_count, 1)

    def test_parse_trade_timestamp_interprets_naive_dhan_strings_as_ist(self):
        """Dhan naive timestamp strings (DD/MM/YYYY HH:MM:SS) must be parsed as IST and converted to UTC."""
        from news_based_strategy.execution.quote import parse_trade_timestamp, IST

        # 14:30:00 IST on 18-Sep-2026 is 09:00:00 UTC
        ts_str = "18/09/2026 14:30:00"
        dt = parse_trade_timestamp(ts_str)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 9)
        self.assertEqual(dt.day, 18)
        self.assertEqual(dt.hour, 9)
        self.assertEqual(dt.minute, 0)
        self.assertEqual(dt.second, 0)

        # Standard YYYY-MM-DD HH:MM:SS format
        ts_str2 = "2026-09-18 14:30:00"
        dt2 = parse_trade_timestamp(ts_str2)
        self.assertEqual(dt2, dt)

        # Naive datetime object should be assumed IST
        naive_dt = datetime(2026, 9, 18, 14, 30, 0)
        dt3 = parse_trade_timestamp(naive_dt)
        self.assertEqual(dt3, dt)

        # String with explicit timezone offset
        explicit_tz_str = "2026-09-18T14:30:00+05:30"
        dt4 = parse_trade_timestamp(explicit_tz_str)
        self.assertEqual(dt4, dt)

    def test_dhan_ist_quote_freshness_in_live_executor(self):
        """A live quote stamped with current IST string must pass freshness check and not be rejected as future-dated."""
        from news_based_strategy.execution.quote import parse_trade_timestamp, IST
        executor = DhanExecutor(
            client_id="dummy_client",
            access_token="dummy_token",
            dry_run=False,
            super_order_enabled=False,
        )
        mock_dhan = MagicMock()
        mock_dhan.place_order.return_value = {"status": "success", "data": {"orderId": "ORD_LIVE_IST_1"}}
        executor.dhan = mock_dhan

        signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Defense order",
        )

        # Generate IST timestamp string as Dhan does (e.g. "18/09/2026 17:30:00")
        now_ist = datetime.now(IST)
        ist_timestamp_str = now_ist.strftime("%d/%m/%Y %H:%M:%S")
        parsed_ltt = parse_trade_timestamp(ist_timestamp_str)

        quote = PriceQuote(
            price=300.0,
            is_real_time=True,
            source="dhan",
            last_trade_time=parsed_ltt,
            security_id="383",
            exchange_segment="NSE_EQ",
        )

        with patch("news_based_strategy.execution.risk.RiskManager.is_trade_allowed", return_value=(True, "OK")):
            res = executor.execute_order(signal, quote=quote)
            self.assertTrue(res.success, f"Order failed with remarks: {res.remarks}")
            self.assertEqual(res.order_id, "ORD_LIVE_IST_1")


if __name__ == "__main__":
    unittest.main()


