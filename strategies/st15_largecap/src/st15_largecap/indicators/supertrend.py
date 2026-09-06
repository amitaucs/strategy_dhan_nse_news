"""SuperTrend indicator calculation module."""

from typing import List, Sequence, Tuple
from st15_largecap.core.models import Candle


def calculate_supertrend(
    candles: Sequence[Candle],
    period: int = 10,
    multiplier: float = 3.0,
) -> Tuple[List[float], List[bool]]:
    """Calculate SuperTrend indicator.
    
    Returns:
        (supertrend_values, is_green_list)
        where is_green_list is True for Bullish (Green) and False for Bearish (Red).
    """
    n = len(candles)
    if n == 0:
        return [], []

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]

    # 1. Calculate True Range (TR)
    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hpc, lpc)

    # 2. Calculate ATR (Wilder's Smoothing / RMA)
    atr = [0.0] * n
    if n >= period:
        # Initial ATR = Simple average of first `period` TRs
        atr[period - 1] = sum(tr[:period]) / period
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    else:
        # Fallback for short histories
        for i in range(n):
            atr[i] = sum(tr[:i + 1]) / (i + 1)

    # 3. Calculate Upper & Lower Basic Bands
    upper_basic = [0.0] * n
    lower_basic = [0.0] * n
    for i in range(n):
        hl2 = (highs[i] + lows[i]) / 2.0
        upper_basic[i] = hl2 + (multiplier * atr[i])
        lower_basic[i] = hl2 - (multiplier * atr[i])

    # 4. Calculate Final Bands & SuperTrend Line
    upper_final = [0.0] * n
    lower_final = [0.0] * n
    supertrend = [0.0] * n
    is_green = [True] * n

    for i in range(n):
        if i == 0:
            upper_final[i] = upper_basic[i]
            lower_final[i] = lower_basic[i]
            supertrend[i] = lower_basic[i]
            is_green[i] = closes[i] >= supertrend[i]
            continue

        # Final Lower Band
        if lower_basic[i] > lower_final[i - 1] or closes[i - 1] < lower_final[i - 1]:
            lower_final[i] = lower_basic[i]
        else:
            lower_final[i] = lower_final[i - 1]

        # Final Upper Band
        if upper_basic[i] < upper_final[i - 1] or closes[i - 1] > upper_final[i - 1]:
            upper_final[i] = upper_basic[i]
        else:
            upper_final[i] = upper_final[i - 1]

        # Direction determination
        prev_st = supertrend[i - 1]
        prev_green = is_green[i - 1]

        if prev_green:
            if closes[i] < lower_final[i]:
                # Flipped Bearish
                is_green[i] = False
                supertrend[i] = upper_final[i]
            else:
                is_green[i] = True
                supertrend[i] = lower_final[i]
        else:
            if closes[i] > upper_final[i]:
                # Flipped Bullish
                is_green[i] = True
                supertrend[i] = lower_final[i]
            else:
                is_green[i] = False
                supertrend[i] = upper_final[i]

    st_rounded = [round(v, 2) for v in supertrend]
    return st_rounded, is_green
