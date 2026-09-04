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

        # ₹20,000 capital @ ₹300 price (BEL) -> 66 shares
        qty2 = RiskManager.calculate_position_size(capital=20000, ltp=300)
        self.assertEqual(qty2, 66)

        # Minimum quantity is 1
        qty3 = RiskManager.calculate_position_size(capital=20000, ltp=50000)
        self.assertEqual(qty3, 1)

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


if __name__ == "__main__":
    unittest.main()



