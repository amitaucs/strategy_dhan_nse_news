"""Heikin Ashi Candlestick Calculation."""

from __future__ import annotations

import pandas as pd

__all__ = ["calculate_heikin_ashi"]


def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Heikin Ashi candles from a standard OHLC DataFrame.

    Returns a DataFrame with columns:
    - ha_open
    - ha_high
    - ha_low
    - ha_close
    - is_green (bool: True if ha_close > ha_open)
    """
    if df.empty or len(df) == 0:
        return pd.DataFrame(columns=["ha_open", "ha_high", "ha_low", "ha_close", "is_green"])

    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0

    ha_open: list[float] = [(float(df["open"].iloc[0]) + float(df["close"].iloc[0])) / 2.0]
    for i in range(1, len(df)):
        prev_open = ha_open[-1]
        prev_close = float(ha_close.iloc[i - 1])
        ha_open.append((prev_open + prev_close) / 2.0)

    ha_open_series = pd.Series(ha_open, index=df.index)

    ha_high = pd.concat([df["high"], ha_open_series, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([df["low"], ha_open_series, ha_close], axis=1).min(axis=1)
    is_green = ha_close > ha_open_series

    return pd.DataFrame(
        {
            "ha_open": ha_open_series,
            "ha_high": ha_high,
            "ha_low": ha_low,
            "ha_close": ha_close,
            "is_green": is_green,
        },
        index=df.index,
    )
