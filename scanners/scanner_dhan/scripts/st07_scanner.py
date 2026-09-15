#!/usr/bin/env python3
"""ST07: Monthly Heikin Ashi + 89 EMA Crossover Stock Scanner (DhanHQ).

Executes the Monthly Heikin Ashi + 89 EMA strategy across NSE Equities (Nifty 500, Nifty 100,
Nifty 50, Smallcap 100, All F&O) with 21 EMA exit benchmarking and CSV export.

Usage:
    python scripts/st07_scanner.py --universe NIFTY_100
    python scripts/st07_scanner.py --universe NIFTY_500 --category FRESH_CROSSOVER
    python scripts/st07_scanner.py --universe ALL_F_AND_O --csv st07_results.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.scanner.st07_scanner import (  # noqa: E402
    MonthlyHeikinAshi89EmaScanner,
    format_st07_dataframe,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ST07: Monthly Heikin Ashi + 89 EMA Crossover Scanner (DhanHQ SDK)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "NIFTY_SMALLCAP_100", "ALL_F_AND_O"],
        help="Stock universe to scan (default: NIFTY_100)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default="ALL",
        choices=["ALL", "FRESH_CROSSOVER", "ACCUMULATION_PULLBACK"],
        help="Filter by setup category (default: ALL)",
    )
    parser.add_argument(
        "--min-bars",
        type=int,
        default=90,
        help="Minimum monthly bars required for EMA calculation (default: 90)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="Export results to CSV file path (e.g. data/st07_scan.csv)",
    )
    parser.add_argument(
        "--only-matched",
        action="store_true",
        help="Display only matched crossover / pullback candidates",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n🚀 Initializing ST07 Monthly HA 89 EMA Scanner...")
    print(f"   Universe: {args.universe} | Category Filter: {args.category}")

    scanner = MonthlyHeikinAshi89EmaScanner()
    report = scanner.run(
        params={
            "universe": args.universe,
            "target_category": args.category,
            "min_monthly_bars": args.min_bars,
        }
    )

    df = format_st07_dataframe(report, only_matched=args.only_matched)

    time_str = report.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 110)
    print(f"  ST07: MONTHLY HEIKIN ASHI + 89 EMA SCANNER REPORT — {time_str}")
    print(
        f"  Universe: {args.universe} | Total Scanned: {report.total_scanned} | "
        f"Matched Setups: {report.matched_count}"
    )
    print("=" * 110)

    if df.empty:
        print("No stocks matched the specified ST07 criteria.")
    else:
        print(df.to_string(index=False))

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        print(f"\n✅ Results exported successfully to {csv_path}")


if __name__ == "__main__":
    main()
