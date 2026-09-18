"""Models for 2H Heikin Ashi EMA Pullback + Supertrend Scanner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["HeikinAshiEmaScanResult"]


@dataclass(frozen=True, slots=True)
class HeikinAshiEmaScanResult:
    """Scan result for a single stock under 2H Heikin Ashi EMA pullback strategy."""

    symbol: str
    security_id: str
    ltp: float
    nearest_ema_name: str
    nearest_ema_price: float
    distance_pct: float
    is_ha_green: bool
    is_supertrend_green: bool
    supertrend_val: float
    is_matched: bool
    is_first_green: bool = False
    is_pullback: bool = False
    volume: int = 0
    rsi: float | None = None
    candle_signal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "support_price": round(self.nearest_ema_price, 2),
            "support_type": self.nearest_ema_name,
            "support_desc": f"{self.nearest_ema_name} (₹{self.nearest_ema_price:,.2f})",
            "distance_pct": self.distance_pct,
            "is_at_support": self.is_matched,
            "is_pullback": self.is_pullback,
            "is_ha_green": self.is_ha_green,
            "is_first_green": self.is_first_green,
            "is_supertrend_green": self.is_supertrend_green,
            "supertrend_val": round(self.supertrend_val, 2),
            "volume": self.volume,
            "rsi": self.rsi,
            "candle_signal": (
                self.candle_signal
                or (
                    "⭐ 1st Green HA + ST Bullish"
                    if (self.is_first_green and self.is_supertrend_green)
                    else (
                        "Green HA + ST Bullish"
                        if (self.is_ha_green and self.is_supertrend_green)
                        else "HA Candle"
                    )
                )
            ),
        }
