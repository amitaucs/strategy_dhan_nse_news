"""Data models for Fair Value Gap (FVG) + 0.618 Fibonacci Retracement Confluence Scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class FvgType(str, Enum):
    """Type of Fair Value Gap."""

    BULLISH_FVG = "BULLISH_FVG"  # BISI: Buy-side Imbalance Sell-side Inefficiency
    BEARISH_FVG = "BEARISH_FVG"  # SIBI: Sell-side Imbalance Buy-side Inefficiency


class FvgStatus(str, Enum):
    """Status of FVG and Fibonacci Pullback Confluence."""

    PULLBACK_AT_618 = "PULLBACK_AT_618"      # Price currently testing 0.618 Fib + FVG zone (Triggered Setup)
    WATCHLIST_UNMITIGATED = "UNMITIGATED"     # Fresh FVG with 0.618 confluence, waiting for pullback
    PARTIALLY_FILLED = "PARTIALLY_FILLED"     # Price entered FVG but holding above/below 50% CE
    INVALIDATED = "INVALIDATED"               # Price closed beyond 0.786 Fib or swing origin


@dataclass(frozen=True, slots=True)
class FairValueGap:
    """Detected 3-candle Fair Value Gap with Consequent Encroachment (50% CE)."""

    fvg_type: FvgType
    bar_index: int
    timestamp: datetime
    top_price: float
    bottom_price: float
    ce_price: float                     # 50% Consequent Encroachment (Midpoint)
    gap_size: float
    gap_size_pct: float
    candle_1_time: datetime
    candle_1_price: float
    candle_2_time: datetime
    candle_2_price: float
    candle_3_time: datetime
    candle_3_price: float
    body_atr_ratio: float = 1.0
    volume_ratio: float = 1.0
    is_mitigated: bool = False
    mitigation_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fvg_type": self.fvg_type.value,
            "bar_index": self.bar_index,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
            "top_price": round(self.top_price, 2),
            "bottom_price": round(self.bottom_price, 2),
            "ce_price": round(self.ce_price, 2),
            "gap_size": round(self.gap_size, 2),
            "gap_size_pct": round(self.gap_size_pct, 2),
            "candle_1_time": str(self.candle_1_time),
            "candle_2_time": str(self.candle_2_time),
            "candle_3_time": str(self.candle_3_time),
            "body_atr_ratio": round(self.body_atr_ratio, 2),
            "volume_ratio": round(self.volume_ratio, 2),
            "is_mitigated": self.is_mitigated,
            "mitigation_date": self.mitigation_date,
        }


@dataclass(frozen=True, slots=True)
class FibonacciRetracement:
    """Fibonacci Retracement and Optimal Trade Entry (OTE) Levels for the impulse leg."""

    swing_low: float
    swing_high: float
    direction: str                     # "BULLISH" or "BEARISH"
    fib_0: float                       # Swing extreme (Target 1)
    fib_236: float
    fib_382: float
    fib_500: float                     # Equilibrium
    fib_618: float                     # Golden Retracement Level
    fib_705: float                     # ICT OTE Midpoint
    fib_786: float                     # Deep Golden Level / Stop Buffer
    fib_100: float                     # Swing Origin
    extension_272: float               # Target 2 (-0.272 extension)
    extension_618: float               # Target 3 (-0.618 extension)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "swing_low": round(self.swing_low, 2),
            "swing_high": round(self.swing_high, 2),
            "direction": self.direction,
            "fib_0": round(self.fib_0, 2),
            "fib_236": round(self.fib_236, 2),
            "fib_382": round(self.fib_382, 2),
            "fib_500": round(self.fib_500, 2),
            "fib_618": round(self.fib_618, 2),
            "fib_705": round(self.fib_705, 2),
            "fib_786": round(self.fib_786, 2),
            "fib_100": round(self.fib_100, 2),
            "extension_272": round(self.extension_272, 2),
            "extension_618": round(self.extension_618, 2),
        }


@dataclass
class FvgFibConfluenceSetup:
    """Combined setup where 0.618 Fibonacci aligns with a Fair Value Gap."""

    fvg: FairValueGap
    fib: FibonacciRetracement
    status: FvgStatus
    confluence_price: float             # 0.618 Fibonacci level price
    fvg_overlap_desc: str               # e.g. "Inside FVG [1420 - 1450] (CE: 1435)"
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward_ratio: float
    current_price: float
    distance_pct: float                 # Distance from LTP to 0.618 Fib
    is_at_confluence: bool              # True if price is within tolerance of 0.618 Fib
    candle_signal: str                  # Candlestick or bounce confirmation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fvg": self.fvg.to_dict(),
            "fib": self.fib.to_dict(),
            "status": self.status.value,
            "confluence_price": round(self.confluence_price, 2),
            "fvg_overlap_desc": self.fvg_overlap_desc,
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "current_price": round(self.current_price, 2),
            "distance_pct": round(self.distance_pct, 2),
            "is_at_confluence": self.is_at_confluence,
            "candle_signal": self.candle_signal,
        }


@dataclass
class FvgFibScanResult:
    """Complete scan outcome for a single stock for FVG + 0.618 Fib Scanner."""

    symbol: str
    security_id: str
    ltp: float = 0.0
    timeframe: str = "Daily"
    scanned_at: datetime = field(default_factory=datetime.now)
    has_setup: bool = False
    setup: Optional[FvgFibConfluenceSetup] = None
    rsi: Optional[float] = None
    volume: float = 0.0
    error: Optional[str] = None

    # Flattened properties for seamless table & card rendering in UI
    status: Optional[FvgStatus] = None
    fvg_type: Optional[FvgType] = None
    confluence_price: float = 0.0
    support_price: float = 0.0
    distance_pct: float = 0.0
    support_desc: str = ""
    candle_signal: str = ""
    target_1: float = 0.0
    stop_loss: float = 0.0
    risk_reward_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.setup:
            self.has_setup = True
            if self.status is None:
                self.status = self.setup.status
            if self.fvg_type is None:
                self.fvg_type = self.setup.fvg.fvg_type
            if not self.confluence_price:
                self.confluence_price = self.setup.confluence_price
            if not self.support_price:
                self.support_price = self.confluence_price
            if not self.distance_pct:
                self.distance_pct = self.setup.distance_pct
            if not self.target_1:
                self.target_1 = self.setup.target_1
            if not self.stop_loss:
                self.stop_loss = self.setup.stop_loss
            if not self.risk_reward_ratio:
                self.risk_reward_ratio = self.setup.risk_reward_ratio

            if not self.support_desc:
                dir_label = "⚡ Bullish FVG + 0.618" if self.fvg_type == FvgType.BULLISH_FVG else "⚡ Bearish FVG + 0.618"
                status_label = "Pullback Confirmed" if self.status == FvgStatus.PULLBACK_AT_618 else "Testing Level"
                self.support_desc = f"{dir_label} ({status_label})"

            if not self.candle_signal:
                rr_txt = f" (1:{self.risk_reward_ratio:.1f})" if self.risk_reward_ratio > 0 else ""
                setup_sig = self.setup.candle_signal if self.setup and self.setup.candle_signal else "⚡ 0.618 Fib Tap"
                self.candle_signal = f"{setup_sig}{rr_txt}"

    @property
    def is_at_support(self) -> bool:
        """Alias for BaseScanner matched report counting."""
        return self.has_setup and self.setup is not None and self.setup.is_at_confluence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": round(self.ltp, 2),
            "timeframe": self.timeframe,
            "scanned_at": self.scanned_at.isoformat() if hasattr(self.scanned_at, "isoformat") else str(self.scanned_at),
            "has_setup": self.has_setup,
            "is_at_support": self.is_at_support,
            "is_pullback": self.is_at_support,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status) if self.status else None,
            "fvg_type": self.fvg_type.value if hasattr(self.fvg_type, "value") else str(self.fvg_type) if self.fvg_type else None,
            "confluence_price": round(self.confluence_price, 2),
            "support_price": round(self.support_price or self.confluence_price, 2),
            "distance_pct": round(self.distance_pct, 2),
            "support_desc": self.support_desc,
            "candle_signal": self.candle_signal,
            "target_1": round(self.target_1, 2),
            "stop_loss": round(self.stop_loss, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "volume": round(self.volume, 2),
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "setup": self.setup.to_dict() if self.setup else None,
            "error": self.error,
        }

