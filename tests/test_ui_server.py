"""Unit tests for FastAPI Web GUI server and endpoints."""

import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from news_based_strategy.core.models import FilingAudit
from news_based_strategy.ui.server import create_app


class TestUIServer(unittest.TestCase):
    """Test suite for GUI Dashboard API endpoints."""

    def setUp(self):
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_get_index_html(self):
        """Root GET request should serve the full HTML dashboard."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("NSE Catalyst Trading Terminal", res.text)
        self.assertIn("AUTO ORDER", res.text)
        self.assertIn("Simulate Feed", res.text)

    def test_get_status_api(self):
        """API status endpoint returns system state."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("dry_run", data)
        self.assertIn("auto_order", data)
        self.assertIn("max_shares_per_trade", data)
        self.assertIn("confidence_threshold", data)
        self.assertIn("gemini_model", data)

    def test_toggle_auto_order_api(self):
        """Toggle auto order endpoint switches state cleanly."""
        res = self.client.post("/api/toggle-auto-order", json={"auto_order": False})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["auto_order"])

        res2 = self.client.post("/api/toggle-auto-order", json={"auto_order": True})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()["auto_order"])

    def test_place_order_api(self):
        """Place order endpoint creates trade execution record and returns order details."""
        res = self.client.post(
            "/api/orders/place",
            json={
                "seq_id": "TEST_GUI_001",
                "symbol": "BEL",
                "action": "BUY",
                "product_type": "INTRADAY",
                "confidence": 95,
                "catalyst_type": "ORDER_WIN",
                "summary": "Major defense contract win",
                "ltp": 300.0,
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["symbol"], "BEL")
        self.assertEqual(data["quantity"], 10)
        self.assertIsNotNone(data["order_id"])

    def test_simulate_api_with_mocked_gemini(self):
        """Simulation endpoint runs full pipeline, filtering noise and returning Bullish/Bearish items."""
        mock_analyzer = self.app.state.dashboard.analyzer
        mock_analyzer.audit = MagicMock()

        # Define responses for test filings
        def side_effect(symbol, headline, details):
            if symbol == "BEL":
                return FilingAudit(
                    sentiment="BULLISH",
                    confidence=95,
                    catalyst_type="ORDER_WIN",
                    material_impact=True,
                    summary="BEL secured defense export contract worth 3850 Cr",
                )
            elif symbol == "BANKINDIA":
                return FilingAudit(
                    sentiment="BEARISH",
                    confidence=92,
                    catalyst_type="PENALTY",
                    material_impact=True,
                    summary="RBI regulatory penalty imposed",
                )
            return None

        mock_analyzer.audit.side_effect = side_effect

        res = self.client.post("/api/simulate")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["processed_count"], 2)  # BEL and BANKINDIA (SBC & TATASTEEL filtered)

        # Check feed items
        symbols = [item["symbol"] for item in data["items"]]
        self.assertIn("BEL", symbols)
        self.assertIn("BANKINDIA", symbols)
        self.assertNotIn("SBC", symbols)  # Non-F&O filtered
        self.assertNotIn("TATASTEEL", symbols)  # Noise filtered

        # Check order status on BEL
        bel_item = next(item for item in data["items"] if item["symbol"] == "BEL")
        self.assertEqual(bel_item["sentiment"], "BULLISH")
        self.assertEqual(bel_item["order"]["quantity"], 10)
        self.assertTrue(bel_item["order"]["placed"])

        # Check order status on BANKINDIA
        bi_item = next(item for item in data["items"] if item["symbol"] == "BANKINDIA")
        self.assertEqual(bi_item["sentiment"], "BEARISH")
        self.assertFalse(bi_item["order"]["placed"])


if __name__ == "__main__":
    unittest.main()

