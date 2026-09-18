"""Next-Candle Breakout High Trigger Confirmation Evaluator."""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from scanner_dhan.data.dhan_provider import DhanDataProvider

logger = logging.getLogger(__name__)

__all__ = ["check_breakout_candle_cross"]


def check_breakout_candle_cross(
    symbol: str,
    sec_id: str,
    breakout_candle_high: float,
    current_ltp: Optional[float] = None,
    provider: Optional[DhanDataProvider] = None,
) -> Tuple[bool, float, str]:
    """Check if the subsequent candle / live price has breached the 1H Breakout Candle High.

    Rule:
      Trigger fires when live LTP > Breakout Candle High (H_breakout).

    Returns:
        Tuple[bool, float, str]:
            - is_crossed: True if LTP > breakout_candle_high
            - live_ltp: Current LTP checked
            - message: Status message describing the trigger state
    """
    ltp = None
    dhan_prov = provider or DhanDataProvider()
    if dhan_prov.dhan and sec_id:
        try:
            ltp_map = dhan_prov.fetch_ltp_batch([sec_id])
            if sec_id in ltp_map and ltp_map[sec_id] > 0:
                ltp = ltp_map[sec_id]
        except Exception as exc:
            logger.debug("Error fetching live LTP for %s: %s", symbol, exc)

    if ltp is None or ltp <= 0:
        ltp = current_ltp

    if ltp is None or ltp <= 0:
        return False, 0.0, f"⏳ Pending Trigger: Live price unavailable for {symbol} (Breakout High: ₹{breakout_candle_high:,.2f})"

    is_crossed = ltp > breakout_candle_high

    if is_crossed:
        diff_pct = ((ltp - breakout_candle_high) / breakout_candle_high) * 100.0
        msg = f"🟢 Breakout Confirmed: LTP ₹{ltp:,.2f} crossed Breakout High ₹{breakout_candle_high:,.2f} (+{diff_pct:.2f}%)"
    else:
        diff_pct = ((breakout_candle_high - ltp) / breakout_candle_high) * 100.0
        msg = f"⏳ Pending Trigger: LTP ₹{ltp:,.2f} below Breakout High ₹{breakout_candle_high:,.2f} (-{diff_pct:.2f}%)"

    return is_crossed, ltp, msg

