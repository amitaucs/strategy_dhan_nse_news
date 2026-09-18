"""Unit tests for RSI Extremes & Momentum Reversal Scanner."""

from __future__ import annotations

import pandas as pd

from scanner_dhan.scanner.registry import ScannerRegistry
from scanner_dhan.scanner.rsi_scanner import (
    Nifty50RsiScanner,
    RsiExtremesScanner,
    RsiScanResult,
    RsiZone,
)


def test_rsi_scanner_registration() -> None:
    """Verify RSI scanner is correctly registered in ScannerRegistry."""
    scanner = RsiExtremesScanner()
    assert scanner.id == "nifty50_rsi"
    assert scanner.category == "Momentum"
    assert issubclass(Nifty50RsiScanner, RsiExtremesScanner)

    registered = ScannerRegistry.get("nifty50_rsi")
    assert registered is not None
    assert registered.id == "nifty50_rsi"


def test_rsi_scan_parameters() -> None:
    """Verify parameters defined for RSI scanner."""
    scanner = RsiExtremesScanner()
    param_names = [p.name for p in scanner.parameters]
    assert "universe" in param_names
    assert "timeframe" in param_names
    assert "oversold_threshold" in param_names
    assert "overbought_threshold" in param_names
    assert "rsi_period" in param_names
    assert "scan_mode" in param_names


def test_rsi_scan_result_model() -> None:
    """Verify RsiScanResult serialization and alias compatibility."""
    res = RsiScanResult(
        symbol="TCS",
        security_id="11536",
        ltp=3950.0,
        rsi=28.5,
        rsi_zone=RsiZone.OVERSOLD,
        candle_signal="Hammer / Pin Bar (Reversal)",
        is_matched=True,
        volume=1200000,
        change_pct=-1.45,
    )

    assert res.symbol == "TCS"
    assert res.rsi == 28.5
    assert res.rsi_zone == RsiZone.OVERSOLD
    assert res.is_matched is True
    assert res.is_at_support is True  # Legacy alias compatibility

    d = res.to_dict()
    assert d["symbol"] == "TCS"
    assert d["rsi"] == 28.5
    assert d["rsi_zone"] == "OVERSOLD"
    assert d["is_matched"] is True
    assert d["is_at_support"] is True

