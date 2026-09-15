"""Unit tests for ST07: Monthly Heikin Ashi + 89 EMA Crossover Strategy Scanner."""

from __future__ import annotations

import pandas as pd
import pytest

from scanner_dhan.scanner.st07_scanner.engine import (
    analyze_st07_stock,
    calculate_monthly_ha_and_emas,
    resample_to_monthly,
)
from scanner_dhan.scanner.st07_scanner.models import St07Category
from scanner_dhan.scanner.st07_scanner.scanner import format_st07_dataframe


def _create_synthetic_monthly_ohlcv(bars: int = 120, base_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic monthly OHLCV DataFrame."""
    dates = pd.date_range("2014-01-01", periods=bars, freq="MS")
    rows = []
    price = base_price
    for d in dates:
        # Create gradual upward drift
        price += 1.0
        open_p = price
        high_p = price + 5.0
        low_p = price - 3.0
        close_p = price + 2.0
        rows.append(
            {
                "timestamp": d,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 500000.0,
            }
        )
    return pd.DataFrame(rows)


def test_resample_to_monthly() -> None:
    """Test converting daily bars to monthly OHLCV."""
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
    # Give Jan 1 a specific open, Jan 15 a high, Jan 20 a low, Jan 31 a close
    daily_df.loc[0, "open"] = 95.0
    daily_df.loc[14, "high"] = 125.0
    daily_df.loc[19, "low"] = 85.0
    daily_df.loc[30, "close"] = 115.0

    monthly_df = resample_to_monthly(daily_df)
    assert len(monthly_df) == 3  # Jan, Feb, Mar 2024
    jan_row = monthly_df.iloc[0]
    assert jan_row["open"] == 95.0
    assert jan_row["high"] == 125.0
    assert jan_row["low"] == 85.0
    assert jan_row["close"] == 115.0
    assert jan_row["volume"] == 31000.0


def test_calculate_monthly_ha_and_emas() -> None:
    """Verify Heikin Ashi and 89/21 EMA series computation on HA close."""
    m_df = _create_synthetic_monthly_ohlcv(120, base_price=100.0)
    df_calc = calculate_monthly_ha_and_emas(m_df, ema_fast_span=21, ema_slow_span=89)

    assert "ha_open" in df_calc.columns
    assert "ha_close" in df_calc.columns
    assert "ema_89" in df_calc.columns
    assert "ema_21" in df_calc.columns

    # Check 1st HA Open calculation: (Open_0 + Close_0) / 2
    expected_first_ha_open = (m_df.iloc[0]["open"] + m_df.iloc[0]["close"]) / 2.0
    assert pytest.approx(df_calc.iloc[0]["ha_open"], 0.01) == expected_first_ha_open

    # Check that EMAs are calculated and positive
    assert df_calc.iloc[-1]["ema_89"] > 0
    assert df_calc.iloc[-1]["ema_21"] > 0


def test_st07_fresh_crossover_trigger() -> None:
    """Verify detection of Fresh Crossover (HA Open < 89 EMA < HA Close & rising 89 EMA)."""
    # Create 120 bars with gentle upward slope so 89 EMA is rising
    dates = pd.date_range("2014-01-01", periods=120, freq="MS")
    rows = []
    price = 100.0
    for i, d in enumerate(dates):
        price += 0.2
        if 114 <= i < 119:
            # Dip below 89 EMA so HA Open starts below
            op, hi, lo, cl = 98.0, 100.0, 96.0, 98.0
        elif i == 119:
            # Fresh Crossover bar expanding from below to above 89 EMA
            op, hi, lo, cl = 98.0, 140.0, 97.0, 135.0
        else:
            op, hi, lo, cl = price, price + 3.0, price - 3.0, price + 1.0
        rows.append(
            {"timestamp": d, "open": op, "high": hi, "low": lo, "close": cl, "volume": 50000.0}
        )
    m_df = pd.DataFrame(rows)

    result = analyze_st07_stock(
        symbol="TEST_CROSS",
        security_id="12345",
        daily_or_monthly_df=m_df,
        is_already_monthly=True,
        min_monthly_bars=90,
    )

    assert result is not None
    assert result.is_ema_89_rising is True
    assert result.is_fresh_crossover is True
    assert result.scan_category == St07Category.FRESH_CROSSOVER
    assert result.is_at_support is True
    assert "Fresh Crossover" in result.candle_signal
    assert result.buy_trigger_price == m_df.iloc[-1]["high"]
    assert result.stop_loss == m_df.iloc[-1]["low"]


def test_st07_accumulation_pullback_trigger() -> None:
    """Verify detection of Accumulation Pullback (HA Low <= 89 EMA <= HA Close & rising 89 EMA)."""
    m_df = _create_synthetic_monthly_ohlcv(120, base_price=100.0)

    # Let stock rise steadily, then in latest bar pull back to test 89 EMA from above
    df_calc = calculate_monthly_ha_and_emas(m_df, ema_fast_span=21, ema_slow_span=89)
    current_89_ema = df_calc.iloc[-1]["ema_89"]

    # Prior bar firmly above 89 EMA
    m_df.loc[118, "open"] = current_89_ema + 15.0
    m_df.loc[118, "high"] = current_89_ema + 20.0
    m_df.loc[118, "low"] = current_89_ema + 12.0
    m_df.loc[118, "close"] = current_89_ema + 18.0

    # Bar 119: HA Open is above 89 EMA, HA Low dips below/at 89 EMA, HA Close bounces above 89 EMA
    m_df.loc[119, "open"] = current_89_ema + 12.0
    m_df.loc[119, "high"] = current_89_ema + 16.0
    m_df.loc[119, "low"] = current_89_ema - 1.5  # Low dips below
    m_df.loc[119, "close"] = current_89_ema + 5.0  # Closes above

    result = analyze_st07_stock(
        symbol="TEST_PULLBACK",
        security_id="54321",
        daily_or_monthly_df=m_df,
        is_already_monthly=True,
        min_monthly_bars=90,
    )

    assert result is not None
    assert result.is_ema_89_rising is True
    assert result.is_accumulation_pullback is True
    assert result.scan_category == St07Category.ACCUMULATION_PULLBACK
    assert result.is_at_support is True
    assert "Accumulation Pullback" in result.candle_signal


def test_st07_falling_89_ema_filter() -> None:
    """Verify that falling 89 EMA invalidates triggers."""
    # Create downtrending series
    dates = pd.date_range("2014-01-01", periods=120, freq="MS")
    rows = []
    price = 500.0
    for d in dates:
        price -= 2.0
        rows.append(
            {
                "timestamp": d,
                "open": price,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price - 1.0,
                "volume": 10000.0,
            }
        )
    m_df = pd.DataFrame(rows)

    result = analyze_st07_stock(
        symbol="TEST_FALLING",
        security_id="99999",
        daily_or_monthly_df=m_df,
        is_already_monthly=True,
        min_monthly_bars=90,
    )

    assert result is not None
    assert result.is_ema_89_rising is False
    assert result.is_fresh_crossover is False
    assert result.is_accumulation_pullback is False
    assert result.scan_category is None
    assert result.is_at_support is False


def test_st07_insufficient_history_skipped() -> None:
    """Verify that stocks with fewer than min_monthly_bars are skipped gracefully."""
    m_df = _create_synthetic_monthly_ohlcv(50, base_price=100.0)
    result = analyze_st07_stock(
        symbol="TEST_SHORT",
        security_id="11111",
        daily_or_monthly_df=m_df,
        is_already_monthly=True,
        min_monthly_bars=90,
    )
    assert result is None


def test_st07_format_dataframe() -> None:
    """Verify DataFrame formatting and export columns."""
    from datetime import datetime

    from scanner_dhan.scanner.base import ScanReport

    m_df = _create_synthetic_monthly_ohlcv(120, base_price=100.0)
    res = analyze_st07_stock(
        symbol="RELIANCE",
        security_id="2885",
        daily_or_monthly_df=m_df,
        is_already_monthly=True,
        min_monthly_bars=90,
    )
    assert res is not None
    assert res.volume > 0
    assert res.rsi is not None and res.rsi > 0

    mock_report = ScanReport(
        timestamp=datetime.now(),
        scanner_id="st07_monthly_ha_89ema",
        scanner_name="Monthly Heikin Ashi + 89 EMA Crossover - ST07",
        total_scanned=1,
        matched_count=1 if res.is_at_support else 0,
        results=[res],
    )

    df = format_st07_dataframe(mock_report, only_matched=False)
    assert not df.empty
    assert "TradingSymbol" in df.columns
    assert "SecurityID" in df.columns
    assert "Scan Category" in df.columns
    assert "Current HA Close" in df.columns
    assert "89 EMA" in df.columns
    assert "Buy Trigger Price" in df.columns
    assert "Stop-Loss Level" in df.columns
    assert "21 EMA (Exit Benchmark)" in df.columns
    assert "Volume" in df.columns
    assert "RSI (14)" in df.columns
