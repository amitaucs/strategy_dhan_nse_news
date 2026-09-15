#!/usr/bin/env python3
"""Executable Nifty 50 Support Level Scanner.

Scans all 50 Nifty constituents using DhanHQ API data to detect stocks trading
at or near critical support levels (Swing Lows, 50 EMA, 100/200 SMA, and Monthly Pivots).

Usage:
    python examples/nifty50_support_scanner.py
    python examples/nifty50_support_scanner.py --threshold 1.5 --all
    python examples/nifty50_support_scanner.py --csv data/support_scan.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.data.dhan_provider import DhanDataProvider  # noqa: E402
from scanner_dhan.scanner.nifty50_support_resistance import Nifty50Scanner  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan Nifty 50 stocks for key support levels using DhanHQ."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.0,
        help="Proximity threshold percentage to consider a stock 'At Support' (default: 2.0%%)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=150,
        help="Number of historical daily bars to analyze (default: 150 days)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all 50 stocks instead of filtering to only those at support",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="Save scan results to specified CSV path (e.g. data/support_scan.csv)",
    )

    args = parser.parse_args()

    print(
        f"\n🔍 Initializing Nifty 50 Support Scanner "
        f"(Threshold: ±{args.threshold}%, Lookback: {args.lookback} days)..."
    )

    try:
        provider = DhanDataProvider()
    except Exception as exc:
        print(f"\n❌ Error initializing Dhan provider: {exc}")
        print("💡 Ensure DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN are set in .env or environment.\n")
        sys.exit(1)

    scanner = Nifty50Scanner(
        provider=provider,
        threshold_pct=args.threshold,
        lookback_days=args.lookback,
    )

    def on_progress(current: int, total: int, sym: str) -> None:
        pct = (current / total) * 100
        print(
            f"\rScanning [{current:02d}/{total:02d}] ({pct:.0f}%): Fetching & Analyzing {sym:<12}",
            end="",
            flush=True,
        )

    report = scanner.scan(progress_callback=on_progress)
    print("\r" + " " * 70 + "\r", end="")  # Clear progress line

    # Print formatted ASCII table
    print(report.to_cli_table(only_at_support=not args.all))

    # Print TradingView watchlist string for easy copy-pasting
    matched_symbols = [r.symbol for r in report.results if r.is_at_support]
    if matched_symbols:
        print(f"\n📋 TradingView Watchlist ({len(matched_symbols)} symbols):")
        print(", ".join(matched_symbols))

    # Optional CSV export
    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df = report.to_dataframe(only_matched=False)
        df.to_csv(csv_path, index=False)
        print(f"\n💾 Full scan results saved to: {csv_path}")

    print(
        f"\n✅ Scan completed: {report.matched_count} out of {report.total_scanned} "
        "stocks currently near key support levels."
    )


if __name__ == "__main__":
    main()
