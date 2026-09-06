"""Unit tests for FastAPI Web Dashboard & REST APIs."""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from st15_largecap.ui.server import app, runner


class TestServerAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        runner.stop_background_loop()

    def tearDown(self):
        runner.stop_background_loop()

    def test_root_html_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ST15 Large-Cap Positional Momentum", response.text)
        self.assertIn("Dip Tolerance", response.text)
        self.assertIn("tolerancePresetSelect", response.text)

    def test_api_status(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["strategy"], "ST15_LargeCap")
        self.assertEqual(data["universe"], "Nifty 200")
        self.assertIn("dip_tolerance_pct", data)
        self.assertIn("tolerance_value", data)

    def test_api_tolerance_update(self):
        # 1. Update to positive 1.25%
        res = self.client.post("/api/tolerance", json={"tolerance_pct": 1.25})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["tolerance_pct"], 1.25)
        self.assertEqual(runner.screener.ema_proximity_pct, 1.25)

        # 2. Update to 0.0% (Exact Touch)
        res_zero = self.client.post("/api/tolerance", json={"tolerance_pct": 0.0})
        self.assertEqual(res_zero.status_code, 200)
        self.assertEqual(res_zero.json()["tolerance_pct"], 0.0)
        self.assertEqual(runner.screener.ema_proximity_pct, 0.0)

        # 3. Update to negative -0.2% (Penetration below EMA)
        res_neg = self.client.post("/api/tolerance", json={"tolerance_pct": -0.2})
        self.assertEqual(res_neg.status_code, 200)
        self.assertEqual(res_neg.json()["tolerance_pct"], -0.2)
        self.assertEqual(runner.screener.ema_proximity_pct, -0.2)

        # Verify status endpoint reflects updated tolerance
        status_res = self.client.get("/api/status")
        status_data = status_res.json()
        self.assertEqual(status_data["tolerance_value"], -0.2)

        # Reset back to 0.5%
        self.client.post("/api/tolerance", json={"tolerance_pct": 0.5})

    def test_api_scans(self):
        response = self.client.get("/api/scans")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_api_signals(self):
        response = self.client.get("/api/signals")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_api_positions(self):
        response = self.client.get("/api/positions")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_api_orders(self):
        response = self.client.get("/api/orders")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_api_toggle_scanner(self):
        with patch.object(runner, "start_background_loop") as mock_start, \
             patch.object(runner, "stop_background_loop") as mock_stop:
            res1 = self.client.post("/api/toggle-scanner")
            self.assertEqual(res1.status_code, 200)
            mock_start.assert_called_once()

            # Simulate running state
            runner._is_running = True
            res2 = self.client.post("/api/toggle-scanner")
            self.assertEqual(res2.status_code, 200)
            mock_stop.assert_called_once()
            runner._is_running = False

    def test_qualified_signals_and_execution(self):
        from datetime import datetime
        from st15_largecap.core.models import ScanResult, SetupSignal, SignalStatus

        # Simulate a qualified scan result with signal
        sig = SetupSignal(
            symbol="AARTIIND",
            sec_id="28",
            setup_time=datetime.now(),
            trigger_price=650.0,
            stop_loss_price=630.0,
            target_profit_price=710.0,
            risk_per_share=20.0,
            risk_reward_ratio=3.0,
            ema_20=640.0,
            ema_50=620.0,
            ema_200=580.0,
            supertrend=635.0,
            ha_close=648.0,
            ha_open=642.0,
            nearest_ema_name="EMA_20",
            nearest_ema_dist_pct=0.03,
            status=SignalStatus.TRIGGERED,
        )
        scan = ScanResult(
            symbol="AARTIIND",
            sec_id="28",
            ltp=648.0,
            ema_20=640.0,
            ema_50=620.0,
            ema_200=580.0,
            is_ema_stacked=True,
            is_in_dip=True,
            nearest_ema="EMA_20",
            nearest_ema_dist_pct=0.03,
            is_ha_green=True,
            is_supertrend_green=True,
            is_setup_ready=True,
            swing_low=630.0,
            signal=sig,
            candles_count=80,
            scanned_at=datetime.now(),
        )
        runner._latest_results = [scan]
        runner._latest_signals = [sig]

        # Verify status endpoint reflects triggered count
        status_res = self.client.get("/api/status")
        self.assertGreaterEqual(status_res.json()["triggered_count"], 1)

        # Verify signals endpoint returns qualified signal
        signals_res = self.client.get("/api/signals")
        self.assertEqual(signals_res.status_code, 200)
        sig_data = signals_res.json()
        self.assertGreaterEqual(len(sig_data), 1)
        self.assertTrue(any(s["symbol"] == "AARTIIND" for s in sig_data))

        # Verify manual execution endpoint
        exec_res = self.client.post("/api/execute/AARTIIND")
        self.assertEqual(exec_res.status_code, 200)
        self.assertEqual(exec_res.json()["status"], "success")


if __name__ == "__main__":
    unittest.main()
