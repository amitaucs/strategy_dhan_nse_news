"""Average True Range (ATR) and Volume Moving Average Indicators."""

from __future__ import annotations

import pandas as pd

__all__ = ["calculate_atr", "calculate_volume_sma"]


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Wilder's Average True Range (ATR) series.

    Returns a pandas Series indexed to df.
    """
    if df.empty or len(df) < period:
        return pd.Series(0.0, index=df.index, dtype=float)

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's exponential smoothing (alpha = 1 / period)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr


def calculate_volume_sma(series: pd.Series, window: int = 20) -> pd.Series:
    """Calculate Simple Moving Average of Volume."""
    if len(series) < window:
        return series.rolling(len(series), min_periods=1).mean()
    return series.rolling(window, min_periods=1).mean()
