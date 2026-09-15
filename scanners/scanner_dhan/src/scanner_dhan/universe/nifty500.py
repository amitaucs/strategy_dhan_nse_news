"""Nifty 500 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.fno import FNO_SECURITY_IDS, FNO_SYMBOLS
from scanner_dhan.universe.nifty50 import NIFTY_50_SECURITY_IDS, NIFTY_50_SYMBOLS
from scanner_dhan.universe.nifty100 import NIFTY_100_SECURITY_IDS, NIFTY_100_SYMBOLS
from scanner_dhan.universe.nifty_smallcap100 import (
    NIFTY_SMALLCAP_100_SECURITY_IDS,
    NIFTY_SMALLCAP_100_SYMBOLS,
)

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_500_SYMBOLS",
    "NIFTY_500_SECURITY_IDS",
    "resolve_nifty500_securities",
]

# Combined broad-market universe symbols
# (Nifty 100 + Nifty Smallcap 100 + F&O + Major Nifty 500 Midcaps)
_NIFTY_500_BASE: list[str] = sorted(
    list(
        set(
            NIFTY_50_SYMBOLS
            + NIFTY_100_SYMBOLS
            + NIFTY_SMALLCAP_100_SYMBOLS
            + FNO_SYMBOLS
            + [
                "AARTIIND",
                "ABBOTINDIA",
                "ABCAPITAL",
                "ABFRL",
                "ACC",
                "AJANTPHARM",
                "ALKEM",
                "APLLTD",
                "ASHOKLEY",
                "ASTRAL",
                "ATUL",
                "AUBANK",
                "AUROPHARMA",
                "BALKRISIND",
                "BALRAMCHIN",
                "BANDHANBNK",
                "BATAINDIA",
                "BEL",
                "BHARATFORG",
                "BHEL",
                "BIOCON",
                "BSOFT",
                "CANFINHOME",
                "CHAMBLFERT",
                "COFORGE",
                "CONCOR",
                "COROMANDEL",
                "CROMPTON",
                "CUB",
                "DALBHARAT",
                "DEEPAKNTR",
                "DELHIVERY",
                "DIXON",
                "ESCORTS",
                "EXIDEIND",
                "FEDERALBNK",
                "GLENMARK",
                "GMRINFRA",
                "GNFC",
                "GODREJPROP",
                "GRANULES",
                "GUJGASLTD",
                "HDFCAMC",
                "HINDPETRO",
                "IBULHSGFIN",
                "IDFC",
                "IDFCFIRSTB",
                "IEX",
                "IGL",
                "INDHOTEL",
                "INDIACEM",
                "INDUSTOWER",
                "IPCALAB",
                "JINDALSTEL",
                "JKCEMENT",
                "JUBLFOOD",
                "LALPATHLAB",
                "LAURUSLABS",
                "LICHSGFIN",
                "LUPIN",
                "MANAPPURAM",
                "MARICO",
                "MCDOWELL-N",
                "MCX",
                "METROPOLIS",
                "MFSL",
                "MGL",
                "MPHASIS",
                "MRF",
                "MUTHOOTFIN",
                "NATIONALUM",
                "NAUKRI",
                "NAVINFLUOR",
                "NMDC",
                "OBEROIRLTY",
                "OFSS",
                "PAGEIND",
                "PEL",
                "PERSISTENT",
                "PETRONET",
                "PFC",
                "PIDILITIND",
                "PIIND",
                "PNB",
                "POLYCAB",
                "PVRINOX",
                "RAMCOCEM",
                "RBLBANK",
                "RECLTD",
                "SAIL",
                "SBICARD",
                "SRF",
                "SUNTV",
                "SYNGENE",
                "TATACHEM",
                "TATACOMM",
                "TATAPOWER",
                "TRENT",
                "TVSMOTOR",
                "UBL",
                "VOLTAS",
                "ZEEL",
                "ZYDUSLIFE",
            ]
        )
    )
)

NIFTY_500_SYMBOLS: list[str] = _NIFTY_500_BASE

# Pre-mapped security IDs combining F&O, Nifty 100, Nifty 50, and Smallcap 100
NIFTY_500_SECURITY_IDS: dict[str, str] = {
    **NIFTY_50_SECURITY_IDS,
    **NIFTY_100_SECURITY_IDS,
    **NIFTY_SMALLCAP_100_SECURITY_IDS,
    **FNO_SECURITY_IDS,
}


def resolve_nifty500_securities(
    dhan_client: dhanhq | None = None,
    security_list_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Resolve security IDs for Nifty 500 symbols using Dhan master or fallback maps."""
    resolved = dict(NIFTY_500_SECURITY_IDS)

    if security_list_df is not None and not security_list_df.empty:
        try:
            df = security_list_df
            sym_col = next((c for c in df.columns if "symbol" in c.lower()), None)
            id_col = next(
                (c for c in df.columns if "security" in c.lower() or "id" in c.lower()), None
            )
            if sym_col and id_col:
                for sym in NIFTY_500_SYMBOLS:
                    match = df[df[sym_col].str.upper() == sym.upper()]
                    if not match.empty:
                        resolved[sym] = str(match.iloc[0][id_col])
        except Exception as exc:
            logger.warning("Error resolving Nifty 500 security IDs from DF: %s", exc)

    return resolved
