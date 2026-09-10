"""Dhan OAuth consent generation and token consumption helpers."""

import logging
from typing import Tuple
import requests

logger = logging.getLogger(__name__)


def generate_dhan_consent_url(
    client_id: str,
    app_id: str,
    app_secret: str,
    auth_url: str = "https://auth.dhan.co",
) -> Tuple[bool, str]:
    """Call Dhan /app/generate-consent to obtain the consentAppId and login redirect URL."""
    try:
        url = f"{auth_url.rstrip('/')}/app/generate-consent?client_id={client_id}"
        headers = {
            "app_id": app_id,
            "app_secret": app_secret,
            "Accept": "application/json",
        }
        resp = requests.post(url, headers=headers, timeout=10)
        data = resp.json()
        consent_id = data.get("consentAppId") or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("consentAppId")
        if consent_id:
            login_url = f"{auth_url.rstrip('/')}/login/consentApp-login?consentAppId={consent_id}"
            return True, login_url
        error_msg = data.get("remarks") or data.get("message") or str(data)
        return False, f"Dhan Consent generation failed: {error_msg}"
    except Exception as e:
        return False, f"Dhan Auth connection error: {str(e)}"


def consume_dhan_consent(
    token_id: str,
    app_id: str,
    app_secret: str,
    auth_url: str = "https://auth.dhan.co",
) -> Tuple[bool, str, dict]:
    """Exchange tokenId for accessToken via Dhan /app/consumeApp-consent."""
    try:
        url = f"{auth_url.rstrip('/')}/app/consumeApp-consent?tokenId={token_id}"
        headers = {
            "app_id": app_id,
            "app_secret": app_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = requests.post(url, headers=headers, json={"tokenId": token_id}, timeout=10)
        data = resp.json()
        access_token = data.get("accessToken") or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("accessToken")
        if access_token:
            return True, access_token, data
        error_msg = data.get("remarks") or data.get("message") or str(data)
        return False, f"Dhan token exchange failed: {error_msg}", data
    except Exception as e:
        return False, f"Dhan Auth connection error: {str(e)}", {}


__all__ = [
    "generate_dhan_consent_url",
    "consume_dhan_consent",
]

