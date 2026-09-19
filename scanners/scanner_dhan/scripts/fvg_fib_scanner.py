#!/usr/bin/env python3
"""Fair Value Gap (FVG) + 0.618 Fibonacci Retracement Confluence CLI Scanner (DhanHQ SDK).

Usage:
    python scripts/fvg_fib_scanner.py --universe NIFTY_100 --timeframe Daily
    python scripts/fvg_fib_scanner.py --universe NIFTY_500 --direction BULLISH_ONLY
    python scripts/fvg_fib_scanner.py --universe FNO --csv fvg_fib_results.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
import pandas as pd

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.scanner.fvg_fibonacci import (  # noqa: E402
    FvgFibonacciScanner,
    format_fvg_fib_dataframe,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Money Concepts (SMC) FVG + 0.618 Fibonacci Retracement Confluence Scanner"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "FNO", "NIFTY_MIDCAP_100"],
        help="Stock universe to scan (default: NIFTY_100)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="Daily",
        choices=["Daily", "1Hour", "15Min"],
        help="Analysis timeframe (default: Daily)",
    )
    parser.add_argument(
        "--direction",
        type=str,
        default="ALL",
        choices=["ALL", "BULLISH_ONLY", "BEARISH_ONLY"],
        help="Trade direction filter (default: ALL)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.5,
        help="Distance tolerance (%) to 0.618 Fib (default: 1.5)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="Export results to CSV file path (e.g. data/fvg_fib_scan.csv)",
    )
    parser.add_argument(
        "--only-matched",
        action="store_true",
        help="Display only stocks currently at active 0.618 pullback confluence",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("================================================================================")
    print("⚡ Smart Money Concepts (SMC): Fair Value Gap + 0.618 Fib Confluence Scanner")
    print(f"📊 Universe: {args.universe} | Timeframe: {args.timeframe} | Direction: {args.direction}")
    print("================================================================================")

    scanner = FvgFibonacciScanner()
    report = scanner.run(
        params={
            "universe": args.universe,
            "timeframe": args.timeframe,
            "direction": args.direction,
            "confluence_tolerance_pct": args.tolerance,
        }
    )

    print(f"\n✅ Scan Completed! Scanned: {report.total_scanned} | Pullback Ready: {report.matched_count}")

    # Build DataFrame
    df = pd.DataFrame(report.results)
    if not df.empty:
        df_display = df[
            [
                "symbol",
                "ltp",
                "support_desc",
                "confluence_price",
                "distance_pct",
                "volume",
                "rsi",
                "candle_signal",
                "target_1",
                "stop_loss",
                "risk_reward_ratio",
            ]
        ]
        if args.only_matched:
            df_display = df_display[df["is_at_support"] == True]  # noqa: E712

        print("\n" + df_display.to_string(index=False))

        if args.csv:
            csv_path = Path(args.csv)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(csv_path, index=False)
            print(f"\n💾 Results exported to {csv_path.resolve()}")


if __name__ == "__main__":
    main()

