"""Unit tests for Supertrend calculation."""

from __future__ import annotations

import pandas as pd

from scanner_dhan.indicators.supertrend import calculate_supertrend


def test_calculate_supertrend_empty() -> None:
    """Test Supertrend with empty or insufficient data."""
    df = pd.DataFrame(columns=["open", "high", "low", "close"])
    st = calculate_supertrend(df, period=10, multiplier=3.0)
    assert st.empty


def test_calculate_supertrend_trend_detection() -> None:
    """Test Supertrend detects bullish (green) and bearish trends."""
    # Strongly rising price series
    prices = [100.0 + i * 2.0 for i in range(30)]
    df_uptrend = pd.DataFrame(
        {
            "open": [p - 1.0 for p in prices],
            "high": [p + 2.0 for p in prices],
            "low": [p - 2.0 for p in prices],
            "close": prices,
        }
    )
    st_up = calculate_supertrend(df_uptrend, period=10, multiplier=3.0)
    assert len(st_up) == 30
    assert st_up["is_green"].iloc[-1]
    assert st_up["direction"].iloc[-1] == 1
    assert st_up["supertrend"].iloc[-1] < prices[-1]
