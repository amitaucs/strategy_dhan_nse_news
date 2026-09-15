"""Candlestick Pattern Detection."""

from __future__ import annotations

import pandas as pd

__all__ = ["identify_candlestick_patterns"]


def identify_candlestick_patterns(df: pd.DataFrame) -> str:
    """Identify key reversal and directional candlestick patterns."""
    if len(df) < 2:
        return ""

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    open_p, high_p = latest["open"], latest["high"]
    low_p, close_p = latest["low"], latest["close"]
    body = abs(close_p - open_p)
    total_range = high_p - low_p
    lower_wick = min(open_p, close_p) - low_p
    upper_wick = high_p - max(open_p, close_p)

    signals: list[str] = []

    if total_range > 0 and lower_wick >= 1.8 * max(body, 0.01) and upper_wick <= 0.3 * total_range:
        signals.append("Hammer / Pin Bar (Reversal)")
    elif (
        total_range > 0 and upper_wick >= 1.8 * max(body, 0.01) and lower_wick <= 0.3 * total_range
    ):
        signals.append("Shooting Star (Rejection)")
    elif close_p > open_p:
        signals.append("Bullish Green Candle")
    else:
        signals.append("Red Candle")

    if (
        prev["close"] < prev["open"]
        and close_p > open_p
        and close_p >= prev["open"]
        and open_p <= prev["close"]
    ):
        signals.append("Bullish Engulfing")

    return " | ".join(signals)
