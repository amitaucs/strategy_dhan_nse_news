"""2-Hour Heikin Ashi EMA Pullback + Supertrend Scanner."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.indicators import (
    calculate_heikin_ashi,
    calculate_rsi,
    calculate_supertrend,
)
from scanner_dhan.scanner.base import BaseScanner, ScannerParameter, ScanReport
from scanner_dhan.scanner.st15_largecap.models import HeikinAshiEmaScanResult
from scanner_dhan.scanner.registry import register_scanner
from scanner_dhan.universe import get_active_universe

logger = logging.getLogger(__name__)

__all__ = ["HeikinAshiEmaPullbackScanner"]


@register_scanner
class HeikinAshiEmaPullbackScanner(BaseScanner):
    """Detects 2H Green Heikin Ashi candles forming after pullback near 20/50/200 EMAs."""

    id = "heikin_ashi_ema_pullback"
    name = "2H Heikin Ashi EMA Pullback + Supertrend - ST15 LargeCap"
    description = (
        "Identifies bullish continuation setups on 2-Hour Heikin Ashi charts: "
        "Green Heikin Ashi candle bouncing off/testing 20, 50, or 200 EMA with Green Supertrend."
    )
    category = "Trend Following"
    icon = "zap"
    parameters = [
        ScannerParameter(
            name="universe",
            label="Stock Universe",
            param_type="select",
            default="NIFTY_100",
            description=(
                "Choose between Nifty 500 (Broad Market), Nifty 100 (Default), Nifty 50, "
                "Nifty Smallcap 100, or All F&O Stocks."
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
            default="2H",
            description=(
                "Candle resolution: 2 Hours (120m Default), 1 Day (Daily), 1 Hour (60m), "
                "or 15 Minutes."
            ),
            options=[
                {"value": "2H", "label": "2 Hours (120m Default) ⭐"},
                {"value": "1D", "label": "1 Day (Daily)"},
                {"value": "1H", "label": "1 Hour (60m)"},
                {"value": "15M", "label": "15 Minutes"},
            ],
        ),
        ScannerParameter(
            name="target_ema",
            label="Target EMA Pullback",
            param_type="select",
            default="ALL",
            description="Target a specific EMA (20, 50, or 200 EMA) or Auto-Detect Nearest.",
            options=[
                {"value": "ALL", "label": "All EMAs (Auto-Detect Nearest)"},
                {"value": "EMA_20", "label": "20 EMA Pullback"},
                {"value": "EMA_50", "label": "50 EMA Pullback"},
                {"value": "EMA_200", "label": "200 EMA Major Trend Support"},
            ],
        ),
        ScannerParameter(
            name="first_candle_only",
            label="First Green Candle Only",
            param_type="select",
            default="no",
            description="Filter only stocks forming the 1st Green HA candle after a Red pullback.",
            options=[
                {"value": "no", "label": "All Green HA Pullbacks (Any in Wave)"},
                {"value": "yes", "label": "1st Green HA Candle Only (Fresh Entry ⭐)"},
            ],
        ),
        ScannerParameter(
            name="threshold_pct",
            label="EMA Pullback Proximity (%)",
            param_type="float",
            default=1.5,
            min_value=0.0,
            max_value=4.0,
            step=0.1,
            description="Max distance (%) from 20/50/200 EMA to qualify as EMA pullback.",
        ),
        ScannerParameter(
            name="supertrend_period",
            label="Supertrend ATR Period",
            param_type="int",
            default=10,
            min_value=5,
            max_value=20,
            step=1,
            description="ATR lookback period for Supertrend.",
        ),
        ScannerParameter(
            name="supertrend_multiplier",
            label="Supertrend Multiplier",
            param_type="float",
            default=3.0,
            min_value=1.0,
            max_value=5.0,
            step=0.5,
            description="ATR multiplier for Supertrend upper/lower bands.",
        ),
    ]

    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        p = params or {}
        universe_choice = str(p.get("universe", "NIFTY_100"))
        timeframe = str(p.get("timeframe", "2H")).upper()
        target_ema = str(p.get("target_ema", "ALL")).upper().strip()
        first_candle_only = str(p.get("first_candle_only", "no")).lower() in ("yes", "true", "1")
        threshold_pct = float(p.get("threshold_pct", 1.5))
        st_period = int(p.get("supertrend_period", 10))
        st_mult = float(p.get("supertrend_multiplier", 3.0))

        prov = provider or DhanDataProvider()
        universe_name, symbols, sec_map = get_active_universe(universe_choice)

        security_ids = [sec_map[sym] for sym in symbols if sym in sec_map]
        ltp_map = prov.fetch_ltp_batch(security_ids)

        scan_results: list[HeikinAshiEmaScanResult] = []

        for sym in symbols:
            sid = sec_map.get(sym, "")
            if not sid:
                continue

            df_2h = prov.fetch_bars(sid, timeframe=timeframe, days=30 if timeframe != "1D" else 150)
            if df_2h.empty or len(df_2h) < 15:
                # Insufficient data fallback
                ltp = ltp_map.get(str(sid), 0.0)
                scan_results.append(
                    HeikinAshiEmaScanResult(
                        symbol=sym,
                        security_id=sid,
                        ltp=ltp,
                        nearest_ema_name="N/A",
                        nearest_ema_price=0.0,
                        distance_pct=999.0,
                        is_ha_green=False,
                        is_supertrend_green=False,
                        supertrend_val=0.0,
                        is_matched=False,
                        is_first_green=False,
                        candle_signal=f"Insufficient {timeframe} Data",
                    )
                )
                continue

            current_price = ltp_map.get(str(sid)) or float(df_2h["close"].iloc[-1])
            volume = (
                int(df_2h["volume"].iloc[-1])
                if ("volume" in df_2h.columns and pd.notna(df_2h["volume"].iloc[-1]))
                else 0
            )

            # 1. Compute Full 2-Hour Heikin Ashi Series
            ha_df = calculate_heikin_ashi(df_2h)

            df_ha = pd.DataFrame(
                {
                    "open": ha_df["ha_open"],
                    "high": ha_df["ha_high"],
                    "low": ha_df["ha_low"],
                    "close": ha_df["ha_close"],
                },
                index=df_2h.index,
            )

            ha_open = float(df_ha["open"].iloc[-1])
            ha_close = float(df_ha["close"].iloc[-1])
            ha_low = float(df_ha["low"].iloc[-1])

            # Current candle MUST be closed GREEN (HA Close > HA Open)
            is_ha_green = bool(ha_close > ha_open)

            # Previous candle MUST be closed RED (HA Close < HA Open) to qualify as a fresh bounce
            if len(df_ha) >= 2:
                prev_ha_open = float(df_ha["open"].iloc[-2])
                prev_ha_close = float(df_ha["close"].iloc[-2])
                prev_is_red = bool(prev_ha_close < prev_ha_open)
            else:
                prev_is_red = False

            # Strict 1st Green HA condition:
            # Previous was RED pullback AND current is CLOSED GREEN
            is_first_green = is_ha_green and prev_is_red

            # 2. Supertrend Calculation on 2-Hour Heikin Ashi OHLC
            st_df = calculate_supertrend(df_ha, period=st_period, multiplier=st_mult)
            is_st_green = bool(st_df["is_green"].iloc[-1]) if not st_df.empty else False
            st_val = float(st_df["supertrend"].iloc[-1]) if not st_df.empty else 0.0

            # 3. 20, 50, 200 EMAs on 2-Hour Heikin Ashi Close
            ha_close_series = df_ha["close"].astype(float)
            ema_20 = float(ha_close_series.ewm(span=20, adjust=False).mean().iloc[-1])
            ema_50 = float(ha_close_series.ewm(span=50, adjust=False).mean().iloc[-1])
            ema_200 = float(
                ha_close_series.ewm(span=min(200, len(ha_close_series)), adjust=False)
                .mean()
                .iloc[-1]
            )

            # Evaluate distance from Heikin Ashi Close & Low to each of the 3 EMAs
            ema_candidates = [
                ("20 EMA", ema_20, ((ha_close - ema_20) / ema_20) * 100.0),
                ("50 EMA", ema_50, ((ha_close - ema_50) / ema_50) * 100.0),
                ("200 EMA", ema_200, ((ha_close - ema_200) / ema_200) * 100.0),
            ]

            # Find closest EMA
            if target_ema == "EMA_20":
                best_ema_name, best_ema_price, best_dist_pct = ema_candidates[0]
            elif target_ema == "EMA_50":
                best_ema_name, best_ema_price, best_dist_pct = ema_candidates[1]
            elif target_ema == "EMA_200":
                best_ema_name, best_ema_price, best_dist_pct = ema_candidates[2]
            else:
                ema_candidates.sort(key=lambda x: abs(x[2]))
                best_ema_name, best_ema_price, best_dist_pct = ema_candidates[0]

            # Check if Heikin Ashi low touched / pulled back near the EMA
            recent_ha_low = float(df_ha["low"].tail(2).min())
            ha_low_dist_pct = ((recent_ha_low - best_ema_price) / best_ema_price) * 100.0

            is_holding_ema = ha_close >= (best_ema_price * (1.0 - threshold_pct / 100.0))
            is_pullback_near = (
                abs(best_dist_pct) <= threshold_pct
                or (-1.0 <= ha_low_dist_pct <= threshold_pct)
                or (ha_low <= best_ema_price * 1.005 and ha_close >= best_ema_price * 0.995)
            )
            is_near_ema = is_holding_ema and is_pullback_near

            # Strategy Match Condition:
            # 1. Current candle MUST BE CLOSED GREEN (ha_close > ha_open)
            # 2. Supertrend is Green (Bullish) on 2H Heikin Ashi
            # 3. Pullback near 20, 50, or 200 EMA (within threshold %)
            is_pullback = bool(is_ha_green and is_st_green and is_near_ema)
            is_matched = bool(is_pullback and (not first_candle_only or is_first_green))

            rsi = calculate_rsi(df_ha["close"], period=14)

            if is_first_green and is_st_green:
                candle_signal = "⭐ 1st Green HA (Fresh Entry) + ST Bullish"
            elif is_ha_green and is_st_green:
                candle_signal = "🟢 Green HA + Bullish ST"
            elif is_ha_green:
                candle_signal = "🟢 Green HA"
            else:
                candle_signal = "🔴 Red HA (Pulling Back)"

            scan_results.append(
                HeikinAshiEmaScanResult(
                    symbol=sym,
                    security_id=sid,
                    ltp=current_price,
                    nearest_ema_name=best_ema_name,
                    nearest_ema_price=best_ema_price,
                    distance_pct=round(best_dist_pct, 2),
                    is_ha_green=is_ha_green,
                    is_first_green=is_first_green,
                    is_pullback=is_pullback,
                    is_supertrend_green=is_st_green,
                    supertrend_val=st_val,
                    is_matched=is_matched,
                    volume=volume,
                    rsi=rsi,
                    candle_signal=candle_signal,
                )
            )

        # Sort with matched first, 1st green candle priority, then closest to EMA
        scan_results.sort(
            key=lambda x: (not x.is_matched, not x.is_first_green, abs(x.distance_pct))
        )
        matched_count = sum(1 for r in scan_results if r.is_matched)

        return ScanReport(
            timestamp=datetime.now(),
            scanner_id=self.id,
            scanner_name=f"{self.name} ({universe_name} | {timeframe})",
            total_scanned=len(scan_results),
            matched_count=matched_count,
            results=scan_results,
        )
