"""Floor & Standard Pivot Point Calculations."""

from __future__ import annotations

import pandas as pd

__all__ = ["calculate_floor_pivots"]


def calculate_floor_pivots(
    df: pd.DataFrame,
    lookback_window: int = 25,
) -> dict[str, float]:
    """Calculate Classic Floor Pivot Points (Pivot, S1, S2, R1, R2)."""
    if len(df) < 5 or "high" not in df or "low" not in df or "close" not in df:
        return {}

    window_df = df.iloc[-lookback_window:-1] if len(df) >= lookback_window else df.iloc[:-1]
    high = float(window_df["high"].max())
    low = float(window_df["low"].min())
    close = float(window_df["close"].iloc[-1])

    pivot = (high + low + close) / 3.0
    s1 = (2.0 * pivot) - high
    s2 = pivot - (high - low)
    r1 = (2.0 * pivot) - low
    r2 = pivot + (high - low)

    return {
        "pivot": round(pivot, 2),
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2),
    }
