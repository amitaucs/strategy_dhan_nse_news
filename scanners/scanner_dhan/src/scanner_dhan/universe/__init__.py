"""Stock universe definitions and dynamic security ID resolution."""

from __future__ import annotations

import os

from scanner_dhan.universe.fno import (
    FNO_SECURITY_IDS,
    FNO_SYMBOLS,
    get_fno_lot_size,
    get_fno_lot_sizes,
    get_fno_symbols,
    is_fno_stock,
    resolve_fno_securities,
)
from scanner_dhan.universe.manager import (
    DhanUniverseManager,
    get_universe_manager,
)
from scanner_dhan.universe.nifty50 import (
    NIFTY_50_SECURITY_IDS,
    NIFTY_50_SYMBOLS,
    get_nifty50_symbols,
    resolve_nifty50_securities,
)
from scanner_dhan.universe.nifty100 import (
    NIFTY_100_SECURITY_IDS,
    NIFTY_100_SYMBOLS,
    get_nifty100_symbols,
    resolve_nifty100_securities,
)
from scanner_dhan.universe.nifty200 import (
    NIFTY_200_SECURITY_IDS,
    NIFTY_200_SYMBOLS,
    get_nifty200_symbols,
    resolve_nifty200_securities,
)
from scanner_dhan.universe.nifty500 import (
    NIFTY_500_SECURITY_IDS,
    NIFTY_500_SYMBOLS,
    get_nifty500_symbols,
    resolve_nifty500_securities,
)
from scanner_dhan.universe.nifty_smallcap100 import (
    NIFTY_SMALLCAP_100_SECURITY_IDS,
    NIFTY_SMALLCAP_100_SYMBOLS,
    get_nifty_smallcap100_symbols,
    resolve_nifty_smallcap100_securities,
)

__all__ = [
    "DhanUniverseManager",
    "get_universe_manager",
    "is_fno_stock",
    "get_fno_lot_size",
    "get_fno_lot_sizes",
    "NIFTY_50_SECURITY_IDS",
    "NIFTY_50_SYMBOLS",
    "get_nifty50_symbols",
    "resolve_nifty50_securities",
    "NIFTY_100_SECURITY_IDS",
    "NIFTY_100_SYMBOLS",
    "get_nifty100_symbols",
    "resolve_nifty100_securities",
    "NIFTY_200_SECURITY_IDS",
    "NIFTY_200_SYMBOLS",
    "get_nifty200_symbols",
    "resolve_nifty200_securities",
    "NIFTY_500_SECURITY_IDS",
    "NIFTY_500_SYMBOLS",
    "get_nifty500_symbols",
    "resolve_nifty500_securities",
    "NIFTY_SMALLCAP_100_SECURITY_IDS",
    "NIFTY_SMALLCAP_100_SYMBOLS",
    "get_nifty_smallcap100_symbols",
    "resolve_nifty_smallcap100_securities",
    "FNO_SECURITY_IDS",
    "FNO_SYMBOLS",
    "get_fno_symbols",
    "resolve_fno_securities",
    "get_active_universe",
]


def get_active_universe(
    universe_name: str | None = None,
) -> tuple[str, list[str], dict[str, str]]:
    """Return active stock universe symbols and security ID mapping dynamically from DhanUniverseManager.

    Supports `NIFTY_500`, `NIFTY_200`, `NIFTY_100`, `NIFTY_50`, `NIFTY_SMALLCAP_100`, and `ALL_F_AND_O`.
    """
    return get_universe_manager().get_universe(universe_name)
