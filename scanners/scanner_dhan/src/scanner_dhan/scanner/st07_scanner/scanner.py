"""ST07: Monthly Heikin Ashi + 89 EMA Crossover Stock Scanner."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.st07_scanner.engine import analyze_st07_stock
from scanner_dhan.scanner.st07_scanner.models import St07ScanResult
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["MonthlyHeikinAshi89EmaScanner"]


@register_scanner
class MonthlyHeikinAshi89EmaScanner(BaseScanner):
    """Scans for Monthly Heikin Ashi Fresh Crossovers & Accumulation Pullbacks on rising 89 EMA."""

    id = "st07_monthly_ha_89ema"
    name = "Monthly Heikin Ashi + 89 EMA Crossover - ST07"
    description = (
        "Positional / Swing strategy on Monthly Heikin Ashi candles: "
        "Detects Fresh 89 EMA Crossovers & Accumulation Pullbacks with rising "
        "89 EMA and 21 EMA exit levels."
    )
    category = "Trend Following"
    icon = "trending-up"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description=(
                "Choose between Nifty 500 (Broad Market), Nifty 100, Nifty 50, "
                "Nifty Smallcap 100, or All F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks) ⭐"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="target_category",
            label="Scan Category Filter",
            param_type="select",
            default="ALL",
            description="Filter by specific ST07 trigger setup or show all candidates.",
            options=[
                {"value": "ALL", "label": "All Setups (Crossovers + Pullbacks)"},
                {
                    "value": "FRESH_CROSSOVER",
                    "label": "⚡ Fresh Crossover Only (HA Open < 89 EMA < HA Close)",
                },
                {
                    "value": "ACCUMULATION_PULLBACK",
                    "label": "🎯 Accumulation Pullback Only (HA Low ≤ 89 EMA ≤ HA Close)",
                },
            ],
        ),
        ScannerParameter(
            name="min_monthly_bars",
            label="Min Monthly History (Bars)",
            param_type="int",
            default=90,
            min_value=50,
            max_value=200,
            step=5,
            description="Minimum monthly candles required for stable 89 EMA calculation.",
        ),
        ScannerParameter(
            name="history_days",
            label="Daily Lookback (Days)",
            param_type="int",
            default=4500,
            min_value=1500,
            max_value=6000,
            step=250,
            description="Historical daily calendar days fetched to resample into monthly bars.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        universe_choice = str(p.get("universe", "NIFTY_100"))
        target_category = str(p.get("target_category", "ALL")).upper().strip()
        min_monthly_bars = int(p.get("min_monthly_bars", 90))
        history_days = int(p.get("history_days", 4500))

        # 1. Resolve Universe & Security IDs
        univ_name, symbols, sec_id_map = get_active_universe(universe_choice)

        # Merge with live scrip master mapping only if missing symbol IDs exist
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

        results: list[St07ScanResult] = []
        logger.info(
            "Running ST07 Monthly HA 89 EMA Scanner on %d symbols in %s...",
            len(symbols),
            univ_name,
        )

        for sym in symbols:
            sid = sec_id_map.get(sym)
            if not sid:
                continue

            try:
                # Fetch multi-year daily bars to resample to monthly candles
                daily_df = data_provider.fetch_daily_bars(security_id=sid, days=history_days)
                if daily_df.empty:
                    continue

                ltp_override = ltp_map.get(sid)

                res = analyze_st07_stock(
                    symbol=sym,
                    security_id=sid,
                    daily_or_monthly_df=daily_df,
                    is_already_monthly=False,
                    min_monthly_bars=min_monthly_bars,
                    ltp_override=ltp_override,
                )

                if res is not None:
                    # Apply Target Category Filter if specified
                    if target_category == "FRESH_CROSSOVER" and not res.is_fresh_crossover:
                        continue
                    if (
                        target_category == "ACCUMULATION_PULLBACK"
                        and not res.is_accumulation_pullback
                    ):
                        continue

                    results.append(res)
            except Exception as exc:
                logger.error("Error scanning %s (ID %s) for ST07: %s", sym, sid, exc)

        # Sort results: Fresh crossovers first, then Accumulation pullbacks,
        # then by nearest distance to 89 EMA
        results.sort(
            key=lambda r: (
                0 if r.is_fresh_crossover else (1 if r.is_accumulation_pullback else 2),
                abs(r.distance_pct),
            )
        )

        matched_count = sum(1 for r in results if r.is_at_support)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=self.name,
            total_scanned=len(symbols),
            matched_count=matched_count,
            results=results,
        )


def format_st07_dataframe(report: ScanReport, only_matched: bool = False) -> pd.DataFrame:
    """Format ST07 scan results into a clean, presentation-ready DataFrame."""
    rows = []
    for r in report.results:
        if only_matched and not getattr(r, "is_at_support", False):
            continue

        cat_str = r.scan_category.value if r.scan_category else "No Setup"
        rows.append(
            {
                "TradingSymbol": r.symbol,
                "SecurityID": r.security_id,
                "Scan Category": cat_str,
                "LTP (₹)": r.ltp,
                "Current HA Close": r.ha_close,
                "89 EMA": r.ema_89,
                "89 EMA Rising": "YES" if r.is_ema_89_rising else "NO",
                "Buy Trigger Price": r.buy_trigger_price,
                "Stop-Loss Level": r.stop_loss,
                "21 EMA (Exit Benchmark)": r.ema_21,
                "Distance to 89 EMA (%)": f"{r.distance_pct:+.2f}%",
                "Volume": r.volume,
                "RSI (14)": r.rsi if r.rsi is not None else "-",
                "Signal": r.candle_signal,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """CLI runner for ST07 Monthly Heikin Ashi + 89 EMA Crossover Scanner."""
    parser = argparse.ArgumentParser(
        description="ST07: Monthly Heikin Ashi + 89 EMA Crossover Scanner (DhanHQ)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="NIFTY_100",
        choices=["NIFTY_50", "NIFTY_100", "NIFTY_500", "NIFTY_SMALLCAP_100", "ALL_F_AND_O"],
        help="Target stock universe (Default: NIFTY_100)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default="ALL",
        choices=["ALL", "FRESH_CROSSOVER", "ACCUMULATION_PULLBACK"],
        help="Filter by setup category (Default: ALL)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Export results to CSV file path (e.g. st07_results.csv)",
    )
    parser.add_argument(
        "--only-matched",
        action="store_true",
        help="Display only matched crossover / pullback candidates",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    scanner = MonthlyHeikinAshi89EmaScanner()
    report = scanner.run(params={"universe": args.universe, "target_category": args.category})

    df = format_st07_dataframe(report, only_matched=args.only_matched)

    time_str = report.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 105)
    print(f"  ST07: MONTHLY HEIKIN ASHI + 89 EMA SCANNER REPORT — {time_str}")
    print(
        f"  Universe: {args.universe} | Total Scanned: {report.total_scanned} | "
        f"Matched Setups: {report.matched_count}"
    )
    print("=" * 105)

    if df.empty:
        print("No stocks matched the specified ST07 criteria.")
    else:
        print(df.to_string(index=False))

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\n✅ Results exported successfully to {args.csv}")


if __name__ == "__main__":
    main()
