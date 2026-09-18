"""Data models for Head & Shoulders and Inverse Head & Shoulders Pattern Scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PatternType(str, Enum):
    """Type of Head and Shoulders pattern."""

    REGULAR_HS = "REGULAR_HS"          # Bearish Head and Shoulders (Breakdown / Short)
    INVERSE_HS = "INVERSE_HS"          # Bullish Inverse Head and Shoulders (Breakout / Long)


class ConfirmationStatus(str, Enum):
    """Confirmation status of the pattern."""

    CONFIRMED = "CONFIRMED"            # Neckline breached with candle close (Trade Ready)
    FORMING = "FORMING"                # Right shoulder formed, watching for neckline breach
    INVALIDATED = "INVALIDATED"        # Price breached head level in wrong direction


@dataclass(frozen=True, slots=True)
class ExtremaPoint:
    """A local extrema (peak or trough) in price action."""

    index: int
    timestamp: datetime
    price: float
    point_type: str = "PEAK"           # "PEAK" or "TROUGH"
    point_name: Optional[str] = None   # "A", "B", "C", "D", "E"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
            "price": round(self.price, 2),
            "type": self.point_type,
            "point_name": self.point_name,
        }


@dataclass
class HeadAndShouldersPattern:
    """Detected 5-point Head and Shoulders or Inverse Head and Shoulders pattern."""

    pattern_type: PatternType
    symbol: str
    timeframe: str

    # 5 Key Geometric Points
    left_shoulder: ExtremaPoint        # Point A
    neckline_1: ExtremaPoint           # Point B
    head: ExtremaPoint                 # Point C
    neckline_2: ExtremaPoint           # Point D
    right_shoulder: ExtremaPoint       # Point E

    # Metrics
    neckline_price: float              # Neckline level (Point D price or slope projected)
    head_height: float                 # Distance between Head and Neckline 2
    shoulder_symmetry_pct: float       # |Left_Sh - Right_Sh| / Mean(Left_Sh, Right_Sh) * 100
    neckline_symmetry_pct: float       # |Neck_1 - Neck_2| / Mean(Neck_1, Neck_2) * 100
    pattern_bar_span: int              # Total bar count from Left Shoulder to Right Shoulder

    # Status & Confirmation
    status: ConfirmationStatus
    confirmation_date: Optional[datetime] = None
    confirmation_bar_index: Optional[int] = None
    confirmation_price: Optional[float] = None
    bars_since_formation: int = 0

    # Trade Levels
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    risk_reward_ratio: float = 0.0
    current_price: float = 0.0
    breakout_date: Optional[str] = None

    @property
    def neckline_level(self) -> float:
        return self.neckline_price

    @property
    def shoulder_diff_pct(self) -> float:
        return self.shoulder_symmetry_pct / 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value if hasattr(self.pattern_type, "value") else str(self.pattern_type),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "left_shoulder": self.left_shoulder.to_dict(),
            "neckline_1": self.neckline_1.to_dict(),
            "head": self.head.to_dict(),
            "neckline_2": self.neckline_2.to_dict(),
            "right_shoulder": self.right_shoulder.to_dict(),
            "neckline_price": round(self.neckline_price, 2),
            "head_height": round(self.head_height, 2),
            "shoulder_symmetry_pct": round(self.shoulder_symmetry_pct, 2),
            "neckline_symmetry_pct": round(self.neckline_symmetry_pct, 2),
            "pattern_bar_span": self.pattern_bar_span,
            "confirmation_date": self.confirmation_date.isoformat() if hasattr(self.confirmation_date, "isoformat") else (str(self.confirmation_date) if self.confirmation_date else None),
            "confirmation_price": round(self.confirmation_price, 2) if self.confirmation_price else None,
            "bars_since_formation": self.bars_since_formation,
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "current_price": round(self.current_price, 2),
            "breakout_date": self.breakout_date,
        }


@dataclass
class HeadAndShouldersScanResult:
    """Scan outcome for a single stock."""

    symbol: str
    security_id: str
    ltp: float = 0.0
    timeframe: str = "Daily"
    scanned_at: datetime = field(default_factory=datetime.now)
    has_pattern: bool = False
    pattern: Optional[HeadAndShouldersPattern] = None
    rsi: Optional[float] = None
    error: Optional[str] = None
    # Optional direct attributes / shortcuts
    status: Optional[ConfirmationStatus] = None
    pattern_type: Optional[PatternType] = None
    neckline: float = 0.0
    head_price: float = 0.0
    current_price: float = 0.0
    target_1: float = 0.0
    stop_loss: float = 0.0
    shoulder_symmetry_pct: float = 0.0
    signal_desc: str = ""

    def __post_init__(self) -> None:
        if self.pattern:
            self.has_pattern = True
            if self.status is None:
                self.status = self.pattern.status
            if self.pattern_type is None:
                self.pattern_type = self.pattern.pattern_type
            if not self.neckline:
                self.neckline = self.pattern.neckline_price
            if not self.head_price:
                self.head_price = self.pattern.head.price
            if not self.current_price:
                self.current_price = self.pattern.current_price or self.ltp
            if not self.target_1:
                self.target_1 = self.pattern.target_1
            if not self.stop_loss:
                self.stop_loss = self.pattern.stop_loss
            if not self.shoulder_symmetry_pct:
                self.shoulder_symmetry_pct = self.pattern.shoulder_symmetry_pct
            if not self.signal_desc:
                dir_txt = "Bearish Breakdown" if self.pattern.pattern_type == PatternType.REGULAR_HS else "Bullish Breakout"
                if self.pattern.status == ConfirmationStatus.CONFIRMED:
                    self.signal_desc = f"⚡ Confirmed {dir_txt} below/above Neckline ₹{self.neckline:.2f}"
                else:
                    self.signal_desc = f"⏳ Forming {dir_txt} near Neckline ₹{self.neckline:.2f}"

    @property
    def is_at_support(self) -> bool:
        """Alias for BaseScanner report matching."""
        return self.has_pattern and self.pattern is not None and self.pattern.status == ConfirmationStatus.CONFIRMED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": round(self.ltp, 2),
            "timeframe": self.timeframe,
            "scanned_at": self.scanned_at.isoformat() if hasattr(self.scanned_at, "isoformat") else str(self.scanned_at),
            "has_pattern": self.has_pattern,
            "is_confirmed": self.is_at_support,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status) if self.status else None,
            "pattern_type": self.pattern_type.value if hasattr(self.pattern_type, "value") else str(self.pattern_type) if self.pattern_type else None,
            "neckline": round(self.neckline, 2),
            "head_price": round(self.head_price, 2),
            "current_price": round(self.current_price, 2),
            "target_1": round(self.target_1, 2),
            "stop_loss": round(self.stop_loss, 2),
            "shoulder_symmetry_pct": round(self.shoulder_symmetry_pct, 2),
            "signal_desc": self.signal_desc,
            "pattern": self.pattern.to_dict() if self.pattern else None,
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "error": self.error,
        }
