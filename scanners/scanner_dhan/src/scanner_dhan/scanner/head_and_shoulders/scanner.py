"""Head & Shoulders and Inverse Head & Shoulders BaseScanner Implementation."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.head_and_shoulders.engine import scan_stock_for_head_and_shoulders
from scanner_dhan.scanner.head_and_shoulders.models import (
    ConfirmationStatus,
    HeadAndShouldersScanResult,
    PatternType,
)
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["HeadAndShouldersScanner", "format_head_and_shoulders_dataframe"]


def format_head_and_shoulders_dataframe(
    results: List[HeadAndShouldersScanResult],
    only_matched: bool = False,
) -> pd.DataFrame:
    """Format scan results into a clean presentation DataFrame."""
    columns = [
        "Symbol",
        "LTP (₹)",
        "Pattern",
        "Status",
        "Neckline (₹)",
        "Head (₹)",
        "Right Shoulder (₹)",
        "Symmetry (%)",
        "Entry (₹)",
        "Stop Loss (₹)",
        "Target 1 (₹)",
        "Target 2 (₹)",
        "R:R",
        "RSI (14)",
        "Bars Ago",
    ]
    rows = []
    for r in results:
        p = r.pattern
        if not p:
            if not only_matched:
                rows.append(
                    {
                        "Symbol": r.symbol,
                        "LTP (₹)": r.ltp,
                        "Pattern": "-",
                        "Status": "NO_PATTERN",
                        "Neckline (₹)": "-",
                        "Head (₹)": "-",
                        "Right Shoulder (₹)": "-",
                        "Symmetry (%)": "-",
                        "Entry (₹)": "-",
                        "Stop Loss (₹)": "-",
                        "Target 1 (₹)": "-",
                        "Target 2 (₹)": "-",
                        "R:R": "-",
                        "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
                        "Bars Ago": "-",
                    }
                )
            continue

        if only_matched and p.status != ConfirmationStatus.CONFIRMED:
            continue

        pattern_label = (
            "🔴 Bearish H&S" if p.pattern_type == PatternType.REGULAR_HS else "🟢 Bullish Inv H&S"
        )
        status_label = "✅ CONFIRMED" if p.status == ConfirmationStatus.CONFIRMED else "⏳ FORMING"

        rows.append(
            {
                "Symbol": r.symbol,
                "LTP (₹)": r.ltp,
                "Pattern": pattern_label,
                "Status": status_label,
                "Neckline (₹)": p.neckline_price,
                "Head (₹)": p.head.price,
                "Right Shoulder (₹)": p.right_shoulder.price,
                "Symmetry (%)": f"{p.shoulder_symmetry_pct:.1f}%",
                "Entry (₹)": p.entry_price,
                "Stop Loss (₹)": p.stop_loss,
                "Target 1 (₹)": p.target_1,
                "Target 2 (₹)": p.target_2,
                "R:R": f"1:{p.risk_reward_ratio:.1f}" if p.risk_reward_ratio > 0 else "-",
                "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
                "Bars Ago": p.bars_since_formation,
            }
        )
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


@register_scanner
class HeadAndShouldersScanner(BaseScanner):
    """Scans for regular Head & Shoulders and Inverse Head & Shoulders chart patterns."""

    id = "head_and_shoulders"
    name = "Head & Shoulders Pattern Scanner"
    description = (
        "Detects classic Bearish Head & Shoulders breakdowns and Bullish Inverse Head & Shoulders "
        "breakouts across NSE equities with multi-point geometric symmetry and neckline confirmation."
    )
    category = "Chart Patterns"
    icon = "trending-up"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description="Target universe to scan for pattern formations.",
            options=[
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks) ⭐"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="pattern_type",
            label="Pattern Direction",
            param_type="select",
            default="ALL",
            description="Filter by pattern type: Both, Bullish Inverse H&S, or Bearish Regular H&S.",
            options=[
                {"value": "ALL", "label": "All Patterns (Bullish + Bearish)"},
                {"value": "INVERSE_ONLY", "label": "🟢 Bullish Inverse H&S Only (Breakouts)"},
                {"value": "REGULAR_ONLY", "label": "🔴 Bearish Head & Shoulders Only (Breakdowns)"},
            ],
        ),
        ScannerParameter(
            name="status_filter",
            label="Confirmation Filter",
            param_type="select",
            default="CONFIRMED_ONLY",
            description="Filter for trade-ready confirmed setups or watching forming patterns.",
            options=[
                {"value": "CONFIRMED_ONLY", "label": "🎯 Confirmed Breakouts / Breakdowns Only ⭐"},
                {"value": "ALL", "label": "All (Confirmed + Forming Setups)"},
                {"value": "FORMING_ONLY", "label": "⏳ Forming Only (Watchlist)"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Candle Timeframe",
            param_type="select",
            default="Daily",
            description="Bar aggregation timeframe for pattern detection.",
            options=[
                {"value": "Daily", "label": "Daily Candles (Positional / Swing) ⭐"},
                {"value": "1-Hour", "label": "1-Hour (Intraday Multi-Day)"},
                {"value": "15-Minute", "label": "15-Minute (Intraday)"},
            ],
        ),
        ScannerParameter(
            name="extrema_order",
            label="Peak/Trough Sensitivity (Bars)",
            param_type="int",
            default=10,
            min_value=5,
            max_value=25,
            step=1,
            description="Rolling window size for identifying local peaks and troughs.",
        ),
        ScannerParameter(
            name="symmetry_tolerance_pct",
            label="Symmetry Tolerance (%)",
            param_type="float",
            default=3.0,
            min_value=1.0,
            max_value=6.0,
            step=0.5,
            description="Maximum allowed percentage difference between Left and Right shoulder peaks.",
        ),
        ScannerParameter(
            name="history_days",
            label="Historical Lookback (Days)",
            param_type="int",
            default=500,
            min_value=120,
            max_value=1200,
            step=50,
            description="Number of calendar days of price history to fetch.",
        ),
        ScannerParameter(
            name="max_workers",
            label="Concurrent Workers",
            param_type="int",
            default=4,
            min_value=1,
            max_value=12,
            step=1,
            description="Parallel thread pool worker count for network requests.",
        ),
    ]

    def run(
        self,
        params: Optional[Dict[str, Any]] = None,
        provider: Optional[DhanDataProvider] = None,
    ) -> ScanReport:
        """Execute Head & Shoulders scan across selected universe."""
        p = params or {}
        universe_choice = str(p.get("universe", "NIFTY_100")).upper()
        pattern_filter = str(p.get("pattern_type", "ALL"))
        status_filter = str(p.get("status_filter", "CONFIRMED_ONLY"))
        timeframe = str(p.get("timeframe", "Daily"))
        extrema_order = int(p.get("extrema_order", p.get("order", 10)))
        raw_tol = float(p.get("symmetry_tolerance_pct", p.get("shoulder_tolerance", 3.0)))
        tolerance = raw_tol / 100.0 if raw_tol > 1.0 else raw_tol
        history_days = int(p.get("history_days", p.get("lookback_days", 500)))
        max_workers = int(p.get("max_workers", 4))

        scan_time = datetime.now()
        logger.info(
            "Starting Head & Shoulders scan on %s (Pattern: %s, Status: %s, Order: %d)...",
            universe_choice,
            pattern_filter,
            status_filter,
            extrema_order,
        )

        universe_choice = str(p.get("universe", "NIFTY_100")).upper()
        univ_name, symbols, sec_map = get_active_universe(universe_choice)
        if not symbols:
            univ_name, symbols, sec_map = get_active_universe("NIFTY_100")

        # Fallback scrip map if needed
        try:
            extra_sec_map = get_nse_equity_symbols_map()
            for k, v in extra_sec_map.items():
                if k not in sec_map:
                    sec_map[k] = v
        except Exception:
            pass

        data_provider = provider or DhanDataProvider()

        results: List[HeadAndShouldersScanResult] = []

        def _scan_worker(sym: str) -> Optional[HeadAndShouldersScanResult]:
            clean_sym = str(sym).strip().upper()
            sec_id = sec_map.get(clean_sym)
            if not sec_id:
                return None

            try:
                if hasattr(data_provider, "fetch_bars"):
                    df = data_provider.fetch_bars(security_id=sec_id, timeframe=timeframe, days=history_days)
                elif hasattr(data_provider, "fetch_daily_bars"):
                    df = data_provider.fetch_daily_bars(security_id=sec_id, days=history_days)
                elif hasattr(data_provider, "fetch_daily_ohlcv"):
                    df = data_provider.fetch_daily_ohlcv(security_id=sec_id, days=history_days)
                else:
                    return None

                if df is None or df.empty:
                    return None

                res = scan_stock_for_head_and_shoulders(
                    df=df,
                    symbol=sym,
                    security_id=sec_id,
                    timeframe=timeframe,
                    pattern_filter=pattern_filter,
                    order=extrema_order,
                    symmetry_tolerance=tolerance,
                )
                return res
            except Exception as e:
                logger.debug("Error analyzing %s for H&S pattern: %s", sym, e)
                return None

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="HSScanner"
        ) as executor:
            future_to_sym = {executor.submit(_scan_worker, s): s for s in symbols}
            for future in concurrent.futures.as_completed(future_to_sym):
                res = future.result()
                if res is not None:
                    results.append(res)

        # Apply status filter
        filtered_results: List[HeadAndShouldersScanResult] = []
        for r in results:
            if not r.has_pattern or not r.pattern:
                continue

            if status_filter == "CONFIRMED_ONLY" and r.pattern.status != ConfirmationStatus.CONFIRMED:
                continue
            if status_filter == "FORMING_ONLY" and r.pattern.status != ConfirmationStatus.FORMING:
                continue

            filtered_results.append(r)

        # Sort: Confirmed first, then highest risk/reward ratio
        filtered_results.sort(
            key=lambda r: (
                1 if r.pattern and r.pattern.status == ConfirmationStatus.CONFIRMED else 0,
                r.pattern.risk_reward_ratio if r.pattern else 0.0,
            ),
            reverse=True,
        )

        matched_count = len(filtered_results)
        logger.info(
            "Head & Shoulders scan completed. Total Scanned: %d | Matched: %d",
            len(results),
            matched_count,
        )

        return ScanReport(
            timestamp=scan_time,
            scanner_id=self.id,
            scanner_name=self.name,
            total_scanned=len(results),
            matched_count=matched_count,
            results=filtered_results,
            status="success",
        )

