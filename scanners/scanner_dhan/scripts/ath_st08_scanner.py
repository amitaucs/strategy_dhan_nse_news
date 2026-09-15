#!/usr/bin/env python3
"""ATH-ST08: Monthly All-Time High Breakout Scanner Script (DhanHQ SDK).

Scans NSE universe for Primary Monthly All-Time High Breakouts across complete listing history
with >30m Base Classification, Exhaustion Filter, 30-Week SMA exit benchmark, and CSV export.

Usage:
    python scripts/ath_st08_scanner.py --universe NIFTY_100
    python scripts/ath_st08_scanner.py --universe NIFTY_500 --class-filter A_CLASS_ONLY
    python scripts/ath_st08_scanner.py --universe ALL_F_AND_O --csv ath_results.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.scanner.ath_st08_scanner import (  # noqa: E402
    MonthlyAthBreakoutScanner,
    format_ath_dataframe,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ATH-ST08: Monthly All-Time High Breakout Scanner (DhanHQ SDK)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "NIFTY_SMALLCAP_100", "ALL_F_AND_O"],
        help="Stock universe to scan (default: NIFTY_100)",
    )
    parser.add_argument(
        "--class-filter",
        type=str,
        default="ALL",
        choices=["ALL", "A_CLASS_ONLY", "B_CLASS_ONLY"],
        help="Filter by setup class (default: ALL)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of concurrent worker threads (default: 6)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="Export results to CSV file path (e.g. data/ath_scan.csv)",
    )
    parser.add_argument(
        "--only-matched",
        action="store_true",
        help="Display only matched breakout candidates",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n🚀 Initializing ATH-ST08 Monthly All-Time High Breakout Scanner...")
    print(f"   Universe: {args.universe} | Class: {args.class_filter} | Workers: {args.workers}")

    scanner = MonthlyAthBreakoutScanner()
    report = scanner.run(
        params={
            "universe": args.universe,
            "target_class": args.class_filter,
            "max_workers": args.workers,
        }
    )

    df = format_ath_dataframe(report, only_matched=args.only_matched)

    time_str = report.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 115)
    print(f"  ATH-ST08: MONTHLY ALL-TIME HIGH BREAKOUT REPORT — {time_str}")
    print(
        f"  Universe: {args.universe} | Total Scanned: {report.total_scanned} | "
        f"Matched Breakouts: {report.matched_count}"
    )
    print("=" * 115)

    if df.empty:
        print("No stocks currently matching ATH-ST08 breakout criteria.")
    else:
        print(df.to_string(index=False))

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        print(f"\n✅ Results exported successfully to {csv_path}")


if __name__ == "__main__":
    main()
