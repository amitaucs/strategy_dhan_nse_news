#!/usr/bin/env python3
"""Head & Shoulders and Inverse Head & Shoulders Pattern Scanner Script (DhanHQ SDK v2).

Screens the NSE universe for Classical Head & Shoulders (Bearish) and Inverse
Head & Shoulders (Bullish) reversal patterns using local extrema detection,
geometric symmetry rules, neckline breakout confirmation, and target projections.

Usage:
    python scripts/head_and_shoulders_scanner.py
    python scripts/head_and_shoulders_scanner.py --universe ALL_F_AND_O --pattern-type INVERSE_HS
    python scripts/head_and_shoulders_scanner.py --matched-only --csv data/hs_patterns.csv
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.head_and_shoulders import (
    ConfirmationStatus,
    HeadAndShouldersPattern,
    HeadAndShouldersScanResult,
    HeadAndShouldersScanner,
    PatternType,
    format_head_and_shoulders_dataframe,
)


def run_scanner(
    universe: str = "NIFTY_50",
    pattern_type: str = "ALL",
    status_filter: str = "ALL",
    order: int = 5,
    shoulder_tolerance: float = 0.03,
    lookback_days: int = 250,
    workers: int = 4,
    provider: DhanDataProvider | None = None,
) -> tuple[pd.DataFrame, list[HeadAndShouldersScanResult]]:
    """Main orchestrator for Head & Shoulders Scanner."""
    scanner = HeadAndShouldersScanner()
    report = scanner.run(
        params={
            "universe": universe,
            "pattern_type": pattern_type,
            "status_filter": status_filter,
            "order": order,
            "shoulder_tolerance": shoulder_tolerance,
            "lookback_days": lookback_days,
            "max_workers": workers,
        },
        provider=provider,
    )
    df = format_head_and_shoulders_dataframe(report.results)
    return df, report.results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Head & Shoulders and Inverse Head & Shoulders Pattern Scanner (DhanHQ SDK v2)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_50",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "ALL_F_AND_O"],
        help="Stock universe to scan (default: NIFTY_50)",
    )
    parser.add_argument(
        "--pattern-type",
        type=str,
        default="ALL",
        choices=["ALL", "REGULAR_HS", "INVERSE_HS"],
        help="Pattern type to filter (default: ALL)",
    )
    parser.add_argument(
        "--status",
        type=str,
        default="ALL",
        choices=["ALL", "CONFIRMED", "FORMING"],
        help="Confirmation status to filter (default: ALL)",
    )
    parser.add_argument(
        "--order",
        type=int,
        default=5,
        help="Window size for local extrema detection (default: 5)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.03,
        help="Shoulder height symmetry tolerance (default: 0.03 -> 3.0%%)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=250,
        help="Daily history lookback in days (default: 250)",
    )
    parser.add_argument(
        "--matched-only",
        action="store_true",
        help="Display only MATCHED patterns (FORMING or CONFIRMED)",
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
        help="Path to export results as CSV (e.g. data/hs_scan.csv)",
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
    print("👤 HEAD & SHOULDERS & INVERSE H&S PATTERN SCANNER (DhanHQ SDK v2)")
    print("=" * 80)
    print(f"📊 Universe:          {args.universe}")
    print(f"🔍 Pattern Type:      {args.pattern_type}")
    print(f"🎯 Status Filter:     {args.status}")
    print(f"📐 Extrema Order:     {args.order} candles | Symmetry Tol: {args.tolerance * 100:.1f}%")
    print(f"📅 Lookback:          {args.lookback} days | Workers: {args.workers}")
    print("=" * 80)

    start_time = time.time()
    try:
        provider = (
            DhanDataProvider(client_id=client_id, access_token=access_token)
            if (client_id and access_token)
            else None
        )
        df, results = run_scanner(
            universe=args.universe,
            pattern_type=args.pattern_type,
            status_filter=args.status,
            order=args.order,
            shoulder_tolerance=args.tolerance,
            lookback_days=args.lookback,
            workers=args.workers,
            provider=provider,
        )
    except Exception as exc:
        print(f"\n❌ Scanner execution error: {exc}")
        sys.exit(1)

    elapsed = time.time() - start_time
    confirmed = [r for r in results if r.status == ConfirmationStatus.CONFIRMED]
    forming = [r for r in results if r.status == ConfirmationStatus.FORMING]

    print(f"\n✅ Scan Completed in {elapsed:.1f}s")
    print(f"🎯 Total Evaluated:     {len(results)}")
    print(f"⚡ CONFIRMED Patterns:  {len(confirmed)}")
    print(f"👀 FORMING Patterns:    {len(forming)}\n")

    display_df = format_head_and_shoulders_dataframe(
        results, only_matched=args.matched_only
    )

    if display_df.empty:
        print("ℹ️ No candidates matched the specified criteria.")
    else:
        try:
            from tabulate import tabulate

            print(
                tabulate(
                    display_df,
                    headers="keys",
                    tablefmt="fancy_grid",
                    showindex=False,
                )
            )
        except ImportError:
            print(display_df.to_string(index=False))

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        display_df.to_csv(csv_path, index=False)
        print(f"\n📁 Exported {len(display_df)} rows to: {csv_path}")


if __name__ == "__main__":
    main()

