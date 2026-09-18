"""Models for RSI Extremes & Momentum Reversal Scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["RsiZone", "RsiScanResult"]


class RsiZone(StrEnum):
    OVERSOLD = "OVERSOLD"
    OVERBOUGHT = "OVERBOUGHT"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True, slots=True)
class RsiScanResult:
    """Results of RSI extremes analysis for a single stock."""

    symbol: str
    security_id: str
    ltp: float
    rsi: float | None = None
    rsi_zone: RsiZone | str = RsiZone.NEUTRAL
    candle_signal: str = ""
    is_matched: bool = False
    volume: int = 0
    change_pct: float = 0.0

    # Backward-compatibility alias fields matching StockSupportScan
    @property
    def is_at_support(self) -> bool:
        """Alias for is_matched to maintain full compatibility with legacy UI consumers."""
        return self.is_matched

    @property
    def nearest_support(self) -> Any:
        return None

    @property
    def distance_pct(self) -> float:
        return 0.0

    @property
    def all_supports(self) -> list:
        return []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for JSON serialization."""
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "rsi": self.rsi,
            "rsi_zone": str(self.rsi_zone),
            "candle_signal": self.candle_signal,
            "is_matched": self.is_matched,
            "is_at_support": self.is_matched,
            "volume": self.volume,
            "change_pct": self.change_pct,
            "nearest_support": None,
            "distance_pct": 0.0,
            "all_supports": [],
        }

