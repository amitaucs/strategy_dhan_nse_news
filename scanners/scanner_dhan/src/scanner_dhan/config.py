"""Validated configuration for a backtest run."""

from dataclasses import dataclass
from datetime import date

__all__ = ["BacktestConfig"]


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Inputs that control portfolio simulation."""

    start_date: date
    end_date: date
    initial_cash: float = 100_000.0
    commission_rate: float = 0.0
    slippage_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.commission_rate < 0 or self.slippage_rate < 0:
            raise ValueError("cost rates cannot be negative")
