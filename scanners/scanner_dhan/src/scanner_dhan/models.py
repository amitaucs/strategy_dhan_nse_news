"""Shared, dependency-free domain models."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

__all__ = ["Bar", "Signal", "SignalType"]


class SignalType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")
        if not self.low <= self.open <= self.high or not self.low <= self.close <= self.high:
            raise ValueError("open and close must lie inside the low/high range")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")


@dataclass(frozen=True, slots=True)
class Signal:
    timestamp: datetime
    symbol: str
    action: SignalType
    quantity: int = 1

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
