#!/usr/bin/env python3
"""Example: Running the HA_ST01 Daily Heikin Ashi + RSI Reversal Strategy Scanner."""

from scanner_dhan.scanner.ha_st01_scanner import (
    HaSt01ReversalScanner,
    format_ha_st01_dataframe,
)


def main() -> None:
    scanner = HaSt01ReversalScanner()
    report = scanner.run(
        params={
            "universe": "NIFTY_100",
            "timeframe": "1D",
            "setup_filter": "ALL",
            "max_workers": 4,
        }
    )

    df = format_ha_st01_dataframe(report, only_matched=True)
    print(f"Scanned {report.total_scanned} stocks. Found {report.matched_count} reversal setups.")
    if not df.empty:
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
