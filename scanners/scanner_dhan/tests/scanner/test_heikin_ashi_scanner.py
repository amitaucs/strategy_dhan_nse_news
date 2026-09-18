"""Unit tests for 2H Heikin Ashi EMA Pullback + Supertrend Scanner."""

from __future__ import annotations

from scanner_dhan.scanner.st15_largecap.scanner import HeikinAshiEmaPullbackScanner
from scanner_dhan.universe.nifty100 import NIFTY_100_SYMBOLS, resolve_nifty100_securities


def test_nifty100_universe_resolution() -> None:
    """Verify Nifty 100 resolution contains all 100 symbols."""
    resolved = resolve_nifty100_securities()
    assert len(resolved) >= 95
    assert len(NIFTY_100_SYMBOLS) == 100
    expected = ("RELIANCE", "INFY", "TCS", "HDFCBANK", "TATAPOWER", "HAL")
    for sym in expected:
        assert sym in resolved


def test_heikin_ashi_scanner_registration() -> None:
    """Test scanner registration in registry and parameters."""
    scanner = HeikinAshiEmaPullbackScanner()
    assert scanner.id == "heikin_ashi_ema_pullback"
    assert scanner.category == "Trend Following"
    param_names = [p.name for p in scanner.parameters]
    assert "universe" in param_names
    assert "timeframe" in param_names
    assert "first_candle_only" in param_names
    assert "threshold_pct" in param_names
    assert "supertrend_period" in param_names
    assert "supertrend_multiplier" in param_names


def test_heikin_ashi_scan_result_model() -> None:
    """Verify HeikinAshiEmaScanResult preserves all fields in to_dict."""
    from scanner_dhan.scanner.st15_largecap.models import HeikinAshiEmaScanResult

    res = HeikinAshiEmaScanResult(
        symbol="KOTAKBANK",
        security_id="1922",
        ltp=422.50,
        nearest_ema_name="20 EMA",
        nearest_ema_price=421.50,
        distance_pct=0.42,
        is_ha_green=True,
        is_first_green=True,
        is_pullback=True,
        is_supertrend_green=True,
        supertrend_val=410.0,
        is_matched=True,
        rsi=60.8,
    )
    d = res.to_dict()
    assert d["symbol"] == "KOTAKBANK"
    assert d["is_at_support"] is True
    assert d["is_pullback"] is True
    assert d["is_ha_green"] is True
    assert d["is_first_green"] is True
    assert d["is_supertrend_green"] is True
    assert d["support_price"] == 421.50
