"""Unit tests for ATH-ST08: Monthly All-Time High Breakout Strategy Scanner."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from scanner_dhan.scanner.ath_st08_scanner.engine import (
    analyze_ath_stock,
    calculate_30_week_sma,
    resample_to_monthly_ath,
    resample_to_weekly_ath,
)
from scanner_dhan.scanner.ath_st08_scanner.models import AthClass
from scanner_dhan.scanner.ath_st08_scanner.scanner import format_ath_dataframe
from scanner_dhan.scanner.base import ScanReport


def _create_synthetic_daily_df(
    total_months: int = 60,
    ath_month_idx: int = 15,
    ath_price: float = 200.0,
    breakout_close: float = 220.0,
    is_exhaustion: bool = False,
    is_red: bool = False,
) -> pd.DataFrame:
    """Generate clean synthetic daily OHLCV across `total_months` months."""
    month_starts = pd.date_range(end="2024-10-31", periods=total_months, freq="MS")
    rows = []

    for m_idx, m_start in enumerate(month_starts):
        # 20 trading days per month
        days_in_m = pd.date_range(start=m_start, periods=20, freq="B")

        if m_idx == total_months - 1:
            # Current breakout month
            if is_exhaustion:
                # Huge range: >2.5x average
                m_open = breakout_close - 10.0
                m_high = breakout_close + 120.0
                m_low = max(50.0, breakout_close - 100.0)
                m_close = breakout_close
            elif is_red:
                # Red candle: Open > Close
                m_open = breakout_close + 15.0
                m_high = breakout_close + 20.0
                m_low = breakout_close - 15.0
                m_close = breakout_close
            else:
                # Clean breakout
                m_open = breakout_close - 10.0
                m_high = breakout_close + 5.0
                m_low = breakout_close - 15.0
                m_close = breakout_close
        elif m_idx == ath_month_idx:
            # Historical ATH month
            m_open = ath_price - 10.0
            m_high = ath_price
            m_low = ath_price - 15.0
            m_close = ath_price - 5.0
        elif m_idx < ath_month_idx:
            # Build-up before ATH
            base = 100.0 + (m_idx / max(1, ath_month_idx)) * 70.0
            m_open = base
            m_high = base + 8.0
            m_low = base - 4.0
            m_close = base + 5.0
        else:
            # Consolidation period below ATH (e.g. within 70-90% of ATH)
            base = ath_price * 0.80 + ((m_idx % 6) - 3) * 3.0
            m_open = base
            m_high = min(base + 8.0, ath_price - 2.0)
            m_low = base - 4.0
            m_close = base + 3.0

        # Spread into 20 daily bars
        for d_i, d in enumerate(days_in_m):
            if d_i == 0:
                d_open = m_open
                d_high = max(m_open, m_high - 1.0)
                d_low = min(m_open, m_low + 1.0)
                d_close = (m_open + m_close) / 2.0
            elif d_i == 10:
                d_open = (m_open + m_close) / 2.0
                d_high = m_high
                d_low = m_low
                d_close = (m_open + m_close) / 2.0
            elif d_i == 19:
                d_open = (m_open + m_close) / 2.0
                d_high = max(m_close, m_high - 1.0)
                d_low = min(m_close, m_low + 1.0)
                d_close = m_close
            else:
                d_open = (m_open + m_close) / 2.0
                d_high = d_open + 2.0
                d_low = d_open - 2.0
                d_close = d_open + 1.0

            rows.append(
                {
                    "timestamp": d,
                    "open": d_open,
                    "high": d_high,
                    "low": d_low,
                    "close": d_close,
                    "volume": 50000.0,
                }
            )

    return pd.DataFrame(rows)


def test_resample_to_monthly_ath() -> None:
    """Verify daily to monthly resampling."""
    daily_dates = pd.date_range("2024-01-01", "2024-03-31", freq="D")
    daily_df = pd.DataFrame(
        {
            "timestamp": daily_dates,
            "open": [100.0] * len(daily_dates),
            "high": [110.0] * len(daily_dates),
            "low": [90.0] * len(daily_dates),
            "close": [105.0] * len(daily_dates),
            "volume": [1000.0] * len(daily_dates),
        }
    )
    daily_df.loc[0, "open"] = 92.0
    daily_df.loc[14, "high"] = 125.0
    daily_df.loc[19, "low"] = 85.0
    daily_df.loc[30, "close"] = 118.0

    monthly_df = resample_to_monthly_ath(daily_df)
    assert len(monthly_df) == 3
    jan_row = monthly_df.iloc[0]
    assert jan_row["open"] == 92.0
    assert jan_row["high"] == 125.0
    assert jan_row["low"] == 85.0
    assert jan_row["close"] == 118.0
    assert jan_row["volume"] == 31000.0


def test_calculate_30_week_sma() -> None:
    """Verify weekly resampling and 30-week SMA calculation."""
    daily_dates = pd.date_range(end="2024-10-31", periods=500, freq="D")
    daily_df = pd.DataFrame(
        {
            "timestamp": daily_dates,
            "open": [100.0] * len(daily_dates),
            "high": [105.0] * len(daily_dates),
            "low": [95.0] * len(daily_dates),
            "close": [100.0 + (i * 0.1) for i in range(len(daily_dates))],
            "volume": [10000.0] * len(daily_dates),
        }
    )
    weekly_df = resample_to_weekly_ath(daily_df)
    assert len(weekly_df) >= 30

    sma_30w = calculate_30_week_sma(daily_df)
    assert sma_30w is not None
    assert sma_30w > 0


def test_ath_st08_a_class_breakout() -> None:
    """Verify A-Class breakout detection (>30 months consolidation)."""
    # 60 months total, ATH at month 15 -> 44 months consolidation (>30m)
    df = _create_synthetic_daily_df(
        total_months=60,
        ath_month_idx=15,
        ath_price=200.0,
        breakout_close=220.0,
        is_exhaustion=False,
        is_red=False,
    )

    result = analyze_ath_stock(
        symbol="TITAN",
        security_id="3506",
        daily_df=df,
        min_monthly_bars=24,
    )

    assert result is not None
    assert result.is_ath_breakout is True
    assert result.is_at_support is True
    assert result.ath_class == AthClass.A_CLASS
    assert result.months_in_consolidation > 30
    assert result.prior_ath_price == 200.0
    assert result.ltp == 220.0
    assert result.trigger_entry_price == pytest.approx(result.breakout_candle_high * 1.01, 0.01)
    assert result.is_exhaustion_passed is True
    assert result.volume > 0
    assert result.rsi is not None
    assert result.sma_30_week > 0
    assert "A-Class" in result.candle_signal


def test_ath_st08_b_class_breakout() -> None:
    """Verify B-Class breakout detection (<= 30 months consolidation)."""
    # 40 months total, ATH at month 25 -> 14 months consolidation (<= 30m)
    df = _create_synthetic_daily_df(
        total_months=40,
        ath_month_idx=25,
        ath_price=300.0,
        breakout_close=325.0,
        is_exhaustion=False,
        is_red=False,
    )

    result = analyze_ath_stock(
        symbol="BEL",
        security_id="383",
        daily_df=df,
        min_monthly_bars=24,
    )

    assert result is not None
    assert result.is_ath_breakout is True
    assert result.is_at_support is True
    assert result.ath_class == AthClass.B_CLASS
    assert result.months_in_consolidation <= 30
    assert result.prior_ath_price == 300.0
    assert result.ltp == 325.0
    assert result.is_exhaustion_passed is True
    assert "B-Class" in result.candle_signal


def test_ath_st08_exhaustion_candle_rejected() -> None:
    """Verify that candles with excessive range (>2.5x 12m avg range) are rejected."""
    df = _create_synthetic_daily_df(
        total_months=60,
        ath_month_idx=15,
        ath_price=200.0,
        breakout_close=220.0,
        is_exhaustion=True,
        is_red=False,
    )

    result = analyze_ath_stock(
        symbol="RELIANCE",
        security_id="2885",
        daily_df=df,
        min_monthly_bars=24,
    )

    assert result is not None
    assert result.is_exhaustion_passed is False
    assert result.is_ath_breakout is False
    assert result.is_at_support is False
    assert "Exhaustion" in result.candle_signal


def test_ath_st08_red_candle_rejected() -> None:
    """Verify that red monthly candles (Close <= Open) are not flagged as breakouts."""
    df = _create_synthetic_daily_df(
        total_months=60,
        ath_month_idx=15,
        ath_price=200.0,
        breakout_close=210.0,
        is_exhaustion=False,
        is_red=True,
    )

    result = analyze_ath_stock(
        symbol="TCS",
        security_id="11536",
        daily_df=df,
        min_monthly_bars=24,
    )

    assert result is not None
    assert result.is_ath_breakout is False
    assert result.is_at_support is False
    assert "Red Candle" in result.candle_signal


def test_ath_st08_insufficient_history_skipped() -> None:
    """Verify that stocks with fewer than min_monthly_bars are skipped."""
    daily_dates = pd.date_range("2024-01-01", periods=100, freq="D")
    df = pd.DataFrame(
        {
            "timestamp": daily_dates,
            "open": [100.0] * 100,
            "high": [110.0] * 100,
            "low": [90.0] * 100,
            "close": [105.0] * 100,
            "volume": [50000.0] * 100,
        }
    )

    result = analyze_ath_stock(
        symbol="NEW_IPO",
        security_id="99999",
        daily_df=df,
        min_monthly_bars=24,
    )
    assert result is None


def test_ath_st08_format_dataframe() -> None:
    """Verify DataFrame export schema for ATH-ST08."""
    df = _create_synthetic_daily_df(
        total_months=60,
        ath_month_idx=15,
        ath_price=200.0,
        breakout_close=220.0,
        is_exhaustion=False,
        is_red=False,
    )
    res = analyze_ath_stock(
        symbol="TITAN",
        security_id="3506",
        daily_df=df,
        min_monthly_bars=24,
    )
    assert res is not None

    mock_report = ScanReport(
        timestamp=datetime.now(),
        scanner_id="ath_st08_breakout",
        scanner_name="Monthly ATH Breakout Strategy - ATH-ST08",
        total_scanned=1,
        matched_count=1 if res.is_at_support else 0,
        results=[res],
    )

    formatted_df = format_ath_dataframe(mock_report, only_matched=False)
    assert not formatted_df.empty
    assert "TradingSymbol" in formatted_df.columns
    assert "SecurityID" in formatted_df.columns
    assert "Setup Class" in formatted_df.columns
    assert "LTP (₹)" in formatted_df.columns
    assert "Prior ATH Level (₹)" in formatted_df.columns
    assert "Prior ATH Date" in formatted_df.columns
    assert "Months in Consolidation" in formatted_df.columns
    assert "Recommended Entry Trigger (High + 1%)" in formatted_df.columns
    assert "30-Week SMA Level" in formatted_df.columns
    assert "Expansion Ratio" in formatted_df.columns
    assert "Distance to Prior ATH (%)" in formatted_df.columns
    assert "Volume" in formatted_df.columns
    assert "RSI (14)" in formatted_df.columns
    assert "Signal" in formatted_df.columns
