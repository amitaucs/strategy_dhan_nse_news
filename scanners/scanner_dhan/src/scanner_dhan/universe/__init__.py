"""Stock universe definitions and security ID resolution."""

from __future__ import annotations

import os

from scanner_dhan.universe.fno import (
    FNO_SECURITY_IDS,
    FNO_SYMBOLS,
    resolve_fno_securities,
)
from scanner_dhan.universe.nifty50 import (
    NIFTY_50_SECURITY_IDS,
    NIFTY_50_SYMBOLS,
    resolve_nifty50_securities,
)
from scanner_dhan.universe.nifty100 import (
    NIFTY_100_SECURITY_IDS,
    NIFTY_100_SYMBOLS,
    resolve_nifty100_securities,
)
from scanner_dhan.universe.nifty500 import (
    NIFTY_500_SECURITY_IDS,
    NIFTY_500_SYMBOLS,
    resolve_nifty500_securities,
)
from scanner_dhan.universe.nifty_smallcap100 import (
    NIFTY_SMALLCAP_100_SECURITY_IDS,
    NIFTY_SMALLCAP_100_SYMBOLS,
    resolve_nifty_smallcap100_securities,
)

__all__ = [
    "NIFTY_50_SECURITY_IDS",
    "NIFTY_50_SYMBOLS",
    "resolve_nifty500_securities",
    "NIFTY_500_SECURITY_IDS",
    "NIFTY_500_SYMBOLS",
    "resolve_nifty50_securities",
    "NIFTY_100_SECURITY_IDS",
    "NIFTY_100_SYMBOLS",
    "resolve_nifty100_securities",
    "NIFTY_SMALLCAP_100_SECURITY_IDS",
    "NIFTY_SMALLCAP_100_SYMBOLS",
    "resolve_nifty_smallcap100_securities",
    "FNO_SECURITY_IDS",
    "FNO_SYMBOLS",
    "resolve_fno_securities",
    "get_active_universe",
]


def get_active_universe(
    universe_name: str | None = None,
) -> tuple[str, list[str], dict[str, str]]:
    """Return active stock universe symbols and security ID mapping.

    Supports `NIFTY_500`, `NIFTY_100`, `NIFTY_50`, `NIFTY_SMALLCAP_100`, and `ALL_F_AND_O`.
    """
    val = universe_name or os.getenv("UNIVERSE") or "NIFTY_50"
    raw_name = str(val).strip().upper()

    if raw_name in ("NIFTY_500", "NIFTY500", "500", "NSE_500", "NSE500"):
        return "NIFTY_500", NIFTY_500_SYMBOLS, resolve_nifty500_securities()
    if raw_name in ("ALL_F_AND_O", "ALL_FNO", "FNO", "F&O", "F_AND_O"):
        return "ALL_F_AND_O", FNO_SYMBOLS, resolve_fno_securities()
    if raw_name in ("NIFTY_100", "NIFTY100", "100"):
        return "NIFTY_100", NIFTY_100_SYMBOLS, resolve_nifty100_securities()
    if raw_name in (
        "NIFTY_SMALLCAP_100",
        "NIFTY_SMALLCAP",
        "SMALLCAP_100",
        "SMALLCAP100",
        "SMALLCAP",
        "SMALL_CAP",
    ):
        return (
            "NIFTY_SMALLCAP_100",
            NIFTY_SMALLCAP_100_SYMBOLS,
            resolve_nifty_smallcap100_securities(),
        )

    return "NIFTY_50", NIFTY_50_SYMBOLS, resolve_nifty50_securities()
