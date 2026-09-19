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
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.wick_filter import get_wick_parameter
from scanner_dhan.scanner.fvg_fibonacci.engine import scan_stock_for_fvg_fib
from scanner_dhan.scanner.fvg_fibonacci.models import (
    FvgFibScanResult,
    FvgStatus,
    FvgType,
)
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["FvgFibonacciScanner", "format_fvg_fib_dataframe"]


def format_fvg_fib_dataframe(
    results: List[FvgFibScanResult],
    only_matched: bool = False,
) -> pd.DataFrame:
    """Format FVG + 0.618 Fib scan results into a presentation DataFrame."""
    columns = [
        "Symbol",
        "LTP (₹)",
        "Setup",
        "FVG Zone",
        "0.618 Fib (₹)",
        "0.705 OTE (₹)",
        "Stop Loss (₹)",
        "Target 1 (₹)",
        "Target 2 (₹)",
        "R:R",
        "Distance (%)",
        "Signal",
        "RSI (14)",
    ]

    rows = []
    for r in results:
        if not r.has_setup:
            continue
        if only_matched and not r.is_at_support:
            continue

        setup = r.setup
        if not setup:
            continue

        rows.append(
            {
                "Symbol": r.symbol,
                "LTP (₹)": f"₹{r.ltp:,.2f}",
                "Setup": setup.fvg.fvg_type.value,
                "FVG Zone": setup.fvg_overlap_desc,
                "0.618 Fib (₹)": f"₹{setup.fib.fib_618:,.2f}",
                "0.705 OTE (₹)": f"₹{setup.fib.fib_705:,.2f}",
                "Stop Loss (₹)": f"₹{setup.stop_loss:,.2f}",
                "Target 1 (₹)": f"₹{setup.target_1:,.2f}",
                "Target 2 (₹)": f"₹{setup.target_2:,.2f}",
                "R:R": f"1:{setup.risk_reward_ratio:.1f}",
                "Distance (%)": f"{setup.distance_pct:+.2f}%",
                "Signal": r.candle_signal,
                "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
            }
        )

    return pd.DataFrame(rows, columns=columns)


@register_scanner
class FvgFibonacciScanner(BaseScanner):
    """Scans for Fair Value Gaps aligned with the 0.618 Golden Pocket & 0.705 OTE."""

    id = "fvg_0618_fibonacci"
    name = "FVG + 0.618 Fibonacci Pullback"
    description = (
        "Screens for institutional displacement Fair Value Gaps (FVG) that align "
        "with 0.618 Golden Ratio & 0.705 OTE Fibonacci retracements with multi-candle "
        "confirmation and strict invalidation."
    )
    category = "Smart Money Concepts"
    icon = "layers"
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
                {"value": "NIFTY_MIDCAP_100", "label": "Nifty Midcap 100 (100 Mid-Caps) 🚀"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Small-Caps) 🎯"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Large-Caps)"},
                {"value": "FNO", "label": "F&O Active Stocks (~180)"},
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
        get_wick_parameter(default="NA"),
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
        max_wick_pct = params.get("max_wick_pct", "NA")

        return scan_stock_for_fvg_fib(
            provider=provider,
            symbol=symbol,
            security_id=security_id,
            timeframe=timeframe,
            days=180,
            min_gap_pct=min_gap_pct,
            confluence_tolerance_pct=confluence_tolerance_pct,
            direction_filter=direction_filter,
            max_wick_pct=max_wick_pct,
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

