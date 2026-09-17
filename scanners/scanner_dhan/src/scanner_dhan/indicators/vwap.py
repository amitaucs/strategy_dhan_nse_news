"""Intraday Volume Weighted Average Price (VWAP) and Slope Calculation."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "calculate_intraday_vwap_series",
    "calculate_vwap_slope_and_angle",
]


def calculate_intraday_vwap_series(df: pd.DataFrame) -> pd.Series:
    """Calculate session-anchored Intraday Cumulative VWAP on OHLCV DataFrame.

    Typical Price = (High + Low + Close) / 3
    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)
    Anchors / resets at the start of each daily trading session (09:15 IST).
    """
    if df.empty or "close" not in df.columns or "high" not in df.columns or "low" not in df.columns:
        return pd.Series(dtype=float)

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    typical_price = (high + low + close) / 3.0

    if "volume" in df.columns:
        vol = df["volume"].astype(float).fillna(0.0)
    else:
        vol = pd.Series(1.0, index=df.index)

    # Detect session date groups for intraday resetting
    date_group = None
    if "timestamp" in df.columns:
        ts_col = df["timestamp"]
        if pd.api.types.is_datetime64_any_dtype(ts_col):
            date_group = ts_col.dt.date
        else:
            try:
                date_group = pd.to_datetime(ts_col).dt.date
            except Exception:
                date_group = None
    elif isinstance(df.index, pd.DatetimeIndex):
        date_group = df.index.date

    pv = typical_price * vol

    if date_group is not None:
        cum_pv = pv.groupby(date_group).cumsum()
        cum_vol = vol.groupby(date_group).cumsum()
        vwap = cum_pv / cum_vol.replace(0, np.nan)
    else:
        cum_pv = pv.cumsum()
        cum_vol = vol.cumsum()
        vwap = cum_pv / cum_vol.replace(0, np.nan)

    # Fallback to typical price or close if volume is zero
    return vwap.fillna(typical_price).fillna(close)


def calculate_vwap_slope_and_angle(
    vwap_series: pd.Series,
    lookback_bars: int = 2,
) -> tuple[float, float, bool]:
    """Calculate VWAP percentage slope, visual angle (degrees), and rising status.

    Returns:
        tuple[float, float, bool]:
            - slope_pct: Percentage change of VWAP over lookback
            - angle_deg: Visual chart angle in degrees [-90, +90] (target ~45 deg)
            - is_rising: True if VWAP is ascending (slope_pct >= 0)
    """
    valid_vwap = vwap_series.dropna()
    if len(valid_vwap) < 2:
        return 0.0, 0.0, True

    curr_vwap = float(valid_vwap.iloc[-1])
    # Compare with 1 to lookback bars prior
    idx_prev = max(0, len(valid_vwap) - 1 - lookback_bars)
    prev_vwap = float(valid_vwap.iloc[idx_prev])
    bars_diff = max(1, len(valid_vwap) - 1 - idx_prev)

    if prev_vwap <= 0 or curr_vwap <= 0:
        return 0.0, 0.0, True

    # Percentage change
    slope_pct = ((curr_vwap - prev_vwap) / prev_vwap) * 100.0
    slope_per_bar = slope_pct / bars_diff

    # Visual chart angle scaling:
    # A standard intraday 1H breakout trend has 0.2% - 1.0% change per bar,
    # which maps to ~30 to 60 degrees on visual candlesticks (centered around ~45 degrees).
    scaling_factor = 45.0  # 1% move per bar maps to 45 degrees
    normalized_rad = math.atan(slope_per_bar * (scaling_factor / 100.0) * 100.0)
    angle_deg = round(math.degrees(normalized_rad), 1)

    is_rising = slope_pct >= -0.05  # Allow flat to positive ascending

    return round(slope_pct, 2), angle_deg, is_rising

