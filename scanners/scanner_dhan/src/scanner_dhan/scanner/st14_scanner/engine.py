"""ST-14: Bullish CE Intraday Setup Engine and Technical Evaluation."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import numpy as np
import pandas as pd

from scanner_dhan.indicators.moving_averages import calculate_ema_series
from scanner_dhan.indicators.vwap import (
    calculate_intraday_vwap_series,
    calculate_vwap_slope_and_angle,
)
from scanner_dhan.scanner.st14_scanner.models import St14ScanResult, St14Status

logger = logging.getLogger(__name__)

__all__ = [
    "compute_indicators",
    "check_timing_constraint",
    "evaluate_bullish_conditions",
    "analyze_st14_stock",
]


def check_timing_constraint(
    target_dt: datetime | None = None,
    cutoff_hour: int = 10,
    cutoff_minute: int = 15,
) -> tuple[bool, str]:
    """Check if current execution timing is after 10:15 AM IST.

    Returns (is_valid, timing_message).
    """
    try:
        ist_tz = ZoneInfo("Asia/Kolkata")
        now_ist = target_dt.astimezone(ist_tz) if target_dt else datetime.now(ist_tz)
        current_minutes = now_ist.hour * 60 + now_ist.minute
        cutoff_minutes = cutoff_hour * 60 + cutoff_minute

        if current_minutes >= cutoff_minutes:
            return True, f"Valid entry window (>= {cutoff_hour:02d}:{cutoff_minute:02d} IST)"
        return False, f"Early session before {cutoff_hour:02d}:{cutoff_minute:02d} IST (Entry blocked)"
    except Exception as exc:
        logger.warning("Error checking timing constraint: %s", exc)
        return True, "Timing check bypassed"


def compute_indicators(
    df: pd.DataFrame,
    ema_period: int = 20,
    total_window_bars: int = 5,
) -> pd.DataFrame:
    """Compute 20 EMA, Intraday VWAP, and breakout levels for a 5-bar window (including current bar).

    - total_window_bars = 5 (includes 4 previous bars + current bar).
    - prior_window_high: Rolling maximum of the 4 PREVIOUS completed bars (the breakout hurdle).
    - total_5_high: Rolling maximum of all 5 bars including the current bar.
    """
    if df.empty or len(df) < max(ema_period, total_window_bars + 1) + 2:
        return df

    out = df.copy()
    close_s = out["close"].astype(float)
    high_s = out["high"].astype(float)

    # 1. 20-period Exponential Moving Average (EMA)
    out["ema20"] = calculate_ema_series(close_s, span=ema_period)

    # 2. Intraday Cumulative VWAP
    out["vwap"] = calculate_intraday_vwap_series(out)

    # 3. Prior 4 bars rolling peak (resistance hurdle in the 5-candle window including current bar)
    prior_bars = max(1, total_window_bars - 1)
    out["prior_window_high"] = high_s.shift(1).rolling(window=prior_bars).max()

    # 4. Total 5-bar peak including current bar
    out["total_5_high"] = high_s.rolling(window=total_window_bars).max()

    return out


def evaluate_bullish_conditions(
    df_daily: pd.DataFrame,
    df_hourly: pd.DataFrame,
    ema_period: int = 20,
    total_window_bars: int = 5,
    vwap_min_dist_pct: float = -1.0,
    vwap_max_dist_pct: float = 5.0,
    require_rising_vwap: bool = True,
    enforce_timing: bool = True,
    current_time_ist: datetime | None = None,
) -> dict[str, Any]:
    """Core vectorized evaluation of ST-14 Bullish CE setup rules on Daily and Hourly data.

    5-Day and 5-Hour window includes the current day and current hour candle respectively.
    """
    result: dict[str, Any] = {
        "is_valid": False,
        "is_daily_bullish": False,
        "is_hourly_bullish": False,
        "is_vwap_valid": False,
        "timing_valid": True,
        "timing_message": "Timing check not enforced",
        "status": St14Status.NO_SETUP,
        "daily_close": 0.0,
        "daily_ema20": 0.0,
        "five_day_high": 0.0,
        "is_5d_breakout": False,
        "hourly_close": 0.0,
        "hourly_ema20": 0.0,
        "five_hour_high": 0.0,
        "is_5h_breakout": False,
        "vwap": 0.0,
        "vwap_dist_pct": 0.0,
        "vwap_angle_deg": 0.0,
        "is_vwap_near": False,
        "is_vwap_rising": False,
        "dist_to_5d_high_pct": 0.0,
        "dist_to_5h_high_pct": 0.0,
    }

    min_required_daily = max(ema_period, total_window_bars + 1, 15)
    min_required_hourly = max(ema_period, total_window_bars + 1, 15)

    if df_daily.empty or len(df_daily) < min_required_daily:
        return result

    if df_hourly.empty or len(df_hourly) < min_required_hourly:
        return result

    # 1. Process Daily Indicators
    daily_ind = compute_indicators(
        df_daily,
        ema_period=ema_period,
        total_window_bars=total_window_bars,
    )
    last_daily = daily_ind.iloc[-1]
    daily_close = float(last_daily["close"])
    daily_high = float(last_daily["high"]) if "high" in last_daily else daily_close
    daily_ema20 = float(last_daily["ema20"]) if pd.notna(last_daily.get("ema20")) else 0.0
    five_day_hurdle = float(last_daily["prior_window_high"]) if pd.notna(last_daily.get("prior_window_high")) else 0.0

    # Daily Condition Checks (5-Day window including today):
    # Rule 1: Daily Close > Daily 20 EMA
    d_close_above_ema = daily_close > daily_ema20 if daily_ema20 > 0 else False
    # Rule 2: Daily Close / LTP crossed 5-Day High (broke above the 4 prior days in the 5-day window)
    is_5d_breakout = daily_close > five_day_hurdle if five_day_hurdle > 0 else False

    is_daily_bullish = d_close_above_ema and is_5d_breakout

    # 2. Process Hourly Indicators
    hourly_ind = compute_indicators(
        df_hourly,
        ema_period=ema_period,
        total_window_bars=total_window_bars,
    )
    last_hourly = hourly_ind.iloc[-1]
    hourly_close = float(last_hourly["close"])
    hourly_high = float(last_hourly["high"]) if "high" in last_hourly else hourly_close
    hourly_ema20 = float(last_hourly["ema20"]) if pd.notna(last_hourly.get("ema20")) else 0.0
    five_hour_hurdle = float(last_hourly["prior_window_high"]) if pd.notna(last_hourly.get("prior_window_high")) else 0.0
    vwap_val = float(last_hourly["vwap"]) if pd.notna(last_hourly.get("vwap")) else hourly_close

    # Hourly Condition Checks (5-Hour window including current hour):
    # Rule 3: 1H Close > 1H 20 EMA
    h_close_above_ema = hourly_close > hourly_ema20 if hourly_ema20 > 0 else False
    # Rule 4: 1H Close / LTP crossed 5-Hour High (broke above the 4 prior hours in the 5-hour window)
    is_5h_breakout = hourly_close > five_hour_hurdle if five_hour_hurdle > 0 else False

    is_hourly_bullish = h_close_above_ema and is_5h_breakout

    # 3. Intraday VWAP Proximity & ~45° Rising Slope Evaluation
    vwap_dist_pct = round(((hourly_close - vwap_val) / vwap_val) * 100.0, 2) if vwap_val > 0 else 0.0
    _, vwap_angle_deg, is_vwap_rising = calculate_vwap_slope_and_angle(hourly_ind["vwap"])

    is_vwap_near = vwap_min_dist_pct <= vwap_dist_pct <= vwap_max_dist_pct
    is_vwap_valid = is_vwap_near and (is_vwap_rising if require_rising_vwap else True)

    # 4. Timing Constraint Check (>= 10:15 AM IST)
    if enforce_timing:
        timing_valid, timing_msg = check_timing_constraint(target_dt=current_time_ist)
    else:
        timing_valid, timing_msg = True, "Timing filter bypassed"

    # Distances
    dist_to_5d_high_pct = round(((daily_close - five_day_hurdle) / five_day_hurdle) * 100.0, 2) if five_day_hurdle > 0 else 0.0
    dist_to_5h_high_pct = round(((hourly_close - five_hour_hurdle) / five_hour_hurdle) * 100.0, 2) if five_hour_hurdle > 0 else 0.0

    # Setup Status Determination
    if is_daily_bullish and is_hourly_bullish and is_vwap_valid and timing_valid:
        status = St14Status.QUALIFIED
    elif is_daily_bullish and (h_close_above_ema or is_vwap_near or dist_to_5h_high_pct >= -1.5):
        status = St14Status.WATCHLIST
    else:
        status = St14Status.NO_SETUP

    result.update(
        {
            "is_valid": True,
            "is_daily_bullish": is_daily_bullish,
            "is_hourly_bullish": is_hourly_bullish,
            "is_vwap_valid": is_vwap_valid,
            "timing_valid": timing_valid,
            "timing_message": timing_msg,
            "status": status,
            "daily_close": daily_close,
            "daily_ema20": round(daily_ema20, 2),
            "five_day_high": round(five_day_hurdle, 2),
            "is_5d_breakout": is_5d_breakout,
            "hourly_close": hourly_close,
            "hourly_ema20": round(hourly_ema20, 2),
            "five_hour_high": round(five_hour_hurdle, 2),
            "is_5h_breakout": is_5h_breakout,
            "vwap": round(vwap_val, 2),
            "vwap_dist_pct": vwap_dist_pct,
            "vwap_angle_deg": vwap_angle_deg,
            "is_vwap_near": is_vwap_near,
            "is_vwap_rising": is_vwap_rising,
            "dist_to_5d_high_pct": dist_to_5d_high_pct,
            "dist_to_5h_high_pct": dist_to_5h_high_pct,
        }
    )
    return result


def analyze_st14_stock(
    symbol: str,
    security_id: str,
    df_daily: pd.DataFrame,
    df_hourly: pd.DataFrame,
    ltp_override: float | None = None,
    ema_period: int = 20,
    total_window_bars: int = 5,
    vwap_min_dist_pct: float = -1.0,
    vwap_max_dist_pct: float = 5.0,
    require_rising_vwap: bool = True,
    enforce_timing: bool = True,
    current_time_ist: datetime | None = None,
) -> St14ScanResult | None:
    """Evaluate a single stock against ST-14 Bullish CE Intraday rules and return St14ScanResult."""
    eval_res = evaluate_bullish_conditions(
        df_daily=df_daily,
        df_hourly=df_hourly,
        ema_period=ema_period,
        total_window_bars=total_window_bars,
        vwap_min_dist_pct=vwap_min_dist_pct,
        vwap_max_dist_pct=vwap_max_dist_pct,
        require_rising_vwap=require_rising_vwap,
        enforce_timing=enforce_timing,
        current_time_ist=current_time_ist,
    )

    if not eval_res["is_valid"]:
        return None

    ltp = ltp_override or eval_res["hourly_close"] or eval_res["daily_close"]
    status = eval_res["status"]
    is_at_support = status == St14Status.QUALIFIED

    now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y %H:%M:%S IST")

    vol_val = 0
    if not df_hourly.empty and "volume" in df_hourly.columns and pd.notna(df_hourly["volume"].iloc[-1]):
        vol_val = int(df_hourly["volume"].iloc[-1])
    if vol_val <= 0 and not df_daily.empty and "volume" in df_daily.columns and pd.notna(df_daily["volume"].iloc[-1]):
        vol_val = int(df_daily["volume"].iloc[-1])

    return St14ScanResult(
        symbol=symbol,
        security_id=security_id,
        ltp=round(ltp, 2),
        status=status,
        is_at_support=is_at_support,
        daily_close=eval_res["daily_close"],
        daily_ema20=eval_res["daily_ema20"],
        five_day_high=eval_res["five_day_high"],
        is_5d_breakout=eval_res["is_5d_breakout"],
        is_daily_bullish=eval_res["is_daily_bullish"],
        hourly_close=eval_res["hourly_close"],
        hourly_ema20=eval_res["hourly_ema20"],
        five_hour_high=eval_res["five_hour_high"],
        is_5h_breakout=eval_res["is_5h_breakout"],
        is_hourly_bullish=eval_res["is_hourly_bullish"],
        vwap=eval_res["vwap"],
        vwap_dist_pct=eval_res["vwap_dist_pct"],
        vwap_angle_deg=eval_res["vwap_angle_deg"],
        is_vwap_near=eval_res["is_vwap_near"],
        is_vwap_rising=eval_res["is_vwap_rising"],
        timing_valid=eval_res["timing_valid"],
        timing_message=eval_res["timing_message"],
        dist_to_5d_high_pct=eval_res["dist_to_5d_high_pct"],
        dist_to_5h_high_pct=eval_res["dist_to_5h_high_pct"],
        analysis_time_ist=now_ist,
        volume=vol_val,
    )
