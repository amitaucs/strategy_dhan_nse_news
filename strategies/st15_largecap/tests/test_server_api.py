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
        self.assertIn("Live Universe Scanner", response.text)

    def test_api_status(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["strategy"], "ST15_LargeCap")
        self.assertEqual(data["universe"], "Nifty 200")
        self.assertIn("proximity_tolerance_pct", data)
        self.assertIn("supertrend", data)

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


if __name__ == "__main__":
    unittest.main()
