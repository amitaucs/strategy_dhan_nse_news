#!/usr/bin/env python3
"""ATH-ST08: Monthly All-Time High Breakout Scanner Example."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from scanner_dhan.scanner.ath_st08_scanner import MonthlyAthBreakoutScanner  # noqa: E402


def main() -> None:
    scanner = MonthlyAthBreakoutScanner()
    report = scanner.run(params={"universe": "NIFTY_50"})
    print(report.to_cli_table(only_at_support=True))


if __name__ == "__main__":
    main()
