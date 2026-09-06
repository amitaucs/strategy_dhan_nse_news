"""Unit tests for execution risk manager and sizing."""

from datetime import datetime
import unittest
from news_based_strategy.execution.risk import RiskManager


class TestRiskManager(unittest.TestCase):
    """Test position sizing and exchange compliance gates."""

    def test_position_sizing(self):
        # ₹20,000 capital @ ₹9,000 price (Bajaj Auto) -> 2 shares
        qty1 = RiskManager.calculate_position_size(capital=20000, ltp=9000)
        self.assertEqual(qty1, 2)

        # ₹6,600 trade capital (33% of 20k) @ ₹300 price (BEL) with default max_quantity=10 -> Capped at 10 shares
        qty2 = RiskManager.calculate_position_size(capital=6600, ltp=300)
        self.assertEqual(qty2, 10)

        # ₹6,600 trade capital @ ₹1,100 price -> 6 shares (whatever covered by 6600)
        qty_mid = RiskManager.calculate_position_size(capital=6600, ltp=1100)
        self.assertEqual(qty_mid, 6)

        # ₹20,000 capital @ ₹300 price with max_quantity=1000 -> 66 shares
        qty2_uncapped = RiskManager.calculate_position_size(capital=20000, ltp=300, max_quantity=1000)
        self.assertEqual(qty2_uncapped, 66)

        # When LTP > capital, returns 0 shares (order rejected)
        qty3 = RiskManager.calculate_position_size(capital=20000, ltp=50000)
        self.assertEqual(qty3, 0)
        qty4 = RiskManager.calculate_position_size(capital=6600, ltp=9000)
        self.assertEqual(qty4, 0)

    def test_safe_product_type_enforcement(self):
        # SELL must ALWAYS be forced to INTRADAY
        self.assertEqual(RiskManager.get_safe_product_type("SELL", "CNC"), "INTRADAY")
        self.assertEqual(RiskManager.get_safe_product_type("BEARISH", "CNC"), "INTRADAY")

        # BUY can be CNC or INTRADAY
        self.assertEqual(RiskManager.get_safe_product_type("BUY", "CNC"), "CNC")
        self.assertEqual(RiskManager.get_safe_product_type("BULLISH", "INTRADAY"), "INTRADAY")

    def test_market_hours_validation(self):
        # Midday Wednesday (Market Open)
        open_dt = datetime(2026, 9, 2, 11, 30)  # Wednesday 11:30 AM
        self.assertTrue(RiskManager.is_market_open(open_dt))

        # Sunday (Market Closed)
        weekend_dt = datetime(2026, 9, 6, 11, 30)  # Sunday
        self.assertFalse(RiskManager.is_market_open(weekend_dt))

        # Night time Wednesday (Market Closed)
        night_dt = datetime(2026, 9, 2, 22, 00)  # 10:00 PM
        self.assertFalse(RiskManager.is_market_open(night_dt))

    def test_parse_exchange_timestamp(self):
        # NSE Standard format: 04-Sep-2026 15:18:43
        dt1 = RiskManager.parse_exchange_timestamp("04-Sep-2026 15:18:43")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 9)
        self.assertEqual(dt1.day, 4)
        self.assertEqual(dt1.hour, 15)
        self.assertEqual(dt1.minute, 18)

        # Alternate formats
        dt2 = RiskManager.parse_exchange_timestamp("2026-09-04 15:18:43")
        self.assertIsNotNone(dt2)
        dt3 = RiskManager.parse_exchange_timestamp("04-09-2026 15:18:43")
        self.assertIsNotNone(dt3)

        # Invalid / Empty
        self.assertIsNone(RiskManager.parse_exchange_timestamp(""))
        self.assertIsNone(RiskManager.parse_exchange_timestamp("invalid_date"))

    def test_is_news_fresh_evaluation(self):
        ref_time = datetime(2026, 9, 4, 15, 20, 0)  # Reference: 15:20:00

        # Fresh news: 45 seconds ago (15:19:15)
        fresh_time_str = "04-Sep-2026 15:19:15"
        is_fresh, age = RiskManager.is_news_fresh(fresh_time_str, max_age_seconds=180, reference_time=ref_time)
        self.assertTrue(is_fresh)
        self.assertAlmostEqual(age, 45.0, places=1)

        # Stale news: 250 seconds ago (15:15:50) -> Greater than 180s threshold
        stale_time_str = "04-Sep-2026 15:15:50"
        is_fresh2, age2 = RiskManager.is_news_fresh(stale_time_str, max_age_seconds=180, reference_time=ref_time)
        self.assertFalse(is_fresh2)
        self.assertAlmostEqual(age2, 250.0, places=1)

        # Clock skew resilience: Exchange clock slightly ahead of local machine
        skew_time_str = "04-Sep-2026 15:20:10"  # 10s into the future
        is_fresh3, age3 = RiskManager.is_news_fresh(skew_time_str, max_age_seconds=180, reference_time=ref_time)
        self.assertTrue(is_fresh3)
        self.assertEqual(age3, 0.0)

        # Disabled check (max_age_seconds <= 0)
        is_fresh4, _ = RiskManager.is_news_fresh(stale_time_str, max_age_seconds=0, reference_time=ref_time)
        self.assertTrue(is_fresh4)

    def test_executor_stale_news_rejection(self):
        from news_based_strategy.core.models import TradeSignal
        from news_based_strategy.execution.executor import DhanExecutor

        executor = DhanExecutor(dry_run=True, max_news_age_seconds=120)

        # Stale signal (from yesterday / 1 hour ago)
        stale_signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Order win",
            exchange_time="01-Jan-2026 10:00:00",
        )
        res = executor.execute_order(stale_signal, ltp=300.0)
        self.assertFalse(res.success)
        self.assertEqual(res.quantity, 0)
        self.assertIn("ORDER REJECTED: Catalyst too stale", res.remarks)

        # Fresh signal (exchange_time None or recent)
        now_str = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        fresh_signal = TradeSignal(
            symbol="BEL",
            security_id="383",
            action="BUY",
            product_type="CNC",
            confidence=90,
            catalyst_type="ORDER_WIN",
            summary="Order win",
            exchange_time=now_str,
        )
        res2 = executor.execute_order(fresh_signal, ltp=300.0)
        self.assertTrue(res2.success)
        self.assertGreater(res2.quantity, 0)

    def test_calculate_super_order_levels_buy(self):
        # LTP = ₹1000, 3% TP, 1% SL, 0.2% slippage
        entry, tp, sl = RiskManager.calculate_super_order_levels(
            ltp=1000.0,
            action="BUY",
            target_pct=3.0,
            sl_pct=1.0,
            slippage_buffer_pct=0.2,
        )
        self.assertEqual(entry, 1002.0)
        self.assertEqual(tp, 1030.0)
        self.assertEqual(sl, 990.0)

    def test_calculate_super_order_levels_sell(self):
        # LTP = ₹1000, 3% TP, 1% SL, 0.2% slippage
        entry, tp, sl = RiskManager.calculate_super_order_levels(
            ltp=1000.0,
            action="SELL",
            target_pct=3.0,
            sl_pct=1.0,
            slippage_buffer_pct=0.2,
        )
        self.assertEqual(entry, 998.0)
        self.assertEqual(tp, 970.0)
        self.assertEqual(sl, 1010.0)

    def test_calculate_super_order_levels_zero_ltp(self):
        entry, tp, sl = RiskManager.calculate_super_order_levels(ltp=0.0)
        self.assertEqual((entry, tp, sl), (0.0, 0.0, 0.0))

    def test_is_daily_order_limit_reached(self):
        """Test daily order limit checking logic."""
        # Limit 3: count 0, 1, 2 not reached; count 3, 4 reached
        self.assertFalse(RiskManager.is_daily_order_limit_reached(today_order_count=0, max_orders_per_day=3))
        self.assertFalse(RiskManager.is_daily_order_limit_reached(today_order_count=2, max_orders_per_day=3))
        self.assertTrue(RiskManager.is_daily_order_limit_reached(today_order_count=3, max_orders_per_day=3))
        self.assertTrue(RiskManager.is_daily_order_limit_reached(today_order_count=4, max_orders_per_day=3))

        # Limit <= 0 disables check
        self.assertFalse(RiskManager.is_daily_order_limit_reached(today_order_count=100, max_orders_per_day=0))

    def test_executor_daily_max_order_limit_enforcement(self):
        """Test that DhanExecutor enforces the max 3 orders per day limit."""
        from news_based_strategy.core.models import TradeSignal
        from news_based_strategy.execution.executor import DhanExecutor

        executor = DhanExecutor(dry_run=True, max_orders_per_day=3)
        self.assertEqual(executor.get_daily_order_count(), 0)

        def make_signal(sym: str) -> TradeSignal:
            return TradeSignal(
                symbol=sym,
                security_id="383",
                action="BUY",
                product_type="CNC",
                confidence=95,
                catalyst_type="ORDER_WIN",
                summary=f"Order win for {sym}",
            )

        # 1st order -> Allowed
        r1 = executor.execute_order(make_signal("BEL"), ltp=300.0)
        self.assertTrue(r1.success)
        self.assertEqual(executor.get_daily_order_count(), 1)

        # 2nd order -> Allowed
        r2 = executor.execute_order(make_signal("HAL"), ltp=4500.0)
        self.assertTrue(r2.success)
        self.assertEqual(executor.get_daily_order_count(), 2)

        # 3rd order -> Allowed (reaches 3)
        r3 = executor.execute_order(make_signal("BHEL"), ltp=250.0)
        self.assertTrue(r3.success)
        self.assertEqual(executor.get_daily_order_count(), 3)

        # 4th order -> REJECTED due to daily limit (3/3)
        r4 = executor.execute_order(make_signal("SBIN"), ltp=800.0)
        self.assertFalse(r4.success)
        self.assertEqual(r4.quantity, 0)
    def test_is_trade_allowed(self):
        # Wednesday 10:30 AM (Allowed)
        wed_morning = datetime(2026, 9, 2, 10, 30)
        allowed, reason = RiskManager.is_trade_allowed(wed_morning, cutoff_str="14:45")
        self.assertTrue(allowed)
        self.assertEqual(reason, "OK")

        # Wednesday 14:44:59 (Allowed before cutoff)
        wed_before_cutoff = datetime(2026, 9, 2, 14, 44, 59)
        allowed, _ = RiskManager.is_trade_allowed(wed_before_cutoff, cutoff_str="14:45")
        self.assertTrue(allowed)

        # Wednesday 14:45:00 / 14:46 (Blocked after 14:45 cutoff)
        wed_after_cutoff = datetime(2026, 9, 2, 14, 46, 0)
        allowed, reason = RiskManager.is_trade_allowed(wed_after_cutoff, cutoff_str="14:45")
        self.assertFalse(allowed)
        self.assertIn("Trade cutoff reached", reason)

        # Sunday 11:00 AM (Blocked - Market Closed)
        sun_dt = datetime(2026, 9, 6, 11, 0)
        allowed, reason = RiskManager.is_trade_allowed(sun_dt, cutoff_str="14:45")
        self.assertFalse(allowed)
        self.assertIn("Market is closed", reason)

    def test_is_square_off_time(self):
        # Wednesday 14:59 (Not square-off time yet)
        wed_early = datetime(2026, 9, 2, 14, 59, 0)
        self.assertFalse(RiskManager.is_square_off_time(wed_early, square_off_str="15:00"))

        # Wednesday 15:00 sharp (Square-off time triggered)
        wed_sq = datetime(2026, 9, 2, 15, 0, 0)
        self.assertTrue(RiskManager.is_square_off_time(wed_sq, square_off_str="15:00"))

        # Wednesday 15:15 (Within square-off window before 15:30)
        wed_sq_late = datetime(2026, 9, 2, 15, 15, 0)
        self.assertTrue(RiskManager.is_square_off_time(wed_sq_late, square_off_str="15:00"))

        # Wednesday 15:31 (After market close)
        wed_after_close = datetime(2026, 9, 2, 15, 31, 0)
        self.assertFalse(RiskManager.is_square_off_time(wed_after_close, square_off_str="15:00"))

        # Sunday 15:00 (Weekend - no square-off)
        sun_sq = datetime(2026, 9, 6, 15, 0, 0)
        self.assertFalse(RiskManager.is_square_off_time(sun_sq, square_off_str="15:00"))


if __name__ == "__main__":
    unittest.main()



