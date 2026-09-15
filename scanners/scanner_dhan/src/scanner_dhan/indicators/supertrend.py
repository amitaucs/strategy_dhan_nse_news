"""Supertrend Indicator Calculation."""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["calculate_supertrend"]


def calculate_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """Calculate Supertrend indicator and trend direction.

    Returns a DataFrame with columns:
    - supertrend: float value of the current trailing stop level
    - is_green: bool, True if trend is bullish (price above supertrend), False if bearish
    - direction: int, 1 for bullish, -1 for bearish
    """
    if df.empty or len(df) < period:
        return pd.DataFrame(
            columns=["supertrend", "is_green", "direction"],
            index=df.index,
        )

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    # Calculate True Range (TR)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Average True Range (ATR) with exponential smoothing
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    n = len(df)
    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    supertrend = np.zeros(n)
    direction = np.zeros(n, dtype=int)  # 1 for bullish (green), -1 for bearish (red)

    # Initialize first bar
    final_upper[0] = basic_upper.iloc[0]
    final_lower[0] = basic_lower.iloc[0]
    direction[0] = 1
    supertrend[0] = final_lower[0]

    for i in range(1, n):
        # Upper band calculation
        if basic_upper.iloc[i] < final_upper[i - 1] or close.iloc[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper.iloc[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Lower band calculation
        if basic_lower.iloc[i] > final_lower[i - 1] or close.iloc[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower.iloc[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Trend direction and Supertrend value
        prev_dir = direction[i - 1]
        if prev_dir == 1:
            if close.iloc[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else:
            if close.iloc[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    is_green = direction == 1

    return pd.DataFrame(
        {
            "supertrend": supertrend,
            "is_green": is_green,
            "direction": direction,
        },
        index=df.index,
    )
