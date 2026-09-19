"""Data models for Mark Minervini Volatility Contraction Pattern (VCP) Scanner."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class VcpStatus(str, Enum):
    """Lifecycle and trigger status of the VCP setup."""

    PRIMED_TIGHT = "PRIMED_TIGHT"  # Final contraction <= 6.5% with VDU, primed at pivot
    BREAKOUT_ACTIVE = "BREAKOUT_ACTIVE"  # Price breaking out above pivot with volume expansion
    FORMING_CONTRACTION = "FORMING_CONTRACTION"  # Valid contraction sequence forming
    WATCHLIST = "WATCHLIST"  # Stage 2 valid, waiting for final compression or VDU


class VcpSchematic(str, Enum):
    """Classification matching Mid-Cap institutional accumulation schematics."""

    SCHEMATIC_1_UNDER_RESISTANCE = "Schematic 1: Base under Pivot"
    SCHEMATIC_2_BREAKOUT_RETEST = "Schematic 2: Breakout Shelf Retest"
    SCHEMATIC_3_STAIRCASE_BASE = "Schematic 3: Staircase Trend Base"
    SCHEMATIC_5_HIGH_TIGHT_SHELF = "Schematic 5: High Tight Shelf VCP"


@dataclass
class VcpWave:
    """Represents a single contraction wave (T1, T2, T3, T4)."""

    wave_number: int
    peak_bar: int
    trough_bar: int
    peak_price: float
    trough_price: float
    depth_pct: float
    bars_duration: int
    avg_volume: float = 0.0
    vdu_ratio: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Stage2Metrics:
    """Minervini Stage 2 Institutional Trend Template parameters."""

    current_close: float
    sma_50: float
    sma_150: float
    sma_200: float
    sma_200_slope_pct: float
    high_52w: float
    low_52w: float
    pct_from_52w_high: float
    pct_from_52w_low: float
    is_stage2: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VcpPattern:
    """Complete Volatility Contraction Pattern with multi-wave structural math."""

    waves: List[VcpWave]
    contractions_count: int
    depth_sequence_pct: List[float]
    final_depth_pct: float
    pivot_level: float
    stop_loss: float
    risk_pct: float
    target_1: float
    target_2: float
    risk_reward_ratio: float
    vdu_ratio: float
    is_vdu: bool
    status: VcpStatus
    schematic: VcpSchematic
    stage2: Stage2Metrics
    candle_signal: str = "⚡ VCP Primed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "waves": [w.to_dict() for w in self.waves],
            "contractions_count": self.contractions_count,
            "depth_sequence_pct": self.depth_sequence_pct,
            "final_depth_pct": round(self.final_depth_pct, 2),
            "pivot_level": round(self.pivot_level, 2),
            "stop_loss": round(self.stop_loss, 2),
            "risk_pct": round(self.risk_pct, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "vdu_ratio": round(self.vdu_ratio, 2),
            "is_vdu": self.is_vdu,
            "status": self.status.value,
            "schematic": self.schematic.value,
            "stage2": self.stage2.to_dict(),
            "candle_signal": self.candle_signal,
        }


@dataclass
class VcpScanResult:
    """Unified scan output for a single stock."""

    symbol: str
    security_id: str
    ltp: float = 0.0
    timeframe: str = "Daily"
    has_setup: bool = False
    is_at_support: bool = False  # Set to True when setup is Primed or Active Breakout
    setup: Optional[VcpPattern] = None
    rsi: Optional[float] = None
    volume: float = 0.0
    support_desc: str = ""
    candle_signal: str = ""
    error: Optional[str] = None

    @property
    def is_confirmed(self) -> bool:
        return self.is_at_support

    @property
    def distance_pct(self) -> float:
        if self.setup and self.setup.pivot_level > 0 and self.ltp > 0:
            return round(((self.ltp - self.setup.pivot_level) / self.setup.pivot_level) * 100.0, 2)
        return 0.0

    @property
    def nearest_support_price(self) -> float:
        return self.setup.stop_loss if self.setup else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": round(self.ltp, 2),
            "timeframe": self.timeframe,
            "has_setup": self.has_setup,
            "is_at_support": self.is_at_support,
            "is_confirmed": self.is_confirmed,
            "setup": self.setup.to_dict() if self.setup else None,
            "rsi": round(self.rsi, 1) if self.rsi is not None else None,
            "volume": self.volume,
            "support_desc": self.support_desc,
            "candle_signal": self.candle_signal,
            "distance_pct": self.distance_pct,
            "nearest_support_price": self.nearest_support_price,
            "error": self.error,
        }

