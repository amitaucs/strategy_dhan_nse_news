"""Nifty 50 Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.manager import get_universe_manager

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_50_SYMBOLS",
    "NIFTY_50_SECURITY_IDS",
    "resolve_nifty50_securities",
    "get_nifty50_symbols",
]


def get_nifty50_symbols() -> List[str]:
    """Retrieve dynamic Nifty 50 symbol list from DhanUniverseManager."""
    _, symbols, _ = get_universe_manager().get_universe("NIFTY_50")
    return symbols


def resolve_nifty50_securities(
    dhan: dhanhq | None = None,
    security_list_df: pd.DataFrame | None = None,
) -> Dict[str, str]:
    """Resolve Dhan security IDs for all Nifty 50 stocks."""
    _, _, sec_ids = get_universe_manager().get_universe("NIFTY_50")
    return sec_ids


class _DynamicN50Symbols(list):
    def __iter__(self):
        return iter(get_nifty50_symbols())

    def __len__(self):
        return len(get_nifty50_symbols())

    def __contains__(self, item):
        return item in get_nifty50_symbols()

    def __getitem__(self, index):
        return get_nifty50_symbols()[index]

    def __repr__(self):
        return repr(get_nifty50_symbols())


class _DynamicN50SecIds(dict):
    def items(self):
        return resolve_nifty50_securities().items()

    def keys(self):
        return resolve_nifty50_securities().keys()

    def values(self):
        return resolve_nifty50_securities().values()

    def get(self, key, default=None):
        return resolve_nifty50_securities().get(key, default)

    def __getitem__(self, key):
        return resolve_nifty50_securities()[key]

    def __contains__(self, key):
        return key in resolve_nifty50_securities()

    def __len__(self):
        return len(resolve_nifty50_securities())

    def __repr__(self):
        return repr(resolve_nifty50_securities())


NIFTY_50_SYMBOLS = _DynamicN50Symbols()
NIFTY_50_SECURITY_IDS = _DynamicN50SecIds()
