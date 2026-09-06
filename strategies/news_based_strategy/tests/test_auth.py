"""Unit tests for dedicated user authentication, sessions, and login routes."""

import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from news_based_strategy.storage.repository import StrategyStorage, hash_password, verify_password
from news_based_strategy.ui.server import create_app


class TestAuthentication(unittest.TestCase):
    """Test suite for user database authentication, session tokens, and login routes."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = f"{self.temp_dir.name}/test_auth.db"
        self.storage = StrategyStorage(db_path=self.test_db)
        self.storage_patcher = patch(
            "news_based_strategy.ui.server.StrategyStorage",
            lambda *args, **kwargs: StrategyStorage(db_path=self.test_db),
        )
        self.storage_patcher.start()
        self.app = create_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.storage_patcher.stop()
        self.storage.close()
        self.temp_dir.cleanup()

    def test_password_hashing_and_verification(self):
        """Test PBKDF2 password hashing and constant-time verification."""
        pwd = "SecretPassword123!"
        hashed, salt = hash_password(pwd)
        self.assertNotEqual(pwd, hashed)
        self.assertTrue(verify_password(pwd, salt, hashed))
        self.assertFalse(verify_password("WrongPassword", salt, hashed))

    def test_default_user_amit_seeded(self):
        """Verify default user 'amit' is automatically seeded in the database with password 'Kls@1982'."""
        user = self.storage.get_user("amit")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "amit")
        self.assertTrue(self.storage.verify_user_credentials("amit", "Kls@1982"))
        self.assertFalse(self.storage.verify_user_credentials("amit", "WrongPassword!"))

    def test_session_creation_validation_and_deletion(self):
        """Test database session lifecycle."""
        token = self.storage.create_session("amit", max_age_days=1)
        self.assertTrue(len(token) > 20)

        # Validate active session
        username = self.storage.validate_session(token)
        self.assertEqual(username, "amit")

        # Invalid token returns None
        self.assertIsNone(self.storage.validate_session("non_existent_token"))

        # Delete session
        deleted = self.storage.delete_session(token)
        self.assertTrue(deleted)
        self.assertIsNone(self.storage.validate_session(token))

    def test_unauthenticated_request_to_root_redirects_to_login(self):
        """Unauthenticated requests to / should redirect to /login."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 307)
        self.assertEqual(res.headers.get("location"), "/login")

    def test_get_login_page_renders_html(self):
        """GET /login should render the dedicated login page with credentials and Dhan SSO buttons."""
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertIn("NSE Catalyst Trading Terminal", res.text)
        self.assertIn("Username or Email", res.text)
        self.assertIn("Log In with Dhan", res.text)
        self.assertIn("Don't have an account?", res.text)
        self.assertIn("https://join.dhan.co/?invite=VEVQU13117", res.text)

    def test_login_api_invalid_credentials(self):
        """POST /api/auth/login with wrong credentials returns HTTP 401."""
        res = self.client.post("/api/auth/login", json={"username": "amit", "password": "BadPassword"})
        self.assertEqual(res.status_code, 401)
        data = res.json()
        self.assertFalse(data["success"])
        self.assertIn("Invalid", data["message"])

    def test_login_api_success_and_cookie_issuance(self):
        """POST /api/auth/login with valid credentials sets cookie and permits access to /."""
        res = self.client.post("/api/auth/login", json={"username": "amit", "password": "Kls@1982"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["username"], "amit")
        self.assertEqual(data["redirect"], "/")

        # Verify cookie in response
        cookie_header = res.headers.get("set-cookie", "")
        self.assertIn("app_session_token=", cookie_header)

        # Extract cookie and access /
        cookie_val = res.cookies.get("app_session_token")
        self.assertIsNotNone(cookie_val)

        authed_client = TestClient(self.app, cookies={"app_session_token": cookie_val}, follow_redirects=False)
        root_res = authed_client.get("/")
        self.assertEqual(root_res.status_code, 200)
        self.assertIn("NSE Catalyst Trading Terminal", root_res.text)

        # Accessing /login while authenticated redirects to /
        login_res = authed_client.get("/login")
        self.assertEqual(login_res.status_code, 307)
        self.assertEqual(login_res.headers.get("location"), "/")

    def test_app_logout_clears_session(self):
        """POST /api/auth/app-logout terminates session and clears cookie."""
        # Login first
        login_res = self.client.post("/api/auth/login", json={"username": "amit", "password": "Kls@1982"})
        cookie_val = login_res.cookies.get("app_session_token")
        self.assertIsNotNone(cookie_val)

        authed_client = TestClient(self.app, cookies={"app_session_token": cookie_val}, follow_redirects=False)

        # Logout
        logout_res = authed_client.post("/api/auth/app-logout")
        self.assertEqual(logout_res.status_code, 200)
        self.assertTrue(logout_res.json()["success"])

        # Subsequent request to / redirects to /login
        subsequent_res = authed_client.get("/")
        self.assertEqual(subsequent_res.status_code, 307)
        self.assertEqual(subsequent_res.headers.get("location"), "/login")

    def test_dhan_sso_endpoint_with_mocked_consent(self):
        """GET /api/auth/dhan/sso returns Dhan consent login URL."""
        with patch("news_based_strategy.ui.server.generate_dhan_consent_url") as mock_consent:
            mock_consent.return_value = (True, "https://auth.dhan.co/login/consentApp-login?consentAppId=TEST_123")
            self.app.state.dashboard.app_id = "test_app"
            self.app.state.dashboard.app_secret = "test_sec"
            self.app.state.dashboard.executor.client_id = "10001"

            res = self.client.get("/api/auth/dhan/sso")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIn("https://auth.dhan.co/login/consentApp-login", data["login_url"])


if __name__ == "__main__":
    unittest.main()
