"""Engine for Fair Value Gap (FVG) and 0.618 Fibonacci Retracement Confluence Detection."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.indicators.atr import calculate_atr, calculate_volume_sma
from scanner_dhan.indicators.candlesticks import identify_candlestick_patterns
from scanner_dhan.indicators.rsi import calculate_rsi, calculate_rsi_series
from scanner_dhan.scanner.wick_filter import check_candle_wick
from scanner_dhan.scanner.fvg_fibonacci.models import (
    FairValueGap,
    FibonacciRetracement,
    FvgFibConfluenceSetup,
    FvgFibScanResult,
    FvgStatus,
    FvgType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "detect_fair_value_gaps",
    "calculate_fibonacci_retracement",
    "detect_fvg_fib_confluences",
    "scan_stock_for_fvg_fib",
]


def detect_fair_value_gaps(
    df: pd.DataFrame,
    min_gap_pct: float = 0.2,
    body_atr_mult: float = 1.1,
    vol_mult: float = 1.0,
    atr_period: int = 14,
    lookback_bars: int = 80,
) -> List[FairValueGap]:
    """Detect 3-candle Fair Value Gaps with middle-candle displacement & volume expansion."""
    if df.empty or len(df) < max(atr_period, 20) + 4:
        return []

    df = df.copy()
    atr_series = calculate_atr(df, period=atr_period)
    vol_series = df["volume"].astype(float)
    vol_sma_series = calculate_volume_sma(vol_series, window=20)

    gaps: List[FairValueGap] = []
    n = len(df)
    start_idx = max(atr_period + 2, n - lookback_bars)

    for i in range(start_idx, n):
        # 3 Consecutive Candles:
        # Candle 1 = i - 2
        # Candle 2 = i - 1 (Displacement candle)
        # Candle 3 = i
        c1_high = float(df["high"].iloc[i - 2])
        c1_low = float(df["low"].iloc[i - 2])
        c1_time = df.index[i - 2] if isinstance(df.index, pd.DatetimeIndex) else df.iloc[i - 2].get("timestamp", i - 2)

        c2_open = float(df["open"].iloc[i - 1])
        c2_close = float(df["close"].iloc[i - 1])
        c2_vol = float(df["volume"].iloc[i - 1])
        c2_time = df.index[i - 1] if isinstance(df.index, pd.DatetimeIndex) else df.iloc[i - 1].get("timestamp", i - 1)

        c3_high = float(df["high"].iloc[i])
        c3_low = float(df["low"].iloc[i])
        c3_time = df.index[i] if isinstance(df.index, pd.DatetimeIndex) else df.iloc[i].get("timestamp", i)

        atr_val = float(atr_series.iloc[i - 1]) if not pd.isna(atr_series.iloc[i - 1]) else 0.0
        vol_sma = float(vol_sma_series.iloc[i - 1]) if not pd.isna(vol_sma_series.iloc[i - 1]) else 1.0

        if atr_val <= 0 or vol_sma <= 0:
            continue

        c2_high = float(df["high"].iloc[i - 1])
        c2_low = float(df["low"].iloc[i - 1])
        c2_range = max(c2_high - c2_low, 1e-4)
        c2_body = abs(c2_close - c2_open)
        body_to_range_ratio = c2_body / c2_range
        body_atr_ratio = c2_body / atr_val
        volume_ratio = c2_vol / vol_sma

        # 1. Bullish FVG (BISI): High of Candle 1 < Low of Candle 3 with strong Green displacement
        if c2_close > c2_open and c1_high < c3_low:
            gap_size = c3_low - c1_high
            gap_size_pct = (gap_size / c1_high) * 100.0
            upper_wick = c2_high - c2_close
            upper_wick_ratio = upper_wick / c2_range

            # Clean Candle Filter: Solid body >= 50% of range and upper selling wick <= 30% of range
            if (
                gap_size_pct >= min_gap_pct
                and body_atr_ratio >= body_atr_mult
                and volume_ratio >= vol_mult
                and body_to_range_ratio >= 0.50
                and upper_wick_ratio <= 0.30
            ):
                ce_price = (c1_high + c3_low) / 2.0
                gaps.append(
                    FairValueGap(
                        fvg_type=FvgType.BULLISH_FVG,
                        bar_index=i - 1,
                        timestamp=pd.to_datetime(c2_time) if not isinstance(c2_time, datetime) else c2_time,
                        top_price=c3_low,
                        bottom_price=c1_high,
                        ce_price=ce_price,
                        gap_size=gap_size,
                        gap_size_pct=gap_size_pct,
                        candle_1_time=pd.to_datetime(c1_time) if not isinstance(c1_time, datetime) else c1_time,
                        candle_1_price=c1_high,
                        candle_2_time=pd.to_datetime(c2_time) if not isinstance(c2_time, datetime) else c2_time,
                        candle_2_price=c2_close,
                        candle_3_time=pd.to_datetime(c3_time) if not isinstance(c3_time, datetime) else c3_time,
                        candle_3_price=c3_low,
                        body_atr_ratio=body_atr_ratio,
                        volume_ratio=volume_ratio,
                    )
                )

        # 2. Bearish FVG (SIBI): Low of Candle 1 > High of Candle 3 with strong Red displacement
        elif c2_close < c2_open and c1_low > c3_high:
            gap_size = c1_low - c3_high
            gap_size_pct = (gap_size / c3_high) * 100.0
            lower_wick = c2_close - c2_low
            lower_wick_ratio = lower_wick / c2_range

            # Clean Candle Filter: Solid body >= 50% of range and lower buying wick <= 30% of range
            if (
                gap_size_pct >= min_gap_pct
                and body_atr_ratio >= body_atr_mult
                and volume_ratio >= vol_mult
                and body_to_range_ratio >= 0.50
                and lower_wick_ratio <= 0.30
            ):
                ce_price = (c3_high + c1_low) / 2.0
                gaps.append(
                    FairValueGap(
                        fvg_type=FvgType.BEARISH_FVG,
                        bar_index=i - 1,
                        timestamp=pd.to_datetime(c2_time) if not isinstance(c2_time, datetime) else c2_time,
                        top_price=c1_low,
                        bottom_price=c3_high,
                        ce_price=ce_price,
                        gap_size=gap_size,
                        gap_size_pct=gap_size_pct,
                        candle_1_time=pd.to_datetime(c1_time) if not isinstance(c1_time, datetime) else c1_time,
                        candle_1_price=c1_low,
                        candle_2_time=pd.to_datetime(c2_time) if not isinstance(c2_time, datetime) else c2_time,
                        candle_2_price=c2_close,
                        candle_3_time=pd.to_datetime(c3_time) if not isinstance(c3_time, datetime) else c3_time,
                        candle_3_price=c3_high,
                        body_atr_ratio=body_atr_ratio,
                        volume_ratio=volume_ratio,
                    )
                )

    return gaps


def calculate_fibonacci_retracement(
    swing_low: float,
    swing_high: float,
    direction: str = "BULLISH",
) -> FibonacciRetracement:
    """Calculate standard Fibonacci Retracement and ICT OTE levels."""
    diff = max(swing_high - swing_low, 1e-4)

    if direction == "BULLISH":
        fib_0 = swing_high
        fib_236 = swing_high - 0.236 * diff
        fib_382 = swing_high - 0.382 * diff
        fib_500 = swing_high - 0.500 * diff
        fib_618 = swing_high - 0.618 * diff
        fib_705 = swing_high - 0.705 * diff
        fib_786 = swing_high - 0.786 * diff
        fib_100 = swing_low
        extension_272 = swing_high + 0.272 * diff
        extension_618 = swing_high + 0.618 * diff
    else:  # BEARISH
        fib_0 = swing_low
        fib_236 = swing_low + 0.236 * diff
        fib_382 = swing_low + 0.382 * diff
        fib_500 = swing_low + 0.500 * diff
        fib_618 = swing_low + 0.618 * diff
        fib_705 = swing_low + 0.705 * diff
        fib_786 = swing_low + 0.786 * diff
        fib_100 = swing_high
        extension_272 = swing_low - 0.272 * diff
        extension_618 = swing_low - 0.618 * diff

    return FibonacciRetracement(
        swing_low=swing_low,
        swing_high=swing_high,
        direction=direction,
        fib_0=fib_0,
        fib_236=fib_236,
        fib_382=fib_382,
        fib_500=fib_500,
        fib_618=fib_618,
        fib_705=fib_705,
        fib_786=fib_786,
        fib_100=fib_100,
        extension_272=extension_272,
        extension_618=extension_618,
    )


def _has_freak_wicks_or_noise(
    df: pd.DataFrame,
    start_idx: int,
    end_idx: int,
    atr_series: pd.Series,
) -> bool:
    """Check if any candle in slice [start_idx, end_idx) contains freak outlier wicks or erratic wide-range spinning tops."""
    for i in range(start_idx, end_idx):
        o = float(df["open"].iloc[i])
        h = float(df["high"].iloc[i])
        l = float(df["low"].iloc[i])
        c = float(df["close"].iloc[i])
        rng = max(h - l, 1e-4)
        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        bar_atr = float(atr_series.iloc[i]) if (i < len(atr_series) and not pd.isna(atr_series.iloc[i]) and atr_series.iloc[i] > 0) else 0.0
        if bar_atr <= 0:
            continue

        # 1. Extreme Freak Wick: single-sided wick > 2.0 * ATR
        if upper_wick > 2.0 * bar_atr or lower_wick > 2.0 * bar_atr:
            return True

        # 2. Erratic Wide-Range Spinning Top / High Noise Doji: Range > 1.3 * ATR with body < 22% of range
        if rng > 1.3 * bar_atr and (body / rng) < 0.22:
            return True

    return False


def detect_fvg_fib_confluences(
    df: pd.DataFrame,
    min_gap_pct: float = 0.2,
    confluence_tolerance_pct: float = 1.5,
    body_atr_mult: float = 1.1,
    vol_mult: float = 1.0,
    direction_filter: str = "ALL",
) -> List[FvgFibConfluenceSetup]:
    """Detect True Smart Money Concepts (SMC) FVG + 0.618 Fibonacci Retracement Confluence setups.
    
    True SMC Rules Enforced:
    1. Break of Structure (BOS / MSS): Impulse must break the prior swing high (Bullish) or low (Bearish).
    2. Freshness: The impulse extreme (Peak / Trough) must be recent (within last 20 bars).
    3. Approach Direction: Price must be pulling back DOWN from peak into Bullish FVG (never rising from below).
    4. Single Mitigation / Strict Invalidation: FVG must never have been previously closed below/above or breached.
    5. Clean Candle Filter: Disqualifies freak outlier wicks (> 2.0x ATR) and erratic spinning top noise.
    6. Price Action Confirmation: Requires a clean bounce/rejection bar without heavy opposing shadow.
    """
    if df.empty or len(df) < 25:
        return []

    atr_series = calculate_atr(df, period=14)

    gaps = detect_fair_value_gaps(
        df,
        min_gap_pct=min_gap_pct,
        body_atr_mult=body_atr_mult,
        vol_mult=vol_mult,
        lookback_bars=45,
    )

    if not gaps:
        return []

    current_price = float(df["close"].iloc[-1])
    n = len(df)
    setups: List[FvgFibConfluenceSetup] = []

    for fvg in reversed(gaps):  # Prioritize most recent FVGs
        fvg_idx = fvg.bar_index
        # Strict SMC Freshness: Total setup lifecycle from FVG to current bar must be <= 15 bars
        if fvg_idx >= n - 1 or (n - 1 - fvg_idx > 15):
            continue

        if fvg.fvg_type == FvgType.BULLISH_FVG:
            if direction_filter == "BEARISH_ONLY":
                continue

            # 1. Prior Market Structure before FVG (Swing Low Base)
            lookback_origin = max(0, fvg_idx - 15)
            prior_swing_high = float(df["high"].iloc[lookback_origin : fvg_idx].max())
            swing_low = float(df["low"].iloc[lookback_origin : fvg_idx].min())

            # 2. Impulse Peak High created directly AFTER FVG formed
            impulse_slice = df["high"].iloc[fvg_idx + 1 :]
            if impulse_slice.empty:
                continue
            swing_high = float(impulse_slice.max())
            peak_rel_idx = int(impulse_slice.values.argmax())
            peak_idx = (fvg_idx + 1) + peak_rel_idx
            bars_from_fvg_to_peak = peak_idx - fvg_idx
            bars_since_peak = n - 1 - peak_idx

            # Rule 1: Break of Structure (BOS) - Impulse must break above prior swing high
            if swing_high <= prior_swing_high * 1.001:
                continue

            # Rule 2: Clean Direct Impulse - Peak must form within 1 to 4 bars of FVG
            if bars_from_fvg_to_peak > 4:
                continue

            # Rule 3: Tight Pullback - Pullback from peak must be active and tight (1 to 7 bars)
            if bars_since_peak > 7 or bars_since_peak < 1:
                continue

            # Rule 4: Structural Integrity - Peak > FVG Top > FVG Bottom > Swing Low
            if not (swing_high > fvg.top_price > fvg.bottom_price > swing_low):
                continue

            if (swing_high - swing_low) / swing_low < 0.015:
                continue

            fib = calculate_fibonacci_retracement(swing_low, swing_high, direction="BULLISH")

            # Rule 4: Confluence Alignment - 0.618 Fib or 0.705 OTE must land inside FVG
            fvg_min_bound = fvg.bottom_price * 0.995
            fvg_max_bound = fvg.top_price * 1.005
            fib_in_fvg = (fvg_min_bound <= fib.fib_618 <= fvg_max_bound) or (fvg.bottom_price <= fib.fib_705 <= fvg.top_price)

            if not fib_in_fvg:
                continue

            # Rule 5: Strict Invalidation & Direction of Approach
            # Price must be pulling DOWN from peak. It must NEVER have closed below FVG bottom or 0.786 Fib
            post_peak_slice = df.iloc[peak_idx :]
            lowest_close_since_peak = float(post_peak_slice["close"].min())
            lowest_low_since_peak = float(post_peak_slice["low"].min())

            if lowest_close_since_peak < fvg.bottom_price * 0.995 or lowest_close_since_peak < fib.fib_786 * 0.995:
                continue  # Violated / Destroyed FVG

            # Disqualify if price previously crashed below FVG and is now rising up from below (Overhead Resistance)
            if lowest_low_since_peak < fvg.bottom_price * 0.985:
                continue

            # Rule 5b: Anti-Wick & Noise Filter across cycle
            start_noise_check = max(0, fvg_idx - 2)
            if _has_freak_wicks_or_noise(df, start_noise_check, n - 1, atr_series):
                continue  # Disqualify setups with freak shadows or spinning-top noise

            # Check Zone Alignment
            dist_to_618_pct = ((current_price - fib.fib_618) / fib.fib_618) * 100.0
            in_zone = (
                abs(dist_to_618_pct) <= confluence_tolerance_pct
                or (fvg.bottom_price <= current_price <= fvg.top_price * 1.01)
            ) and (current_price >= fib.fib_786 * 0.995)

            if not in_zone:
                continue

            # Rule 6: Price Action Confirmation (No Falling Knives & No Heavy Upper Wicks)
            curr_bar = df.iloc[-1]
            curr_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) and atr_series.iloc[-1] > 0 else 1.0
            c_open = float(curr_bar["open"])
            c_high = float(curr_bar["high"])
            c_low = float(curr_bar["low"])
            c_close = float(curr_bar["close"])
            c_range = max(c_high - c_low, 0.01)

            c_upper_wick = c_high - max(c_open, c_close)
            c_lower_wick = min(c_open, c_close) - c_low
            c_upper_wick_ratio = c_upper_wick / c_range
            c_lower_wick_ratio = c_lower_wick / c_range

            # Freak wick on trigger bar rejection
            if c_upper_wick > 2.0 * curr_atr or c_lower_wick > 2.0 * curr_atr:
                continue

            is_green = c_close >= c_open

            candle_patterns = identify_candlestick_patterns(df.iloc[-2:]) if len(df) >= 2 else ""
            has_bullish_pattern = any(
                p in candle_patterns for p in ["Hammer", "Bullish Engulfing", "Bullish Green", "Piercing", "Morning Star", "Reversal"]
            )

            # Heavy selling rejection at top of bounce candle invalidates clean trigger
            has_heavy_upper_selling = (c_upper_wick_ratio > 0.40) and (c_upper_wick > 0.4 * curr_atr)

            has_bounce_confirmation = (
                (is_green or (c_lower_wick_ratio >= 0.35) or has_bullish_pattern)
                and not has_heavy_upper_selling
            )
            is_waterfall = (c_close < c_open) and (c_lower_wick_ratio < 0.25) and not has_bullish_pattern

            if has_bounce_confirmation:
                is_at_confluence = True
                status = FvgStatus.PULLBACK_AT_618
                if has_bullish_pattern:
                    candle_signal = "🟢 Reversal Candle"
                elif c_lower_wick_ratio >= 0.35:
                    candle_signal = "🟢 Lower Wick Rejection"
                else:
                    candle_signal = "🟢 Green Bounce Bar"
            else:
                is_at_confluence = False
                status = FvgStatus.WATCHLIST_UNMITIGATED
                if is_waterfall:
                    candle_signal = "🔴 Waterfall / Awaiting Bounce"
                else:
                    candle_signal = "🟡 Testing 0.618 / No Trigger"

            # Trade Levels
            entry_price = round(fib.fib_618, 2)
            stop_loss = round(min(fib.fib_786, fvg.bottom_price * 0.995), 2)
            target_1 = round(fib.fib_0, 2)
            target_2 = round(fib.extension_272, 2)

            risk = max(entry_price - stop_loss, 0.05)
            reward = max(target_1 - entry_price, 0.1)
            rr_ratio = reward / risk if risk > 0 else 0.0

            overlap_desc = f"FVG [₹{fvg.bottom_price:.1f} - ₹{fvg.top_price:.1f}] • 50% CE: ₹{fvg.ce_price:.1f}"

            setups.append(
                FvgFibConfluenceSetup(
                    fvg=fvg,
                    fib=fib,
                    status=status,
                    confluence_price=entry_price,
                    fvg_overlap_desc=overlap_desc,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_reward_ratio=rr_ratio,
                    current_price=round(current_price, 2),
                    distance_pct=round(dist_to_618_pct, 2),
                    is_at_confluence=is_at_confluence,
                    candle_signal=candle_signal,
                )
            )

        elif fvg.fvg_type == FvgType.BEARISH_FVG:
            if direction_filter == "BULLISH_ONLY":
                continue

            # 1. Prior Market Structure before FVG (Swing High Base)
            lookback_origin = max(0, fvg_idx - 15)
            prior_swing_low = float(df["low"].iloc[lookback_origin : fvg_idx].min())
            swing_high = float(df["high"].iloc[lookback_origin : fvg_idx].max())

            # 2. Impulse Valley Low created directly AFTER FVG formed
            impulse_slice = df["low"].iloc[fvg_idx + 1 :]
            if impulse_slice.empty:
                continue
            swing_low = float(impulse_slice.min())
            trough_rel_idx = int(impulse_slice.values.argmin())
            trough_idx = (fvg_idx + 1) + trough_rel_idx
            bars_from_fvg_to_trough = trough_idx - fvg_idx
            bars_since_trough = n - 1 - trough_idx

            # Rule 1: Break of Structure (BOS) - Impulse must break below prior swing low
            if swing_low >= prior_swing_low * 0.999:
                continue

            # Rule 2: Clean Direct Impulse - Trough must form within 1 to 4 bars of FVG
            if bars_from_fvg_to_trough > 4:
                continue

            # Rule 3: Tight Rally - Rally from trough must be active and tight (1 to 7 bars)
            if bars_since_trough > 7 or bars_since_trough < 1:
                continue

            # Rule 4: Structural Integrity - Swing Low < FVG Bottom < FVG Top < Swing High
            if not (swing_low < fvg.bottom_price < fvg.top_price < swing_high):
                continue

            if (swing_high - swing_low) / swing_low < 0.015:
                continue

            fib = calculate_fibonacci_retracement(swing_low, swing_high, direction="BEARISH")

            # Rule 4: Confluence Alignment - 0.618 Fib or 0.705 OTE must land inside Bearish FVG
            fvg_min_bound = fvg.bottom_price * 0.995
            fvg_max_bound = fvg.top_price * 1.005
            fib_in_fvg = (fvg_min_bound <= fib.fib_618 <= fvg_max_bound) or (fvg.bottom_price <= fib.fib_705 <= fvg.top_price)

            if not fib_in_fvg:
                continue

            # Rule 5: Strict Invalidation & Direction of Approach
            # Price must be pulling UP from trough. It must NEVER have closed above FVG top or 0.786 Fib
            post_trough_slice = df.iloc[trough_idx :]
            highest_close_since_trough = float(post_trough_slice["close"].max())
            highest_high_since_trough = float(post_trough_slice["high"].max())

            if highest_close_since_trough > fvg.top_price * 1.005 or highest_close_since_trough > fib.fib_786 * 1.005:
                continue  # Violated / Destroyed FVG

            # Disqualify if price previously blew above FVG and is now falling back down (Support, not Resistance)
            if highest_high_since_trough > fvg.top_price * 1.015:
                continue

            # Rule 5b: Anti-Wick & Noise Filter across cycle
            start_noise_check = max(0, fvg_idx - 2)
            if _has_freak_wicks_or_noise(df, start_noise_check, n - 1, atr_series):
                continue  # Disqualify setups with freak shadows or spinning-top noise

            # Check Zone Alignment
            dist_to_618_pct = ((current_price - fib.fib_618) / fib.fib_618) * 100.0
            in_zone = (
                abs(dist_to_618_pct) <= confluence_tolerance_pct
                or (fvg.bottom_price * 0.99 <= current_price <= fvg.top_price)
            ) and (current_price <= fib.fib_786 * 1.005)

            if not in_zone:
                continue

            # Rule 6: Price Action Confirmation (No Bullish Runaways & No Heavy Lower Wicks)
            curr_bar = df.iloc[-1]
            curr_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) and atr_series.iloc[-1] > 0 else 1.0
            c_open = float(curr_bar["open"])
            c_high = float(curr_bar["high"])
            c_low = float(curr_bar["low"])
            c_close = float(curr_bar["close"])
            c_range = max(c_high - c_low, 0.01)

            c_upper_wick = c_high - max(c_open, c_close)
            c_lower_wick = min(c_open, c_close) - c_low
            c_upper_wick_ratio = c_upper_wick / c_range
            c_lower_wick_ratio = c_lower_wick / c_range

            # Freak wick on trigger bar rejection
            if c_upper_wick > 2.0 * curr_atr or c_lower_wick > 2.0 * curr_atr:
                continue

            is_red = c_close <= c_open

            candle_patterns = identify_candlestick_patterns(df.iloc[-2:]) if len(df) >= 2 else ""
            has_bearish_pattern = any(
                p in candle_patterns for p in ["Shooting Star", "Bearish Engulfing", "Hanging Man", "Dark Cloud", "Reversal"]
            )

            # Heavy buying absorption at bottom of rejection candle invalidates clean trigger
            has_heavy_lower_buying = (c_lower_wick_ratio > 0.40) and (c_lower_wick > 0.4 * curr_atr)

            has_rejection_confirmation = (
                (is_red or (c_upper_wick_ratio >= 0.35) or has_bearish_pattern)
                and not has_heavy_lower_buying
            )
            is_bullish_surge = (c_close > c_open) and (c_upper_wick_ratio < 0.25) and not has_bearish_pattern

            if has_rejection_confirmation:
                is_at_confluence = True
                status = FvgStatus.PULLBACK_AT_618
                if has_bearish_pattern:
                    candle_signal = "🔴 Reversal Candle"
                elif c_upper_wick_ratio >= 0.35:
                    candle_signal = "🔴 Upper Wick Rejection"
                else:
                    candle_signal = "🔴 Red Rejection Bar"
            else:
                is_at_confluence = False
                status = FvgStatus.WATCHLIST_UNMITIGATED
                if is_bullish_surge:
                    candle_signal = "🟢 Surging / Awaiting Rejection"
                else:
                    candle_signal = "🟡 Testing 0.618 / No Trigger"

            # Trade Levels
            entry_price = round(fib.fib_618, 2)
            stop_loss = round(max(fib.fib_786, fvg.top_price * 1.005), 2)
            target_1 = round(fib.fib_0, 2)
            target_2 = round(fib.extension_272, 2)

            risk = max(stop_loss - entry_price, 0.05)
            reward = max(entry_price - target_1, 0.1)
            rr_ratio = reward / risk if risk > 0 else 0.0

            overlap_desc = f"FVG [₹{fvg.bottom_price:.1f} - ₹{fvg.top_price:.1f}] • 50% CE: ₹{fvg.ce_price:.1f}"

            setups.append(
                FvgFibConfluenceSetup(
                    fvg=fvg,
                    fib=fib,
                    status=status,
                    confluence_price=entry_price,
                    fvg_overlap_desc=overlap_desc,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    risk_reward_ratio=rr_ratio,
                    current_price=round(current_price, 2),
                    distance_pct=round(dist_to_618_pct, 2),
                    is_at_confluence=is_at_confluence,
                    candle_signal=candle_signal,
                )
            )

    return setups


def scan_stock_for_fvg_fib(
    provider: DhanDataProvider | Any,
    symbol: str,
    security_id: str,
    timeframe: str = "Daily",
    days: int = 180,
    min_gap_pct: float = 0.2,
    confluence_tolerance_pct: float = 1.5,
    body_atr_mult: float = 1.1,
    vol_mult: float = 1.0,
    direction_filter: str = "ALL",
    max_wick_pct: Any = "NA",
) -> FvgFibScanResult:
    """Scan a single stock for Fair Value Gap and 0.618 Fibonacci Retracement Confluence."""
    try:
        df: Optional[pd.DataFrame] = None
        if hasattr(provider, "fetch_bars"):
            df = provider.fetch_bars(security_id=security_id, timeframe=timeframe, days=days)
        elif hasattr(provider, "fetch_daily_bars"):
            df = provider.fetch_daily_bars(security_id=security_id, days=days)
        elif hasattr(provider, "fetch_daily_ohlcv"):
            df = provider.fetch_daily_ohlcv(security_id=security_id, days=days)
        elif hasattr(provider, "get_historical_data"):
            df = provider.get_historical_data(symbol=symbol, security_id=security_id, timeframe=timeframe, days=days)

        if df is None or df.empty or len(df) < 25:
            return FvgFibScanResult(
                symbol=symbol,
                security_id=security_id,
                timeframe=timeframe,
                error="Insufficient price history",
            )

        ltp = float(df["close"].iloc[-1])
        vol_raw = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
        rsi_series = calculate_rsi_series(df["close"], period=14)
        rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else None

        candle_patterns = identify_candlestick_patterns(df.iloc[-3:]) if len(df) >= 3 else ""

        setups = detect_fvg_fib_confluences(
            df=df,
            min_gap_pct=min_gap_pct,
            confluence_tolerance_pct=confluence_tolerance_pct,
            body_atr_mult=body_atr_mult,
            vol_mult=vol_mult,
            direction_filter=direction_filter,
        )

        if not setups:
            return FvgFibScanResult(
                symbol=symbol,
                security_id=security_id,
                ltp=ltp,
                timeframe=timeframe,
                rsi=rsi_val,
                volume=vol_raw,
                has_setup=False,
                candle_signal=candle_patterns if candle_patterns else "Neutral",
            )

        # Prioritize active pullback setups over watchlist setups
        pullback_setups = [s for s in setups if s.is_at_confluence]
        best_setup = pullback_setups[0] if pullback_setups else setups[0]

        # Apply directional rejection wick filter on trigger candle
        is_bullish = best_setup.fvg.fvg_type == FvgType.BULLISH_FVG
        last_o = float(df["open"].iloc[-1])
        last_h = float(df["high"].iloc[-1])
        last_l = float(df["low"].iloc[-1])
        last_c = float(df["close"].iloc[-1])
        wick_ok, _ = check_candle_wick(
            open_price=last_o,
            high_price=last_h,
            low_price=last_l,
            close_price=last_c,
            is_bullish_setup=is_bullish,
            max_wick_pct_param=max_wick_pct,
        )

        is_at_support = bool(best_setup.is_at_confluence and wick_ok)
        best_setup.is_at_confluence = is_at_support

        return FvgFibScanResult(
            symbol=symbol,
            security_id=security_id,
            ltp=ltp,
            timeframe=timeframe,
            has_setup=True,
            setup=best_setup,
            rsi=rsi_val,
            volume=vol_raw,
            candle_signal=best_setup.candle_signal or candle_patterns or "⚡ 0.618 Fib Tap",
        )

    except Exception as exc:
        logger.error("Error scanning FVG+Fib for %s: %s", symbol, exc, exc_info=True)
        return FvgFibScanResult(
            symbol=symbol,
            security_id=security_id,
            timeframe=timeframe,
            error=str(exc),
        )

