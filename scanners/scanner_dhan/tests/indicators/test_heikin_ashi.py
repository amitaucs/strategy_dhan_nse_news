"""Unit tests for Heikin Ashi candlestick calculations."""

from __future__ import annotations

import pandas as pd

from scanner_dhan.indicators.heikin_ashi import calculate_heikin_ashi


def test_calculate_heikin_ashi_empty() -> None:
    """Test Heikin Ashi with empty dataframe."""
    df = pd.DataFrame(columns=["open", "high", "low", "close"])
    ha = calculate_heikin_ashi(df)
    assert ha.empty
    assert "ha_open" in ha.columns
    assert "ha_close" in ha.columns


def test_calculate_heikin_ashi_bullish_bearish() -> None:
    """Test green and red Heikin Ashi candles."""
    # Bullish candles
    df_bullish = pd.DataFrame(
        {
            "open": [100.0, 105.0, 110.0, 115.0],
            "high": [106.0, 112.0, 118.0, 122.0],
            "low": [99.0, 104.0, 109.0, 114.0],
            "close": [105.0, 110.0, 115.0, 120.0],
        }
    )
    ha_bullish = calculate_heikin_ashi(df_bullish)
    assert len(ha_bullish) == 4
    # After first candle initialization, candles are green
    assert ha_bullish["is_green"].iloc[1:].all()

    # Bearish candles
    df_bearish = pd.DataFrame(
        {
            "open": [120.0, 115.0, 110.0, 105.0],
            "high": [122.0, 116.0, 111.0, 106.0],
            "low": [114.0, 109.0, 104.0, 99.0],
            "close": [115.0, 110.0, 105.0, 100.0],
        }
    )
    ha_bearish = calculate_heikin_ashi(df_bearish)
    assert len(ha_bearish) == 4
    # In falling market, ha_close < ha_open
    assert not ha_bearish["is_green"].iloc[-1]
