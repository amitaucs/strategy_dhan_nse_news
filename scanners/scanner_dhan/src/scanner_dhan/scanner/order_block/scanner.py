"""Smart Money Concepts (SMC) Institutional Order Block Scanner Implementation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.order_block.detector import analyze_stock_order_block
from scanner_dhan.scanner.order_block.models import (
    OrderBlockScanResult,
    OrderBlockType,
)
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["OrderBlockScanner"]


@register_scanner
class OrderBlockScanner(BaseScanner):
    """Detects Institutional Order Blocks with ATR Body Expansion and Volume Surge."""

    id = "order_block"
    name = "Institutional Order Block Scanner - Stockwiz"
    description = (
        "Detects Smart Money Concepts (SMC) Order Blocks formed by simultaneous price displacement "
        "(ATR body expansion) and institutional volume surge."
    )
    category = "Smart Money Concepts"
    icon = "box"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description=(
                "Choose between Nifty 500 (Broad Market), Nifty 100 (Default), Nifty 50, "
                "Nifty Smallcap 100, or All NSE F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_SMALLCAP_100", "label": "Nifty Smallcap 100 (100 Stocks)"},
                {"value": "ALL_F_AND_O", "label": "All F&O Stocks (215 Stocks)"},
            ],
        ),
        ScannerParameter(
            name="timeframe",
            label="Candle Timeframe",
            param_type="select",
            default="1D",
            description=(
                "Candle resolution: 1 Day (Daily), 2 Hours (120m), 1 Hour (60m), or 15 Minutes."
            ),
            options=[
                {"value": "1D", "label": "1 Day (Daily)"},
                {"value": "2H", "label": "2 Hours (120m)"},
                {"value": "1H", "label": "1 Hour (60m)"},
                {"value": "15M", "label": "15 Minutes"},
            ],
        ),
        ScannerParameter(
            name="block_type",
            label="Order Block Type",
            param_type="select",
            default="BULLISH",
            description="Filter for Bullish Demand OBs, Bearish Supply OBs, or All.",
            options=[
                {"value": "BULLISH", "label": "Bullish Demand OBs Only ⭐"},
                {"value": "BEARISH", "label": "Bearish Supply OBs Only"},
                {"value": "ALL", "label": "All Order Blocks (Demand & Supply)"},
            ],
        ),
        ScannerParameter(
            name="impulse_multiplier",
            label="Displacement / ATR Multiplier",
            param_type="float",
            default=1.5,
            min_value=1.0,
            max_value=3.5,
            step=0.1,
            description=(
                "Minimum candle body expansion over ATR(14) to qualify as institutional "
                "displacement."
            ),
        ),
        ScannerParameter(
            name="volume_multiplier",
            label="Volume Surge Multiplier",
            param_type="float",
            default=1.5,
            min_value=1.0,
            max_value=3.5,
            step=0.1,
            description="Minimum volume expansion over 20-period Volume SMA.",
        ),
        ScannerParameter(
            name="threshold_pct",
            label="OB Retest Proximity (%)",
            param_type="float",
            default=2.0,
            min_value=0.0,
            max_value=5.0,
            step=0.1,
            description="Max distance (%) from Order Block zone to qualify as 'Testing OB'.",
        ),
        ScannerParameter(
            name="lookback_days",
            label="Historical Lookback (Days)",
            param_type="int",
            default=100,
            min_value=30,
            max_value=250,
            step=10,
            description="Number of historical daily bars used to identify Order Blocks.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        universe_choice = str(p.get("universe", "NIFTY_100"))
        timeframe = str(p.get("timeframe", "1D")).upper()
        block_type_filter = str(p.get("block_type", "BULLISH")).upper()
        impulse_mult = float(p.get("impulse_multiplier", 1.5))
        vol_mult = float(p.get("volume_multiplier", 1.5))
        threshold_pct = float(p.get("threshold_pct", 2.0))
        lookback_days = int(p.get("lookback_days", 100))

        prov = provider or DhanDataProvider()
        universe_name, symbols, sec_map = get_active_universe(universe_choice)

        security_ids = [sec_map[sym] for sym in symbols if sym in sec_map]
        ltp_map = prov.fetch_ltp_batch(security_ids)

        scan_results: list[OrderBlockScanResult] = []

        for sym in symbols:
            sid = sec_map.get(sym, "")
            if not sid:
                continue

            df = prov.fetch_bars(sid, timeframe=timeframe, days=lookback_days)
            ltp = ltp_map.get(str(sid))

            scan = analyze_stock_order_block(
                df=df,
                symbol=sym,
                security_id=sid,
                ltp=ltp,
                threshold_pct=threshold_pct,
                impulse_multiplier=impulse_mult,
                volume_multiplier=vol_mult,
            )

            # Check block type filter
            is_matched = scan.is_at_order_block
            if scan.nearest_order_block:
                if (
                    block_type_filter == "BULLISH"
                    and scan.nearest_order_block.block_type != OrderBlockType.BULLISH_DEMAND
                ):
                    is_matched = False
                elif (
                    block_type_filter == "BEARISH"
                    and scan.nearest_order_block.block_type != OrderBlockType.BEARISH_SUPPLY
                ):
                    is_matched = False
            elif not scan.is_fresh_impulse:
                is_matched = False

            scan_results.append(
                OrderBlockScanResult(
                    symbol=scan.symbol,
                    security_id=scan.security_id,
                    ltp=scan.ltp,
                    nearest_order_block=scan.nearest_order_block,
                    distance_pct=scan.distance_pct,
                    is_at_order_block=is_matched,
                    is_fresh_impulse=scan.is_fresh_impulse,
                    all_order_blocks=scan.all_order_blocks,
                    volume=scan.volume,
                    rsi=scan.rsi,
                    candle_signal=scan.candle_signal,
                )
            )

        # Sort with matched first, then closest distance to Order Block zone
        scan_results.sort(key=lambda x: (not x.is_at_order_block, abs(x.distance_pct)))
        matched_count = sum(1 for r in scan_results if r.is_at_order_block)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=f"{self.name} ({universe_name} | {timeframe})",
            total_scanned=len(scan_results),
            matched_count=matched_count,
            results=scan_results,
        )
