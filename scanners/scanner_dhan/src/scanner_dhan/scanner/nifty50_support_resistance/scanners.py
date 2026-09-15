"""Nifty 50 and F&O Support, Resistance, and RSI Scanner Implementations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.nifty50_support_resistance.level_detector import (
    analyze_stock_resistance,
    analyze_stock_support,
)
from scanner_dhan.scanner.nifty50_support_resistance.models import StockSupportScan
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = [
    "Nifty50SupportScanner",
    "Nifty50ResistanceScanner",
    "Nifty50RsiScanner",
    "Nifty50Scanner",
]


@register_scanner
class Nifty50SupportScanner(BaseScanner):
    """Detects stocks near major Support levels across Nifty 50 or F&O."""

    id = "nifty50_support"
    name = "Support Level Scanner - Stockwiz"
    description = (
        "Tracks stocks testing major horizontal swing lows, 20/50/100/200 EMAs, "
        "and Monthly Pivot S1/S2."
    )
    category = "Support & Resistance"
    icon = "trending-down"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_50",
            description=(
                "Choose between Nifty 500 (Broad Market), Nifty 100, Nifty 50, "
                "Nifty Smallcap 100, or All NSE F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Candle Timeframe",
            param_type="select",
            default="1D",
            description=(
                "Candle resolution: 1 Day (Daily), 2 Hours (120m), 1 Hour (60m), or 15 Minutes."
            ),
            options=[
                {"value": "1D", "label": "1 Day (Daily)"},
                {"value": "2H", "label": "2 Hours (120m)"},
                {"value": "1H", "label": "1 Hour (60m)"},
                {"value": "15M", "label": "15 Minutes"},
            ],
        ),
        ScannerParameter(
            name="target_level",
            label="Target Support / EMA",
            param_type="select",
            default="ALL",
            description=(
                "Target a specific EMA (20/50/100/200), Swing Lows, Pivots, or Auto-Detect Nearest."
            ),
            options=[
                {"value": "ALL", "label": "All Supports (Auto-Detect Highest Confluence)"},
                {"value": "MAJOR_ZONES", "label": "🏛️ Major Support Zones (2+ Bounces)"},
                {"value": "CONFLUENCE", "label": "🔥 Multi-Level Confluences"},
                {"value": "EMA_200", "label": "200 EMA Major Trend Support"},
                {"value": "EMA_100", "label": "100 EMA Support"},
                {"value": "EMA_50", "label": "50 EMA Support"},
                {"value": "EMA_20", "label": "20 EMA Support"},
                {"value": "SWING_LOW", "label": "Swing Lows (All Horizontal Swings)"},
                {"value": "PIVOTS", "label": "Monthly Floor Pivots (S1 / S2)"},
                {"value": "LOW_52W", "label": "52-Week Low Support"},
            ],
        ),
        ScannerParameter(
            name="threshold_pct",
            label="Proximity Threshold (%)",
            param_type="float",
            default=2.0,
            min_value=0.0,
            max_value=5.0,
            step=0.1,
            description="Max distance (%) from support to qualify as 'At Support'.",
        ),
        ScannerParameter(
            name="lookback_days",
            label="Historical Lookback (Days)",
            param_type="int",
            default=150,
            min_value=60,
            max_value=365,
            step=10,
            description="Number of daily bars used to calculate support zones.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        threshold_pct = float(p.get("threshold_pct", 2.0))
        lookback_days = int(p.get("lookback_days", 150))
        universe_choice = str(p.get("universe", "NIFTY_50"))
        timeframe = str(p.get("timeframe", "1D")).upper()
        target_level = str(p.get("target_level", "ALL"))
        prov = provider or DhanDataProvider()

        universe_name, symbols, sec_map = get_active_universe(universe_choice)
        security_ids = [sec_map[sym] for sym in symbols if sym in sec_map]
        ltp_map = prov.fetch_ltp_batch(security_ids)

        scan_results: list[StockSupportScan] = []
        for sym in symbols:
            sid = sec_map.get(sym, "")
            if not sid:
                continue
            df = prov.fetch_bars(sid, timeframe=timeframe, days=lookback_days)
            ltp = ltp_map.get(str(sid))
            scan = analyze_stock_support(
                df,
                sym,
                sid,
                ltp=ltp,
                threshold_pct=threshold_pct,
                target_level=target_level,
            )
            scan_results.append(scan)

        scan_results.sort(key=lambda x: (not x.is_at_support, abs(x.distance_pct)))
        matched_count = sum(1 for r in scan_results if r.is_at_support)

        target_suffix = f" | {target_level}" if target_level != "ALL" else ""
        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=f"{self.name} ({universe_name} | {timeframe}{target_suffix})",
            total_scanned=len(scan_results),
            matched_count=matched_count,
            results=scan_results,
        )


@register_scanner
class Nifty50ResistanceScanner(BaseScanner):
    """Detects stocks near major Resistance levels across Nifty 50 or F&O."""

    id = "nifty50_resistance"
    name = "Resistance Level Scanner - Stockwiz"
    description = (
        "Tracks stocks testing major horizontal swing highs, Monthly Pivots (R1/R2), "
        "and 52-week highs."
    )
    category = "Support & Resistance"
    icon = "trending-up"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_50",
            description=(
                "Choose between Nifty 500 (Broad Market), Nifty 100, Nifty 50, "
                "Nifty Smallcap 100, or All NSE F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Candle Timeframe",
            param_type="select",
            default="1D",
            description=(
                "Candle resolution: 1 Day (Daily), 2 Hours (120m), 1 Hour (60m), or 15 Minutes."
            ),
            options=[
                {"value": "1D", "label": "1 Day (Daily)"},
                {"value": "2H", "label": "2 Hours (120m)"},
                {"value": "1H", "label": "1 Hour (60m)"},
                {"value": "15M", "label": "15 Minutes"},
            ],
        ),
        ScannerParameter(
            name="target_level",
            label="Target Resistance",
            param_type="select",
            default="ALL",
            description=(
                "Target specific Swing Highs, Monthly R1/R2, 52-Week High, or Auto-Detect Nearest."
            ),
            options=[
                {"value": "ALL", "label": "All Resistances (Auto-Detect Highest Confluence)"},
                {"value": "MAJOR_ZONES", "label": "🏛️ Major Resistance Zones (2+ Rejections)"},
                {"value": "CONFLUENCE", "label": "🔥 Multi-Level Confluences"},
                {"value": "EMA_200", "label": "200 EMA Major Trend Resistance"},
                {"value": "EMA_100", "label": "100 EMA Resistance"},
                {"value": "EMA_50", "label": "50 EMA Resistance"},
                {"value": "EMA_20", "label": "20 EMA Resistance"},
                {"value": "SWING_HIGH", "label": "Swing Highs (All Horizontal Swings)"},
                {"value": "PIVOTS", "label": "Monthly Floor Pivots (R1 / R2)"},
                {"value": "HIGH_52W", "label": "52-Week High Range"},
            ],
        ),
        ScannerParameter(
            name="threshold_pct",
            label="Proximity Threshold (%)",
            param_type="float",
            default=2.0,
            min_value=0.0,
            max_value=5.0,
            step=0.1,
            description="Max distance (%) from resistance to qualify as 'At Resistance'.",
        ),
        ScannerParameter(
            name="lookback_days",
            label="Historical Lookback (Days)",
            param_type="int",
            default=150,
            min_value=60,
            max_value=365,
            step=10,
            description="Number of daily bars used to calculate resistance zones.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        threshold_pct = float(p.get("threshold_pct", 2.0))
        lookback_days = int(p.get("lookback_days", 150))
        universe_choice = str(p.get("universe", "NIFTY_50"))
        timeframe = str(p.get("timeframe", "1D")).upper()
        target_level = str(p.get("target_level", "ALL"))
        prov = provider or DhanDataProvider()

        universe_name, symbols, sec_map = get_active_universe(universe_choice)
        security_ids = [sec_map[sym] for sym in symbols if sym in sec_map]
        ltp_map = prov.fetch_ltp_batch(security_ids)

        scan_results: list[StockSupportScan] = []
        for sym in symbols:
            sid = sec_map.get(sym, "")
            if not sid:
                continue
            df = prov.fetch_bars(sid, timeframe=timeframe, days=lookback_days)
            ltp = ltp_map.get(str(sid))
            scan = analyze_stock_resistance(
                df,
                sym,
                sid,
                ltp=ltp,
                threshold_pct=threshold_pct,
                target_level=target_level,
            )
            scan_results.append(scan)

        scan_results.sort(key=lambda x: (not x.is_at_support, abs(x.distance_pct)))
        matched_count = sum(1 for r in scan_results if r.is_at_support)

        target_suffix = f" | {target_level}" if target_level != "ALL" else ""
        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=f"{self.name} ({universe_name} | {timeframe}{target_suffix})",
            total_scanned=len(scan_results),
            matched_count=matched_count,
            results=scan_results,
        )


@register_scanner
class Nifty50RsiScanner(BaseScanner):
    """Detects stocks in extreme Oversold or Overbought territory."""

    id = "nifty50_rsi"
    name = "RSI Extremes Scanner - Stockwiz"
    description = (
        "Finds oversold (RSI <= 38) or overbought (RSI >= 68) opportunities across stocks."
    )
    category = "Momentum"
    icon = "activity"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_50",
            description=(
                "Choose between Nifty 500 (Broad Market), Nifty 100, Nifty 50, "
                "Nifty Smallcap 100, or All NSE F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Candle Timeframe",
            param_type="select",
            default="1D",
            description=(
                "Candle resolution: 1 Day (Daily), 2 Hours (120m), 1 Hour (60m), or 15 Minutes."
            ),
            options=[
                {"value": "1D", "label": "1 Day (Daily)"},
                {"value": "2H", "label": "2 Hours (120m)"},
                {"value": "1H", "label": "1 Hour (60m)"},
                {"value": "15M", "label": "15 Minutes"},
            ],
        ),
        ScannerParameter(
            name="oversold_threshold",
            label="Oversold RSI",
            param_type="float",
            default=38.0,
            min_value=20.0,
            max_value=45.0,
            step=1.0,
            description="Stocks with RSI below this value are flagged.",
        ),
        ScannerParameter(
            name="overbought_threshold",
            label="Overbought RSI",
            param_type="float",
            default=68.0,
            min_value=55.0,
            max_value=85.0,
            step=1.0,
            description="Stocks with RSI above this value are flagged.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        oversold = float(p.get("oversold_threshold", 38.0))
        overbought = float(p.get("overbought_threshold", 68.0))
        universe_choice = str(p.get("universe", "NIFTY_50"))
        timeframe = str(p.get("timeframe", "1D")).upper()
        prov = provider or DhanDataProvider()

        universe_name, symbols, sec_map = get_active_universe(universe_choice)
        security_ids = [sec_map[sym] for sym in symbols if sym in sec_map]
        ltp_map = prov.fetch_ltp_batch(security_ids)

        scan_results: list[StockSupportScan] = []
        for sym in symbols:
            sid = sec_map.get(sym, "")
            if not sid:
                continue
            df = prov.fetch_bars(sid, timeframe=timeframe, days=100)
            ltp = ltp_map.get(str(sid))
            scan = analyze_stock_support(df, sym, sid, ltp=ltp, threshold_pct=2.0)

            # Override match condition for RSI
            is_matched = False
            if scan.rsi is not None:
                if scan.rsi <= oversold or scan.rsi >= overbought:
                    is_matched = True

            scan_results.append(
                StockSupportScan(
                    symbol=scan.symbol,
                    security_id=scan.security_id,
                    ltp=scan.ltp,
                    nearest_support=scan.nearest_support,
                    distance_pct=scan.distance_pct,
                    all_supports=scan.all_supports,
                    rsi=scan.rsi,
                    candle_signal=scan.candle_signal,
                    is_at_support=is_matched,
                    volume=scan.volume,
                )
            )

        scan_results.sort(key=lambda x: (not x.is_at_support, abs(x.distance_pct)))
        matched_count = sum(1 for r in scan_results if r.is_at_support)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=f"{self.name} ({universe_name} | {timeframe})",
            total_scanned=len(scan_results),
            matched_count=matched_count,
            results=scan_results,
        )


# Backward compatibility helper
class Nifty50Scanner:
    """Wrapper providing backward compatibility for existing scripts."""

    def __init__(
        self,
        provider: DhanDataProvider | None = None,
        threshold_pct: float = 2.0,
        lookback_days: int = 150,
    ) -> None:
        self.provider = provider
        self.threshold_pct = threshold_pct
        self.lookback_days = lookback_days
        self._scanner = Nifty50SupportScanner()

    def scan(
        self,
        symbols: list[str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ScanReport:
        return self._scanner.run(
            params={"threshold_pct": self.threshold_pct, "lookback_days": self.lookback_days},
            provider=self.provider,
        )
