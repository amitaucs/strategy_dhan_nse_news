"""Nifty 200 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.manager import get_universe_manager

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_200_SYMBOLS",
    "NIFTY_200_SECURITY_IDS",
    "resolve_nifty200_securities",
    "get_nifty200_symbols",
]


def get_nifty200_symbols() -> List[str]:
    """Retrieve dynamic Nifty 200 symbol list from DhanUniverseManager."""
    _, symbols, _ = get_universe_manager().get_universe("NIFTY_200")
    return symbols


def resolve_nifty200_securities(
    dhan: dhanhq | None = None,
    security_list_df: pd.DataFrame | None = None,
) -> Dict[str, str]:
    """Resolve security IDs for all Nifty 200 stocks."""
    _, _, sec_ids = get_universe_manager().get_universe("NIFTY_200")
    return sec_ids


# Dynamic accessors / properties for backwards compatibility
class _DynamicSymbols(list):
    def __iter__(self):
        return iter(get_nifty200_symbols())

    def __len__(self):
        return len(get_nifty200_symbols())

    def __contains__(self, item):
        return item in get_nifty200_symbols()

    def __getitem__(self, index):
        return get_nifty200_symbols()[index]


class _DynamicSecIds(dict):
    def items(self):
        return resolve_nifty200_securities().items()

    def keys(self):
        return resolve_nifty200_securities().keys()

    def values(self):
        return resolve_nifty200_securities().values()

    def get(self, key, default=None):
        return resolve_nifty200_securities().get(key, default)

    def __getitem__(self, key):
        return resolve_nifty200_securities()[key]

    def __contains__(self, key):
        return key in resolve_nifty200_securities()

    def __len__(self):
        return len(resolve_nifty200_securities())


NIFTY_200_SYMBOLS = _DynamicSymbols()
NIFTY_200_SECURITY_IDS = _DynamicSecIds()

