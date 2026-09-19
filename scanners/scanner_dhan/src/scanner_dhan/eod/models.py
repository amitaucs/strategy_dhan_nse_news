"""Data models for EOD Multi-Scanner Daily Digest snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class EODMatchedStrategy:
    """Summary of a specific strategy match for a stock."""
    scanner_id: str
    scanner_name: str
    category: str
    signal: str
    level_desc: str
    score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanner_id": self.scanner_id,
            "scanner_name": self.scanner_name,
            "category": self.category,
            "signal": self.signal,
            "level_desc": self.level_desc,
            "score": self.score,
            "details": self.details,
        }


@dataclass
class EODConfluenceStock:
    """A stock that triggered one or more scanner strategies on the EOD run."""
    symbol: str
    company_name: str
    security_id: str
    close: float
    change_pct: float
    volume: int
    volume_ratio: float
    match_count: int
    confluence_score: float
    strategies: List[EODMatchedStrategy] = field(default_factory=list)
    primary_category: str = "Breakout"
    pivot_level: Optional[float] = None
    stop_loss: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "security_id": self.security_id,
            "close": self.close,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "volume_ratio": self.volume_ratio,
            "match_count": self.match_count,
            "confluence_score": self.confluence_score,
            "primary_category": self.primary_category,
            "pivot_level": self.pivot_level,
            "stop_loss": self.stop_loss,
            "strategies": [s.to_dict() for s in self.strategies],
        }


@dataclass
class EODStrategySummary:
    """Aggregated hit counts and items for a single scanner."""
    scanner_id: str
    scanner_name: str
    category: str
    icon: str
    matches_count: int
    items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scanner_id": self.scanner_id,
            "scanner_name": self.scanner_name,
            "category": self.category,
            "icon": self.icon,
            "matches_count": self.matches_count,
            "items": self.items,
        }


@dataclass
class EODDigestReport:
    """Complete End-of-Day Multi-Scanner Daily Digest snapshot."""
    date: str  # YYYY-MM-DD
    timestamp: str  # ISO formatted IST timestamp
    universe: str  # e.g., NIFTY_500
    total_scanners_run: int
    total_matches: int
    unique_stocks_count: int
    confluence_stocks_count: int  # stocks with match_count >= 2
    bullish_count: int
    bearish_count: int
    top_confluence_stocks: List[EODConfluenceStock] = field(default_factory=list)
    all_stocks: List[EODConfluenceStock] = field(default_factory=list)
    strategies: Dict[str, EODStrategySummary] = field(default_factory=dict)
    execution_time_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "timestamp": self.timestamp,
            "universe": self.universe,
            "total_scanners_run": self.total_scanners_run,
            "total_matches": self.total_matches,
            "unique_stocks_count": self.unique_stocks_count,
            "confluence_stocks_count": self.confluence_stocks_count,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "top_confluence_stocks": [s.to_dict() for s in self.top_confluence_stocks],
            "all_stocks": [s.to_dict() for s in self.all_stocks],
            "strategies": {k: v.to_dict() for k, v in self.strategies.items()},
            "execution_time_seconds": round(self.execution_time_seconds, 2),
        }

