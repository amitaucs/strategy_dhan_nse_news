"""Unit tests for position sizing and order executor."""

from datetime import datetime
import unittest

from st15_largecap.core.models import SetupSignal, SignalStatus
from st15_largecap.execution.risk import calculate_position_size, calculate_trade_parameters
from st15_largecap.execution.executor import OrderExecutor


class TestExecutionAndRisk(unittest.TestCase):
    def test_position_sizing(self):
        # Capital 100,000, Stock price 2500 -> 40 shares
        self.assertEqual(calculate_position_size(entry_price=2500.0, capital_per_trade=100000.0), 40)
        # Capital 100,000, Stock price 3333 -> 30 shares
        self.assertEqual(calculate_position_size(entry_price=3333.0, capital_per_trade=100000.0), 30)
        # Zero or invalid
        self.assertEqual(calculate_position_size(entry_price=0.0), 0)

    def test_trade_parameters_calculation(self):
        signal = SetupSignal(
            symbol="TCS",
            sec_id="11536",
            setup_time=datetime.now(),
            trigger_price=3500.0,
            stop_loss_price=3400.0,
            target_profit_price=3800.0,
            risk_per_share=100.0,
            risk_reward_ratio=3.0,
            ema_20=3480.0,
            ema_50=3420.0,
            ema_200=3300.0,
            supertrend=3410.0,
            ha_close=3495.0,
            ha_open=3470.0,
            nearest_ema_name="EMA_20",
            nearest_ema_dist_pct=0.2,
            status=SignalStatus.TRIGGERED,
        )

        params = calculate_trade_parameters(signal, capital_per_trade=70000.0)
        self.assertEqual(params["quantity"], 20)
        self.assertEqual(params["total_investment"], 70000.0)
        self.assertEqual(params["max_risk_amount"], 2000.0)
        self.assertEqual(params["potential_profit_amount"], 6000.0)

    def test_order_executor_dry_run(self):
        executor = OrderExecutor(dhan_client=None, dry_run=True)
        signal = SetupSignal(
            symbol="INFY",
            sec_id="1594",
            setup_time=datetime.now(),
            trigger_price=1800.0,
            stop_loss_price=1750.0,
            target_profit_price=1950.0,
            risk_per_share=50.0,
            risk_reward_ratio=3.0,
            ema_20=1780.0,
            ema_50=1720.0,
            ema_200=1600.0,
            supertrend=1740.0,
            ha_close=1790.0,
            ha_open=1770.0,
            nearest_ema_name="EMA_20",
            nearest_ema_dist_pct=0.3,
            status=SignalStatus.TRIGGERED,
        )

        order = executor.execute_signal(signal, quantity=10)
        self.assertTrue(order.dry_run)
        self.assertEqual(order.status, "SIMULATED")
        self.assertEqual(order.symbol, "INFY")
        self.assertEqual(order.quantity, 10)
        self.assertEqual(order.entry_price, 1800.0)


if __name__ == "__main__":
    unittest.main()
