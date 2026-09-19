"""ATH-ST08: Monthly All-Time High (ATH) Breakout Scanner."""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.ath_st08_scanner.engine import analyze_ath_stock
from scanner_dhan.scanner.ath_st08_scanner.models import AthBreakoutScanResult, AthClass
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.wick_filter import get_wick_parameter
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["MonthlyAthBreakoutScanner", "format_ath_dataframe"]


@register_scanner
class MonthlyAthBreakoutScanner(BaseScanner):
    """Scans for Monthly All-Time High (ATH) Breakouts with base duration & exhaustion filtering."""

    id = "ath_st08_breakout"
    name = "Monthly All-Time High Breakout - ATH-ST08"
    description = (
        "Scans NSE equities for Monthly All-Time High Breakouts across complete "
        "historical data with >30m Base Classification, Exhaustion Filter, and 30-Week SMA "
        "exit levels."
    )
    category = "Breakout / Momentum"
    icon = "award"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description=(
                "Target universe: Nifty 500 (Broad Market), Nifty 100, Nifty 50, "
                "Smallcap 100, or All F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks) ⭐"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_MIDCAP_100", "label": "Nifty Midcap 100 (100 Mid-Caps) 🚀"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Small-Caps) 🎯"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="target_class",
            label="Setup Class Filter",
            param_type="select",
            default="ALL",
            description="Filter by base consolidation duration (A-Class >30m vs B-Class <=30m).",
            options=[
                {"value": "ALL", "label": "All ATH Breakouts (A-Class + B-Class)"},
                {
                    "value": "A_CLASS_ONLY",
                    "label": "🏆 A-Class Only (>30 Months Base Consolidation ⭐)",
                },
                {
                    "value": "B_CLASS_ONLY",
                    "label": "⚡ B-Class Only (≤30 Months Base Consolidation)",
                },
            ],
        ),
        get_wick_parameter(default="NA"),
        ScannerParameter(
            name="max_exhaustion_ratio",
            label="Max Exhaustion Ratio (x)",
            param_type="float",
            default=2.5,
            min_value=1.5,
            max_value=4.0,
            step=0.1,
            description="Max allowed candle range expansion ratio vs 12M average range.",
        ),
        ScannerParameter(
            name="history_days",
            label="Historical Lookback (Days)",
            param_type="int",
            default=7500,
            min_value=3000,
            max_value=9000,
            step=500,
            description="Calendar days fetched to capture full listing history for ATH evaluation.",
        ),
        ScannerParameter(
            name="max_workers",
            label="Concurrent Workers",
            param_type="int",
            default=4,
            min_value=1,
            max_value=8,
            step=1,
            description="Number of parallel worker threads for accelerated scanning.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        universe_choice = str(p.get("universe", "NIFTY_100"))
        target_class = str(p.get("target_class", "ALL")).upper().strip()
        max_exhaustion_ratio = float(p.get("max_exhaustion_ratio", 2.5))
        history_days = int(p.get("history_days", 7500))
        max_workers = int(p.get("max_workers", 4))
        max_wick_pct = p.get("max_wick_pct", "NA")

        # 1. Resolve Universe & Security IDs
        univ_name, symbols, sec_id_map = get_active_universe(universe_choice)

        missing_syms = [s for s in symbols if s not in sec_id_map]
        if missing_syms:
            master_map = get_nse_equity_symbols_map()
            for sym in missing_syms:
                if sym in master_map:
                    sec_id_map[sym] = master_map[sym]

        data_provider = provider or DhanDataProvider()

        # 2. Fetch Latest LTPs in batch
        valid_sids = [sec_id_map[s] for s in symbols if s in sec_id_map]
        ltp_map = data_provider.fetch_ltp_batch(valid_sids)

        results: list[AthBreakoutScanResult] = []
        logger.info(
            "Running ATH-ST08 Breakout Scanner on %d symbols in %s with %d workers...",
            len(symbols),
            univ_name,
            max_workers,
        )

        def _scan_single_stock(sym: str) -> AthBreakoutScanResult | None:
            sid = sec_id_map.get(sym)
            if not sid:
                return None
            try:
                daily_df = data_provider.fetch_daily_bars(security_id=sid, days=history_days)
                if daily_df.empty:
                    return None

                ltp_override = ltp_map.get(sid)
                return analyze_ath_stock(
                    symbol=sym,
                    security_id=sid,
                    daily_df=daily_df,
                    ltp_override=ltp_override,
                    min_monthly_bars=12,
                    max_exhaustion_ratio=max_exhaustion_ratio,
                    max_wick_pct=max_wick_pct,
                )
            except Exception as exc:
                logger.error("Error scanning %s for ATH-ST08: %s", sym, exc)
                return None

        # Execute parallel scans
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {executor.submit(_scan_single_stock, s): s for s in symbols}
            for future in concurrent.futures.as_completed(future_to_symbol):
                res = future.result()
                if res is not None:
                    # Apply setup class filter if specified
                    if target_class == "A_CLASS_ONLY" and res.ath_class != AthClass.A_CLASS:
                        continue
                    if target_class == "B_CLASS_ONLY" and res.ath_class != AthClass.B_CLASS:
                        continue

                    results.append(res)

        # Sort results: A-Class breakouts first, then B-Class, then nearest distance to ATH
        results.sort(
            key=lambda r: (
                0
                if r.ath_class == AthClass.A_CLASS
                else (1 if r.ath_class == AthClass.B_CLASS else 2),
                -r.months_in_consolidation if r.is_ath_breakout else -abs(r.distance_pct),
            )
        )

        matched_count = sum(1 for r in results if r.is_ath_breakout)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=self.name,
            total_scanned=len(symbols),
            matched_count=matched_count,
            results=results,
        )


def format_ath_dataframe(report: ScanReport, only_matched: bool = False) -> pd.DataFrame:
    """Format ATH-ST08 scan results into a presentation-ready DataFrame."""
    rows = []
    for r in report.results:
        if only_matched and not getattr(r, "is_ath_breakout", False):
            continue

        class_str = r.ath_class.value if r.ath_class else "No Setup"
        rows.append(
            {
                "TradingSymbol": r.symbol,
                "SecurityID": r.security_id,
                "Setup Class": class_str,
                "LTP (₹)": r.ltp,
                "Prior ATH Level (₹)": r.prior_ath_price,
                "Prior ATH Date": r.prior_ath_date,
                "Months in Consolidation": r.months_in_consolidation,
                "Recommended Entry Trigger (High + 1%)": r.trigger_entry_price,
                "30-Week SMA Level": r.sma_30_week,
                "Expansion Ratio": f"{r.range_expansion_ratio:.2f}x",
                "Distance to Prior ATH (%)": f"{r.distance_pct:+.2f}%",
                "Volume": r.volume,
                "RSI (14)": r.rsi if r.rsi is not None else "-",
                "Signal": r.candle_signal,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """CLI runner for ATH-ST08 Monthly All-Time High Breakout Scanner."""
    parser = argparse.ArgumentParser(
        description="ATH-ST08: Monthly All-Time High (ATH) Breakout Scanner (DhanHQ)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "NIFTY_MIDCAP_100", "NIFTY_SMALLCAP_100", "ALL_F_AND_O"],
        help="Target stock universe (Default: NIFTY_100)",
    )
    parser.add_argument(
        "--class-filter",
        type=str,
        default="ALL",
        choices=["ALL", "A_CLASS_ONLY", "B_CLASS_ONLY"],
        help="Filter by setup class (Default: ALL)",
    )
    parser.add_argument(
        "--max-wick-pct",
        type=str,
        default="NA",
        choices=["NA", "20", "30", "40", "50"],
        help="Max allowed opposing rejection wick percentage (Default: NA)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of concurrent worker threads (Default: 6)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Export scan results to CSV file (e.g. ath_st08_results.csv)",
    )
    parser.add_argument(
        "--only-matched",
        action="store_true",
        help="Display only matched breakout stocks",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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
        df.to_csv(args.csv, index=False)
        print(f"\n✅ Results exported successfully to {args.csv}")


if __name__ == "__main__":
    main()
