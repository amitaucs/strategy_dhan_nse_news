"""ST-14: Bullish CE Intraday Setup Scanner Implementation."""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.st14_scanner.engine import analyze_st14_stock
from scanner_dhan.scanner.st14_scanner.models import St14ScanResult, St14Status
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["BullishCeIntradayScanner", "format_st14_dataframe"]


def format_st14_dataframe(results: list[St14ScanResult], only_matched: bool = False) -> pd.DataFrame:
    """Format ST-14 scan results into a clean tabular DataFrame."""
    rows = []
    for r in results:
        if r.status == St14Status.NO_SETUP:
            continue
        if only_matched and r.status != St14Status.QUALIFIED:
            continue
        vol_display = f"{r.volume:,}" if r.volume else "-"
        angle_arrow = "↗" if r.is_vwap_rising else "↘"
        rows.append(
            {
                "Symbol": r.symbol,
                "LTP": f"₹{r.ltp:,.2f}",
                "Volume": vol_display,
                "VWAP": f"₹{r.vwap:,.2f}",
                "VWAP Dist (%)": f"{r.vwap_dist_pct:+.2f}%",
                "VWAP Angle": f"{r.vwap_angle_deg:.0f}° {angle_arrow}",
                "5H Breakout": "YES" if r.is_5h_breakout else "NO",
                "5D Breakout": "YES" if r.is_5d_breakout else "NO",
                "1H 20 EMA": f"₹{r.hourly_ema20:,.2f}",
                "Daily 20 EMA": f"₹{r.daily_ema20:,.2f}",
                "5H High": f"₹{r.five_hour_high:,.2f}",
                "5D High": f"₹{r.five_day_high:,.2f}",
                "Dist to 5H High (%)": f"{r.dist_to_5h_high_pct:+.2f}%",
                "Status": r.status.value,
                "Timing": "PASS" if r.timing_valid else "BLOCKED",
            }
        )
    return pd.DataFrame(rows)


@register_scanner
class BullishCeIntradayScanner(BaseScanner):
    """Screens NSE F&O universe for Daily trend alignment & 1H momentum breakouts (Bullish CE Setup)."""

    id = "st14_bullish_ce"
    name = "Bullish CE Intraday Setup - ST-14"
    description = (
        "Screens NSE Equity F&O stocks for Daily trend alignment (Close > 20 EMA, Close > 5D High) "
        "and 1-Hour momentum breakouts (1H Close > 20 EMA, 1H Close > 5H High, LTP near Rising VWAP). "
        "Valid entry execution starts after 10:15 AM IST."
    )
    category = "Options / Intraday Momentum"
    icon = "trending-up"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="ALL_F_AND_O",
            description="Target universe to scan: F&O Stocks (228+), Nifty 100, Nifty 50, or Nifty 500.",
            options=[
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (228 Stocks) ⭐"},
                {"value": "NIFTY_100", "label": "Nifty 100 (Top 100 Leaders)"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Liquid Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
            ],
        ),
        ScannerParameter(
            name="vwap_min_dist_pct",
            label="Min VWAP Distance (%)",
            param_type="float",
            default=-1.0,
            min_value=-5.0,
            max_value=2.0,
            step=0.5,
            description="Minimum allowed percentage distance from Intraday VWAP (e.g. -1.0%).",
        ),
        ScannerParameter(
            name="vwap_max_dist_pct",
            label="Max VWAP Distance (%)",
            param_type="float",
            default=5.0,
            min_value=0.5,
            max_value=10.0,
            step=0.5,
            description="Maximum allowed percentage distance above Intraday VWAP (e.g. +5.0%).",
        ),
        ScannerParameter(
            name="require_rising_vwap",
            label="Require Rising VWAP (~45° Angle)",
            param_type="bool",
            default=True,
            description="Requires Intraday VWAP to be ascending (positive slope) indicating institutional buying pressure.",
        ),
        ScannerParameter(
            name="enforce_timing",
            label="Enforce 10:15 AM Cutoff",
            param_type="bool",
            default=True,
            description="When enabled, requires execution timing to be >= 10:15 AM IST to bypass opening noise.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        """Execute ST-14 Bullish CE scan across selected stock universe."""
        p = {param.name: param.default for param in self.parameters}
        if params:
            p.update(params)

        universe_name = p.get("universe", "ALL_F_AND_O")
        vwap_min_dist_pct = float(p.get("vwap_min_dist_pct", -1.0))
        vwap_max_dist_pct = float(p.get("vwap_max_dist_pct", 5.0))
        require_rising_vwap = bool(p.get("require_rising_vwap", True))
        enforce_timing = bool(p.get("enforce_timing", True))
        daily_days = int(p.get("daily_history_days", 90))
        hourly_days = int(p.get("hourly_history_days", 20))
        max_workers = int(p.get("max_workers", 4))

        dhan_prov = provider or DhanDataProvider()
        _, symbols, sec_id_map = get_active_universe(universe_name)

        logger.info(
            "Starting ST-14 Bullish CE Scan on %d %s stocks (VWAP dist: %.1f%% to %.1f%%, Rising VWAP: %s, Enforce Timing: %s)",
            len(symbols),
            universe_name,
            vwap_min_dist_pct,
            vwap_max_dist_pct,
            require_rising_vwap,
            enforce_timing,
        )

        results: list[St14ScanResult] = []

        def _scan_stock(sym: str) -> St14ScanResult | None:
            sec_id = sec_id_map.get(sym)
            if not sec_id:
                return None
            try:
                # 1. Fetch Daily Candles
                df_daily = dhan_prov.fetch_daily_bars(
                    security_id=sec_id,
                    days=daily_days,
                )
                if df_daily.empty or len(df_daily) < 20:
                    return None

                # 2. Fetch 1-Hour Candles
                df_hourly = dhan_prov.fetch_1h_bars(
                    security_id=sec_id,
                    days=hourly_days,
                )
                if df_hourly.empty or len(df_hourly) < 20:
                    return None

                # 3. Technical & Momentum Evaluation
                res = analyze_st14_stock(
                    symbol=sym,
                    security_id=sec_id,
                    df_daily=df_daily,
                    df_hourly=df_hourly,
                    ema_period=20,
                    total_window_bars=5,
                    vwap_min_dist_pct=vwap_min_dist_pct,
                    vwap_max_dist_pct=vwap_max_dist_pct,
                    require_rising_vwap=require_rising_vwap,
                    enforce_timing=enforce_timing,
                )
                return res
            except Exception as exc:
                logger.debug("Error scanning %s in ST-14: %s", sym, exc)
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {executor.submit(_scan_stock, sym): sym for sym in symbols}
            for future in concurrent.futures.as_completed(future_to_sym):
                res = future.result()
                if res and res.status != St14Status.NO_SETUP:
                    results.append(res)

        # Sort: Qualified triggers first, then Watchlist, then by proximity to breakout high
        status_priority = {
            St14Status.QUALIFIED: 0,
            St14Status.WATCHLIST: 1,
            St14Status.NO_SETUP: 2,
        }
        results.sort(key=lambda r: (status_priority.get(r.status, 3), abs(r.vwap_dist_pct)))

        matched_count = sum(1 for r in results if r.status == St14Status.QUALIFIED)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=self.name,
            total_scanned=len(symbols),
            matched_count=matched_count,
            results=results,
        )


def main() -> None:
    """CLI Entry point for ST-14 Bullish CE Scanner."""
    parser = argparse.ArgumentParser(description="ST-14: Bullish CE Intraday Setup Scanner")
    parser.add_argument(
        "--universe",
        default="ALL_F_AND_O",
        choices=["ALL_F_AND_O", "NIFTY_100", "NIFTY_50", "NIFTY_500"],
        help="Target stock universe (default: ALL_F_AND_O)",
    )
    parser.add_argument("--vwap-min", type=float, default=-1.0, help="Min VWAP Distance % (default: -1.0)")
    parser.add_argument("--vwap-max", type=float, default=5.0, help="Max VWAP Distance % (default: 5.0)")
    parser.add_argument("--bypass-timing", action="store_true", help="Bypass 10:15 AM IST timing cutoff")
    parser.add_argument("--matched-only", action="store_true", help="Display only QUALIFIED triggers")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent workers (default: 4)")
    args = parser.parse_args()

    scanner = BullishCeIntradayScanner()
    report = scanner.run(
        params={
            "universe": args.universe,
            "vwap_min_dist_pct": args.vwap_min,
            "vwap_max_dist_pct": args.vwap_max,
            "enforce_timing": not args.bypass_timing,
            "max_workers": args.workers,
        }
    )

    df = format_st14_dataframe(report.results, only_matched=args.matched_only)
    print(f"\n⚡ {report.scanner_name}")
    print(f"📊 Total Scanned: {report.total_scanned} | 🎯 Qualified Triggers: {report.matched_count}\n")
    if df.empty:
        print("ℹ️ No stocks matched the selected criteria.")
    else:
        try:
            from tabulate import tabulate

            print(tabulate(df, headers="keys", tablefmt="fancy_grid", showindex=False))
        except ImportError:
            print(df.to_string(index=False))


if __name__ == "__main__":
    main()
