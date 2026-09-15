"""Unit tests for shared technical indicators."""

from __future__ import annotations

import pandas as pd

from scanner_dhan.indicators import (
    calculate_ema,
    calculate_floor_pivots,
    calculate_rsi,
    calculate_sma,
    identify_candlestick_patterns,
)


def test_calculate_rsi() -> None:
    # Short series returns None
    short_series = pd.Series([100.0, 102.0, 101.0])
    assert calculate_rsi(short_series, period=14) is None

    # Rising series gives 100.0
    rising = pd.Series([100.0 + i * 2.0 for i in range(30)])
    assert calculate_rsi(rising, period=14) == 100.0


def test_calculate_moving_averages() -> None:
    series = pd.Series([float(i) for i in range(1, 101)])
    ema50 = calculate_ema(series, span=50)
    sma50 = calculate_sma(series, window=50)

    assert ema50 is not None
    assert sma50 is not None
    assert isinstance(ema50, float)
    assert isinstance(sma50, float)
    assert sma50 == 75.5


def test_calculate_floor_pivots() -> None:
    df = pd.DataFrame(
        {
            "high": [105.0] * 30,
            "low": [95.0] * 30,
            "close": [100.0] * 30,
        }
    )
    pivots = calculate_floor_pivots(df, lookback_window=20)
    assert "pivot" in pivots
    assert pivots["pivot"] == 100.0
    assert pivots["s1"] == 95.0
    assert pivots["r1"] == 105.0


def test_identify_candlestick_patterns() -> None:
    # Green candle
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 105.0],
            "low": [99.0, 100.0],
            "close": [101.0, 104.0],
        }
    )
    signal = identify_candlestick_patterns(df)
    assert "Bullish Green Candle" in signal
