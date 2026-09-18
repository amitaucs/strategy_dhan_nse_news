"""1-OTM Call Option Contract Selection and Monthly Expiry Resolver."""

from __future__ import annotations

import calendar
import datetime as dt
import logging
from typing import Any, Dict, List, Optional, Tuple

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.universe.manager import get_fno_lot_size, get_universe_manager, is_fno_stock
from st14_bullish_ce.models import St14OptionContract

logger = logging.getLogger(__name__)

__all__ = [
    "get_monthly_expiry_date",
    "resolve_target_expiry",
    "calculate_strike_interval",
    "resolve_otm1_strike",
    "resolve_1otm_ce_contract",
]


def get_monthly_expiry_date(year: int, month: int) -> dt.date:
    """Calculate the last Thursday of a given month and year (standard NSE F&O monthly expiry)."""
    last_day = calendar.monthrange(year, month)[1]
    last_date = dt.date(year, month, last_day)
    # Thursday is weekday 3 (Monday is 0)
    offset = (last_date.weekday() - 3) % 7
    expiry = last_date - dt.timedelta(days=offset)
    return expiry


def resolve_target_expiry(current_date: Optional[dt.date] = None) -> Tuple[dt.date, bool]:
    """Resolve target monthly expiry date based on the 15th-day rule.

    Rule:
      - If current date <= 15th of the month: Select Current Month Monthly Expiry.
      - If current date > 15th of the month: Select Next Month Monthly Expiry (Theta Shield).

    Returns:
        Tuple[dt.date, bool]: (target_expiry_date, is_next_month)
    """
    today = current_date or dt.date.today()

    if today.day <= 15:
        # Current Month Expiry
        expiry = get_monthly_expiry_date(today.year, today.month)
        # If current month's last Thursday has already passed (rare edge case on day 15), roll to next
        if expiry < today:
            next_month = 1 if today.month == 12 else today.month + 1
            next_year = today.year + 1 if today.month == 12 else today.year
            return get_monthly_expiry_date(next_year, next_month), True
        return expiry, False
    else:
        # Next Month Expiry
        next_month = 1 if today.month == 12 else today.month + 1
        next_year = today.year + 1 if today.month == 12 else today.year
        return get_monthly_expiry_date(next_year, next_month), True


def calculate_strike_interval(underlying_ltp: float) -> float:
    """Determine standard NSE stock option strike interval based on stock price tier."""
    price = abs(underlying_ltp)
    if price < 150:
        return 2.5
    elif price < 350:
        return 5.0
    elif price < 750:
        return 10.0
    elif price < 1500:
        return 20.0
    elif price < 3000:
        return 50.0
    elif price < 6000:
        return 100.0
    elif price < 12000:
        return 200.0
    else:
        return 500.0


def resolve_otm1_strike(
    underlying_ltp: float,
    available_strikes: Optional[List[float]] = None,
) -> Tuple[float, float]:
    """Resolve At-The-Money (ATM) and 1 Strike Out-Of-The-Money (OTM-1) for Call Option (CE).

    Returns:
        Tuple[float, float]: (atm_strike, otm1_strike)
    """
    if available_strikes and len(available_strikes) >= 2:
        sorted_strikes = sorted(available_strikes)
        # Find ATM: closest strike to LTP
        atm = min(sorted_strikes, key=lambda s: abs(s - underlying_ltp))
        atm_idx = sorted_strikes.index(atm)

        # 1 OTM for CE is the immediate next higher strike above ATM
        if atm_idx + 1 < len(sorted_strikes):
            otm1 = sorted_strikes[atm_idx + 1]
        else:
            interval = calculate_strike_interval(underlying_ltp)
            otm1 = atm + interval
        return atm, otm1

    # Standard formulaic fallback
    interval = calculate_strike_interval(underlying_ltp)
    atm = round(underlying_ltp / interval) * interval
    otm1 = atm + interval
    return float(atm), float(otm1)


def resolve_1otm_ce_contract(
    symbol: str,
    underlying_ltp: float,
    provider: Optional[DhanDataProvider] = None,
    current_date: Optional[dt.date] = None,
    available_strikes: Optional[List[float]] = None,
    mock_sec_id: Optional[str] = None,
    mock_lot_size: Optional[int] = None,
) -> Optional[St14OptionContract]:
    """Resolve full 1-OTM CE option contract for the underlying stock with date-based expiry.

    Returns:
        Optional[St14OptionContract]: Option contract details or None if symbol is not in active F&O.
    """
    # 1. Strict F&O Universe Gate
    if not mock_sec_id and not is_fno_stock(symbol):
        logger.warning("⛔ [Option Resolver] Symbol '%s' is not in the active NSE F&O universe. Disqualifying from option trades.", symbol)
        return None

    today = current_date or dt.date.today()
    expiry_dt, is_next_month = resolve_target_expiry(today)
    expiry_str = expiry_dt.strftime("%Y-%m-%d")
    expiry_label = expiry_dt.strftime("%d%b%y").upper()

    atm_strike, otm1_strike = resolve_otm1_strike(
        underlying_ltp=underlying_ltp,
        available_strikes=available_strikes,
    )

    option_symbol = f"{symbol} {expiry_label} {int(otm1_strike) if otm1_strike.is_integer() else otm1_strike} CE"

    # Fetch exact exchange lot size from universe manager
    lot_size = mock_lot_size or get_fno_lot_size(symbol, default=250)

    # Estimated option premium simulation (~1.5% - 2.5% of underlying for 1 OTM)
    simulated_ltp = round(underlying_ltp * 0.02, 2)
    sec_id = mock_sec_id or f"OPT_{symbol}_{int(otm1_strike)}_CE"
    is_synthetic = True

    dhan_prov = provider or DhanDataProvider()
    if dhan_prov.dhan:
        try:
            # Resolve underlying security ID on NSE_EQ
            mgr = get_universe_manager()
            under_sec_id = mgr._equity_sec_ids.get(symbol.upper())
            if not under_sec_id:
                under_sec_id = str(dhan_prov.resolve_security_id(symbol))

            if under_sec_id and str(under_sec_id) not in ("0", ""):
                # Query Dhan option chain
                resp = dhan_prov.dhan.option_chain(
                    under_security_id=int(under_sec_id),
                    under_exchange_segment="NSE_EQ",
                    expiry=expiry_str,
                )
                if isinstance(resp, dict) and resp.get("status") == "success" and "data" in resp:
                    oc_data = resp["data"].get("oc", {})
                    strike_key = f"{otm1_strike:.2f}"
                    if strike_key in oc_data:
                        ce_info = oc_data[strike_key].get("ce", {})
                        if "security_id" in ce_info and str(ce_info["security_id"]).isdigit():
                            sec_id = str(ce_info["security_id"])
                            if "last_price" in ce_info and float(ce_info["last_price"]) > 0:
                                simulated_ltp = float(ce_info["last_price"])
                                is_synthetic = False
        except Exception as exc:
            logger.debug("Option chain lookup fallback for %s: %s", symbol, exc)

    return St14OptionContract(
        symbol=option_symbol,
        underlying_symbol=symbol,
        strike_price=otm1_strike,
        option_type="CE",
        expiry_date=expiry_str,
        security_id=sec_id,
        lot_size=lot_size,
        ltp=simulated_ltp,
        is_next_month=is_next_month,
        is_synthetic=is_synthetic,
    )
