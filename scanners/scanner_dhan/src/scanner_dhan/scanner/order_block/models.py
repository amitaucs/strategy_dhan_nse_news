"""Domain models for Smart Money Concepts (SMC) Order Block Scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["OrderBlockType", "OrderBlock", "OrderBlockScanResult"]


class OrderBlockType(StrEnum):
    BULLISH_DEMAND = "BULLISH_DEMAND"
    BEARISH_SUPPLY = "BEARISH_SUPPLY"


@dataclass(frozen=True, slots=True)
class OrderBlock:
    """Represents an identified Institutional Order Block zone."""

    price_top: float
    price_bottom: float
    block_type: OrderBlockType
    candle_timestamp: str
    impulse_body_expansion: float
    volume_expansion: float
    is_mitigated: bool = False
    description: str = ""

    @property
    def midpoint(self) -> float:
        return (self.price_top + self.price_bottom) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "price_top": round(self.price_top, 2),
            "price_bottom": round(self.price_bottom, 2),
            "midpoint": round(self.midpoint, 2),
            "block_type": self.block_type.value,
            "candle_timestamp": self.candle_timestamp,
            "impulse_body_expansion": round(self.impulse_body_expansion, 2),
            "volume_expansion": round(self.volume_expansion, 2),
            "is_mitigated": self.is_mitigated,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class OrderBlockScanResult:
    """Scan result for a single stock evaluated for Order Block presence & retest."""

    symbol: str
    security_id: str
    ltp: float
    nearest_order_block: OrderBlock | None
    distance_pct: float
    is_at_order_block: bool
    is_fresh_impulse: bool = False
    all_order_blocks: list[OrderBlock] = field(default_factory=list)
    volume: int = 0
    rsi: float | None = None
    candle_signal: str = ""

    def to_dict(self) -> dict[str, Any]:
        ob_desc = (
            self.nearest_order_block.description if self.nearest_order_block else "No Active OB"
        )
        ob_type = self.nearest_order_block.block_type.value if self.nearest_order_block else "NONE"
        ob_price = round(self.nearest_order_block.midpoint, 2) if self.nearest_order_block else None

        is_inside_demand = bool(
            self.nearest_order_block
            and self.nearest_order_block.block_type == OrderBlockType.BULLISH_DEMAND
            and self.distance_pct == 0.0
            and not self.is_fresh_impulse
        )
        is_retest_demand = bool(
            self.nearest_order_block
            and self.nearest_order_block.block_type == OrderBlockType.BULLISH_DEMAND
            and self.distance_pct != 0.0
            and self.is_at_order_block
            and not self.is_fresh_impulse
        )
        is_inside_supply = bool(
            self.nearest_order_block
            and self.nearest_order_block.block_type == OrderBlockType.BEARISH_SUPPLY
            and self.distance_pct == 0.0
            and not self.is_fresh_impulse
        )
        is_retest_supply = bool(
            self.nearest_order_block
            and self.nearest_order_block.block_type == OrderBlockType.BEARISH_SUPPLY
            and self.distance_pct != 0.0
            and self.is_at_order_block
            and not self.is_fresh_impulse
        )

        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "support_price": ob_price,
            "support_type": ob_type,
            "support_desc": ob_desc,
            "distance_pct": self.distance_pct,
            "is_at_support": self.is_at_order_block,
            "is_at_order_block": self.is_at_order_block,
            "is_fresh_impulse": self.is_fresh_impulse,
            "is_inside_demand_ob": is_inside_demand,
            "is_retesting_demand_ob": is_retest_demand,
            "is_inside_supply_ob": is_inside_supply,
            "is_retesting_supply_ob": is_retest_supply,
            "block_type": ob_type,
            "all_supports": [ob.to_dict() for ob in self.all_order_blocks],
            "all_order_blocks": [ob.to_dict() for ob in self.all_order_blocks],
            "volume": self.volume,
            "rsi": self.rsi,
            "candle_signal": self.candle_signal,
        }
