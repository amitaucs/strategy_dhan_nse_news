"""Public interface for the scanner_dhan package."""

from scanner_dhan.config import BacktestConfig
from scanner_dhan.execution import BacktestEngine, BacktestResult
from scanner_dhan.models import Bar, Signal, SignalType
from scanner_dhan.strategies import Strategy

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "Bar",
    "Signal",
    "SignalType",
    "Strategy",
]

__version__ = "0.1.0"
