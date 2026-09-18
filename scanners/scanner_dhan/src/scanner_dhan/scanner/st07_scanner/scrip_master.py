"""Dhan Scrip Master CSV Loader and Caching Utility."""

from __future__ import annotations

import logging
import os
import ssl
import time
import urllib.request
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

__all__ = ["load_dhan_scrip_master", "get_nse_equity_symbols_map"]

DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-compact.csv"
CACHE_DIR = Path.home() / ".cache" / "scanner_dhan"
CACHE_FILE = CACHE_DIR / "api-scrip-master-compact.csv"
CACHE_MAX_AGE_SECONDS = 86400  # 24 hours


def _get_ssl_context() -> ssl.SSLContext:
    """Create a verified SSL context using certifi or system root certificates."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    return ssl.create_default_context()


def load_dhan_scrip_master(force_refresh: bool = False) -> pd.DataFrame:
    """Load Dhan Scrip Master CSV with 24-hour local disk cache.

    Falls back safely if network or download fails.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Check local cache
    if not force_refresh and CACHE_FILE.exists():
        file_age = time.time() - os.path.getmtime(CACHE_FILE)
        if file_age < CACHE_MAX_AGE_SECONDS:
            try:
                df = pd.read_csv(CACHE_FILE, low_memory=False)
                if not df.empty:
                    return df
            except Exception as exc:
                logger.debug("Failed to read cached scrip master: %s", exc)

    # Attempt download
    try:
        req = urllib.request.Request(
            DHAN_SCRIP_MASTER_URL,
            headers={"User-Agent": "DhanHQ-ST07-Scanner/1.0"},
        )
        ctx = _get_ssl_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            content = resp.read()

        with open(CACHE_FILE, "wb") as f:
            f.write(content)
        df = pd.read_csv(CACHE_FILE, low_memory=False)
        return df
    except Exception as exc:
        logger.debug(
            "Could not download Dhan scrip master from web: %s. Using local cache/fallbacks.",
            exc,
        )
        if CACHE_FILE.exists():
            try:
                return pd.read_csv(CACHE_FILE, low_memory=False)
            except Exception:
                pass

    return pd.DataFrame()


def get_nse_equity_symbols_map() -> dict[str, str]:
    """Extract a dictionary of {SYMBOL: SECURITY_ID} for NSE Equity scrips."""
    df = load_dhan_scrip_master()
    if df.empty:
        return {}

    try:
        # Standard Dhan scrip master column headers:
        # SEM_EXM_EXCH_ID: 'NSE', SEM_SEGMENT: 'E', SEM_SMST_SECURITY_ID, SEM_TRADING_SYMBOL
        cols = {c.upper(): c for c in df.columns}
        exch_col = cols.get("SEM_EXM_EXCH_ID") or cols.get("EXCH_ID")
        seg_col = cols.get("SEM_SEGMENT") or cols.get("SEGMENT")
        id_col = cols.get("SEM_SMST_SECURITY_ID") or cols.get("SECURITY_ID")
        sym_col = cols.get("SEM_TRADING_SYMBOL") or cols.get("TRADING_SYMBOL") or cols.get("SYMBOL")

        if exch_col and id_col and sym_col:
            nse_df = df[df[exch_col].astype(str).str.upper() == "NSE"]
            if seg_col:
                nse_df = nse_df[nse_df[seg_col].astype(str).str.upper().isin(["E", "EQ", "EQUITY"])]

            mapping: dict[str, str] = {}
            for _, row in nse_df.iterrows():
                raw_sym = str(row[sym_col]).strip().upper()
                raw_id = str(row[id_col]).strip()
                if raw_sym.endswith("-EQ"):
                    raw_sym = raw_sym[:-3]
                if raw_sym and raw_id:
                    mapping[raw_sym] = raw_id
            return mapping
    except Exception as exc:
        logger.warning("Error parsing NSE equity symbols from Dhan scrip master: %s", exc)

    return {}
