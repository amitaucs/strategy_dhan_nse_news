"""Engine for Mark Minervini Volatility Contraction Pattern (VCP) Detection."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from scipy.signal import find_peaks
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

from scanner_dhan.indicators.atr import calculate_atr
from scanner_dhan.indicators.rsi import calculate_rsi_series
from scanner_dhan.scanner.wick_filter import check_candle_wick
from scanner_dhan.scanner.vcp_scanner.models import (
    Stage2Metrics,
    VcpPattern,
    VcpScanResult,
    VcpSchematic,
    VcpStatus,
    VcpWave,
)

logger = logging.getLogger(__name__)

__all__ = [
    "evaluate_stage2_trend",
    "detect_peaks_and_troughs",
    "detect_vcp_pattern",
    "scan_stock_for_vcp",
]


def evaluate_stage2_trend(df: pd.DataFrame) -> Stage2Metrics:
    """Evaluate Mark Minervini's Stage 2 Institutional Trend Template criteria.

    Rules:
    1. Close > SMA 50 > SMA 150 > SMA 200 (or Close within 2% of SMA 50 in tight base)
    2. 200 SMA slope is positive over past 20 trading sessions.
    3. Close is within 30% of 52-week High.
    4. Close is at least 25% above 52-week Low.
    """
    n = len(df)
    if n < 150:
        c_val = float(df["close"].iloc[-1]) if not df.empty else 0.0
        return Stage2Metrics(
            current_close=c_val,
            sma_50=0.0,
            sma_150=0.0,
            sma_200=0.0,
            sma_200_slope_pct=0.0,
            high_52w=c_val,
            low_52w=c_val,
            pct_from_52w_high=0.0,
            pct_from_52w_low=0.0,
            is_stage2=False,
        )

    closes = df["close"].astype(float)
    highs = df["high"].astype(float)
    lows = df["low"].astype(float)

    sma50_series = closes.rolling(50, min_periods=35).mean()
    sma150_series = closes.rolling(150, min_periods=100).mean()
    sma200_series = closes.rolling(200, min_periods=120).mean()

    c = float(closes.iloc[-1])
    sma50 = float(sma50_series.iloc[-1]) if not pd.isna(sma50_series.iloc[-1]) else c
    sma150 = float(sma150_series.iloc[-1]) if not pd.isna(sma150_series.iloc[-1]) else c * 0.95
    sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else c * 0.90

    # 200 SMA Slope
    slope_lookback = min(20, len(sma200_series.dropna()) - 1)
    if slope_lookback > 5 and not pd.isna(sma200_series.iloc[-slope_lookback]):
        past_200 = float(sma200_series.iloc[-slope_lookback])
        slope_pct = ((sma200 - past_200) / max(past_200, 1e-4)) * 100.0
    else:
        slope_pct = 0.0

    # 52-Week Statistics (using available lookback up to 250 bars)
    stat_window = min(250, n)
    high_52w = float(highs.iloc[-stat_window:].max())
    low_52w = float(lows.iloc[-stat_window:].min())

    pct_from_high = ((c - high_52w) / max(high_52w, 1e-4)) * 100.0
    pct_from_low = ((c - low_52w) / max(low_52w, 1e-4)) * 100.0

    # Evaluate Stage 2 Template
    # Allow close to be slightly below SMA50 during tight base consolidation (within 3.5%)
    sma_alignment = (c >= sma50 * 0.965) and (sma50 >= sma150 * 0.98) and (sma150 >= sma200 * 0.98)
    upward_slope = slope_pct >= -0.25  # Flat to upward sloping
    near_highs = c >= (0.70 * high_52w)
    above_lows = c >= (1.25 * low_52w)

    is_stage2 = bool(sma_alignment and upward_slope and near_highs and above_lows)

    return Stage2Metrics(
        current_close=round(c, 2),
        sma_50=round(sma50, 2),
        sma_150=round(sma150, 2),
        sma_200=round(sma200, 2),
        sma_200_slope_pct=round(slope_pct, 2),
        high_52w=round(high_52w, 2),
        low_52w=round(low_52w, 2),
        pct_from_52w_high=round(pct_from_high, 2),
        pct_from_52w_low=round(pct_from_low, 2),
        is_stage2=is_stage2,
    )


def _find_peaks_numpy(values: np.ndarray, distance: int, prominence: float) -> np.ndarray:
    """Pure NumPy fallback for extrema detection when SciPy is unavailable."""
    peaks = []
    n = len(values)
    for i in range(1, n - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            # Prominence check
            left_min = np.min(values[max(0, i - distance) : i])
            right_min = np.min(values[i + 1 : min(n, i + distance + 1)])
            prom = values[i] - max(left_min, right_min)
            if prom >= prominence:
                if not peaks or (i - peaks[-1]) >= distance:
                    peaks.append(i)
                elif values[i] > values[peaks[-1]]:
                    peaks[-1] = i
    return np.array(peaks, dtype=int)


def detect_peaks_and_troughs(
    df: pd.DataFrame,
    lookback_bars: int = 120,
    peak_distance: int = 5,
    prominence_pct: float = 0.018,
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract significant swing highs (peaks) and swing lows (troughs) using dynamic prominence."""
    n = len(df)
    window = min(lookback_bars, n)
    base_df = df.iloc[-window:].copy().reset_index(drop=True)

    highs = base_df["high"].values.astype(float)
    lows = base_df["low"].values.astype(float)
    closes = base_df["close"].values.astype(float)

    avg_price = float(np.mean(closes))
    min_prominence = max(avg_price * prominence_pct, 0.5)

    if _HAS_SCIPY:
        peaks, _ = find_peaks(highs, distance=peak_distance, prominence=min_prominence)
        troughs, _ = find_peaks(-lows, distance=peak_distance, prominence=min_prominence)
    else:
        peaks = _find_peaks_numpy(highs, distance=peak_distance, prominence=min_prominence)
        troughs = _find_peaks_numpy(-lows, distance=peak_distance, prominence=min_prominence)

    return peaks, troughs


def _classify_vcp_schematic(
    waves: List[VcpWave],
    current_price: float,
    high_52w: float,
    prior_resistance: float,
) -> VcpSchematic:
    """Classify the VCP pattern into one of the institutional Mid-Cap schematics."""
    pivot = waves[-1].peak_price
    base_low = min(w.trough_price for w in waves)
    base_high = max(w.peak_price for w in waves)

    # Schematic 2: Breakout Retest (Base formed on top of broken resistance shelf)
    if prior_resistance > 0 and base_low >= prior_resistance * 0.97 and current_price >= prior_resistance:
        return VcpSchematic.SCHEMATIC_2_BREAKOUT_RETEST

    # Schematic 3: Staircase Trend Base (Near 52-week Highs, shallow depth)
    if high_52w > 0 and (high_52w - pivot) / high_52w <= 0.05 and waves[0].depth_pct <= 18.0:
        return VcpSchematic.SCHEMATIC_3_STAIRCASE_BASE

    # Schematic 5: High Tight Shelf VCP (Sharp V-recovery with tight shelf)
    if len(waves) >= 2 and waves[0].depth_pct >= 20.0 and waves[-1].depth_pct <= 4.5:
        return VcpSchematic.SCHEMATIC_5_HIGH_TIGHT_SHELF

    # Default Schematic 1: Standard Base under Pivot
    return VcpSchematic.SCHEMATIC_1_UNDER_RESISTANCE


def detect_vcp_pattern(
    df: pd.DataFrame,
    lookback_bars: int = 120,
    peak_distance: int = 5,
    prominence_pct: float = 0.018,
    max_final_depth_pct: float = 6.5,
    vdu_threshold: float = 0.75,
    min_contractions: int = 2,
) -> Optional[VcpPattern]:
    """Detect complete Mark Minervini Volatility Contraction Pattern (VCP) with institutional rules."""
    if df.empty or len(df) < 60:
        return None

    # 1. Evaluate Stage 2 Institutional Trend Template
    stage2 = evaluate_stage2_trend(df)
    if not stage2.is_stage2:
        return None

    # 2. Extract Peaks and Troughs in Base Window
    n = len(df)
    window = min(lookback_bars, n)
    base_df = df.iloc[-window:].copy().reset_index(drop=True)

    highs = base_df["high"].values.astype(float)
    lows = base_df["low"].values.astype(float)
    closes = base_df["close"].values.astype(float)
    volumes = base_df["volume"].values.astype(float)

    peaks, troughs = detect_peaks_and_troughs(
        df=df,
        lookback_bars=lookback_bars,
        peak_distance=peak_distance,
        prominence_pct=prominence_pct,
    )

    if len(peaks) < min_contractions or len(troughs) < min_contractions:
        return None

    # 3. Calculate 50-day Volume SMA for VDU exhaustion analysis
    vol_series = df["volume"].astype(float)
    vol_sma50_series = vol_series.rolling(50, min_periods=20).mean()
    vol_sma50 = float(vol_sma50_series.iloc[-1]) if not pd.isna(vol_sma50_series.iloc[-1]) else float(vol_series.mean())

    # 4. Pair Each Peak with Its Subsequent Trough (Chronological Waves)
    raw_waves: List[VcpWave] = []
    for wave_idx, p in enumerate(peaks):
        subsequent_troughs = [t for t in troughs if t > p]
        if not subsequent_troughs:
            # Check if there is an intraday/recent pullback after peak up to current bar
            if p < len(base_df) - 1:
                t = int(p + np.argmin(lows[p:]))
                if t == p:
                    continue
            else:
                continue
        else:
            # Find the lowest trough before the next peak or within this wave
            next_peak = [np_ for np_ in peaks if np_ > p]
            if next_peak:
                valid_troughs = [t for t in subsequent_troughs if t < next_peak[0]]
                if not valid_troughs:
                    continue
                t = valid_troughs[int(np.argmin([lows[t_] for t_ in valid_troughs]))]
            else:
                t = subsequent_troughs[0]

        p_val = float(highs[p])
        t_val = float(lows[t])
        if p_val <= 0 or t_val >= p_val:
            continue

        depth_pct = ((p_val - t_val) / p_val) * 100.0
        wave_vol = float(np.mean(volumes[p : t + 1])) if t >= p else vol_sma50
        vdu_wave_ratio = wave_vol / max(vol_sma50, 1.0)

        raw_waves.append(
            VcpWave(
                wave_number=len(raw_waves) + 1,
                peak_bar=int(p),
                trough_bar=int(t),
                peak_price=round(p_val, 2),
                trough_price=round(t_val, 2),
                depth_pct=round(depth_pct, 2),
                bars_duration=int(abs(t - p)),
                avg_volume=round(wave_vol, 0),
                vdu_ratio=round(vdu_wave_ratio, 2),
            )
        )

    if len(raw_waves) < min_contractions:
        return None

    # Keep the most recent 2 to 4 contraction waves
    active_waves = raw_waves[-4:]
    for idx, w in enumerate(active_waves):
        w.wave_number = idx + 1

    depths = [w.depth_pct for w in active_waves]

    # 5. Invariant Checks
    # A. Monotonic Contraction Decay (allow 0.85% buffer for market noise)
    is_contracting = all(
        depths[i] > (depths[i + 1] - 0.85) for i in range(len(depths) - 1)
    )
    if not is_contracting:
        return None

    # B. Final Contraction Tightness (<= max_final_depth_pct, default 6.5%)
    final_depth = depths[-1]
    if final_depth > max_final_depth_pct:
        return None

    # C. Flat or Ascending Structural Floor (Troughs must hold base support)
    first_trough = active_waves[0].trough_price
    final_trough = active_waves[-1].trough_price
    if final_trough < (first_trough * 0.94):
        return None

    # D. Volume Dry-Up (VDU) in Final Contraction
    final_trough_idx = active_waves[-1].trough_bar
    final_wave_slice = volumes[final_trough_idx:]
    final_wave_vol = float(np.mean(final_wave_slice)) if len(final_wave_slice) > 0 else float(volumes[-1])
    vdu_ratio = final_wave_vol / max(vol_sma50, 1.0)
    is_vdu = vdu_ratio <= vdu_threshold

    current_price = float(closes[-1])
    current_vol = float(volumes[-1])

    # 6. Pivot Calculation & Trade Levels
    pivot_level = max(w.peak_price for w in active_waves[-2:])  # Pivot is the recent contraction high
    stop_loss = round(active_waves[-1].trough_price * 0.995, 2)
    risk_pct = round(((pivot_level - stop_loss) / pivot_level) * 100.0, 2)

    base_height = pivot_level - min(w.trough_price for w in active_waves)
    target_1 = round(pivot_level + 1.0 * base_height, 2)
    target_2 = round(pivot_level + 2.0 * base_height, 2)

    risk_amt = max(pivot_level - stop_loss, 0.5)
    reward_amt = max(target_1 - pivot_level, 1.0)
    rr_ratio = round(reward_amt / risk_amt, 2) if risk_amt > 0 else 0.0

    # Prior structural resistance estimation for schematic classification
    prior_resistance = float(highs[: active_waves[0].peak_bar].max()) if active_waves[0].peak_bar > 5 else 0.0
    schematic = _classify_vcp_schematic(
        waves=active_waves,
        current_price=current_price,
        high_52w=stage2.high_52w,
        prior_resistance=prior_resistance,
    )

    # 7. Status Resolution & Trigger Detection
    is_breakout = (current_price >= pivot_level * 0.998) and (current_vol >= 1.25 * vol_sma50)
    is_primed = (abs(current_price - pivot_level) / pivot_level <= 0.035) and (final_depth <= max_final_depth_pct) and is_vdu

    if is_breakout:
        status = VcpStatus.BREAKOUT_ACTIVE
        candle_signal = "🔥 Pivot Breakout Active"
    elif is_primed:
        status = VcpStatus.PRIMED_TIGHT
        candle_signal = f"⚡ {len(active_waves)}T VCP (Tight {final_depth:.1f}%)"
    elif is_vdu:
        status = VcpStatus.FORMING_CONTRACTION
        candle_signal = f"⏳ {len(active_waves)}T VCP (VDU {vdu_ratio:.2f}x)"
    else:
        status = VcpStatus.WATCHLIST
        candle_signal = f"👀 {len(active_waves)}T Contraction"

    return VcpPattern(
        waves=active_waves,
        contractions_count=len(active_waves),
        depth_sequence_pct=depths,
        final_depth_pct=final_depth,
        pivot_level=pivot_level,
        stop_loss=stop_loss,
        risk_pct=risk_pct,
        target_1=target_1,
        target_2=target_2,
        risk_reward_ratio=rr_ratio,
        vdu_ratio=round(vdu_ratio, 2),
        is_vdu=is_vdu,
        status=status,
        schematic=schematic,
        stage2=stage2,
        candle_signal=candle_signal,
    )


def scan_stock_for_vcp(
    provider: Any,
    symbol: str,
    security_id: str,
    timeframe: str = "Daily",
    days: int = 365,
    max_final_depth_pct: float = 6.5,
    vdu_threshold: float = 0.75,
    min_contractions: int = 2,
    max_wick_pct: Any = "NA",
) -> VcpScanResult:
    """Scan a single stock for Volatility Contraction Pattern (VCP)."""
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

        if df is None or df.empty or len(df) < 60:
            return VcpScanResult(
                symbol=symbol,
                security_id=security_id,
                timeframe=timeframe,
                error="Insufficient price history (< 60 bars)",
            )

        ltp = float(df["close"].iloc[-1])
        vol_raw = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0.0
        rsi_series = calculate_rsi_series(df["close"], period=14)
        rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else None

        pattern = detect_vcp_pattern(
            df=df,
            lookback_bars=120,
            peak_distance=5,
            prominence_pct=0.018,
            max_final_depth_pct=max_final_depth_pct,
            vdu_threshold=vdu_threshold,
            min_contractions=min_contractions,
        )

        if not pattern:
            return VcpScanResult(
                symbol=symbol,
                security_id=security_id,
                ltp=ltp,
                timeframe=timeframe,
                rsi=rsi_val,
                volume=vol_raw,
                has_setup=False,
                is_at_support=False,
                candle_signal="Neutral",
            )

        # Active setups are either Primed or Active Breakout
        is_ready = pattern.status in (VcpStatus.PRIMED_TIGHT, VcpStatus.BREAKOUT_ACTIVE)

        # Optional opposing wick check on trigger/latest candle
        last_o = float(df["open"].iloc[-1])
        last_h = float(df["high"].iloc[-1])
        last_l = float(df["low"].iloc[-1])
        last_c = float(df["close"].iloc[-1])
        wick_ok, wick_pct = check_candle_wick(
            open_price=last_o,
            high_price=last_h,
            low_price=last_l,
            close_price=last_c,
            is_bullish_setup=True,
            max_wick_pct_param=max_wick_pct,
        )
        if not wick_ok:
            is_ready = False

        seq_str = " → ".join(f"{d:.1f}%" for d in pattern.depth_sequence_pct)
        support_desc = f"VCP {pattern.contractions_count}T [{seq_str}] • Pivot: ₹{pattern.pivot_level:.1f}"

        return VcpScanResult(
            symbol=symbol,
            security_id=security_id,
            ltp=ltp,
            timeframe=timeframe,
            has_setup=True,
            is_at_support=is_ready,
            setup=pattern,
            rsi=rsi_val,
            volume=vol_raw,
            support_desc=support_desc,
            candle_signal=pattern.candle_signal,
        )

    except Exception as exc:
        logger.error("Error scanning VCP for %s: %s", symbol, exc, exc_info=True)
        return VcpScanResult(
            symbol=symbol,
            security_id=security_id,
            timeframe=timeframe,
            error=str(exc),
        )

