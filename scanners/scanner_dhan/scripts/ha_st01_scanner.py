#!/usr/bin/env python3
"""HA_ST01: Daily Positional Heikin Ashi + RSI Reversal Scanner Script (DhanHQ SDK).

Scans NSE equities for Bullish Reversals (Long Setup) detecting Heikin Ashi color flips
following multi-bar downswings with RSI Oversold Recovery or Regular Bullish Divergence.

Usage:
    python scripts/ha_st01_scanner.py --universe NIFTY_100
    python scripts/ha_st01_scanner.py --universe NIFTY_500 --setup-filter DIVERGENCE_ONLY
    python scripts/ha_st01_scanner.py --universe ALL_F_AND_O --csv bullish_reversal_candidates.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.scanner.ha_st01_scanner import (  # noqa: E402
    HaSt01ReversalScanner,
    format_ha_st01_dataframe,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HA_ST01: Heikin Ashi + RSI Bullish Reversal Scanner (DhanHQ SDK)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "NIFTY_SMALLCAP_100", "ALL_F_AND_O"],
        help="Stock universe to scan (default: NIFTY_100)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1D",
        choices=["1D", "2H", "1H"],
        help="Candle timeframe (default: 1D)",
    )
    parser.add_argument(
        "--setup-filter",
        type=str,
        default="ALL",
        choices=["ALL", "DIVERGENCE_ONLY", "OVERSOLD_ONLY"],
        help="Filter by reversal setup type (default: ALL)",
    )
    parser.add_argument(
        "--oversold",
        type=float,
        default=35.0,
        help="RSI oversold threshold (default: 35.0)",
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
        default="bullish_reversal_candidates.csv",
        help="Export results to CSV path (default: bullish_reversal_candidates.csv)",
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
            "oversold_threshold": args.oversold,
            "max_workers": args.workers,
        }
    )

    df = format_ha_st01_dataframe(report, only_matched=args.only_matched)

    print("\n" + "=" * 80)
    print(f"📊 {report.scanner_name} Results ({report.timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"   Total Scanned: {report.total_scanned} | Reversal Setups: {report.matched_count}")
    print("=" * 80)

    if df.empty:
        print("ℹ️  No matching reversal setups found.")
    else:
        print(df.to_string(index=False))

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\n💾 Results exported to: {args.csv}")


if __name__ == "__main__":
    main()
