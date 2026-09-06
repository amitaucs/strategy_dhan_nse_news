"""Exponential Moving Average (EMA) calculations and alignment checks."""

from typing import Dict, List, Sequence, Tuple
import pandas as pd


def calculate_ema(prices: Sequence[float], span: int) -> List[float]:
    """Calculate Exponential Moving Average (EMA) for a sequence of prices."""
    if not prices or span <= 0:
        return []

    series = pd.Series(prices)
    ema_series = series.ewm(span=span, adjust=False).mean()
    return [round(float(v), 2) for v in ema_series.tolist()]


def calculate_triple_ema(
    close_prices: Sequence[float],
    fast_span: int = 20,
    mid_span: int = 50,
    slow_span: int = 200,
) -> Dict[str, List[float]]:
    """Compute 20, 50, and 200 EMAs for close prices."""
    return {
        "ema_20": calculate_ema(close_prices, span=fast_span),
        "ema_50": calculate_ema(close_prices, span=mid_span),
        "ema_200": calculate_ema(close_prices, span=slow_span),
    }


def is_ema_stacked_bullish(ema_20: float, ema_50: float, ema_200: float) -> bool:
    """Check if EMAs are stacked bullishly: 20 EMA > 50 EMA > 200 EMA."""
    if ema_20 <= 0 or ema_50 <= 0 or ema_200 <= 0:
        return False
    return ema_20 > ema_50 > ema_200


def check_ema_proximity(
    low: float,
    high: float,
    close: float,
    ema_20: float,
    ema_50: float,
    ema_200: float,
    tolerance_pct: float = 0.5,
) -> Tuple[bool, str, float]:
    """Check if price has pulled back near or is touching/kissing any of the 3 EMAs.
    
    Returns:
        (is_in_dip, nearest_ema_name, min_distance_pct)
    """
    emas = [
        ("EMA_20", ema_20),
        ("EMA_50", ema_50),
        ("EMA_200", ema_200),
    ]

    min_dist = float("inf")
    nearest_name = ""

    for name, ema_val in emas:
        if ema_val <= 0:
            continue

        # If candle body/wicks cross or touch the EMA line directly:
        if low <= ema_val <= high:
            dist_pct = 0.0
        else:
            # Distance from low (pullback from above) or close/high
            dist_pts = min(abs(low - ema_val), abs(close - ema_val), abs(high - ema_val))
            dist_pct = (dist_pts / ema_val) * 100.0

        if dist_pct < min_dist:
            min_dist = dist_pct
            nearest_name = name

    if min_dist == float("inf"):
        return False, "", 999.0

    is_in_dip = min_dist <= tolerance_pct
    return is_in_dip, nearest_name, round(min_dist, 3)
