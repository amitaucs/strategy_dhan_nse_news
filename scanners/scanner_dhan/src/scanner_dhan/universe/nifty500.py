"""Nifty 500 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.manager import get_universe_manager

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_500_SYMBOLS",
    "NIFTY_500_SECURITY_IDS",
    "resolve_nifty500_securities",
    "get_nifty500_symbols",
]


def get_nifty500_symbols() -> List[str]:
    """Retrieve dynamic Nifty 500 symbol list from DhanUniverseManager."""
    _, symbols, _ = get_universe_manager().get_universe("NIFTY_500")
    return symbols


def resolve_nifty500_securities(
    dhan: dhanhq | None = None,
    security_list_df: pd.DataFrame | None = None,
) -> Dict[str, str]:
    """Resolve Dhan security IDs for all Nifty 500 stocks."""
    _, _, sec_ids = get_universe_manager().get_universe("NIFTY_500")
    return sec_ids


class _DynamicN500Symbols(list):
    def __iter__(self):
        return iter(get_nifty500_symbols())

    def __len__(self):
        return len(get_nifty500_symbols())

    def __contains__(self, item):
        return item in get_nifty500_symbols()

    def __getitem__(self, index):
        return get_nifty500_symbols()[index]

    def __repr__(self):
        return repr(get_nifty500_symbols())


class _DynamicN500SecIds(dict):
    def items(self):
        return resolve_nifty500_securities().items()

    def keys(self):
        return resolve_nifty500_securities().keys()

    def values(self):
        return resolve_nifty500_securities().values()

    def get(self, key, default=None):
        return resolve_nifty500_securities().get(key, default)

    def __getitem__(self, key):
        return resolve_nifty500_securities()[key]

    def __contains__(self, key):
        return key in resolve_nifty500_securities()

    def __len__(self):
        return len(resolve_nifty500_securities())

    def __repr__(self):
        return repr(resolve_nifty500_securities())


NIFTY_500_SYMBOLS = _DynamicN500Symbols()
NIFTY_500_SECURITY_IDS = _DynamicN500SecIds()
