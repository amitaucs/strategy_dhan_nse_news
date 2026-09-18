"""RSI Momentum Extremes & Reversal Scanner Implementation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.indicators import calculate_rsi, identify_candlestick_patterns
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.scanner.rsi_scanner.models import RsiScanResult, RsiZone
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["RsiExtremesScanner", "Nifty50RsiScanner"]


@register_scanner
class RsiExtremesScanner(BaseScanner):
    """Detects stocks in extreme Oversold or Overbought territory for momentum reversals."""

    id = "nifty50_rsi"
    name = "RSI Extremes Scanner - Momentum Reversal"
    description = (
        "Finds oversold (RSI <= 38) or overbought (RSI >= 68) opportunities across stocks."
    )
    category = "Momentum"
    icon = "activity"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_50",
            description=(
                "Choose between Nifty 50 (Default), Nifty 100, Nifty 500, "
                "Nifty Smallcap 100, or All NSE F&O Stocks."
            ),
            options=[
                {"value": "NIFTY_50", "label": "Nifty 50 (50 Stocks)"},
                {"value": "NIFTY_100", "label": "Nifty 100 (100 Stocks)"},
                {"value": "NIFTY_500", "label": "Nifty 500 (Broad Market)"},
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
                "Candle resolution: 1 Day (Daily Default), 2 Hours (120m), 1 Hour (60m), or 15 Minutes."
            ),
            options=[
                {"value": "1D", "label": "1 Day (Daily) ⭐"},
                {"value": "2H", "label": "2 Hours (120m)"},
                {"value": "1H", "label": "1 Hour (60m)"},
                {"value": "15M", "label": "15 Minutes"},
            ],
        ),
        ScannerParameter(
            name="oversold_threshold",
            label="Oversold RSI",
            param_type="float",
            default=38.0,
            min_value=20.0,
            max_value=45.0,
            step=1.0,
            description="Stocks with RSI below or equal to this threshold are flagged as Oversold.",
        ),
        ScannerParameter(
            name="overbought_threshold",
            label="Overbought RSI",
            param_type="float",
            default=68.0,
            min_value=55.0,
            max_value=85.0,
            step=1.0,
            description="Stocks with RSI above or equal to this threshold are flagged as Overbought.",
        ),
        ScannerParameter(
            name="rsi_period",
            label="RSI Period",
            param_type="int",
            default=14,
            min_value=5,
            max_value=30,
            step=1,
            description="Lookback period for Wilder's RSI calculation (Standard: 14).",
        ),
        ScannerParameter(
            name="scan_mode",
            label="Filter Mode",
            param_type="select",
            default="EXTREMES_ONLY",
            description="Choose whether to show only Oversold/Overbought extremes or a specific side.",
            options=[
                {"value": "EXTREMES_ONLY", "label": "Extremes Only (Oversold + Overbought) ⭐"},
                {"value": "OVERSOLD_ONLY", "label": "Oversold Stocks Only (Dip Reversals)"},
                {"value": "OVERBOUGHT_ONLY", "label": "Overbought Stocks Only (Overextended)"},
                {"value": "ALL_STOCKS", "label": "All Stocks (Include Neutral)"},
            ],
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        oversold = float(p.get("oversold_threshold", 38.0))
        overbought = float(p.get("overbought_threshold", 68.0))
        rsi_period = int(p.get("rsi_period", 14))
        scan_mode = str(p.get("scan_mode", "EXTREMES_ONLY")).upper().strip()
        universe_choice = str(p.get("universe", "NIFTY_50"))
        timeframe = str(p.get("timeframe", "1D")).upper()
        prov = provider or DhanDataProvider()

        universe_name, symbols, sec_map = get_active_universe(universe_choice)
        security_ids = [sec_map[sym] for sym in symbols if sym in sec_map]
        ltp_map = prov.fetch_ltp_batch(security_ids)

        scan_results: list[RsiScanResult] = []
        lookback_days = 100 if timeframe == "1D" else 30

        for sym in symbols:
            sid = sec_map.get(sym, "")
            if not sid:
                continue

            df = prov.fetch_bars(sid, timeframe=timeframe, days=lookback_days)
            if df.empty or len(df) < rsi_period + 1:
                ltp = ltp_map.get(str(sid), 0.0)
                scan_results.append(
                    RsiScanResult(
                        symbol=sym,
                        security_id=sid,
                        ltp=ltp,
                        rsi=None,
                        rsi_zone=RsiZone.NEUTRAL,
                        candle_signal=f"Insufficient {timeframe} Data",
                        is_matched=False,
                        volume=0,
                        change_pct=0.0,
                    )
                )
                continue

            ltp = ltp_map.get(str(sid)) or float(df["close"].iloc[-1])
            volume = int(df["volume"].iloc[-1]) if ("volume" in df.columns and pd.notna(df["volume"].iloc[-1])) else 0

            # Calculate RSI on close prices
            rsi_val = calculate_rsi(df["close"], period=rsi_period)

            # Change percentage
            prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else ltp
            change_pct = round(((ltp - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0

            # Identify Candlestick Signal
            candle_signal = identify_candlestick_patterns(df)

            # Match & Zone Evaluation
            is_matched = False
            zone = RsiZone.NEUTRAL
            if rsi_val is not None:
                if rsi_val <= oversold:
                    is_matched = True
                    zone = RsiZone.OVERSOLD
                elif rsi_val >= overbought:
                    is_matched = True
                    zone = RsiZone.OVERBOUGHT

            scan_results.append(
                RsiScanResult(
                    symbol=sym,
                    security_id=sid,
                    ltp=ltp,
                    rsi=rsi_val,
                    rsi_zone=zone,
                    candle_signal=candle_signal,
                    is_matched=is_matched,
                    volume=volume,
                    change_pct=change_pct,
                )
            )

        # Filter output based on user's scan_mode choice (Default: EXTREMES_ONLY)
        if scan_mode == "OVERSOLD_ONLY":
            filtered_results = [r for r in scan_results if r.rsi_zone == RsiZone.OVERSOLD]
        elif scan_mode == "OVERBOUGHT_ONLY":
            filtered_results = [r for r in scan_results if r.rsi_zone == RsiZone.OVERBOUGHT]
        elif scan_mode == "ALL_STOCKS":
            filtered_results = scan_results
        else:  # EXTREMES_ONLY
            filtered_results = [r for r in scan_results if r.is_matched]

        # Sort matches first, oversold (lowest RSI) first, then overbought (highest RSI)
        def _sort_key(r: RsiScanResult) -> tuple[int, float]:
            if not r.is_matched or r.rsi is None:
                return (2, 50.0)
            if r.rsi_zone == RsiZone.OVERSOLD:
                return (0, r.rsi)  # Lower RSI first
            return (1, -r.rsi)  # Higher overbought RSI first

        filtered_results.sort(key=_sort_key)
        matched_count = sum(1 for r in scan_results if r.is_matched)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=f"{self.name} ({universe_name} | {timeframe})",
            total_scanned=len(scan_results),
            matched_count=matched_count,
            results=filtered_results,
        )


# Backward compatibility alias
Nifty50RsiScanner = RsiExtremesScanner

