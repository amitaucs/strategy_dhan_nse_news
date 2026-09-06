"""Swing low calculation module for protective stop-loss placement."""

from typing import Sequence
from st15_largecap.core.models import Candle


def calculate_swing_low(
    candles: Sequence[Candle],
    lookback: int = 6,
    buffer_pct: float = 0.1,
) -> float:
    """Find the lowest price in the last `lookback` candles with a minor safety buffer.
    
    Args:
        candles: Sequence of recent candles.
        lookback: Number of past candles to inspect for local trough.
        buffer_pct: Percentage buffer placed below the lowest low (default 0.1%).
    """
    if not candles:
        return 0.0

    recent_candles = candles[-lookback:] if len(candles) >= lookback else candles
    lowest_val = min(c.low for c in recent_candles)

    # Apply safety buffer
    sl_with_buffer = lowest_val * (1.0 - (buffer_pct / 100.0))
    return round(sl_with_buffer, 2)
