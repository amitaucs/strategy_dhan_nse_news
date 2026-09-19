"""Nifty Midcap 100 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.manager import get_universe_manager

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_MIDCAP_100_SYMBOLS",
    "NIFTY_MIDCAP_100_SECURITY_IDS",
    "resolve_nifty_midcap100_securities",
    "get_nifty_midcap100_symbols",
]


def get_nifty_midcap100_symbols() -> List[str]:
    """Retrieve dynamic Nifty Midcap 100 symbol list from DhanUniverseManager."""
    _, symbols, _ = get_universe_manager().get_universe("NIFTY_MIDCAP_100")
    return symbols


def resolve_nifty_midcap100_securities(
    dhan: dhanhq | None = None,
    security_list_df: pd.DataFrame | None = None,
) -> Dict[str, str]:
    """Resolve Dhan security IDs for all Nifty Midcap 100 stocks."""
    _, _, sec_ids = get_universe_manager().get_universe("NIFTY_MIDCAP_100")
    return sec_ids


class _DynamicMidcapSymbols(list):
    def __iter__(self):
        return iter(get_nifty_midcap100_symbols())

    def __len__(self):
        return len(get_nifty_midcap100_symbols())

    def __contains__(self, item):
        return item in get_nifty_midcap100_symbols()

    def __getitem__(self, index):
        return get_nifty_midcap100_symbols()[index]

    def __repr__(self):
        return repr(get_nifty_midcap100_symbols())


class _DynamicMidcapSecIds(dict):
    def items(self):
        return resolve_nifty_midcap100_securities().items()

    def keys(self):
        return resolve_nifty_midcap100_securities().keys()

    def values(self):
        return resolve_nifty_midcap100_securities().values()

    def __getitem__(self, key):
        return resolve_nifty_midcap100_securities()[key]

    def __contains__(self, key):
        return key in resolve_nifty_midcap100_securities()

    def __len__(self):
        return len(resolve_nifty_midcap100_securities())

    def __repr__(self):
        return repr(resolve_nifty_midcap100_securities())


NIFTY_MIDCAP_100_SYMBOLS: List[str] = _DynamicMidcapSymbols()
NIFTY_MIDCAP_100_SECURITY_IDS: Dict[str, str] = _DynamicMidcapSecIds()
