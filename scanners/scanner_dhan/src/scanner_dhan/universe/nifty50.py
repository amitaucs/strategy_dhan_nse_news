"""Nifty 50 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_50_SYMBOLS",
    "NIFTY_50_SECURITY_IDS",
    "resolve_nifty50_securities",
]

# Standard 50 constituents of Nifty 50 Index (NSE Trading Symbols)
NIFTY_50_SYMBOLS: list[str] = [
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJFINANCE",
    "BAJAJFINSV",
    "BEL",
    "BHARTIARTL",
    "BPCL",
    "BRITANNIA",
    "CIPLA",
    "COALINDIA",
    "DRREDDY",
    "EICHERMOT",
    "GRASIM",
    "HCLTECH",
    "HDFCBANK",
    "HDFCLIFE",
    "HEROMOTOCO",
    "HINDALCO",
    "HINDUNILVR",
    "ICICIBANK",
    "INDUSINDBK",
    "INFY",
    "ITC",
    "JSWSTEEL",
    "KOTAKBANK",
    "LT",
    "M&M",
    "MARUTI",
    "NESTLEIND",
    "NTPC",
    "ONGC",
    "POWERGRID",
    "RELIANCE",
    "SBILIFE",
    "SBIN",
    "SHRIRAMFIN",
    "SUNPHARMA",
    "TATACONSUM",
    "TATAMOTORS",
    "TATASTEEL",
    "TCS",
    "TECHM",
    "TITAN",
    "TRENT",
    "ULTRACEMCO",
    "WIPRO",
]

# Built-in high-stability NSE Equity security_id mapping for Nifty 50 stocks
NIFTY_50_SECURITY_IDS: dict[str, str] = {
    "ADANIENT": "25",
    "ADANIPORTS": "15083",
    "APOLLOHOSP": "157",
    "ASIANPAINT": "236",
    "AXISBANK": "5900",
    "BAJAJ-AUTO": "16669",
    "BAJFINANCE": "317",
    "BAJAJFINSV": "16675",
    "BEL": "383",
    "BHARTIARTL": "10604",
    "BPCL": "526",
    "BRITANNIA": "547",
    "CIPLA": "694",
    "COALINDIA": "20374",
    "DRREDDY": "881",
    "EICHERMOT": "910",
    "GRASIM": "1232",
    "HCLTECH": "7229",
    "HDFCBANK": "1333",
    "HDFCLIFE": "467",
    "HEROMOTOCO": "1348",
    "HINDALCO": "1363",
    "HINDUNILVR": "1394",
    "ICICIBANK": "4963",
    "INDUSINDBK": "5258",
    "INFY": "1594",
    "ITC": "1660",
    "JSWSTEEL": "11723",
    "KOTAKBANK": "1922",
    "LT": "11483",
    "M&M": "2031",
    "MARUTI": "10999",
    "NESTLEIND": "17963",
    "NTPC": "11630",
    "ONGC": "2475",
    "POWERGRID": "14977",
    "RELIANCE": "2885",
    "SBILIFE": "21808",
    "SBIN": "3045",
    "SHRIRAMFIN": "4306",
    "SUNPHARMA": "3351",
    "TATACONSUM": "3432",
    "TATAMOTORS": "3456",
    "TATASTEEL": "3499",
    "TCS": "11536",
    "TECHM": "13538",
    "TITAN": "3506",
    "TRENT": "1964",
    "ULTRACEMCO": "11532",
    "WIPRO": "3787",
}


def resolve_nifty50_securities(
    dhan_client: dhanhq | None = None,
    security_df: pd.DataFrame | None = None,
) -> dict[str, str]:
    """Resolve Nifty 50 symbols to Dhan security IDs.

    Uses security master DataFrame if provided or fetchable, falling back to
    built-in mappings.
    """
    resolved = dict(NIFTY_50_SECURITY_IDS)

    if security_df is not None and not security_df.empty:
        try:
            nse_eq = security_df[
                (security_df["SEM_EXM_EXCH_ID"] == "NSE")
                & (security_df["SEM_INSTRUMENT_NAME"] == "EQUITY")
            ]
            for sym in NIFTY_50_SYMBOLS:
                match = nse_eq[nse_eq["SEM_TRADING_SYMBOL"] == sym]
                if not match.empty:
                    resolved[sym] = str(match.iloc[0]["SEM_SMST_SECURITY_ID"])
            logger.info("Resolved %d Nifty 50 symbols from security master", len(resolved))
        except Exception as exc:
            logger.warning("Error parsing security master DataFrame: %s. Using fallback map.", exc)

    return resolved
