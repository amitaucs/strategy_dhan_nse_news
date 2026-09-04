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

    def test_get_and_update_token_api(self):
        """Test token retrieval and runtime update endpoints."""
        # 1. GET token status
        res = self.client.get("/api/settings/token")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("is_configured", data)
        self.assertIn("masked_token", data)
        self.assertIn("dry_run", data)

        # 2. POST token update with sample token
        update_res = self.client.post(
            "/api/settings/token",
            json={
                "client_id": "1100223344",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiMTIzNDU2In0.sample_signature_xyz",
                "dry_run": True,
            },
        )
        self.assertEqual(update_res.status_code, 200)
        up_data = update_res.json()
        self.assertTrue(up_data["success"])
        self.assertEqual(up_data["client_id"], "1100223344")
        self.assertIn("eyJhbGci...", up_data["masked_token"])
        self.assertTrue(up_data["dry_run"])

        # 3. Verify status endpoint reflects new state
        status_res = self.client.get("/api/status")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["client_id"], "1100223344")
        self.assertIn("eyJhbGci...", status_res.json()["masked_token"])

    @patch("news_based_strategy.ui.server.requests.post")
    def test_dhan_oauth_endpoints(self, mock_post):
        """Test OAuth login initiation and callback consent exchange."""
        # 1. Missing credentials returns 400
        res_fail = self.client.get("/api/auth/dhan/login")
        self.assertEqual(res_fail.status_code, 400)
        self.assertFalse(res_fail.json()["success"])

        # 2. Save OAuth Keys
        save_res = self.client.post(
            "/api/settings/oauth-keys",
            json={
                "client_id": "1000998877",
                "app_id": "app_sample_123",
                "app_secret": "secret_sample_456",
            },
        )
        self.assertEqual(save_res.status_code, 200)
        self.assertTrue(save_res.json()["has_app_keys"])

        # 3. Initiate Login (Mock Dhan generate-consent)
        mock_resp_gen = MagicMock()
        mock_resp_gen.json.return_value = {"consentAppId": "CONSENT_APP_ID_9999"}
        mock_post.return_value = mock_resp_gen

        res_login = self.client.get("/api/auth/dhan/login")
        self.assertEqual(res_login.status_code, 200)
        login_data = res_login.json()
        self.assertTrue(login_data["success"])
        self.assertIn("https://auth.dhan.co/app/login?consentAppId=CONSENT_APP_ID_9999", login_data["login_url"])

        # 4. Callback (Mock Dhan consume-consent)
        mock_resp_consume = MagicMock()
        mock_resp_consume.json.return_value = {
            "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dhan_oauth_live_session_token.sig"
        }
        mock_post.return_value = mock_resp_consume

        res_cb = self.client.get("/api/auth/dhan/callback?tokenId=DHAN_TOKEN_ID_12345", follow_redirects=False)
        self.assertEqual(res_cb.status_code, 307)
        self.assertIn("/?auth_success=true", res_cb.headers["location"])

        # 5. Verify executor in-memory token updated
        token_status = self.client.get("/api/settings/token").json()
        self.assertTrue(token_status["is_configured"])
        self.assertIn("eyJhbGci...", token_status["masked_token"])
        self.assertEqual(token_status["client_id"], "1000998877")


if __name__ == "__main__":
    unittest.main()



