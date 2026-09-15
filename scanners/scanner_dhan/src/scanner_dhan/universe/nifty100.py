"""Nifty 100 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.fno import FNO_SECURITY_IDS
from scanner_dhan.universe.nifty50 import NIFTY_50_SECURITY_IDS, NIFTY_50_SYMBOLS

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_100_SYMBOLS",
    "NIFTY_100_SECURITY_IDS",
    "resolve_nifty100_securities",
]

# Nifty 50 + Nifty Next 50 (Top 100 Indian Equities)
NIFTY_NEXT_50_SYMBOLS: list[str] = [
    "ABB",
    "ADANIENSOL",
    "ADANIGREEN",
    "ADANIPOWER",
    "AMBUJACEM",
    "AUBANK",
    "BANKBARODA",
    "BERGEPAINT",
    "BOSCHLTD",
    "CANBK",
    "CHOLAFIN",
    "COLPAL",
    "DLF",
    "DMART",
    "GAIL",
    "GODREJCP",
    "HAL",
    "HAVELLS",
    "HDFCAMC",
    "INDIGO",
    "IRCTC",
    "IREDA",
    "JIOFIN",
    "JSWENERGY",
    "LICI",
    "LTIM",
    "MARICO",
    "MOTHERSON",
    "NAUKRI",
    "PIDILITIND",
    "PFC",
    "PNB",
    "POLYCAB",
    "RECLTD",
    "SBICARD",
    "SHREECEM",
    "SIEMENS",
    "SRF",
    "TATAPOWER",
    "TORNTPHARM",
    "TVSMOTOR",
    "UNITDSPR",
    "VBL",
    "VEDL",
    "ETERNAL",
    "ZYDUSLIFE",
    "ICICIGI",
    "ICICIPRULI",
    "INDHOTEL",
    "DIVISLAB",
]

NIFTY_100_SYMBOLS: list[str] = sorted(
    list(dict.fromkeys(NIFTY_50_SYMBOLS + NIFTY_NEXT_50_SYMBOLS))[:100]
)

# Built-in verified Dhan Security IDs for Nifty 100 stocks
NIFTY_100_SECURITY_IDS: dict[str, str] = {
    **NIFTY_50_SECURITY_IDS,
    "BERGEPAINT": "404",
    "IRCTC": "13611",
    "LTIM": "17818",
    "ETERNAL": "5097",
    **{k: v for k, v in FNO_SECURITY_IDS.items() if k in NIFTY_100_SYMBOLS},
}


def resolve_nifty100_securities(
    dhan_client: dhanhq | None = None,
    security_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Resolve Nifty 100 symbols to Dhan security IDs.

    Uses security master DataFrame if provided, falling back to
    built-in verified mappings.
    """
    resolved = dict(NIFTY_100_SECURITY_IDS)

    if security_df is not None and not security_df.empty:
        try:
            nse_eq = security_df[
                (security_df["SEM_EXM_EXCH_ID"] == "NSE")
                & (security_df["SEM_INSTRUMENT_NAME"] == "EQUITY")
                & (security_df["SEM_SERIES"] == "EQ")
            ]
            for sym in NIFTY_100_SYMBOLS:
                match = nse_eq[nse_eq["SEM_TRADING_SYMBOL"] == sym]
                if not match.empty:
                    resolved[sym] = str(match.iloc[0]["SEM_SMST_SECURITY_ID"])
            logger.info("Resolved %d Nifty 100 symbols from security master", len(resolved))
        except Exception as exc:
            logger.warning("Error parsing Nifty 100 security master: %s. Using fallback map.", exc)

    return resolved
