"""Models for Support and Resistance Detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["SupportType", "SupportLevel", "StockSupportScan"]


class SupportType(StrEnum):
    SWING_LOW = "SWING_LOW"
    SWING_HIGH = "SWING_HIGH"
    MAJOR_SUPPORT_ZONE = "MAJOR_SUPPORT_ZONE"
    MAJOR_RESISTANCE_ZONE = "MAJOR_RESISTANCE_ZONE"
    CONFLUENCE_SUPPORT = "CONFLUENCE_SUPPORT"
    CONFLUENCE_RESISTANCE = "CONFLUENCE_RESISTANCE"
    EMA_9 = "EMA_9"
    EMA_20 = "EMA_20"
    EMA_21 = "EMA_21"
    EMA_50 = "EMA_50"
    EMA_100 = "EMA_100"
    EMA_200 = "EMA_200"
    SMA_20 = "SMA_20"
    SMA_50 = "SMA_50"
    SMA_100 = "SMA_100"
    SMA_200 = "SMA_200"
    PIVOT_S1 = "PIVOT_S1"
    PIVOT_S2 = "PIVOT_S2"
    PIVOT_R1 = "PIVOT_R1"
    PIVOT_R2 = "PIVOT_R2"
    LOW_52W = "52W_LOW"
    HIGH_52W = "52W_HIGH"


@dataclass(frozen=True, slots=True)
class SupportLevel:
    """Represents an identified support or resistance level."""

    price: float
    level_type: SupportType | str
    strength: int = 1  # Number of touches/bounces or priority
    description: str = ""


@dataclass(frozen=True, slots=True)
class StockSupportScan:
    """Results of support or resistance analysis for a single stock."""

    symbol: str
    security_id: str
    ltp: float
    nearest_support: SupportLevel | None
    distance_pct: float
    all_supports: list[SupportLevel] = field(default_factory=list)
    rsi: float | None = None
    candle_signal: str = ""
    is_at_support: bool = False
    volume: int = 0

    def to_dict(self) -> dict[str, Any]:
        supp_type_val = None
        if self.nearest_support:
            supp_type_val = (
                self.nearest_support.level_type.value
                if hasattr(self.nearest_support.level_type, "value")
                else str(self.nearest_support.level_type)
            )
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "support_price": self.nearest_support.price if self.nearest_support else None,
            "support_type": supp_type_val,
            "support_desc": self.nearest_support.description if self.nearest_support else "N/A",
            "distance_pct": self.distance_pct,
            "is_at_support": self.is_at_support,
            "all_supports": [
                {
                    "price": s.price,
                    "type": (
                        s.level_type.value if hasattr(s.level_type, "value") else str(s.level_type)
                    ),
                    "desc": s.description,
                }
                for s in self.all_supports
            ],
            "rsi": self.rsi,
            "candle_signal": self.candle_signal,
            "volume": self.volume,
        }
