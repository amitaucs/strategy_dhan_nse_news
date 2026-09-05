import dataclasses
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, FilingAudit
from news_based_strategy.storage.repository import StrategyStorage
from news_based_strategy.ui.server import create_app


class TestUIServer(unittest.TestCase):
    """Test suite for GUI Dashboard API endpoints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = f"{self.temp_dir.name}/test_gui.db"
        self.storage = StrategyStorage(db_path=self.test_db)
        self.session_token = self.storage.create_session("amit")
        self.storage_patcher = patch(
            "news_based_strategy.ui.server.StrategyStorage",
            lambda *args, **kwargs: StrategyStorage(db_path=self.test_db),
        )
        self.storage_patcher.start()
        self.app = create_app()
        self.client = TestClient(self.app, cookies={"app_session_token": self.session_token})

    def tearDown(self):
        self.storage_patcher.stop()
        self.storage.close()
        self.temp_dir.cleanup()

    def test_get_index_html(self):
        """Root GET request with active session should serve dashboard with market status indicator and filter dropdown."""
        with patch("news_based_strategy.ui.server.settings", dataclasses.replace(settings, is_simulate_feed=True)):
            res = self.client.get("/")
            self.assertEqual(res.status_code, 200)
            self.assertIn("NSE Catalyst Trading Terminal", res.text)
            self.assertIn("market-status-badge", res.text)
            self.assertIn("feed-filter-select", res.text)
            self.assertIn("All Passed", res.text)
            self.assertIn("AUTO ORDER", res.text)
            self.assertIn("Show All Signals", res.text)
            self.assertIn("Simulate Feed", res.text)
            self.assertIn("Test / Simulate Sample Catalyst Feed", res.text)

        with patch("news_based_strategy.ui.server.settings", dataclasses.replace(settings, is_simulate_feed=False)):
            res_no_sim = self.client.get("/")
            self.assertEqual(res_no_sim.status_code, 200)
            self.assertIn("NSE Catalyst Trading Terminal", res_no_sim.text)
            self.assertIn("market-status-badge", res_no_sim.text)
            self.assertIn("feed-filter-select", res_no_sim.text)
            self.assertIn("All Passed", res_no_sim.text)
            self.assertIn("AUTO ORDER", res_no_sim.text)
            self.assertIn("Show All Signals", res_no_sim.text)
            self.assertNotIn("Simulate Feed", res_no_sim.text)
            self.assertNotIn("Test / Simulate Sample Catalyst Feed", res_no_sim.text)

    def test_get_status_api(self):
        """API status endpoint returns system state including market open/closed status."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("dry_run", data)
        self.assertIn("auto_order", data)
        self.assertIn("is_market_open", data)
        self.assertIn("market_status_label", data)
        self.assertIn("max_shares_per_trade", data)
        self.assertEqual(data["max_orders_per_day"], 3)
        self.assertIn("today_orders_count", data)
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

    def test_toggle_dry_run_api(self):
        """Toggle dry run endpoint switches live/simulated mode cleanly and persists to DB."""
        self.app.state.dashboard.executor.client_id = "11223344"
        self.app.state.dashboard.executor.access_token = "valid_access_token_123"

        with patch.dict("sys.modules", {"dhanhq": MagicMock()}):
            # 1. Switch to LIVE (dry_run: False)
            res = self.client.post("/api/toggle-dry-run", json={"dry_run": False})
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["dry_run"])
            self.assertFalse(self.app.state.dashboard.executor.dry_run)
            self.assertEqual(self.app.state.dashboard.storage.get_setting("dry_run"), "false")

            # 2. Switch back to DRY-RUN (dry_run: True)
            res2 = self.client.post("/api/toggle-dry-run", json={"dry_run": True})
            self.assertEqual(res2.status_code, 200)
            self.assertTrue(res2.json()["dry_run"])
            self.assertTrue(self.app.state.dashboard.executor.dry_run)
            self.assertEqual(self.app.state.dashboard.storage.get_setting("dry_run"), "true")

    def test_load_feed_history_api(self):
        """Load history endpoint hydrates past audit records into feed_items on demand."""
        self.storage.save_audit(
            seq_id="TEST_HIST_001",
            symbol="BEL",
            audit=FilingAudit(
                sentiment="BULLISH",
                confidence=92,
                catalyst_type="ORDER_WIN",
                material_impact=True,
                summary="Past contract win",
            ),
        )
        self.assertEqual(len(self.app.state.dashboard.feed_items), 0)

        res = self.client.post("/api/feed/load-history")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["count"], 1)

        self.assertEqual(len(self.app.state.dashboard.feed_items), 1)
        self.assertEqual(self.app.state.dashboard.feed_items[0]["symbol"], "BEL")
        self.assertEqual(self.app.state.dashboard.feed_items[0]["order"]["status"], "RECORDED")

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

    def test_place_order_api_stale_rejected(self):
        """Place order endpoint rejects stale announcements older than 180s."""
        self.app.state.dashboard.feed_items.append({
            "seq_id": "TEST_STALE_001",
            "symbol": "BEL",
            "an_dt": "01-Jan-2020 10:00:00",
            "order": {"placed": False, "status": "PENDING_APPROVAL"},
        })
        res = self.client.post(
            "/api/orders/place",
            json={
                "seq_id": "TEST_STALE_001",
                "symbol": "BEL",
                "action": "BUY",
                "product_type": "INTRADAY",
                "confidence": 95,
                "catalyst_type": "ORDER_WIN",
                "summary": "Stale defense contract win",
                "ltp": 300.0,
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Catalyst too stale", res.json()["detail"])

    def test_simulate_api_forbidden_when_disabled(self):
        """Simulation endpoint returns 403 Forbidden when IS_SIMULATE_FEED is false."""
        with patch("news_based_strategy.ui.server.settings", dataclasses.replace(settings, is_simulate_feed=False)):
            res = self.client.post("/api/simulate")
            self.assertEqual(res.status_code, 403)
            self.assertIn("Simulated feed is disabled", res.json()["detail"])

    def test_simulate_api_with_mocked_gemini(self):
        """Simulation endpoint runs full pipeline when enabled, filtering noise and returning Bullish/Bearish items."""
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

        with patch("news_based_strategy.ui.server.settings", dataclasses.replace(settings, is_simulate_feed=True)):
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

    def test_clear_feed_api_preserves_db_records(self):
        """Verify that clearing the UI feed list clears in-memory items but preserves all DB audit logs and trade executions."""
        # 1. Populate feed with a simulated item
        mock_analyzer = self.app.state.dashboard.analyzer
        mock_analyzer.audit = MagicMock(return_value=FilingAudit(
            sentiment="BULLISH",
            confidence=90,
            catalyst_type="ORDER_WIN",
            material_impact=True,
            summary="Contract win of 1000 Cr",
        ))

        ann = Announcement(
            seq_id="TEST_SEQ_PRESERVE_001",
            symbol="BEL",
            desc="Contract win",
            details="Contract win details",
            an_dt="04-Sep-2026 10:00:00",
            is_fno=True,
        )
        self.app.state.dashboard.process_and_add_announcement(ann)
        self.assertEqual(len(self.app.state.dashboard.feed_items), 1)

        # Verify audit was written to DB
        cursor = self.app.state.dashboard.storage.conn.cursor()
        cursor.execute("SELECT symbol, sentiment, confidence FROM audit_logs WHERE seq_id = 'TEST_SEQ_PRESERVE_001'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "BEL")

        # 2. Call POST /api/feed/clear
        clear_res = self.client.post("/api/feed/clear")
        self.assertEqual(clear_res.status_code, 200)
        self.assertTrue(clear_res.json()["success"])
        self.assertEqual(clear_res.json()["cleared_count"], 1)

        # In-memory feed items should now be empty
        self.assertEqual(len(self.app.state.dashboard.feed_items), 0)
        get_feed_res = self.client.get("/api/feed")
        self.assertEqual(get_feed_res.status_code, 200)
        self.assertEqual(len(get_feed_res.json()), 0)

        # 3. Verify DB record still EXISTS and was NOT deleted
        cursor.execute("SELECT symbol, sentiment, confidence FROM audit_logs WHERE seq_id = 'TEST_SEQ_PRESERVE_001'")
        preserved_row = cursor.fetchone()
        self.assertIsNotNone(preserved_row)
        self.assertEqual(preserved_row[0], "BEL")
        self.assertEqual(preserved_row[1], "BULLISH")
        self.assertEqual(preserved_row[2], 90)

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
        with patch("news_based_strategy.ui.server.settings", dataclasses.replace(settings, dhan_client_id="", dhan_app_id="", dhan_app_secret="")):
            app = create_app()
            client = TestClient(app, cookies={"app_session_token": self.session_token})

            # 1. Missing credentials returns 400
            res_fail = client.get("/api/auth/dhan/login")
            self.assertEqual(res_fail.status_code, 400)
            self.assertFalse(res_fail.json()["success"])

            # 2. Save OAuth Keys
            save_res = client.post(
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

            res_login = client.get("/api/auth/dhan/login")
            self.assertEqual(res_login.status_code, 200)
            login_data = res_login.json()
            self.assertTrue(login_data["success"])
            self.assertIn("https://auth.dhan.co/login/consentApp-login?consentAppId=CONSENT_APP_ID_9999", login_data["login_url"])

            # 4. Callback (Mock Dhan consume-consent)
            mock_resp_consume = MagicMock()
            mock_resp_consume.json.return_value = {
                "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dhan_oauth_live_session_token.sig"
            }
            mock_post.return_value = mock_resp_consume

            res_cb = client.get("/api/auth/dhan/callback?tokenId=DHAN_TOKEN_ID_12345", follow_redirects=False)
            self.assertEqual(res_cb.status_code, 307)
            self.assertIn("/?auth_success=true", res_cb.headers["location"])

            # 5. Verify executor in-memory token updated
            token_status = client.get("/api/settings/token").json()
            self.assertTrue(token_status["is_configured"])
            self.assertIn("eyJhbGci...", token_status["masked_token"])
            self.assertEqual(token_status["client_id"], "1000998877")

    def test_database_persistence_across_server_restarts(self):
        """Verify that credentials saved in DB persist when creating a new server instance."""
        import tempfile
        from news_based_strategy.storage.repository import StrategyStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = f"{tmpdir}/persisted.db"
            storage = StrategyStorage(db_path=test_db)
            storage.set_setting("dhan_app_id", "PERSISTED_APP_999")
            storage.set_setting("dhan_app_secret", "PERSISTED_SECRET_888")
            storage.set_setting("dhan_client_id", "PERSISTED_CLIENT_777")
            storage.set_setting("dhan_access_token", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.persisted_token_sig")
            storage.close()

            # Create new server instance pointing to the same DB
            with unittest.mock.patch("news_based_strategy.ui.server.StrategyStorage", lambda *args, **kwargs: StrategyStorage(db_path=test_db)):
                new_app = create_app()
                new_client = TestClient(new_app)

                token_res = new_client.get("/api/settings/token")
                self.assertEqual(token_res.status_code, 200)
                data = token_res.json()

                self.assertTrue(data["is_configured"])
                self.assertTrue(data["has_app_keys"])
                self.assertEqual(data["app_id"], "PERSISTED_APP_999")
                self.assertEqual(data["client_id"], "PERSISTED_CLIENT_777")
                self.assertIn("eyJhbGci...", data["masked_token"])


    def test_token_expiry_detected_on_ui_start(self):
        """Verify that an expired JWT token is detected and flagged on UI start / status check."""
        import base64
        import json
        import time

        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
        past_ts = int(time.time()) - 7200  # Expired 2 hours ago
        payload = base64.urlsafe_b64encode(json.dumps({"exp": past_ts, "dhanClientId": "99887766"}).encode()).decode().rstrip("=")
        expired_jwt = f"{header}.{payload}.signature"

        self.app.state.dashboard.executor.access_token = expired_jwt
        self.app.state.dashboard.storage.set_setting("dhan_access_token", expired_jwt)

        # 1. GET /api/settings/token
        token_res = self.client.get("/api/settings/token")
        self.assertEqual(token_res.status_code, 200)
        tdata = token_res.json()
        self.assertTrue(tdata["is_expired"])
        self.assertFalse(tdata["is_configured"])
        self.assertIn("Token expired on", tdata["expiry_message"])

        # 2. GET /api/status
        status_res = self.client.get("/api/status")
        self.assertEqual(status_res.status_code, 200)
        sdata = status_res.json()
        self.assertTrue(sdata["is_expired"])
        self.assertFalse(sdata["is_configured"])

    def test_auth_me_and_logout_flow(self):
        """Verify that /api/auth/me reports session authentication and /api/auth/logout terminates session."""
        import base64
        import json
        import time

        # 1. Initially unconfigured
        self.app.state.dashboard.executor.access_token = ""
        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 200)
        data_me = res_me.json()
        self.assertFalse(data_me["authenticated"])
        self.assertFalse(data_me["is_configured"])

        # 2. Login with valid token (expires in 24 hours)
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
        future_ts = int(time.time()) + 86400
        payload = base64.urlsafe_b64encode(json.dumps({"exp": future_ts, "dhanClientId": "1100223344"}).encode()).decode().rstrip("=")
        valid_jwt = f"{header}.{payload}.valid_signature"

        self.client.post("/api/settings/token", json={
            "client_id": "1100223344",
            "access_token": valid_jwt,
            "dry_run": False,
        })

        res_me_authed = self.client.get("/api/auth/me")
        self.assertEqual(res_me_authed.status_code, 200)
        data_authed = res_me_authed.json()
        self.assertTrue(data_authed["authenticated"])
        self.assertEqual(data_authed["client_id"], "1100223344")
        self.assertFalse(data_authed["is_expired"])
        self.assertIn("Valid until", data_authed["expiry_message"])

        # 3. Logout
        res_logout = self.client.post("/api/auth/logout")
        self.assertEqual(res_logout.status_code, 200)
        self.assertFalse(res_logout.json()["authenticated"])

        # 4. Verify /api/auth/me is now unauthenticated
        res_me_post_logout = self.client.get("/api/auth/me")
        self.assertEqual(res_me_post_logout.status_code, 200)
        self.assertFalse(res_me_post_logout.json()["authenticated"])
        self.assertEqual(self.app.state.dashboard.storage.get_setting("dhan_access_token"), "")

    def test_client_id_masking_and_client_name(self):
        """Verify client ID masking (last 4 digits) and client name in auth/status endpoints."""
        from news_based_strategy.execution.executor import mask_client_id

        # 1. Direct helper tests
        self.assertIsNone(mask_client_id(None))
        self.assertIsNone(mask_client_id(""))
        self.assertEqual(mask_client_id("2040"), "2040")
        self.assertEqual(mask_client_id("1104872040"), "••••2040")

        # 2. Configure credentials
        self.app.state.dashboard.executor.update_credentials(
            client_id="1104872040",
            access_token="valid.sample.token",
            dry_run=True,
        )
        self.app.state.dashboard.storage.set_setting("dhan_client_name", "Amit Datta")

        # 3. Check /api/status
        status_res = self.client.get("/api/status")
        self.assertEqual(status_res.status_code, 200)
        sdata = status_res.json()
        self.assertEqual(sdata["masked_client_id"], "••••2040")
        self.assertEqual(sdata["client_name"], "Amit Datta")

        # 4. Check /api/settings/token
        token_res = self.client.get("/api/settings/token")
        self.assertEqual(token_res.status_code, 200)
        tdata = token_res.json()
        self.assertEqual(tdata["masked_client_id"], "••••2040")
        self.assertEqual(tdata["client_name"], "Amit Datta")

        # 5. Check /api/auth/me
        me_res = self.client.get("/api/auth/me")
        self.assertEqual(me_res.status_code, 200)
        mdata = me_res.json()
        self.assertEqual(mdata["masked_client_id"], "••••2040")
        self.assertEqual(mdata["client_name"], "Amit Datta")


if __name__ == "__main__":
    unittest.main()





