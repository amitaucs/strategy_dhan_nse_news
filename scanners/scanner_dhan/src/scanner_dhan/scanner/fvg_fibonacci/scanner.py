"""Fair Value Gap + 0.618 Fibonacci Retracement BaseScanner Implementation."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.fvg_fibonacci.engine import scan_stock_for_fvg_fib
from scanner_dhan.scanner.fvg_fibonacci.models import (
    FvgFibScanResult,
    FvgStatus,
    FvgType,
)
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["FvgFibonacciScanner", "format_fvg_fib_dataframe"]


def format_fvg_fib_dataframe(
    results: List[FvgFibScanResult],
    only_matched: bool = False,
) -> pd.DataFrame:
    """Format scan results into a clean presentation DataFrame."""
    columns = [
        "Symbol",
        "LTP (₹)",
        "Setup",
        "Status",
        "0.618 Fib (₹)",
        "FVG Range (₹)",
        "50% CE (₹)",
        "0.618 Dist (%)",
        "Entry (₹)",
        "Stop Loss (₹)",
        "Target 1 (₹)",
        "Target 2 (₹)",
        "R:R",
        "RSI (14)",
    ]
    rows = []
    for r in results:
        s = r.setup
        if not s:
            if not only_matched:
                rows.append(
                    {
                        "Symbol": r.symbol,
                        "LTP (₹)": r.ltp,
                        "Setup": "-",
                        "Status": "NO_SETUP",
                        "0.618 Fib (₹)": "-",
                        "FVG Range (₹)": "-",
                        "50% CE (₹)": "-",
                        "0.618 Dist (%)": "-",
                        "Entry (₹)": "-",
                        "Stop Loss (₹)": "-",
                        "Target 1 (₹)": "-",
                        "Target 2 (₹)": "-",
                        "R:R": "-",
                        "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
                    }
                )
            continue

        if only_matched and not s.is_at_confluence:
            continue

        setup_label = (
            "⚡ Bullish FVG + 0.618" if s.fvg.fvg_type == FvgType.BULLISH_FVG else "⚡ Bearish FVG + 0.618"
        )
        status_label = "✅ PULLBACK READY" if s.is_at_confluence else "⏳ WATCHLIST"

        rows.append(
            {
                "Symbol": r.symbol,
                "LTP (₹)": r.ltp,
                "Setup": setup_label,
                "Status": status_label,
                "0.618 Fib (₹)": s.fib.fib_618,
                "FVG Range (₹)": f"₹{s.fvg.bottom_price:.1f} - ₹{s.fvg.top_price:.1f}",
                "50% CE (₹)": s.fvg.ce_price,
                "0.618 Dist (%)": f"{s.distance_pct:+.2f}%",
                "Entry (₹)": s.entry_price,
                "Stop Loss (₹)": s.stop_loss,
                "Target 1 (₹)": s.target_1,
                "Target 2 (₹)": s.target_2,
                "R:R": f"1:{s.risk_reward_ratio:.1f}" if s.risk_reward_ratio > 0 else "-",
                "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
            }
        )
    return pd.DataFrame(rows, columns=columns)


@register_scanner
class FvgFibonacciScanner(BaseScanner):
    """Smart Money Concepts FVG + 0.618 Fibonacci Retracement Confluence Scanner."""

    id = "fvg_fib_0618"
    name = "FVG + 0.618 Fib Confluence Scanner"
    description = (
        "Detects Smart Money Concept (SMC) Fair Value Gaps (FVG) aligned with 0.618 Fibonacci "
        "Retracement levels for high-probability pullback entries."
    )
    category = "Smart Money Concepts"
    icon = "zap"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description="Target universe to scan for FVG + Fib setups.",
            options=[
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks) ⭐"},
                {"value": "NIFTY_500", "label": "Nifty 500 (500 Stocks)"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Large-Caps)"},
                {"value": "FNO", "label": "F&O Active Stocks (~180)"},
                {"value": "NIFTY_MIDCAP_100", "label": "Nifty Midcap 100"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Analysis Timeframe",
            param_type="select",
            default="Daily",
            description="Candle interval to analyze for displacement and imbalances.",
            options=[
                {"value": "Daily", "label": "Daily (Swing Trades) ⭐"},
                {"value": "1Hour", "label": "1-Hour (Positional / Intraday)"},
                {"value": "15Min", "label": "15-Minute (Day Trading)"},
            ],
        ),
        ScannerParameter(
            name="direction",
            label="Trade Direction",
            param_type="select",
            default="ALL",
            description="Filter for Bullish, Bearish, or Both confluence setups.",
            options=[
                {"value": "ALL", "label": "All Setups (Bullish & Bearish) ⚡"},
                {"value": "BULLISH_ONLY", "label": "🟢 Bullish Only (Long Pullbacks)"},
                {"value": "BEARISH_ONLY", "label": "🔴 Bearish Only (Short Pullbacks)"},
            ],
        ),
        ScannerParameter(
            name="confluence_tolerance_pct",
            label="0.618 Fib Distance Tolerance (%)",
            param_type="float",
            default=1.5,
            description="Maximum distance (%) between current price and 0.618 Fib to trigger active pullback alert.",
            min_value=0.2,
            max_value=5.0,
            step=0.1,
        ),
        ScannerParameter(
            name="min_gap_pct",
            label="Minimum FVG Size (%)",
            param_type="float",
            default=0.2,
            description="Minimum percentage gap size between Candle 1 and Candle 3.",
            min_value=0.1,
            max_value=2.0,
            step=0.05,
        ),
    ]

    def scan_symbol(
        self,
        symbol: str,
        security_id: str,
        params: Optional[Dict[str, Any]] = None,
        provider: Optional[DhanDataProvider] = None,
    ) -> FvgFibScanResult:
        """Scan a single symbol for FVG + 0.618 Fib confluence."""
        if provider is None:
            provider = DhanDataProvider()

        params = params or {}
        timeframe = params.get("timeframe", "Daily")
        confluence_tolerance_pct = float(params.get("confluence_tolerance_pct", 1.5))
        min_gap_pct = float(params.get("min_gap_pct", 0.2))
        direction_filter = params.get("direction", "ALL")

        return scan_stock_for_fvg_fib(
            provider=provider,
            symbol=symbol,
            security_id=security_id,
            timeframe=timeframe,
            days=180,
            min_gap_pct=min_gap_pct,
            confluence_tolerance_pct=confluence_tolerance_pct,
            direction_filter=direction_filter,
        )

    def run(
        self,
        params: Optional[Dict[str, Any]] = None,
        provider: Optional[DhanDataProvider] = None,
    ) -> ScanReport:
        """Execute FVG + 0.618 Fibonacci scanner across target universe."""
        if provider is None:
            provider = DhanDataProvider()

        params = params or {}
        universe_choice = str(params.get("universe", "NIFTY_100")).upper()
        univ_name, symbols, sec_map = get_active_universe(universe_choice)
        if not symbols:
            logger.warning("Empty universe '%s', falling back to NIFTY_100", universe_choice)
            univ_name, symbols, sec_map = get_active_universe("NIFTY_100")

        # Fallback scrip map if needed
        try:
            extra_sec_map = get_nse_equity_symbols_map()
            for k, v in extra_sec_map.items():
                if k not in sec_map:
                    sec_map[k] = v
        except Exception:
            pass

        scrip_list: List[tuple[str, str]] = []
        for sym in symbols:
            clean_sym = str(sym).strip().upper()
            sec_id = sec_map.get(clean_sym, clean_sym)
            scrip_list.append((clean_sym, sec_id))

        logger.info(
            "Starting FVG + 0.618 Fib scan on %d symbols (%s, %s)",
            len(scrip_list),
            univ_name,
            params.get("timeframe", "Daily"),
        )

        results: List[FvgFibScanResult] = []
        # Run concurrently with rate-limited thread pool
        max_workers = min(8, len(scrip_list)) if scrip_list else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {
                executor.submit(self.scan_symbol, sym, sec_id, params, provider): sym
                for sym, sec_id in scrip_list
            }
            for future in concurrent.futures.as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    logger.error("Scan failed for %s: %s", sym, exc)
                    results.append(
                        FvgFibScanResult(
                            symbol=sym,
                            security_id="",
                            error=str(exc),
                        )
                    )

        # Filter strictly for active setups that have retested 0.618 Fib
        matched_results = [r for r in results if r.is_at_support]
        matched_results.sort(key=lambda r: abs(r.distance_pct))
        matched_count = len(matched_results)

        logger.info(
            "FVG + 0.618 Fib scan completed. Total Scanned: %d | Matched (0.618 Retest): %d",
            len(results),
            matched_count,
        )

        return ScanReport(
            scanner_id=self.id,
            scanner_name=self.name,
            timestamp=datetime.now(),
            total_scanned=len(results),
            matched_count=matched_count,
            results=[r.to_dict() for r in matched_results],
        )

