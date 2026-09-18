"""Mock candle fixtures strictly for offline unit tests and test suites."""

from datetime import datetime, time, timedelta
from typing import List, Optional
import zlib

from st15_largecap.core.models import Candle


def generate_mock_2h_candles(
    symbol: str = "TCS",
    base_price: Optional[float] = None,
    num_candles: int = 250,
    bullish_trend: Optional[bool] = None,
    pullback_at_end: Optional[bool] = None,
) -> List[Candle]:
    """Generate realistic synthetic 2H candles strictly for unit testing and test fixtures."""
    candles: List[Candle] = []
    num_candles = max(10, num_candles)
    current_time = datetime.now() - timedelta(days=num_candles // 3 + 10)

    sym_clean = (symbol or "STOCK").upper().strip()
    hash_val = zlib.crc32(sym_clean.encode("utf-8"))

    # Specific known profiles for realistic simulation
    if sym_clean in ("AXISBANK", "BANDHANBNK", "INDUSINDBK", "KOTAKBANK"):
        if bullish_trend is None:
            bullish_trend = False  # Bearish downtrend where 200 EMA > 50 EMA > 20 EMA
        if pullback_at_end is None:
            pullback_at_end = False
        if base_price is None:
            base_price = 1180.0 if sym_clean == "AXISBANK" else 1750.0

    if base_price is None:
        # Deterministic distinct price based on symbol name
        base_price = round(200.0 + (hash_val % 3800) + ((hash_val % 99) * 0.1), 2)

    if bullish_trend is None:
        # ~60% bullish, ~40% bearish across universe
        bullish_trend = (hash_val % 10) < 6

    if pullback_at_end is None:
        # ~20% currently triggering a qualified bounce after dip
        pullback_at_end = bullish_trend and ((hash_val % 10) in (0, 1))

    # Determine the target end date (today, or Friday if today is weekend)
    target_end_date = datetime.now().date()
    while target_end_date.weekday() >= 5:
        target_end_date -= timedelta(days=1)

    slots = [time(9, 15), time(11, 15), time(13, 15)]
    num_days = (num_candles + len(slots) - 1) // len(slots)
    start_date = target_end_date
    days_counted = 0
    while days_counted < num_days:
        start_date -= timedelta(days=1)
        if start_date.weekday() < 5:
            days_counted += 1

    current_time = datetime.combine(start_date, time(0, 0))
    current_price = base_price
    slot_idx = 0

    for i in range(num_candles):
        while current_time.weekday() >= 5:  # Skip weekends
            current_time += timedelta(days=1)

        candle_time = datetime.combine(current_time.date(), slots[slot_idx])
        slot_idx += 1
        if slot_idx >= len(slots):
            slot_idx = 0
            current_time += timedelta(days=1)

        # Price progression
        if bullish_trend:
            if pullback_at_end and num_candles - 4 <= i < num_candles - 1:
                drift = -0.003
            elif pullback_at_end and i == num_candles - 1:
                drift = 0.015
            else:
                drift = 0.002
        else:
            drift = -0.002

        o = current_price
        c = o * (1.0 + drift)
        h = max(o, c) * 1.004
        l = min(o, c) * 0.996
        v = 100000.0 + (i * 500.0)

        candles.append(
            Candle(
                timestamp=candle_time,
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
                volume=round(v, 2),
                is_synthetic=True,
            )
        )
        current_price = c

    return candles

