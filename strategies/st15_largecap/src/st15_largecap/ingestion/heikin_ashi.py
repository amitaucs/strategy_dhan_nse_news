"""Heikin Ashi transformation engine for price candles."""

from typing import List, Optional
from st15_largecap.core.models import Candle, HeikinAshiCandle


def calculate_heikin_ashi(candles: List[Candle]) -> List[HeikinAshiCandle]:
    """Convert a sequence of standard OHLC candles into Heikin Ashi candles.
    
    Formula:
      HA_Close = (Open + High + Low + Close) / 4
      HA_Open = (HA_Open_prev + HA_Close_prev) / 2  (for first candle: (Open + Close) / 2)
      HA_High = max(High, HA_Open, HA_Close)
      HA_Low = min(Low, HA_Open, HA_Close)
    """
    if not candles:
        return []

    ha_candles: List[HeikinAshiCandle] = []

    for i, c in enumerate(candles):
        ha_close = (c.open + c.high + c.low + c.close) / 4.0

        if i == 0:
            ha_open = (c.open + c.close) / 2.0
        else:
            prev_ha = ha_candles[-1]
            ha_open = (prev_ha.open + prev_ha.close) / 2.0

        ha_high = max(c.high, ha_open, ha_close)
        ha_low = min(c.low, ha_open, ha_close)

        ha_candles.append(
            HeikinAshiCandle(
                timestamp=c.timestamp,
                open=round(ha_open, 2),
                high=round(ha_high, 2),
                low=round(ha_low, 2),
                close=round(ha_close, 2),
                raw_candle=c,
            )
        )

    return ha_candles

