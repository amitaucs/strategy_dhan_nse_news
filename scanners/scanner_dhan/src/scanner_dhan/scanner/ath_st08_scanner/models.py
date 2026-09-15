"""ATH-ST08: Monthly All-Time High (ATH) Breakout Strategy Data Models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = ["AthClass", "AthBreakoutScanResult"]


class AthClass(StrEnum):
    """Setup Classification for ATH Breakouts based on base consolidation duration."""

    A_CLASS = "A-Class (>30m)"
    B_CLASS = "B-Class (<=30m)"


@dataclass(frozen=True, slots=True)
class AthBreakoutScanResult:
    """Individual stock scan result for Monthly All-Time High Breakout strategy (ATH-ST08)."""

    symbol: str
    security_id: str
    ltp: float
    is_ath_breakout: bool
    prior_ath_price: float
    prior_ath_date: str
    months_in_consolidation: int
    ath_class: AthClass | None
    breakout_candle_high: float
    breakout_candle_low: float
    breakout_candle_open: float
    breakout_candle_close: float
    trigger_entry_price: float
    sma_30_week: float
    candle_range_pct: float
    avg_range_12m_pct: float
    range_expansion_ratio: float
    is_exhaustion_passed: bool
    distance_pct: float
    candle_signal: str
    monthly_bars_count: int
    volume: int = 0
    rsi: float | None = None

    @property
    def is_at_support(self) -> bool:
        """Matched status indicating qualifying ATH Breakout."""
        return self.is_ath_breakout

    @property
    def is_pullback(self) -> bool:
        """Alias for matched status."""
        return self.is_ath_breakout

    def to_dict(self) -> dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "is_ath_breakout": self.is_ath_breakout,
            "prior_ath_price": self.prior_ath_price,
            "prior_ath_date": self.prior_ath_date,
            "months_in_consolidation": self.months_in_consolidation,
            "ath_class": self.ath_class.value if self.ath_class else None,
            "breakout_candle_high": self.breakout_candle_high,
            "breakout_candle_low": self.breakout_candle_low,
            "breakout_candle_open": self.breakout_candle_open,
            "breakout_candle_close": self.breakout_candle_close,
            "trigger_entry_price": self.trigger_entry_price,
            "sma_30_week": self.sma_30_week,
            "candle_range_pct": self.candle_range_pct,
            "avg_range_12m_pct": self.avg_range_12m_pct,
            "range_expansion_ratio": self.range_expansion_ratio,
            "is_exhaustion_passed": self.is_exhaustion_passed,
            "distance_pct": self.distance_pct,
            "candle_signal": self.candle_signal,
            "monthly_bars_count": self.monthly_bars_count,
            "volume": self.volume,
            "rsi": self.rsi,
            "is_at_support": self.is_at_support,
        }
