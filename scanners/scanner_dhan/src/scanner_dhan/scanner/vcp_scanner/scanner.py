"""Mark Minervini Volatility Contraction Pattern (VCP) BaseScanner Implementation."""

from __future__ import annotations

import concurrent.futures
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.st07_scanner.scrip_master import get_nse_equity_symbols_map
from scanner_dhan.scanner.vcp_scanner.engine import scan_stock_for_vcp
from scanner_dhan.scanner.vcp_scanner.models import (
    VcpScanResult,
    VcpStatus,
)
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["VcpScanner", "format_vcp_dataframe"]


def format_vcp_dataframe(
    results: List[VcpScanResult],
    only_matched: bool = False,
) -> pd.DataFrame:
    """Format VCP scan results into a clean presentation DataFrame."""
    columns = [
        "Symbol",
        "LTP (₹)",
        "Pivot (₹)",
        "Contractions",
        "Depth Progression",
        "Final Depth (%)",
        "VDU Ratio",
        "Status",
        "Stop Loss (₹)",
        "Target 1 (₹)",
        "Target 2 (₹)",
        "R:R",
        "RSI (14)",
    ]
    rows = []
    for r in results:
        s = r.setup
        if not s:
            if not only_matched:
                rows.append(
                    {
                        "Symbol": r.symbol,
                        "LTP (₹)": r.ltp,
                        "Pivot (₹)": "-",
                        "Contractions": "-",
                        "Depth Progression": "-",
                        "Final Depth (%)": "-",
                        "VDU Ratio": "-",
                        "Status": "NO_SETUP",
                        "Stop Loss (₹)": "-",
                        "Target 1 (₹)": "-",
                        "Target 2 (₹)": "-",
                        "R:R": "-",
                        "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
                    }
                )
            continue

        if only_matched and not r.is_at_support:
            continue

        seq_str = " → ".join(f"{d:.1f}%" for d in s.depth_sequence_pct)
        status_label = (
            "🔥 BREAKOUT"
            if s.status == VcpStatus.BREAKOUT_ACTIVE
            else "⚡ PRIMED"
            if s.status == VcpStatus.PRIMED_TIGHT
            else "⏳ FORMING"
        )

        rows.append(
            {
                "Symbol": r.symbol,
                "LTP (₹)": r.ltp,
                "Pivot (₹)": s.pivot_level,
                "Contractions": f"{s.contractions_count}T",
                "Depth Progression": seq_str,
                "Final Depth (%)": f"{s.final_depth_pct:.1f}%",
                "VDU Ratio": f"{s.vdu_ratio:.2f}x",
                "Status": status_label,
                "Stop Loss (₹)": s.stop_loss,
                "Target 1 (₹)": s.target_1,
                "Target 2 (₹)": s.target_2,
                "R:R": f"1:{s.risk_reward_ratio:.1f}" if s.risk_reward_ratio > 0 else "-",
                "RSI (14)": f"{r.rsi:.1f}" if r.rsi is not None else "-",
            }
        )
    return pd.DataFrame(rows, columns=columns)


@register_scanner
class VcpScanner(BaseScanner):
    """Mark Minervini Volatility Contraction Pattern (VCP) Institutional Scanner."""

    id = "vcp_contraction"
    name = "Volatility Contraction Pattern (VCP) Scanner"
    description = (
        "Scans for Mark Minervini's Stage 2 Volatility Contraction Patterns (VCP) with "
        "monotonic depth decay, Volume Dry-Up (VDU), and pivot breakout triggers."
    )
    category = "Momentum & Breakouts"
    icon = "activity"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_500",
            description="Target stock universe to scan for VCP contractions.",
            options=[
                {"value": "NIFTY_500", "label": "Nifty 500 (500 Stocks) ⭐"},
                {"value": "NIFTY_MIDCAP_100", "label": "Nifty Midcap 100 (100 Mid-Caps) 🚀"},
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Large-Caps)"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Blue-Chips)"},
                {"value": "FNO", "label": "F&O Active Stocks (~180)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Analysis Timeframe",
            param_type="select",
            default="Daily",
            description="Candle interval to analyze for base contraction cycles.",
            options=[
                {"value": "Daily", "label": "Daily (Swing Trades) ⭐"},
                {"value": "1Hour", "label": "1-Hour (Positional / Intraday)"},
            ],
        ),
        ScannerParameter(
            name="max_final_depth_pct",
            label="Maximum Final Contraction Depth (%)",
            param_type="float",
            default=6.5,
            description="Upper bound of allowed pullback depth for the rightmost wave.",
            min_value=2.0,
            max_value=12.0,
            step=0.5,
        ),
        ScannerParameter(
            name="vdu_threshold",
            label="Volume Dry-Up (VDU) Threshold Ratio",
            param_type="float",
            default=0.75,
            description="Maximum volume ratio in final wave compared to 50 SMA volume.",
            min_value=0.3,
            max_value=1.2,
            step=0.05,
        ),
        ScannerParameter(
            name="min_contractions",
            label="Minimum Contraction Waves",
            param_type="select",
            default="2",
            description="Minimum number of tightening waves (e.g. 2T, 3T, 4T).",
            options=[
                {"value": "2", "label": "2 Waves (2T+)"},
                {"value": "3", "label": "3 Waves (3T+ High Quality)"},
            ],
        ),
    ]

    def scan_symbol(
        self,
        symbol: str,
        security_id: str,
        params: Optional[Dict[str, Any]] = None,
        provider: Optional[DhanDataProvider] = None,
    ) -> VcpScanResult:
        """Scan a single symbol for VCP contraction setup."""
        if provider is None:
            provider = DhanDataProvider()

        params = params or {}
        timeframe = params.get("timeframe", "Daily")
        max_final_depth_pct = float(params.get("max_final_depth_pct", 6.5))
        vdu_threshold = float(params.get("vdu_threshold", 0.75))
        min_contractions = int(params.get("min_contractions", 2))

        return scan_stock_for_vcp(
            provider=provider,
            symbol=symbol,
            security_id=security_id,
            timeframe=timeframe,
            days=365,
            max_final_depth_pct=max_final_depth_pct,
            vdu_threshold=vdu_threshold,
            min_contractions=min_contractions,
        )

    def run(
        self,
        params: Optional[Dict[str, Any]] = None,
        provider: Optional[DhanDataProvider] = None,
    ) -> ScanReport:
        """Execute VCP scanner across selected stock universe."""
        if provider is None:
            provider = DhanDataProvider()

        params = params or {}
        universe_choice = str(params.get("universe", "NIFTY_500")).upper()
        univ_name, symbols, sec_map = get_active_universe(universe_choice)
        if not symbols:
            logger.warning("Empty universe '%s', falling back to NIFTY_500", universe_choice)
            univ_name, symbols, sec_map = get_active_universe("NIFTY_500")

        # Fallback scrip map if needed
        try:
            extra_sec_map = get_nse_equity_symbols_map()
            for k, v in extra_sec_map.items():
                if k not in sec_map:
                    sec_map[k] = v
        except Exception:
            pass

        scrip_list: List[tuple[str, str]] = []
        for sym in symbols:
            clean_sym = str(sym).strip().upper()
            sec_id = sec_map.get(clean_sym, clean_sym)
            scrip_list.append((clean_sym, sec_id))

        logger.info(
            "Starting VCP Contraction scan on %d symbols (%s, %s)",
            len(scrip_list),
            univ_name,
            params.get("timeframe", "Daily"),
        )

        results: List[VcpScanResult] = []
        max_workers = min(12, len(scrip_list)) if scrip_list else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {
                executor.submit(self.scan_symbol, sym, sec_id, params, provider): sym
                for sym, sec_id in scrip_list
            }
            for future in concurrent.futures.as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    logger.error("Scan failed for %s: %s", sym, exc)
                    results.append(
                        VcpScanResult(
                            symbol=sym,
                            security_id="",
                            error=str(exc),
                        )
                    )

        # Filter for valid VCP setups
        matched_results = [r for r in results if r.has_setup and r.setup is not None]
        # Sort by: Primed & Breakout first, then lowest final contraction depth
        matched_results.sort(
            key=lambda r: (
                0 if r.setup.status in (VcpStatus.BREAKOUT_ACTIVE, VcpStatus.PRIMED_TIGHT) else 1,
                r.setup.final_depth_pct if r.setup else 999.0,
            )
        )
        matched_count = len(matched_results)

        logger.info(
            "VCP Contraction scan completed. Total Scanned: %d | Matched VCPs: %d",
            len(results),
            matched_count,
        )

        return ScanReport(
            scanner_id=self.id,
            scanner_name=self.name,
            timestamp=datetime.now(),
            total_scanned=len(results),
            matched_count=matched_count,
            results=[r.to_dict() for r in matched_results],
        )

