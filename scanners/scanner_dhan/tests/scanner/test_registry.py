"""Unit tests for ScannerRegistry and BaseScanner."""

from __future__ import annotations

from scanner_dhan.scanner.base import BaseScanner, ScannerParameter
from scanner_dhan.scanner.registry import ScannerRegistry, register_scanner


def test_registered_scanners() -> None:
    """Verify built-in scanners are auto-registered with metadata."""
    scanners = ScannerRegistry.list_all()
    ids = [s["id"] for s in scanners]

    assert "nifty50_support" in ids
    assert "nifty50_resistance" in ids
    assert "nifty50_rsi" in ids


def test_custom_scanner_registration() -> None:
    """Verify new scanners registered with decorator appear in registry."""

    @register_scanner
    class MockCustomScanner(BaseScanner):
        id = "mock_custom_test"
        name = "Mock Custom Scanner"
        description = "Test custom scanner registration"
        category = "Custom"
        parameters = [
            ScannerParameter(
                name="test_param",
                label="Test Param",
                param_type="int",
                default=10,
            )
        ]

        def run(self, params=None, provider=None):
            return None  # type: ignore

    retrieved = ScannerRegistry.get("mock_custom_test")
    assert retrieved is not None
    assert retrieved.name == "Mock Custom Scanner"
    assert retrieved.category == "Custom"

    all_scanners = ScannerRegistry.list_all()
    custom_meta = next((s for s in all_scanners if s["id"] == "mock_custom_test"), None)
    assert custom_meta is not None
    assert len(custom_meta["parameters"]) == 1
    assert custom_meta["parameters"][0]["name"] == "test_param"
