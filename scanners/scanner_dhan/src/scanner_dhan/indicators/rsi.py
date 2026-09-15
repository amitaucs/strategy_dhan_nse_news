"""Relative Strength Index (RSI) Calculation."""

from __future__ import annotations

import pandas as pd

__all__ = ["calculate_rsi", "calculate_rsi_series"]


def calculate_rsi_series(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate the full rolling RSI series using Wilder's smoothing method.

    Returns a pandas Series with index aligned to the input series.
    """
    if len(series) < period + 1:
        return pd.Series(index=series.index, dtype=float)

    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    rsi_values: list[float] = [float("nan")] * len(series)

    # First simple average over `period`
    avg_gain = float(gain.iloc[1 : period + 1].mean())
    avg_loss = float(loss.iloc[1 : period + 1].mean())

    if avg_loss == 0.0:
        first_rsi = 100.0 if avg_gain > 0.0 else 50.0
    else:
        rs = avg_gain / avg_loss
        first_rsi = 100.0 - (100.0 / (1.0 + rs))

    rsi_values[period] = round(first_rsi, 2)

    # Wilder's exponential smoothing
    for i in range(period + 1, len(series)):
        g = float(gain.iloc[i])
        l_val = float(loss.iloc[i])
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l_val) / period

        if avg_loss == 0.0:
            val = 100.0 if avg_gain > 0.0 else 50.0
        else:
            rs = avg_gain / avg_loss
            val = 100.0 - (100.0 / (1.0 + rs))
        rsi_values[i] = round(val, 2)

    return pd.Series(rsi_values, index=series.index)


def calculate_rsi(series: pd.Series, period: int = 14) -> float | None:
    """Calculate the latest RSI value using Wilder's smoothing method."""
    rsi_s = calculate_rsi_series(series, period=period)
    if rsi_s.empty:
        return None
    latest = rsi_s.iloc[-1]
    return float(latest) if pd.notna(latest) else None
