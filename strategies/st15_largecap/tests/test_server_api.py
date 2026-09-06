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

    def setUp(self):
        runner._latest_results = []
        runner._latest_signals = []
        runner.clear_cache()

    def tearDown(self):
        runner.stop_background_loop()
        runner._latest_results = []
        runner._latest_signals = []
        runner.clear_cache()

    def test_root_html_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ST15 Large-Cap Positional Momentum", response.text)
        self.assertIn("Dip Tolerance", response.text)
        self.assertIn("tolerancePresetSelect", response.text)
        self.assertIn("copyTvSymbol", response.text)
        self.assertIn("copyTvWatchlist", response.text)
        self.assertIn("copySignalsWatchlist", response.text)
        self.assertIn("copyWatchlistBtn", response.text)
        self.assertIn("copyAllTvHeaderBtn", response.text)
        self.assertIn("chartModalCopyTvBtn", response.text)
        self.assertIn("toastContainer", response.text)

    def test_api_status(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["strategy"], "ST15_LargeCap")
        self.assertEqual(data["universe"], "Nifty 200")
        self.assertIn("dip_tolerance_pct", data)
        self.assertIn("tolerance_value", data)
        self.assertIn("is_scanning", data)
        self.assertIn("scan_progress", data)
        self.assertIn("scan_total", data)
        self.assertIsInstance(data["is_scanning"], bool)
        self.assertIsInstance(data["scan_progress"], int)
        self.assertIsInstance(data["scan_total"], int)

    def test_api_scan_trigger(self):
        with patch.object(runner, "scan_universe"):
            response = self.client.post("/api/scan")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn(data["status"], ["success", "in_progress"])

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
            trigger_price=750.0,
            stop_loss_price=700.0,
            target_profit_price=900.0,
            risk_per_share=50.0,
            risk_reward_ratio=3.0,
            ema_20=730.0,
            ema_50=700.0,
            ema_200=650.0,
            supertrend=710.0,
            ha_close=748.0,
            ha_open=742.0,
            nearest_ema_name="EMA_20",
            nearest_ema_dist_pct=0.03,
            status=SignalStatus.TRIGGERED,
        )
        scan = ScanResult(
            symbol="AARTIIND",
            sec_id="28",
            ltp=748.0,
            ema_20=730.0,
            ema_50=700.0,
            ema_200=650.0,
            is_ema_stacked=True,
            is_in_dip=True,
            nearest_ema="EMA_20",
            nearest_ema_dist_pct=0.03,
            is_ha_green=True,
            is_supertrend_green=True,
            is_setup_ready=True,
            swing_low=700.0,
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

        # Verify manual execution endpoint with qualifying candles
        from st15_largecap.ingestion.candles import generate_mock_2h_candles
        mock_candles = generate_mock_2h_candles(
            symbol="AARTIIND",
            base_price=640.0,
            num_candles=80,
            bullish_trend=True,
            pullback_at_end=True,
        )
        runner.screener.ema_proximity_pct = 2.0
        with patch.object(runner.fetcher, "fetch_2h_candles", return_value=mock_candles), \
             patch.object(runner.repository, "get_today_orders", return_value=[]):
            exec_res = self.client.post("/api/execute/AARTIIND")
            self.assertEqual(exec_res.status_code, 200)
            self.assertEqual(exec_res.json()["status"], "success")

        # Reset tolerance back to 0.5%
        runner.screener.ema_proximity_pct = 0.5

    def test_daily_position_limit_enforced(self):
        """Verify that when 3 positions are placed today, subsequent orders are blocked."""
        today_mock_orders = [
            {"order_id": "ORD1", "symbol": "RELIANCE", "status": "PLACED", "placed_at": "2026-09-06T10:00:00"},
            {"order_id": "ORD2", "symbol": "TCS", "status": "SIMULATED", "placed_at": "2026-09-06T11:00:00"},
            {"order_id": "ORD3", "symbol": "INFY", "status": "FILLED", "placed_at": "2026-09-06T12:00:00"},
        ]
        from st15_largecap.ingestion.candles import generate_mock_2h_candles
        mock_candles = generate_mock_2h_candles(symbol="WIPRO", base_price=450.0, num_candles=80, bullish_trend=True, pullback_at_end=True)

        with patch.object(runner.repository, "get_today_orders", return_value=today_mock_orders), \
             patch.object(runner.repository, "get_signals", return_value=[]), \
             patch.object(runner.fetcher, "fetch_2h_candles", return_value=mock_candles):
            exec_res = self.client.post("/api/execute/WIPRO")
            self.assertEqual(exec_res.status_code, 200)
            data = exec_res.json()
            self.assertEqual(data["status"], "error")
            self.assertIn("Daily position limit reached", data["message"])
            self.assertIn("3/3", data["message"])

    def test_duplicate_order_same_day_blocked(self):
        """Verify that placing a second order for the same symbol on the same day is rejected."""
        today_mock_orders = [
            {"order_id": "ORD1", "symbol": "ICICIBANK", "status": "PLACED", "placed_at": "2026-09-06T10:00:00"},
        ]
        from st15_largecap.ingestion.candles import generate_mock_2h_candles
        mock_candles = generate_mock_2h_candles(symbol="ICICIBANK", base_price=1000.0, num_candles=80, bullish_trend=True, pullback_at_end=True)

        with patch.object(runner.repository, "get_today_orders", return_value=today_mock_orders), \
             patch.object(runner.fetcher, "fetch_2h_candles", return_value=mock_candles):
            exec_res = self.client.post("/api/execute/ICICIBANK")
            self.assertEqual(exec_res.status_code, 200)
            data = exec_res.json()
            self.assertEqual(data["status"], "error")
            self.assertIn("Order already placed for ICICIBANK today", data["message"])

    def test_api_mode_toggles(self):
        # 1. Toggle Mode
        res1 = self.client.post("/api/toggle-mode")
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1["status"], "success")
        self.assertEqual(data1["mode"], "LIVE")
        self.assertFalse(data1["dry_run"])

        # Check status endpoint reflects LIVE
        status1 = self.client.get("/api/status").json()
        self.assertEqual(status1["mode"], "LIVE")
        self.assertFalse(status1["dry_run"])

        # 2. Toggle back to VIRTUAL
        res2 = self.client.post("/api/toggle-mode")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["mode"], "VIRTUAL")
        self.assertTrue(data2["dry_run"])

        # 3. Explicit POST /api/mode
        res3 = self.client.post("/api/mode", json={"mode": "LIVE"})
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()["mode"], "LIVE")

        res4 = self.client.post("/api/mode", json={"mode": "VIRTUAL"})
        self.assertEqual(res4.status_code, 200)
        self.assertEqual(res4.json()["mode"], "VIRTUAL")

    def test_api_auto_order_toggles(self):
        # 1. Toggle Auto Order
        res1 = self.client.post("/api/toggle-auto-order")
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1["status"], "success")
        self.assertEqual(data1["order_mode"], "AUTO")
        self.assertTrue(data1["auto_order"])

        # Check status reflects AUTO
        status1 = self.client.get("/api/status").json()
        self.assertEqual(status1["order_mode"], "AUTO")
        self.assertTrue(status1["auto_order"])

        # 2. Toggle back to MANUAL
        res2 = self.client.post("/api/toggle-auto-order")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["order_mode"], "MANUAL")
        self.assertFalse(res2.json()["auto_order"])

        # 3. Explicit POST /api/auto-order
        res3 = self.client.post("/api/auto-order", json={"order_mode": "AUTO"})
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()["order_mode"], "AUTO")

        res4 = self.client.post("/api/auto-order", json={"order_mode": "MANUAL"})
        self.assertEqual(res4.status_code, 200)
        self.assertEqual(res4.json()["order_mode"], "MANUAL")

    def test_fallen_setup_execution_blocked(self):
        from datetime import datetime
        from st15_largecap.core.models import ScanResult, SetupSignal, SignalStatus

        # Signal that had Stop Loss at 630
        sig = SetupSignal(
            symbol="FALLENCO",
            sec_id="999",
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
        # Scan result showing price fell to 625 (below Stop Loss) and HA turned Red
        scan_fallen = ScanResult(
            symbol="FALLENCO",
            sec_id="999",
            ltp=625.0,
            ema_20=640.0,
            ema_50=620.0,
            ema_200=580.0,
            is_ema_stacked=True,
            is_in_dip=True,
            nearest_ema="EMA_20",
            nearest_ema_dist_pct=0.03,
            is_ha_green=False,
            is_supertrend_green=True,
            is_setup_ready=False,
            invalidation_reason="Heikin Ashi turned Red (Bearish)",
            swing_low=630.0,
            signal=sig,
            candles_count=80,
            scanned_at=datetime.now(),
        )
        runner._latest_results = [scan_fallen]
        runner._latest_signals = [sig]

        # Verify signals API marks it as FALLEN
        signals_res = self.client.get("/api/signals")
        self.assertEqual(signals_res.status_code, 200)
        fallen_sig = next((s for s in signals_res.json() if s["symbol"] == "FALLENCO"), None)
        self.assertIsNotNone(fallen_sig)
        self.assertEqual(fallen_sig["status"], "FALLEN")
        self.assertFalse(fallen_sig["is_active"])

        # Attempt to execute order for FALLENCO -> Must be blocked
        with patch.object(runner.screener, "evaluate", return_value=scan_fallen), \
             patch.object(runner.repository, "get_today_orders", return_value=[]):
            exec_res = self.client.post("/api/execute/FALLENCO")
            self.assertEqual(exec_res.status_code, 200)
            exec_data = exec_res.json()
            self.assertEqual(exec_data["status"], "error")
            self.assertEqual(exec_data["reason"], "SETUP_FALLEN")
            self.assertIn("Setup has fallen", exec_data["message"])

    def test_api_chart_endpoint(self):
        from st15_largecap.ingestion.candles import generate_mock_2h_candles
        mock_candles = generate_mock_2h_candles(symbol="RELIANCE", base_price=2900.0, num_candles=80, bullish_trend=True)
        with patch.object(runner.fetcher, "fetch_2h_candles", return_value=mock_candles):
            chart_res = self.client.get("/api/chart/RELIANCE")
            self.assertEqual(chart_res.status_code, 200)
            data = chart_res.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["symbol"], "RELIANCE")
            self.assertIn("raw_candles", data)
            self.assertIn("ha_candles", data)
            self.assertIn("ema_20", data)
            self.assertIn("ema_50", data)
            self.assertIn("ema_200", data)
            self.assertIn("supertrend", data)
            self.assertIn("scan", data)

    def test_cache_clear_endpoint(self):
        res = self.client.post("/api/cache/clear")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("cleared", data["message"])

    def test_runner_parallel_scan(self):
        from st15_largecap.ingestion.candles import generate_mock_2h_candles
        mock_candles = generate_mock_2h_candles(symbol="SBIN", base_price=800.0, num_candles=80, bullish_trend=True)
        test_symbols = ["SBIN", "TCS", "INFY", "RELIANCE"]
        with patch.object(runner.fetcher, "fetch_2h_candles", return_value=mock_candles):
            results = runner.scan_universe(symbols=test_symbols)
            self.assertEqual(len(results), 4)
            self.assertEqual(runner.scan_total, 4)
            self.assertEqual(runner.scan_progress, 4)
            self.assertFalse(runner.is_scanning)

        # Scans endpoint should return the 4 scan results
        scans_res = self.client.get("/api/scans")
        self.assertEqual(scans_res.status_code, 200)
        self.assertEqual(len(scans_res.json()), 4)


if __name__ == "__main__":
    unittest.main()


