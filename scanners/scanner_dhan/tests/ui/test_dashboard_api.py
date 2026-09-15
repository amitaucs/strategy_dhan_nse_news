"""Unit tests for FastAPI Dashboard endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scanner_dhan.ui.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_api_health(client: TestClient) -> None:
    """Verify healthcheck endpoint returns status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "dhan_connected" in data
    assert data["registered_scanners_count"] >= 3


def test_api_list_scanners(client: TestClient) -> None:
    """Verify scanner list returns all registered scanners."""
    response = client.get("/api/scanners")
    assert response.status_code == 200
    scanners = response.json()
    assert isinstance(scanners, list)
    scanner_ids = [s["id"] for s in scanners]

    assert "nifty50_support" in scanner_ids
    assert "nifty50_resistance" in scanner_ids
    assert "nifty50_rsi" in scanner_ids
    assert "heikin_ashi_ema_pullback" in scanner_ids
    assert "order_block" in scanner_ids


def test_run_unknown_scanner(client: TestClient) -> None:
    """Verify 404 is returned for non-existent scanner."""
    response = client.post("/api/scanners/non_existent_scanner_id/run", json={"parameters": {}})
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_serve_dashboard_html(client: TestClient) -> None:
    """Verify root / serves the HTML SPA."""
    response = client.get("/")
    assert response.status_code == 200
    assert "DhanHQ" in response.text
    assert "scanner-nav-list" in response.text
