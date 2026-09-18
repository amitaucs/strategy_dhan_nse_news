import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from news_based_strategy.storage.repository import StrategyStorage
from news_based_strategy.ui.server import create_app
from st14_bullish_ce.models import ExecutionMode, ProductType, St14OptionContract, St14SuperOrderLevels, St14TradeSignal


class TestSt14UIRoutes(unittest.TestCase):
    """Test suite for ST-14 Strategy API endpoints and UI integration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = f"{self.temp_dir.name}/test_st14_gui.db"
        self.storage = StrategyStorage(db_path=self.test_db)
        self.session_token = self.storage.create_session("amit")
        self.storage_patcher = patch(
            "news_based_strategy.ui.state.StrategyStorage",
            lambda *args, **kwargs: StrategyStorage(db_path=self.test_db),
        )
        self.storage_patcher.start()
        self.app = create_app()
        self.client = TestClient(self.app, cookies={"app_session_token": self.session_token})
        state = self.app.state.dashboard
        if hasattr(state, "st14_strategy") and state.st14_strategy is not None:
            state.st14_strategy._executed_order_keys.clear()
            state.st14_strategy._executed_signal_ids.clear()
            state.st14_strategy.active_positions.clear()
            state.st14_strategy.closed_positions.clear()
            state.st14_strategy.signals_history.clear()

    def tearDown(self):
        self.storage_patcher.stop()
        self.storage.close()
        self.temp_dir.cleanup()

    def test_list_strategies_includes_st14(self):
        """GET /api/strategies should return ST-14 with telemetry and control fields."""
        res = self.client.get("/api/strategies")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        st14 = next((s for s in data if s["id"] == "st14_bullish_ce"), None)
        self.assertIsNotNone(st14)
        self.assertEqual(st14["code"], "ST-14")
        self.assertEqual(st14["name"], "Bullish CE Options Strategy")
        self.assertIn("execution_mode", st14)
        self.assertIn("auto_order_enabled", st14)
        self.assertIn("status", st14)

    def test_get_st14_strategy_detail(self):
        """GET /api/strategies/st14_bullish_ce should return detailed telemetry."""
        res = self.client.get("/api/strategies/st14_bullish_ce")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], "st14_bullish_ce")
        self.assertIn("telemetry", data)
        telem = data["telemetry"]
        self.assertIn("market_breadth", telem)
        self.assertIn("active_positions", telem)
        self.assertIn("capital_per_trade", telem)

    def test_toggle_st14_status(self):
        """POST /api/strategies/st14_bullish_ce/toggle-status should toggle engine status between ACTIVE and PAUSED."""
        # Toggle to PAUSED
        res = self.client.post("/api/strategies/st14_bullish_ce/toggle-status", json={"status": "PAUSED"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "PAUSED")

        # Toggle to ACTIVE
        res2 = self.client.post("/api/strategies/st14_bullish_ce/toggle-status", json={"status": "ACTIVE"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "ACTIVE")

    def test_toggle_st14_mode(self):
        """POST /api/strategies/st14_bullish_ce/toggle-mode should toggle between VIRTUAL and LIVE."""
        res = self.client.post("/api/strategies/st14_bullish_ce/toggle-mode", json={"mode": "LIVE"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["mode"], "LIVE")

        res2 = self.client.post("/api/strategies/st14_bullish_ce/toggle-mode", json={"mode": "VIRTUAL"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["mode"], "VIRTUAL")

    def test_toggle_st14_auto_order(self):
        """POST /api/strategies/st14_bullish_ce/toggle-auto-order should toggle auto-order flag."""
        res = self.client.post("/api/strategies/st14_bullish_ce/toggle-auto-order", json={"auto_order": False})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["auto_order"])

        res2 = self.client.post("/api/strategies/st14_bullish_ce/toggle-auto-order", json={"auto_order": True})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()["auto_order"])

    def test_toggle_st14_product_type(self):
        """POST /api/strategies/st14_bullish_ce/toggle-product should toggle product type."""
        res = self.client.post("/api/strategies/st14_bullish_ce/toggle-product", json={"product_type": "DELIVERY"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["product_type"], "DELIVERY")

        res2 = self.client.post("/api/strategies/st14_bullish_ce/toggle-product", json={"product_type": "INTRADAY"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["product_type"], "INTRADAY")

    def test_update_st14_config(self):
        """POST /api/strategies/st14_bullish_ce/config should update capital and target/SL levels."""
        res = self.client.post("/api/strategies/st14_bullish_ce/config", json={
            "capital_per_trade": 35000.0,
            "target_profit_pct": 50.0,
            "stop_loss_pct": 15.0,
            "trailing_jump_pts": 3.0,
            "trade_cutoff_time": "13:30",
            "square_off_time": "15:15",
        })
        self.assertEqual(res.status_code, 200)
        cfg = res.json()["config"]
        self.assertEqual(cfg["capital_per_trade"], 35000.0)
        self.assertEqual(cfg["target_profit_pct"], 50.0)
        self.assertEqual(cfg["stop_loss_pct"], 15.0)
        self.assertEqual(cfg["trailing_jump_pts"], 3.0)
        self.assertEqual(cfg["trade_cutoff_time"], "13:30")
        self.assertEqual(cfg["square_off_time"], "15:15")

    def test_st14_scan_and_execute_endpoints(self):
        """POST /api/strategies/st14_bullish_ce/scan and /execute should process signals cleanly."""
        state = self.app.state.dashboard
        
        # Test scan endpoint with mock
        with patch.object(state.st14_strategy, "run_iteration", return_value={
            "status": "COMPLETED",
            "signals": [],
            "orders_placed": 0,
            "executed_positions": [],
            "breadth": {"both_indices_green": True},
        }):
            res = self.client.post("/api/strategies/st14_bullish_ce/scan?bypass_timing=true")
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["success"])

        # Test manual execute endpoint
        mock_signal = St14TradeSignal(
            signal_id="ST14_TEST_001",
            symbol="TCS",
            underlying_sec_id="11536",
            underlying_ltp=3500.0,
            breakout_candle_high=3480.0,
            daily_ema20=3400.0,
            hourly_ema20=3450.0,
            vwap=3460.0,
            vwap_dist_pct=1.1,
            vwap_angle_deg=45.0,
            is_confirmed=True,
            option_contract=St14OptionContract(
                symbol="TCS 3550 CE",
                underlying_symbol="TCS",
                security_id="9999",
                strike_price=3550.0,
                expiry_date="2026-09-24",
                option_type="CE",
                lot_size=175,
                ltp=50.0,
            ),
            order_levels=St14SuperOrderLevels(
                entry_price=50.25,
                target_price=70.35,
                stop_loss_price=40.20,
            ),
        )
        state.st14_strategy.signals_history.append(mock_signal)

        exec_res = self.client.post("/api/strategies/st14_bullish_ce/execute", json={"signal_id": "ST14_TEST_001"})
        self.assertEqual(exec_res.status_code, 200)
        self.assertTrue(exec_res.json()["success"])
        self.assertIsNotNone(exec_res.json()["position"])

        # Test square off endpoint
        sq_res = self.client.post("/api/strategies/st14_bullish_ce/square-off")
        self.assertEqual(sq_res.status_code, 200)
        self.assertTrue(sq_res.json()["success"])
        self.assertEqual(sq_res.json()["closed_count"], 1)



if __name__ == "__main__":
    unittest.main()
