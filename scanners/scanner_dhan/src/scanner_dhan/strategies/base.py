"""Base contract for trading strategies."""

from abc import ABC, abstractmethod

from scanner_dhan.models import Bar, Signal

__all__ = ["Strategy"]


class Strategy(ABC):
    """Convert each market bar into an optional trading signal."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> Signal | None:
        """Process one chronological bar and optionally emit a signal."""
