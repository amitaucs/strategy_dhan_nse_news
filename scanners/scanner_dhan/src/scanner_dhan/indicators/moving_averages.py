"""Moving Average Indicators."""

from __future__ import annotations

import pandas as pd

__all__ = ["calculate_ema", "calculate_ema_series", "calculate_sma"]


def calculate_ema_series(series: pd.Series, span: int) -> pd.Series:
    """Calculate the full Exponential Moving Average (EMA) series."""
    return series.ewm(span=span, adjust=False).mean()


def calculate_ema(series: pd.Series, span: int) -> float | None:
    """Calculate the latest Exponential Moving Average (EMA)."""
    if len(series) < span:
        return None
    return float(round(calculate_ema_series(series, span).iloc[-1], 2))


def calculate_sma(series: pd.Series, window: int) -> float | None:
    """Calculate the latest Simple Moving Average (SMA)."""
    if len(series) < window:
        return None
    return float(round(series.rolling(window).mean().iloc[-1], 2))
