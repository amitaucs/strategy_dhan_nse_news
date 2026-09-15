"""ST07: Monthly Heikin Ashi + 89 EMA Crossover Strategy Data Models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = ["St07Category", "St07ScanResult"]


class St07Category(StrEnum):
    """Scan Trigger Categories for ST07 Monthly HA 89 EMA Strategy."""

    FRESH_CROSSOVER = "Fresh Crossover"
    ACCUMULATION_PULLBACK = "Accumulation Pullback"


@dataclass(frozen=True, slots=True)
class St07ScanResult:
    """Individual stock analysis result for Monthly Heikin Ashi + 89 EMA strategy."""

    symbol: str
    security_id: str
    ltp: float
    scan_category: St07Category | None
    is_fresh_crossover: bool
    is_accumulation_pullback: bool
    ha_close: float
    ha_open: float
    ha_high: float
    ha_low: float
    ema_89: float
    ema_21: float
    ema_89_prev: float
    is_ema_89_rising: bool
    buy_trigger_price: float
    stop_loss: float
    distance_pct: float
    candle_signal: str
    monthly_bars_count: int
    volume: int = 0
    rsi: float | None = None

    @property
    def is_at_support(self) -> bool:
        """Matched status indicating either Fresh Crossover or Accumulation Pullback."""
        return self.is_fresh_crossover or self.is_accumulation_pullback

    @property
    def is_pullback(self) -> bool:
        """Alias for matched status."""
        return self.is_at_support

    def to_dict(self) -> dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "scan_category": self.scan_category.value if self.scan_category else None,
            "is_fresh_crossover": self.is_fresh_crossover,
            "is_accumulation_pullback": self.is_accumulation_pullback,
            "ha_close": self.ha_close,
            "ha_open": self.ha_open,
            "ha_high": self.ha_high,
            "ha_low": self.ha_low,
            "ema_89": self.ema_89,
            "ema_21": self.ema_21,
            "ema_89_prev": self.ema_89_prev,
            "is_ema_89_rising": self.is_ema_89_rising,
            "buy_trigger_price": self.buy_trigger_price,
            "stop_loss": self.stop_loss,
            "distance_pct": self.distance_pct,
            "candle_signal": self.candle_signal,
            "monthly_bars_count": self.monthly_bars_count,
            "volume": self.volume,
            "rsi": self.rsi,
            "is_at_support": self.is_at_support,
        }
