"""Unit tests for 2H Heikin Ashi EMA Pullback + Supertrend Scanner (ST15)."""

from __future__ import annotations
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from scanner_dhan.scanner.st15_largecap.scanner import HeikinAshiEmaPullbackScanner
from scanner_dhan.scanner.st15_largecap.models import HeikinAshiEmaScanResult
from scanner_dhan.universe.nifty100 import NIFTY_100_SYMBOLS, resolve_nifty100_securities


def test_nifty100_universe_resolution() -> None:
    """Verify Nifty 100 resolution contains all 100 symbols."""
    resolved = resolve_nifty100_securities()
    assert len(resolved) >= 95
    assert len(NIFTY_100_SYMBOLS) == 100
    expected = ("RELIANCE", "INFY", "TCS", "HDFCBANK", "TATAPOWER", "HAL")
    for sym in expected:
        assert sym in resolved


def test_heikin_ashi_scanner_registration_and_defaults() -> None:
    """Test scanner registration, parameters, and strict default settings."""
    scanner = HeikinAshiEmaPullbackScanner()
    assert scanner.id == "heikin_ashi_ema_pullback"
    assert scanner.category == "Trend Following"
    param_dict = {p.name: p.default for p in scanner.parameters}
    assert param_dict["universe"] == "NIFTY_100"
    assert param_dict["timeframe"] == "2H"
    assert param_dict["ema_alignment"] == "strict"
    assert param_dict["first_candle_only"] == "yes"
    assert param_dict["require_supertrend"] == "yes"
    assert param_dict["threshold_pct"] == 1.5


def test_heikin_ashi_scan_result_model() -> None:
    """Verify HeikinAshiEmaScanResult preserves all EMA fields and status in to_dict."""
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
        is_st_fresh_green=False,
        supertrend_val=410.0,
        ema_20=421.50,
        ema_50=415.00,
        ema_200=390.00,
        is_ema_aligned=True,
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
    assert d["is_ema_aligned"] is True
    assert d["ema_20"] == 421.50
    assert d["ema_50"] == 415.00
    assert d["ema_200"] == 390.00
    assert d["support_price"] == 421.50


def _generate_synthetic_candles(
    close_prices: list[float],
    high_offset: float = 2.0,
    low_offset: float = 2.0,
) -> pd.DataFrame:
    """Helper to generate a synthetic OHLCV DataFrame."""
    rows = []
    n = len(close_prices)
    for i, c in enumerate(close_prices):
        prev_c = close_prices[i - 1] if i > 0 else c
        o = prev_c
        h = max(o, c) + high_offset
        l = min(o, c) - low_offset
        rows.append(
            {
                "timestamp": pd.Timestamp("2026-09-01") + pd.Timedelta(hours=2 * i),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 100000,
            }
        )
    return pd.DataFrame(rows)


def test_bearish_ema_stack_rejection() -> None:
    """Ensure scanner strictly rejects bearish/inverted EMA stack (e.g. HDFC Bank: 200 > 50 > 20 EMA)."""
    scanner = HeikinAshiEmaPullbackScanner()
    mock_prov = MagicMock()

    # Create a long downtrend series: prices fall from 800 down to 700
    # On this series, 200 EMA > 50 EMA > 20 EMA
    prices = list(np.linspace(850, 700, 60))
    # Add a slight 2-candle green bounce at the end
    prices[-2] = 705.0  # Red
    prices[-1] = 712.0  # Green bounce
    downtrend_df = _generate_synthetic_candles(prices)

    mock_prov.fetch_ltp_batch.return_value = {"1333": 712.0}
    mock_prov.fetch_bars.return_value = downtrend_df

    # Run with universe resolving to single stock
    from unittest.mock import patch
    with patch(
        "scanner_dhan.scanner.st15_largecap.scanner.get_active_universe",
        return_value=("TEST_UNIVERSE", ["HDFCBANK"], {"HDFCBANK": "1333"}),
    ):
        report = scanner.run(
            params={"universe": "NIFTY_100", "ema_alignment": "strict", "first_candle_only": "yes"},
            provider=mock_prov,
        )

    assert report.total_scanned == 1
    result = report.results[0]
    assert result.symbol == "HDFCBANK"
    assert result.is_ema_aligned is False
    assert result.is_matched is False
    assert "EMA Not Aligned" in result.candle_signal
    assert report.matched_count == 0


def test_bullish_pullback_and_first_green_matched() -> None:
    """Ensure scanner correctly matches valid setup: 20 > 50 > 200 EMA + dip to 20 EMA + 1st Green HA."""
    scanner = HeikinAshiEmaPullbackScanner()
    mock_prov = MagicMock()

    # Create strong uptrend series: prices rise from 500 up to 1000
    # In this series, 20 EMA > 50 EMA > 200 EMA
    prices = list(np.linspace(700, 900, 60))
    # At the end, small pullback to 20 EMA and 1st green candle
    prices[-4] = 900.0
    prices[-3] = 885.0
    prices[-2] = 870.0  # Red pullback dip near 20 EMA (low 868 near EMA 20 ~ 864)
    prices[-1] = 900.0  # Reversal candle -> First green HA candle
    uptrend_df = _generate_synthetic_candles(prices)

    mock_prov.fetch_ltp_batch.return_value = {"2885": 900.0}
    mock_prov.fetch_bars.return_value = uptrend_df

    from unittest.mock import patch
    with patch(
        "scanner_dhan.scanner.st15_largecap.scanner.get_active_universe",
        return_value=("TEST_UNIVERSE", ["RELIANCE"], {"RELIANCE": "2885"}),
    ):
        report = scanner.run(
            params={
                "universe": "NIFTY_100",
                "ema_alignment": "strict",
                "first_candle_only": "yes",
                "require_supertrend": "yes",
                "threshold_pct": 3.0,
            },
            provider=mock_prov,
        )

    assert report.total_scanned == 1
    result = report.results[0]
    assert result.symbol == "RELIANCE"
    assert result.is_ema_aligned is True
    assert result.ema_20 > result.ema_50 > result.ema_200
    assert result.is_first_green is True
    assert result.is_supertrend_green is True
    assert result.is_matched is True
    assert "1st Green HA" in result.candle_signal
    assert report.matched_count == 1
