#!/usr/bin/env python3
"""ST-14: Bullish CE Intraday Setup Scanner Script (DhanHQ SDK v2).

Screens the NSE Equity F&O stock universe for Daily trend alignment and 1-Hour momentum breakouts.
Evaluates:
  Daily:
    1. Daily Close > Daily 20-period EMA
    2. Daily Close > 5-Day High (Close > max(High[-1]..High[-5]))
  Hourly (1H):
    1. 1H Close > 1H 20-period EMA
    2. 1H Close > 5-Hour High (Close > max(High[-1]..High[-5]))
    3. Intraday VWAP Proximity (-1.0% to +5.0%) & Ascending Slope (~45° angle)
  Timing:
    Valid entry execution window begins after 10:15 AM IST.

Usage:
    python scripts/st14_scanner.py
    python scripts/st14_scanner.py --universe ALL_F_AND_O --vwap-min -1.0 --vwap-max 5.0
    python scripts/st14_scanner.py --matched-only --csv data/st14_bullish_ce.csv
    python scripts/st14_scanner.py --bypass-timing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.st14_scanner import (
    BullishCeIntradayScanner,
    St14ScanResult,
    St14Status,
    analyze_st14_stock,
    check_timing_constraint,
    evaluate_bullish_conditions,
    format_st14_dataframe,
)
from scanner_dhan.universe import FNO_SECURITY_IDS, FNO_SYMBOLS, get_active_universe, resolve_fno_securities


def get_fo_universe() -> tuple[list[str], dict[str, str]]:
    """Load security IDs and symbols for the active NSE F&O universe."""
    symbols = FNO_SYMBOLS
    sec_id_map = resolve_fno_securities()
    return symbols, sec_id_map


def run_scanner(
    universe: str = "ALL_F_AND_O",
    vwap_min_dist_pct: float = -1.0,
    vwap_max_dist_pct: float = 5.0,
    require_rising_vwap: bool = True,
    enforce_timing: bool = True,
    workers: int = 4,
    provider: DhanDataProvider | None = None,
) -> tuple[pd.DataFrame, list[St14ScanResult]]:
    """Main orchestrator for ST-14 Bullish CE Setup Scanner."""
    scanner = BullishCeIntradayScanner()
    report = scanner.run(
        params={
            "universe": universe,
            "vwap_min_dist_pct": vwap_min_dist_pct,
            "vwap_max_dist_pct": vwap_max_dist_pct,
            "require_rising_vwap": require_rising_vwap,
            "enforce_timing": enforce_timing,
            "max_workers": workers,
        },
        provider=provider,
    )
    df = format_st14_dataframe(report.results)
    return df, report.results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ST-14: Bullish CE Intraday Setup Scanner (DhanHQ SDK v2)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="ALL_F_AND_O",
        choices=["ALL_F_AND_O", "NIFTY_100", "NIFTY_50", "NIFTY_500"],
        help="Stock universe to scan (default: ALL_F_AND_O)",
    )
    parser.add_argument(
        "--vwap-min",
        type=float,
        default=-1.0,
        help="Minimum Intraday VWAP Distance % (default: -1.0)",
    )
    parser.add_argument(
        "--vwap-max",
        type=float,
        default=5.0,
        help="Maximum Intraday VWAP Distance % (default: 5.0)",
    )
    parser.add_argument(
        "--bypass-timing",
        action="store_true",
        help="Bypass the 10:15 AM IST timing filter",
    )
    parser.add_argument(
        "--matched-only",
        action="store_true",
        help="Display only QUALIFIED triggers",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent worker threads (default: 4)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="Path to export results as CSV (e.g. data/st14_scan.csv)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()

    print("=" * 80)
    print("🚀 ST-14: BULLISH CE INTRADAY SETUP SCANNER (DhanHQ SDK v2)")
    print("=" * 80)
    print(f"📊 Universe:          {args.universe}")
    print(f"📈 Daily Filters:     Close > 20 EMA  |  Close > 5-Day High")
    print(f"⚡ 1H Filters:        1H Close > 20 EMA | 1H Close > 5-Hour High | VWAP [{args.vwap_min:+.1f}% to {args.vwap_max:+.1f}%]")
    
    is_valid_timing, timing_msg = check_timing_constraint()
    print(f"⏰ Execution Timing:  {'Bypassed (--bypass-timing)' if args.bypass_timing else timing_msg}")
    print("=" * 80)

    start_time = time.time()
    try:
        provider = DhanDataProvider(client_id=client_id, access_token=access_token) if (client_id and access_token) else None
        df, results = run_scanner(
            universe=args.universe,
            vwap_min_dist_pct=args.vwap_min,
            vwap_max_dist_pct=args.vwap_max,
            enforce_timing=not args.bypass_timing,
            workers=args.workers,
            provider=provider,
        )
    except Exception as exc:
        print(f"\n❌ Scanner execution error: {exc}")
        sys.exit(1)

    elapsed = time.time() - start_time
    qualified = [r for r in results if r.status == St14Status.QUALIFIED]
    watchlist = [r for r in results if r.status == St14Status.WATCHLIST]

    print(f"\n✅ Scan Completed in {elapsed:.1f}s")
    print(f"🎯 Total Evaluated:  {len(results)}")
    print(f"🚀 QUALIFIED CE:     {len(qualified)}")
    print(f"👀 WATCHLIST:        {len(watchlist)}\n")

    display_df = format_st14_dataframe(results, only_matched=args.matched_only)

    if display_df.empty:
        print("ℹ️ No candidates matched the specified criteria.")
    else:
        try:
            from tabulate import tabulate

            print(tabulate(display_df, headers="keys", tablefmt="fancy_grid", showindex=False))
        except ImportError:
            print(display_df.to_string(index=False))

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        display_df.to_csv(csv_path, index=False)
        print(f"\n📁 Exported {len(display_df)} rows to: {csv_path}")


if __name__ == "__main__":
    main()
