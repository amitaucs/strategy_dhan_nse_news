"""ST-14: Bullish CE Intraday Setup Models and Data Structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "St14Status",
    "St14ScanResult",
]


class St14Status(str, Enum):
    """Execution status classification for ST-14 Bullish CE setup."""

    QUALIFIED = "QUALIFIED"  # Passed Daily + 1H momentum rules + VWAP Proximity + Timing >= 10:15 IST
    WATCHLIST = "WATCHLIST"  # Daily trend passed, 1H near breakout or setting up
    NO_SETUP = "NO_SETUP"  # Setup conditions not met


@dataclass
class St14ScanResult:
    """Scan candidate result for ST-14 Bullish CE Setup."""

    symbol: str
    security_id: str
    ltp: float
    status: St14Status
    is_at_support: bool  # True if QUALIFIED (satisfies BaseScanner contract for matched filtering)
    daily_close: float
    daily_ema20: float
    five_day_high: float
    is_5d_breakout: bool
    is_daily_bullish: bool
    hourly_close: float
    hourly_ema20: float
    five_hour_high: float
    is_5h_breakout: bool
    is_hourly_bullish: bool
    vwap: float
    vwap_dist_pct: float
    vwap_angle_deg: float
    is_vwap_near: bool
    is_vwap_rising: bool
    timing_valid: bool
    timing_message: str
    dist_to_5d_high_pct: float
    dist_to_5h_high_pct: float
    analysis_time_ist: str
    volume: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def distance_pct(self) -> float:
        """Distance % to 5H breakout high."""
        return self.dist_to_5h_high_pct

    @property
    def candle_signal(self) -> str:
        """Textual badge for setup status."""
        if self.status == St14Status.QUALIFIED:
            return "🚀 BULLISH CE TRIGGER"
        if self.status == St14Status.WATCHLIST:
            return "👀 WATCHLIST (Near Trigger)"
        return "⚪ NO SETUP"

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for API and UI tables."""
        return {
            "symbol": self.symbol,
            "security_id": self.security_id,
            "ltp": self.ltp,
            "support_price": self.five_hour_high,
            "support_type": "5H Breakout Level",
            "status": self.status.value,
            "is_at_support": self.is_at_support,
            "matched": self.status == St14Status.QUALIFIED,
            "daily_close": self.daily_close,
            "daily_ema20": self.daily_ema20,
            "five_day_high": self.five_day_high,
            "is_5d_breakout": self.is_5d_breakout,
            "is_daily_bullish": self.is_daily_bullish,
            "hourly_close": self.hourly_close,
            "hourly_ema20": self.hourly_ema20,
            "five_hour_high": self.five_hour_high,
            "is_5h_breakout": self.is_5h_breakout,
            "is_hourly_bullish": self.is_hourly_bullish,
            "vwap": self.vwap,
            "vwap_dist_pct": self.vwap_dist_pct,
            "vwap_angle_deg": self.vwap_angle_deg,
            "is_vwap_near": self.is_vwap_near,
            "is_vwap_rising": self.is_vwap_rising,
            "timing_valid": self.timing_valid,
            "timing_message": self.timing_message,
            "dist_to_5d_high_pct": self.dist_to_5d_high_pct,
            "dist_to_5h_high_pct": self.dist_to_5h_high_pct,
            "distance_pct": self.dist_to_5h_high_pct,
            "volume": self.volume,
            "analysis_time_ist": self.analysis_time_ist,
            "candle_signal": self.candle_signal,
            "support_desc": "Bullish CE Setup (1H Breakout + Rising VWAP)" if self.is_at_support else "Watchlist Setup",
            "description": (
                f"Daily: > 20 EMA (₹{self.daily_ema20:.1f}) & 5D High (₹{self.five_day_high:.1f}) | "
                f"1H: > 20 EMA (₹{self.hourly_ema20:.1f}) & 5H High (₹{self.five_hour_high:.1f}) | "
                f"VWAP: ₹{self.vwap:.1f} ({self.vwap_dist_pct:+.2f}%, {self.vwap_angle_deg:.0f}°) "
                f"[{self.timing_message}]"
            ),
        }
