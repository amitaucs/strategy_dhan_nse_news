"""NSE F&O (Futures & Options) Universe and Dhan Security ID Resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    import pandas as pd
    from dhanhq import dhanhq

from scanner_dhan.universe.manager import (
    get_fno_lot_size,
    get_universe_manager,
    is_fno_stock,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FNO_SYMBOLS",
    "FNO_SECURITY_IDS",
    "resolve_fno_securities",
    "get_fno_symbols",
    "get_fno_lot_sizes",
    "is_fno_stock",
    "get_fno_lot_size",
]


def get_fno_symbols() -> List[str]:
    """Retrieve dynamic active NSE F&O underlying symbol list from DhanUniverseManager."""
    _, symbols, _ = get_universe_manager().get_universe("ALL_F_AND_O")
    return symbols


def get_fno_lot_sizes() -> Dict[str, int]:
    """Retrieve dynamic exchange lot sizes for all active NSE F&O stocks."""
    mgr = get_universe_manager()
    # Trigger load if empty
    if not mgr._fno_lot_sizes:
        mgr.get_universe("ALL_F_AND_O")
    return dict(mgr._fno_lot_sizes)


def resolve_fno_securities(
    dhan: dhanhq | None = None,
    security_list_df: pd.DataFrame | None = None,
) -> Dict[str, str]:
    """Resolve Dhan security IDs for all active NSE F&O stocks."""
    _, _, sec_ids = get_universe_manager().get_universe("ALL_F_AND_O")
    return sec_ids


# Dynamic proxy classes for backwards compatibility
class _DynamicFnoSymbols(list):
    def __iter__(self):
        return iter(get_fno_symbols())

    def __len__(self):
        return len(get_fno_symbols())

    def __contains__(self, item):
        return is_fno_stock(str(item))

    def __getitem__(self, index):
        return get_fno_symbols()[index]

    def __repr__(self):
        return repr(get_fno_symbols())


class _DynamicFnoSecIds(dict):
    def items(self):
        return resolve_fno_securities().items()

    def keys(self):
        return resolve_fno_securities().keys()

    def values(self):
        return resolve_fno_securities().values()

    def get(self, key, default=None):
        return resolve_fno_securities().get(key, default)

    def __getitem__(self, key):
        return resolve_fno_securities()[key]

    def __contains__(self, key):
        return key in resolve_fno_securities()

    def __len__(self):
        return len(resolve_fno_securities())

    def __repr__(self):
        return repr(resolve_fno_securities())


FNO_SYMBOLS = _DynamicFnoSymbols()
FNO_SECURITY_IDS = _DynamicFnoSecIds()
