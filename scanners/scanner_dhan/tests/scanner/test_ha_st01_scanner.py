"""Unit tests for HA_ST01: Heikin Ashi + RSI Bullish Reversal Strategy Scanner."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scanner_dhan.scanner.base import ScanReport
from scanner_dhan.scanner.ha_st01_scanner.engine import (
    analyze_ha_st01_stock,
    detect_bullish_divergence,
)
from scanner_dhan.scanner.ha_st01_scanner.models import HaSt01ScanResult, HaSt01SetupType
from scanner_dhan.scanner.ha_st01_scanner.scanner import (
    HaSt01ReversalScanner,
    format_ha_st01_dataframe,
)


def _create_synthetic_daily_data(bars: int = 150, base_price: float = 200.0) -> pd.DataFrame:
    """Generate base synthetic daily OHLCV DataFrame."""
    dates = pd.date_range("2024-01-01", periods=bars, freq="D")
    rows = []
    price = base_price
    for d in dates:
        open_p = price
        high_p = price + 2.0
        low_p = price - 2.0
        close_p = price + 0.5
        price += 0.5
        rows.append(
            {
                "timestamp": d,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 1000000.0,
            }
        )
    return pd.DataFrame(rows)


def test_detect_bullish_divergence_positive() -> None:
    """Test detecting regular bullish divergence: Price Lower Low & RSI Higher Low."""
    n = 30
    price_series = pd.Series([120.0] * n)
    rsi_series = pd.Series([50.0] * n)

    # Trough 1 around idx 8-12 (Trough at idx 10: price 98.0, rsi 24.0)
    price_series.iloc[8:12] = [105.0, 100.0, 98.0, 102.0]
    rsi_series.iloc[8:12] = [30.0, 26.0, 24.0, 28.0]

    # Recovery in between
    price_series.iloc[15:20] = [110.0, 112.0, 114.0, 112.0, 108.0]
    rsi_series.iloc[15:20] = [45.0, 48.0, 50.0, 47.0, 42.0]

    # Trough 2 around idx 24-28 (Price Lower Low 92.0 vs 98.0, RSI Higher Low 29.0 vs 24.0)
    price_series.iloc[24:28] = [96.0, 93.0, 92.0, 95.0]
    rsi_series.iloc[24:28] = [32.0, 30.0, 29.0, 33.0]

    has_div = detect_bullish_divergence(
        lows=price_series,
        rsi_series=rsi_series,
        lookback=28,
        min_pivot_distance=4,
    )
    assert has_div is True


def test_detect_bullish_divergence_negative() -> None:
    """Test divergence returns False when price and RSI make lower lows (trend continuation)."""
    n = 30
    price_series = pd.Series([120.0] * n)
    rsi_series = pd.Series([50.0] * n)

    # Trough 1
    price_series.iloc[8:12] = [105.0, 100.0, 98.0, 102.0]
    rsi_series.iloc[8:12] = [35.0, 32.0, 30.0, 33.0]

    # Trough 2: Price Lower Low (90.0) AND RSI Lower Low (22.0)
    price_series.iloc[24:28] = [95.0, 92.0, 90.0, 94.0]
    rsi_series.iloc[24:28] = [28.0, 24.0, 22.0, 26.0]

    has_div = detect_bullish_divergence(
        lows=price_series,
        rsi_series=rsi_series,
        lookback=28,
        min_pivot_distance=4,
    )
    assert has_div is False


def test_ha_st01_oversold_flip_setup() -> None:
    """Verify detection of Oversold Flip setup (multi-red HA downswing, RSI <= 35, green flip)."""
    df = _create_synthetic_daily_data(bars=120, base_price=300.0)

    # Simulate strong downswing in last 6 bars so HA candles are red and RSI is oversold
    # Bars 113 to 118: steady drops
    prices_down = [250.0, 240.0, 230.0, 220.0, 210.0, 200.0]
    for idx, p in enumerate(prices_down, start=113):
        df.loc[idx, "open"] = p + 5.0
        df.loc[idx, "high"] = p + 6.0
        df.loc[idx, "low"] = p - 2.0
        df.loc[idx, "close"] = p
        df.loc[idx, "volume"] = 1500000.0

    # Bar 119 (current trigger bar): strong green rebound
    df.loc[119, "open"] = 205.0
    df.loc[119, "high"] = 225.0
    df.loc[119, "low"] = 202.0
    df.loc[119, "close"] = 224.0
    df.loc[119, "volume"] = 2500000.0

    result = analyze_ha_st01_stock(
        symbol="RELIANCE",
        security_id="2885",
        daily_df=df,
        min_prior_red_bars=2,
        oversold_threshold=35.0,
        min_bars_required=40,
    )

    assert result is not None
    assert result.symbol == "RELIANCE"
    assert result.is_reversal_setup is True
    assert result.is_ha_color_flip is True
    assert result.prior_red_ha_count >= 2
    assert result.setup_type in (HaSt01SetupType.OVERSOLD_RECOVERY, HaSt01SetupType.CONFLUENCE)
    assert result.entry_price == pytest.approx(225.0 * 1.002, 0.01)
    assert result.stop_loss <= 205.0
    assert result.risk_per_share > 0
    assert result.target_1r == pytest.approx(result.entry_price + result.risk_per_share, 0.01)
    assert result.target_2r == pytest.approx(result.entry_price + 2 * result.risk_per_share, 0.01)


def test_ha_st01_rejection_no_prior_red_stretch() -> None:
    """Verify that a green HA candle without at least 2 prior red bars is not matched."""
    df = _create_synthetic_daily_data(bars=120, base_price=300.0)

    # All bars trending upward (all green HA)
    result = analyze_ha_st01_stock(
        symbol="TCS",
        security_id="11536",
        daily_df=df,
        min_prior_red_bars=2,
        oversold_threshold=35.0,
    )
    assert result is not None
    assert result.is_reversal_setup is False
    assert result.is_at_support is False


def test_ha_st01_rejection_current_candle_red() -> None:
    """Verify that if current HA candle is red, scanner does NOT trigger a reversal."""
    df = _create_synthetic_daily_data(bars=120, base_price=300.0)

    # Make last 5 bars all red
    for idx in range(115, 120):
        df.loc[idx, "open"] = 250.0 - (idx - 115) * 5.0
        df.loc[idx, "high"] = df.loc[idx, "open"] + 1.0
        df.loc[idx, "low"] = df.loc[idx, "open"] - 10.0
        df.loc[idx, "close"] = df.loc[idx, "open"] - 8.0

    result = analyze_ha_st01_stock(
        symbol="INFY",
        security_id="1594",
        daily_df=df,
        min_prior_red_bars=2,
    )
    assert result is not None
    assert result.is_reversal_setup is False
    assert result.is_at_support is False


def test_ha_st01_rejection_insufficient_bars() -> None:
    """Verify rejection when dataframe has fewer than required bars."""
    df = _create_synthetic_daily_data(bars=20, base_price=100.0)
    result = analyze_ha_st01_stock(
        symbol="WIPRO",
        security_id="3787",
        daily_df=df,
        min_bars_required=40,
    )
    assert result is None


def test_format_ha_st01_dataframe() -> None:
    """Test formatting HaSt01ScanResult objects into DataFrame."""
    res1 = HaSt01ScanResult(
        symbol="SBIN",
        security_id="3045",
        ltp=800.0,
        is_reversal_setup=True,
        setup_type=HaSt01SetupType.OVERSOLD_RECOVERY,
        ha_open=795.0,
        ha_close=802.0,
        ha_high=805.0,
        ha_low=790.0,
        rsi=32.5,
        rsi_prev=29.0,
        rsi_min_last_3=29.0,
        entry_price=806.6,
        stop_loss=785.0,
        risk_per_share=21.6,
        target_1r=828.2,
        target_2r=849.8,
        reward_risk_ratio=2.0,
        prior_red_ha_count=3,
        is_ha_color_flip=True,
        has_bullish_divergence=False,
        is_oversold_recovery=True,
        volume=5000000,
        candle_signal="🟢 Oversold Flip (3 Red HA)",
        distance_pct=0.82,
    )

    mock_report = ScanReport(
        timestamp=datetime.now(),
        scanner_id="ha_st01_rsi_reversal",
        scanner_name="Heikin Ashi + RSI Reversal - HA_ST01",
        total_scanned=1,
        matched_count=1,
        results=[res1],
    )

    df_out = format_ha_st01_dataframe(mock_report, only_matched=False)
    assert len(df_out) == 1
    assert "TradingSymbol" in df_out.columns
    assert "Setup Type" in df_out.columns
    assert "Entry Trigger (₹)" in df_out.columns
    assert "Structural Stop-Loss (₹)" in df_out.columns
    assert "Initial 1R Target (₹)" in df_out.columns
    assert "Target 2R (₹)" in df_out.columns
    assert df_out.iloc[0]["TradingSymbol"] == "SBIN"
    assert df_out.iloc[0]["Setup Type"] == HaSt01SetupType.OVERSOLD_RECOVERY.value
    assert df_out.iloc[0]["Initial 1R Target (₹)"] == 828.2


def test_ha_st01_scanner_run_mocked() -> None:
    """Test HaSt01ReversalScanner scan method with mocked data provider."""
    mock_provider = MagicMock()

    # Generate synthetic data for HDFCBANK (trigger setup) and ICICIBANK (no setup)
    df_hdfc = _create_synthetic_daily_data(bars=120, base_price=300.0)
    prices_down = [250.0, 240.0, 230.0, 220.0, 210.0, 200.0]
    for idx, p in enumerate(prices_down, start=113):
        df_hdfc.loc[idx, "open"] = p + 5.0
        df_hdfc.loc[idx, "high"] = p + 6.0
        df_hdfc.loc[idx, "low"] = p - 2.0
        df_hdfc.loc[idx, "close"] = p
        df_hdfc.loc[idx, "volume"] = 1500000.0
    df_hdfc.loc[119, "open"] = 205.0
    df_hdfc.loc[119, "high"] = 225.0
    df_hdfc.loc[119, "low"] = 202.0
    df_hdfc.loc[119, "close"] = 224.0
    df_hdfc.loc[119, "volume"] = 2500000.0

    df_icici = _create_synthetic_daily_data(bars=120, base_price=1200.0)

    def fake_fetch_bars(security_id: str, timeframe: str = "1D", days: int = 200) -> pd.DataFrame:
        if str(security_id) in ("1333", 1333):
            return df_hdfc
        return df_icici

    mock_provider.fetch_bars.side_effect = fake_fetch_bars
    mock_provider.fetch_ltp_batch.return_value = {"1333": 224.0, "4963": 1200.0}

    scanner = HaSt01ReversalScanner()
    report = scanner.run(
        params={
            "universe": "NIFTY_50",
            "timeframe": "1D",
            "min_prior_red": 2,
            "oversold_threshold": 35.0,
            "max_workers": 2,
        },
        provider=mock_provider,
    )

    assert report is not None
    assert report.scanner_id == "ha_st01_rsi_reversal"
    assert report.total_scanned >= 1
    assert report.matched_count >= 1
    symbols_found = [r.symbol for r in report.results]
    assert "HDFCBANK" in symbols_found
