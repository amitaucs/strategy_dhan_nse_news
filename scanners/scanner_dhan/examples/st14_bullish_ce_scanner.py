#!/usr/bin/env python3
"""Example demonstration of the ST-14 Bullish CE Intraday Scanner using DhanHQ SDK.

Run standalone to screen NSE F&O stocks with custom thresholds:
    python examples/st14_bullish_ce_scanner.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.st14_scanner import (
    BullishCeIntradayScanner,
    format_st14_dataframe,
)


def main() -> None:
    print("=" * 75)
    print("🚀 ST-14: Bullish CE Intraday Setup Example Scanner (VWAP & 20 EMA)")
    print("=" * 75)

    scanner = BullishCeIntradayScanner()
    report = scanner.run(
        params={
            "universe": "NIFTY_50",  # Test on Nifty 50 liquid stocks for fast demo
            "vwap_min_dist_pct": -1.0,
            "vwap_max_dist_pct": 5.0,
            "require_rising_vwap": True,
            "enforce_timing": False,  # Allow demo execution at any hour
            "max_workers": 4,
        }
    )

    df = format_st14_dataframe(report.results)
    print(f"\n📊 Total Scanned: {report.total_scanned} | 🎯 Qualified Triggers: {report.matched_count}\n")

    if df.empty:
        print("No stocks matched the setup.")
    else:
        try:
            from tabulate import tabulate

            print(tabulate(df, headers="keys", tablefmt="fancy_grid", showindex=False))
        except ImportError:
            print(df.to_string(index=False))


if __name__ == "__main__":
    main()
