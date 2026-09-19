"""1-OTM Call Option Contract Selection and Active Expiry Resolver using DhanHQ APIs."""

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
    "resolve_target_expiry_from_list",
    "resolve_target_expiry",
    "calculate_strike_interval",
    "resolve_otm1_strike",
    "resolve_1otm_ce_contract",
]


def get_monthly_expiry_date(year: int, month: int) -> dt.date:
    """Calculate the last Tuesday of a given month and year (NSE stock derivatives standard since September 2025)."""
    last_day = calendar.monthrange(year, month)[1]
    last_date = dt.date(year, month, last_day)
    # Tuesday is weekday 1 (Monday is 0, Tuesday is 1)
    offset = (last_date.weekday() - 1) % 7
    expiry = last_date - dt.timedelta(days=offset)
    return expiry


def resolve_target_expiry_from_list(
    expiry_dates: List[str],
    current_date: Optional[dt.date] = None,
) -> Tuple[dt.date, bool]:
    """Select the target monthly expiry from active dates returned by DhanHQ expiry_list().

    Rule:
      - If current date <= 15th of the month: Select 1st Upcoming Monthly Expiry (Current Month).
      - If current date > 15th of the month: Select 2nd Upcoming Monthly Expiry (Next Month - Theta Shield).
    """
    today = current_date or dt.date.today()
    parsed_dates: List[dt.date] = []

    for d_str in expiry_dates:
        try:
            d_clean = str(d_str).strip()
            parsed_d = dt.datetime.strptime(d_clean, "%Y-%m-%d").date()
            if parsed_d >= today:
                parsed_dates.append(parsed_d)
        except Exception:
            continue

    parsed_dates = sorted(set(parsed_dates))

    if not parsed_dates:
        return resolve_target_expiry(today)

    if today.day <= 15:
        # Current Month Expiry (1st upcoming)
        return parsed_dates[0], False
    else:
        # Next Month Expiry (2nd upcoming, or 1st if only 1 exists)
        if len(parsed_dates) >= 2:
            return parsed_dates[1], True
        return parsed_dates[0], True


def resolve_target_expiry(current_date: Optional[dt.date] = None) -> Tuple[dt.date, bool]:
    """Resolve fallback monthly expiry date using last Tuesday when offline or unconfigured.

    Rule:
      - If current date <= 15th of the month: Select Current Month Monthly Expiry (Last Tuesday).
      - If current date > 15th of the month: Select Next Month Monthly Expiry (Theta Shield).
    """
    today = current_date or dt.date.today()

    if today.day <= 15:
        expiry = get_monthly_expiry_date(today.year, today.month)
        if expiry < today:
            next_month = 1 if today.month == 12 else today.month + 1
            next_year = today.year + 1 if today.month == 12 else today.year
            return get_monthly_expiry_date(next_year, next_month), True
        return expiry, False
    else:
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
        sorted_strikes = sorted(set(available_strikes))
        # Find ATM: closest strike to LTP
        atm = min(sorted_strikes, key=lambda s: abs(s - underlying_ltp))
        atm_idx = sorted_strikes.index(atm)

        # 1 OTM for CE is the immediate next higher strike above ATM
        if atm_idx + 1 < len(sorted_strikes):
            otm1 = sorted_strikes[atm_idx + 1]
        else:
            interval = calculate_strike_interval(underlying_ltp)
            otm1 = atm + interval
        return float(atm), float(otm1)

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
    """Resolve full 1-OTM CE option contract for the underlying stock with live Dhan expiry list & option chain.

    Returns:
        Optional[St14OptionContract]: Option contract details or None if symbol is not in active F&O.
    """
    # 1. Strict F&O Universe Gate
    if not mock_sec_id and not is_fno_stock(symbol):
        logger.warning("⛔ [Option Resolver] Symbol '%s' is not in the active NSE F&O universe. Disqualifying from option trades.", symbol)
        return None

    today = current_date or dt.date.today()
    dhan_prov = provider or DhanDataProvider()

    mgr = get_universe_manager()
    under_sec_id = mgr.get_security_id(symbol)
    if not under_sec_id and dhan_prov and hasattr(dhan_prov, "resolve_security_id"):
        under_sec_id = str(dhan_prov.resolve_security_id(symbol))

    # 2. Resolve Active Expiry Date via DhanHQ expiry_list() API
    expiry_dt: dt.date
    is_next_month: bool
    live_expiries: List[str] = []

    if dhan_prov and dhan_prov.dhan and under_sec_id and str(under_sec_id) not in ("0", ""):
        try:
            live_expiries = dhan_prov.fetch_expiry_list(under_security_id=under_sec_id)
        except Exception as exc:
            logger.debug("Error calling expiry_list for %s: %s", symbol, exc)

    if live_expiries:
        expiry_dt, is_next_month = resolve_target_expiry_from_list(live_expiries, today)
    else:
        expiry_dt, is_next_month = resolve_target_expiry(today)

    expiry_str = expiry_dt.strftime("%Y-%m-%d")
    expiry_label = expiry_dt.strftime("%d%b%y").upper()

    # 3. Query Real-Time Option Chain from DhanHQ
    chain_data: Dict[str, Any] = {}
    if dhan_prov and dhan_prov.dhan and under_sec_id and str(under_sec_id) not in ("0", ""):
        try:
            chain_data = dhan_prov.fetch_option_chain(
                under_security_id=under_sec_id,
                expiry=expiry_str,
            )
        except Exception as exc:
            logger.debug("Option chain lookup failed for %s: %s", symbol, exc)

    oc_entries = chain_data.get("oc", {}) if isinstance(chain_data, dict) else {}

    # Extract all real strikes from option chain if available
    chain_strikes: Optional[List[float]] = available_strikes
    if oc_entries:
        parsed_strikes: List[float] = []
        for k in oc_entries.keys():
            try:
                parsed_strikes.append(float(k))
            except (ValueError, TypeError):
                continue
        if parsed_strikes:
            chain_strikes = sorted(parsed_strikes)

    atm_strike, otm1_strike = resolve_otm1_strike(
        underlying_ltp=underlying_ltp,
        available_strikes=chain_strikes,
    )

    option_symbol = f"{symbol} {expiry_label} {int(otm1_strike) if otm1_strike.is_integer() else otm1_strike} CE"

    # Fetch exact exchange lot size from universe manager
    lot_size = mock_lot_size if mock_lot_size is not None else get_fno_lot_size(symbol, default=None)
    if not lot_size or lot_size <= 0:
        logger.warning("⛔ [Option Resolver] Unverified or missing lot size for %s in F&O master. Disqualifying contract.", symbol)
        return None

    # Resolve Security ID and Real-Time Premium
    simulated_ltp = round(underlying_ltp * 0.02, 2)
    sec_id = mock_sec_id or f"OPT_{symbol}_{int(otm1_strike)}_CE"
    is_synthetic = True

    if oc_entries:
        # Match strike in option chain data
        matched_strike_data = None
        for k, v in oc_entries.items():
            try:
                if abs(float(k) - otm1_strike) < 0.001:
                    matched_strike_data = v
                    break
            except (ValueError, TypeError):
                continue

        if isinstance(matched_strike_data, dict):
            ce_info = matched_strike_data.get("ce", {})
            if isinstance(ce_info, dict):
                cand_sec_id = str(ce_info.get("security_id", "")).strip()
                cand_price = ce_info.get("last_price")
                if cand_sec_id and cand_sec_id.isdigit():
                    sec_id = cand_sec_id
                    if cand_price is not None and float(cand_price) > 0:
                        simulated_ltp = float(cand_price)
                        is_synthetic = False

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
