"""HA_ST01: Daily Positional Heikin Ashi + RSI Reversal Strategy Data Models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = ["HaSt01SetupType", "HaSt01ScanResult"]


class HaSt01SetupType(StrEnum):
    """Setup Classification for Heikin Ashi + RSI Reversal."""

    BULLISH_DIVERGENCE = "Bullish Divergence"
    OVERSOLD_RECOVERY = "Oversold Flip"
    CONFLUENCE = "Divergence + Oversold"


@dataclass(frozen=True, slots=True)
class HaSt01ScanResult:
    """Individual stock scan result for HA_ST01 Reversal Strategy."""

    symbol: str
    security_id: str
    ltp: float
    is_reversal_setup: bool
    setup_type: HaSt01SetupType | None
    ha_open: float
    ha_close: float
    ha_high: float
    ha_low: float
    rsi: float | None
    rsi_prev: float | None
    rsi_min_last_3: float | None
    entry_price: float
    stop_loss: float
    risk_per_share: float
    target_1r: float
    target_2r: float
    reward_risk_ratio: float
    prior_red_ha_count: int
    is_ha_color_flip: bool
    has_bullish_divergence: bool
    is_oversold_recovery: bool
    volume: int = 0
    candle_signal: str = ""
    distance_pct: float = 0.0

    @property
    def is_at_support(self) -> bool:
        """Matched status indicating qualifying Reversal Setup."""
        return self.is_reversal_setup

    @property
    def is_pullback(self) -> bool:
        """Alias for matched status."""
        return self.is_reversal_setup

    def to_dict(self) -> dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "is_reversal_setup": self.is_reversal_setup,
            "setup_type": self.setup_type.value if self.setup_type else None,
            "ha_open": self.ha_open,
            "ha_close": self.ha_close,
            "ha_high": self.ha_high,
            "ha_low": self.ha_low,
            "rsi": self.rsi,
            "rsi_prev": self.rsi_prev,
            "rsi_min_last_3": self.rsi_min_last_3,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "risk_per_share": self.risk_per_share,
            "target_1r": self.target_1r,
            "target_2r": self.target_2r,
            "reward_risk_ratio": self.reward_risk_ratio,
            "prior_red_ha_count": self.prior_red_ha_count,
            "is_ha_color_flip": self.is_ha_color_flip,
            "has_bullish_divergence": self.has_bullish_divergence,
            "is_oversold_recovery": self.is_oversold_recovery,
            "volume": self.volume,
            "candle_signal": self.candle_signal,
            "distance_pct": self.distance_pct,
            "is_at_support": self.is_at_support,
        }
