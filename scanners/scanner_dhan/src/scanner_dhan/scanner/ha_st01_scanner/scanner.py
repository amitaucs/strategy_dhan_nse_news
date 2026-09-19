"""HA_ST01: Daily Positional Heikin Ashi + RSI Reversal Scanner Engine."""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.ha_st01_scanner.engine import analyze_ha_st01_stock
from scanner_dhan.scanner.ha_st01_scanner.models import HaSt01ScanResult
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["HaSt01ReversalScanner", "format_ha_st01_dataframe"]


@register_scanner
class HaSt01ReversalScanner(BaseScanner):
    """Daily Positional Bullish Reversal Scanner (Heikin Ashi + RSI)."""

    id = "ha_st01_rsi_reversal"
    name = "Heikin Ashi + RSI Reversal - HA_ST01"
    description = (
        "Daily Positional Bullish Reversal Scanner detecting Heikin Ashi color "
        "flips after multi-bar downswings with RSI Oversold Recovery or Regular "
        "Bullish Divergence."
    )
    category = "Reversal / Momentum"
    icon = "refresh-cw"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description=(
                "Target universe: Nifty 100 (Default), Nifty 500 (Broad Market), "
                "Nifty 50, Smallcap 100, or All F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks) ⭐"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_MIDCAP_100", "label": "Nifty Midcap 100 (100 Mid-Caps) 🚀"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Small-Caps) 🎯"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Candle Timeframe",
            param_type="select",
            default="1D",
            description="Candle resolution for reversal detection (1D Daily Default).",
            options=[
                {"value": "1D", "label": "1D (Daily - Positional Reversal) ⭐"},
                {"value": "2H", "label": "2H (120m Swing)"},
                {"value": "1H", "label": "1H (60m Intraday)"},
            ],
        ),
        ScannerParameter(
            name="setup_filter",
            label="Reversal Setup Filter",
            param_type="select",
            default="ALL",
            description="Filter by reversal setup type.",
            options=[
                {"value": "ALL", "label": "All Reversals (Divergence + Oversold)"},
                {"value": "DIVERGENCE_ONLY", "label": "🌟 Bullish Divergence Only ⭐"},
                {"value": "OVERSOLD_ONLY", "label": "⚡ Oversold Flips Only"},
            ],
        ),
        ScannerParameter(
            name="oversold_threshold",
            label="RSI Oversold Threshold",
            param_type="float",
            default=35.0,
            min_value=20.0,
            max_value=45.0,
            step=1.0,
            description="RSI level considered oversold in recent 3 bars (Default: 35).",
        ),
        ScannerParameter(
            name="min_prior_red",
            label="Min Prior Red Bars",
            param_type="int",
            default=2,
            min_value=1,
            max_value=6,
            step=1,
            description="Minimum consecutive red HA candles before current trigger bar.",
        ),
        ScannerParameter(
            name="max_workers",
            label="Concurrent Workers",
            param_type="int",
            default=4,
            min_value=1,
            max_value=8,
            step=1,
            description="Number of parallel worker threads.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        universe_choice = str(p.get("universe", "NIFTY_100"))
        timeframe = str(p.get("timeframe", "1D")).strip().upper()
        setup_filter = str(p.get("setup_filter", "ALL")).upper().strip()
        oversold_threshold = float(p.get("oversold_threshold", 35.0))
        min_prior_red = int(p.get("min_prior_red", 2))
        max_workers = int(p.get("max_workers", 4))
        history_days = 200

        # 1. Resolve Universe & Security IDs
        univ_name, symbols, sec_id_map = get_active_universe(universe_choice)

        missing_syms = [s for s in symbols if s not in sec_id_map]
        if missing_syms:
            master_map = get_nse_equity_symbols_map()
            for sym in missing_syms:
                if sym in master_map:
                    sec_id_map[sym] = master_map[sym]

        data_provider = provider or DhanDataProvider()

        # 2. Fetch Latest LTPs in batch
        valid_sids = [sec_id_map[s] for s in symbols if s in sec_id_map]
        ltp_map = data_provider.fetch_ltp_batch(valid_sids)

        results: list[HaSt01ScanResult] = []
        logger.info(
            "Running HA_ST01 Reversal Scanner on %d symbols in %s (%s) with %d workers...",
            len(symbols),
            univ_name,
            timeframe,
            max_workers,
        )

        def _scan_single_stock(sym: str) -> HaSt01ScanResult | None:
            sid = sec_id_map.get(sym)
            if not sid:
                return None
            try:
                df = data_provider.fetch_bars(
                    security_id=sid, timeframe=timeframe, days=history_days
                )
                if df.empty:
                    return None

                ltp_override = ltp_map.get(sid)
                res = analyze_ha_st01_stock(
                    symbol=sym,
                    security_id=sid,
                    daily_df=df,
                    ltp_override=ltp_override,
                    oversold_threshold=oversold_threshold,
                    min_prior_red_bars=min_prior_red,
                    min_bars_required=30,
                )

                if res is not None:
                    # Filter by setup type if requested
                    if setup_filter == "DIVERGENCE_ONLY" and not res.has_bullish_divergence:
                        return None
                    if setup_filter == "OVERSOLD_ONLY" and not res.is_oversold_recovery:
                        return None

                return res
            except Exception as exc:
                logger.debug("Error scanning %s in HA_ST01: %s", sym, exc)
                return None

        # 3. Parallel Scanning with ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {executor.submit(_scan_single_stock, sym): sym for sym in symbols}
            for future in concurrent.futures.as_completed(future_to_sym):
                try:
                    res = future.result()
                    if res is not None:
                        results.append(res)
                except Exception as exc:
                    sym = future_to_sym[future]
                    logger.warning("Scan worker exception for %s: %s", sym, exc)

        # 4. Sort Results: Divergences first, then Oversold Flips, then by RSI ascending
        results.sort(
            key=lambda r: (
                0
                if r.is_reversal_setup and r.has_bullish_divergence
                else (1 if r.is_reversal_setup else 2),
                r.rsi if r.rsi is not None else 100.0,
            )
        )

        matched_count = sum(1 for r in results if r.is_reversal_setup)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=self.name,
            total_scanned=len(symbols),
            matched_count=matched_count,
            results=results,
        )


def format_ha_st01_dataframe(report: ScanReport, only_matched: bool = False) -> pd.DataFrame:
    """Format HA_ST01 ScanReport results into a clean export DataFrame."""
    rows = []
    for r in report.results:
        if only_matched and not getattr(r, "is_reversal_setup", False):
            continue

        setup_str = r.setup_type.value if r.setup_type else "No Setup"
        rows.append(
            {
                "TradingSymbol": r.symbol,
                "SecurityID": r.security_id,
                "Setup Type": setup_str,
                "LTP (₹)": r.ltp,
                "HA Close": r.ha_close,
                "RSI (14)": r.rsi if r.rsi is not None else "-",
                "Entry Trigger (₹)": r.entry_price,
                "Structural Stop-Loss (₹)": r.stop_loss,
                "Risk per Share (₹)": r.risk_per_share,
                "Initial 1R Target (₹)": r.target_1r,
                "Target 2R (₹)": r.target_2r,
                "Prior Red HA Bars": r.prior_red_ha_count,
                "Signal": r.candle_signal,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """CLI runner for HA_ST01 Heikin Ashi + RSI Reversal Scanner."""
    parser = argparse.ArgumentParser(
        description="HA_ST01: Heikin Ashi + RSI Bullish Reversal Scanner (DhanHQ)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "NIFTY_MIDCAP_100", "NIFTY_SMALLCAP_100", "ALL_F_AND_O"],
        help="Target stock universe (Default: NIFTY_100)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1D",
        choices=["1D", "2H", "1H"],
        help="Candle timeframe (Default: 1D)",
    )
    parser.add_argument(
        "--setup-filter",
        type=str,
        default="ALL",
        choices=["ALL", "DIVERGENCE_ONLY", "OVERSOLD_ONLY"],
        help="Filter by setup type (Default: ALL)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent worker threads (Default: 4)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="bullish_reversal_candidates.csv",
        help="Export scan results to CSV file (Default: bullish_reversal_candidates.csv)",
    )
    parser.add_argument(
        "--only-matched",
        action="store_true",
        help="Show only matching reversal setups",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n🚀 Initializing HA_ST01 Heikin Ashi + RSI Reversal Scanner...")
    print(f"   Universe: {args.universe} | Timeframe: {args.timeframe} | Workers: {args.workers}")

    scanner = HaSt01ReversalScanner()
    report = scanner.run(
        params={
            "universe": args.universe,
            "timeframe": args.timeframe,
            "setup_filter": args.setup_filter,
            "max_workers": args.workers,
        }
    )

    df = format_ha_st01_dataframe(report, only_matched=args.only_matched)

    print("\n" + "=" * 80)
    print(f"📊 {report.scanner_name} Results")
    print(f"   Total Scanned: {report.total_scanned} | Matched Candidates: {report.matched_count}")
    print("=" * 80)

    if df.empty:
        print("ℹ️  No matching reversal setups found for current criteria.")
    else:
        print(df.to_string(index=False))

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\n💾 Results exported to: {args.csv}")


if __name__ == "__main__":
    main()
