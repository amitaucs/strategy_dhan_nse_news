"""HA_ST01: Daily Positional Heikin Ashi + RSI Reversal Technical Engine."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from scanner_dhan.indicators.heikin_ashi import calculate_heikin_ashi
from scanner_dhan.indicators.rsi import calculate_rsi_series
from scanner_dhan.scanner.ha_st01_scanner.models import HaSt01ScanResult, HaSt01SetupType
from scanner_dhan.scanner.wick_filter import check_candle_wick

logger = logging.getLogger(__name__)

__all__ = [
    "detect_bullish_divergence",
    "analyze_ha_st01_stock",
]


def detect_bullish_divergence(
    lows: pd.Series,
    rsi_series: pd.Series,
    lookback: int = 25,
    min_pivot_distance: int = 4,
) -> bool:
    """Detect regular bullish divergence between Price Lows and RSI.

    A regular bullish divergence occurs when:
    - Price makes a Lower Low (or equal low).
    - RSI makes a Higher Low over the lookback window.
    """
    if len(lows) < lookback or len(rsi_series) < lookback:
        return False

    sub_lows = lows.iloc[-lookback:].values
    sub_rsi = rsi_series.iloc[-lookback:].values

    # Find swing low pivot points in Price
    price_troughs: list[int] = []
    for i in range(1, len(sub_lows) - 1):
        left_min = min(sub_lows[max(0, i - 2) : i])
        right_min = (
            min(sub_lows[i + 1 : min(len(sub_lows), i + 3)])
            if i < len(sub_lows) - 1
            else sub_lows[i]
        )
        if sub_lows[i] <= left_min and sub_lows[i] <= right_min:
            price_troughs.append(i)

    # Recent minimum in the last 4 bars as the candidate recent trough
    recent_window = 4
    recent_offset = int(np.argmin(sub_lows[-recent_window:]))
    recent_trough_idx = len(sub_lows) - recent_window + recent_offset

    candidate_recent_troughs = set()
    candidate_recent_troughs.add(recent_trough_idx)
    if price_troughs:
        candidate_recent_troughs.add(price_troughs[-1])

    for curr_idx in candidate_recent_troughs:
        curr_price = sub_lows[curr_idx]
        curr_rsi = sub_rsi[curr_idx]
        if np.isnan(curr_rsi):
            continue

        for pt in price_troughs:
            dist = curr_idx - pt
            if dist < min_pivot_distance:
                continue

            prior_price = sub_lows[pt]
            prior_rsi = sub_rsi[pt]

            if np.isnan(prior_rsi):
                continue

            # Regular Bullish Divergence:
            # Price: Lower Low (or equal low <= +0.5%)
            # RSI: Higher Low (>= +1.0 pts)
            if curr_price <= prior_price * 1.005 and curr_rsi >= prior_rsi + 1.0:
                return True

    return False


def analyze_ha_st01_stock(
    symbol: str,
    security_id: str,
    daily_df: pd.DataFrame,
    ltp_override: float | None = None,
    oversold_threshold: float = 35.0,
    min_prior_red_bars: int = 2,
    min_bars_required: int = 40,
    max_wick_pct: Any = "NA",
) -> HaSt01ScanResult | None:
    """Analyze a stock against HA_ST01 Heikin Ashi + RSI Reversal rules.

    Evaluates:
    - Multi-candle downswing stretch (>= min_prior_red_bars consecutive red HA bars before T).
    - Heikin Ashi color flip at latest bar T (previous bar T-1 red, current bar T green).
    - Momentum Exhaustion / Reversal condition:
      * Condition A: RSI(14) <= oversold_threshold (35) in last 3 bars and turning up.
      * Condition B: Regular Bullish Divergence over prior 15-30 bars.
    - Opposing Wick Rejection Filter (Upper rejection wick <= max_wick_pct).
    - Trade Levels:
      * Entry Price = Breakout above current bar High (High * 1.002)
      * Stop-Loss = Lowest Low of last 3-5 bars
      * 1R / 2R Targets & Risk per share.
    """
    if daily_df.empty or len(daily_df) < min_bars_required:
        return None

    df = daily_df.copy()
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)

    # 1. Calculate Heikin Ashi candles & RSI series
    ha_df = calculate_heikin_ashi(df)
    if ha_df.empty or len(ha_df) < min_bars_required:
        return None

    rsi_series = calculate_rsi_series(df["close"], period=14)

    curr_idx = len(df) - 1
    curr_row = df.iloc[curr_idx]
    curr_ha = ha_df.iloc[curr_idx]
    prev_ha = ha_df.iloc[curr_idx - 1]

    ltp = float(ltp_override if ltp_override is not None else curr_row["close"])
    curr_high = float(curr_row["high"])

    # 2. Count prior consecutive Red HA bars before current bar T
    prior_red_count = 0
    for i in range(curr_idx - 1, -1, -1):
        if not bool(ha_df.iloc[i]["is_green"]):
            prior_red_count += 1
        else:
            break

    # 3. Heikin Ashi Color Flip Check
    is_prev_red = not bool(prev_ha["is_green"])
    is_curr_green = bool(curr_ha["is_green"])
    has_prior_downswing = prior_red_count >= min_prior_red_bars
    is_color_flip = bool(is_prev_red and is_curr_green and has_prior_downswing)

    # 4. RSI metrics
    curr_rsi = float(rsi_series.iloc[-1]) if pd.notna(rsi_series.iloc[-1]) else None
    prev_rsi = float(rsi_series.iloc[-2]) if pd.notna(rsi_series.iloc[-2]) else None
    last_3_rsi = [r for r in rsi_series.iloc[-3:] if pd.notna(r)]
    min_rsi_last_3 = float(min(last_3_rsi)) if last_3_rsi else None

    # Condition A: Oversold Recovery
    is_oversold_recovery = False
    if min_rsi_last_3 is not None and curr_rsi is not None and prev_rsi is not None:
        if min_rsi_last_3 <= oversold_threshold and (curr_rsi > prev_rsi or curr_rsi >= 30.0):
            is_oversold_recovery = True

    # Condition B: Bullish Divergence
    has_bullish_div = detect_bullish_divergence(
        lows=df["low"],
        rsi_series=rsi_series,
        lookback=25,
        min_pivot_distance=4,
    )

    # Opposing wick check (Upper wick for bullish reversal)
    is_wick_passed, _ = check_candle_wick(
        open_price=float(curr_row["open"]),
        high_price=float(curr_row["high"]),
        low_price=float(curr_row["low"]),
        close_price=float(curr_row["close"]),
        is_bullish_setup=True,
        max_wick_pct_param=max_wick_pct,
    )

    # 5. Overall Reversal Qualification
    is_reversal_setup = bool(is_color_flip and (is_oversold_recovery or has_bullish_div) and is_wick_passed)

    # Setup Type Classification
    setup_type: HaSt01SetupType | None = None
    if is_reversal_setup:
        if has_bullish_div and is_oversold_recovery:
            setup_type = HaSt01SetupType.CONFLUENCE
        elif has_bullish_div:
            setup_type = HaSt01SetupType.BULLISH_DIVERGENCE
        else:
            setup_type = HaSt01SetupType.OVERSOLD_RECOVERY

    # 6. Trade Execution Levels
    # Entry Trigger: Break above current candle High with tiny 0.2% buffer
    entry_price = round(curr_high * 1.002, 2)

    # Structural Stop-Loss: Lowest Low of recent 3 to 5 bars
    lookback_sl_bars = min(5, len(df))
    cluster_low = float(df.iloc[-lookback_sl_bars:]["low"].min())
    stop_loss = round(cluster_low, 2)

    # Risk per share
    risk_per_share = round(entry_price - stop_loss, 2)
    if risk_per_share <= 0:
        # Fallback 1.5% stop loss below entry if bar is exceptionally flat
        stop_loss = round(entry_price * 0.985, 2)
        risk_per_share = round(entry_price - stop_loss, 2)

    # Targets
    target_1r = round(entry_price + risk_per_share, 2)
    target_2r = round(entry_price + (2 * risk_per_share), 2)
    reward_risk_ratio = 1.0

    # Distance to Stop Loss (%)
    distance_pct = round(((ltp - stop_loss) / stop_loss) * 100.0, 2) if stop_loss > 0 else 0.0

    # Monthly / Daily volume
    volume_val = (
        int(curr_row["volume"]) if "volume" in curr_row and pd.notna(curr_row["volume"]) else 0
    )

    # Candle Signal badge string
    if is_reversal_setup:
        if setup_type == HaSt01SetupType.CONFLUENCE:
            candle_signal = f"🔥 Divergence + Oversold ({prior_red_count} Red Flip)"
        elif setup_type == HaSt01SetupType.BULLISH_DIVERGENCE:
            candle_signal = f"🌟 Bullish Divergence ({prior_red_count} Red Flip)"
        else:
            candle_signal = f"⚡ Oversold Flip ({prior_red_count} Red Flip, RSI {curr_rsi:.0f})"
    elif is_color_flip:
        candle_signal = f"HA Green Flip ({prior_red_count} Red, RSI {curr_rsi:.0f})"
    elif is_prev_red and not is_curr_green:
        candle_signal = f"Red Downswing ({prior_red_count} Bars)"
    else:
        candle_signal = f"RSI {curr_rsi:.0f}" if curr_rsi is not None else "-"

    return HaSt01ScanResult(
        symbol=symbol,
        security_id=security_id,
        ltp=round(ltp, 2),
        is_reversal_setup=is_reversal_setup,
        setup_type=setup_type,
        ha_open=round(float(curr_ha["ha_open"]), 2),
        ha_close=round(float(curr_ha["ha_close"]), 2),
        ha_high=round(float(curr_ha["ha_high"]), 2),
        ha_low=round(float(curr_ha["ha_low"]), 2),
        rsi=curr_rsi,
        rsi_prev=prev_rsi,
        rsi_min_last_3=min_rsi_last_3,
        entry_price=entry_price,
        stop_loss=stop_loss,
        risk_per_share=risk_per_share,
        target_1r=target_1r,
        target_2r=target_2r,
        reward_risk_ratio=reward_risk_ratio,
        prior_red_ha_count=prior_red_count,
        is_ha_color_flip=is_color_flip,
        has_bullish_divergence=has_bullish_div,
        is_oversold_recovery=is_oversold_recovery,
        volume=volume_val,
        candle_signal=candle_signal,
        distance_pct=distance_pct,
    )
