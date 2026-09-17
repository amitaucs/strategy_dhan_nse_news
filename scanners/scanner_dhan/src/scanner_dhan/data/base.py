"""Contracts implemented by historical market-data providers."""

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from scanner_dhan.models import Bar

__all__ = ["MarketDataSource"]


class MarketDataSource(Protocol):
    def get_bars(self, symbol: str, start: date, end: date) -> Iterable[Bar]:
        """Return chronological bars for the requested date range."""
        ...
