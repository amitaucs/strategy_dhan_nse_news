"""ATH-ST08: Monthly All-Time High Breakout Technical Calculation Engine."""

from __future__ import annotations

import logging

import pandas as pd

from scanner_dhan.indicators import calculate_rsi, calculate_sma
from scanner_dhan.scanner.ath_st08_scanner.models import AthBreakoutScanResult, AthClass

logger = logging.getLogger(__name__)

__all__ = [
    "resample_to_monthly_ath",
    "resample_to_weekly_ath",
    "calculate_30_week_sma",
    "analyze_ath_stock",
]


def resample_to_monthly_ath(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV DataFrame into Monthly OHLCV candles."""
    if daily_df.empty or len(daily_df) < 5:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = daily_df.copy()
    if "timestamp" not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
        else:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values("timestamp").set_index("timestamp")

    monthly = (
        df.resample("MS")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum" if "volume" in df.columns else "count",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return monthly


def resample_to_weekly_ath(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV DataFrame into Weekly OHLCV candles (Friday aligned)."""
    if daily_df.empty or len(daily_df) < 5:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = daily_df.copy()
    if "timestamp" not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
        else:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values("timestamp").set_index("timestamp")

    weekly = (
        df.resample("W-FRI")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum" if "volume" in df.columns else "count",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return weekly


def calculate_30_week_sma(weekly_df: pd.DataFrame) -> float:
    """Calculate the 30-Week Simple Moving Average on weekly close prices."""
    if weekly_df.empty:
        return 0.0

    sma_val = calculate_sma(weekly_df["close"], window=30)
    if sma_val is not None:
        return float(round(sma_val, 2))

    # Fallback to rolling average of available weekly bars
    return float(round(weekly_df["close"].mean(), 2))


def analyze_ath_stock(
    symbol: str,
    security_id: str,
    daily_df: pd.DataFrame,
    ltp_override: float | None = None,
    min_monthly_bars: int = 12,
    max_exhaustion_ratio: float = 2.5,
) -> AthBreakoutScanResult | None:
    """Analyze a single stock against ATH-ST08 Monthly Breakout rules.

    Evaluates:
    - Prior ATH High strictly BEFORE current month.
    - Green candle condition (Close > Open).
    - Breakout close (Close > Prior ATH High).
    - Exhaustion filter (Current candle range <= 2.5x 12-month avg range).
    - Consolidation duration (A-Class >30m vs B-Class <=30m).
    - Trigger Entry (High + 1%) and 30-Week SMA trailing level.
    """
    if daily_df.empty or len(daily_df) < 20:
        return None

    # 1. Resample to Monthly and Weekly
    m_df = resample_to_monthly_ath(daily_df)
    w_df = resample_to_weekly_ath(daily_df)

    bars_count = len(m_df)
    if bars_count < min_monthly_bars:
        logger.debug(
            "Skipping %s: insufficient history (%d < %d)", symbol, bars_count, min_monthly_bars
        )
        return None

    # 2. Prior ATH Calculation (strictly before current month)
    prior_df = m_df.iloc[:-1]
    prior_highs = prior_df["high"]
    prior_ath_price = float(prior_highs.max())
    prior_ath_idx = int(prior_highs.idxmax())

    prior_ath_timestamp = prior_df.loc[prior_ath_idx, "timestamp"]
    if isinstance(prior_ath_timestamp, pd.Timestamp):
        prior_ath_date = prior_ath_timestamp.strftime("%Y-%m-%d")
    else:
        prior_ath_date = str(prior_ath_timestamp)[:10]

    # 3. Current Monthly Candle
    curr = m_df.iloc[-1]
    curr_open = float(curr["open"])
    curr_high = float(curr["high"])
    curr_low = float(curr["low"])
    curr_close = float(curr["close"])
    ltp = float(ltp_override if ltp_override is not None else curr_close)

    # 4. Breakout & Green Candle Conditions
    is_green = curr_close > curr_open
    is_above_prior_ath = curr_close > prior_ath_price

    # 5. Exhaustion Filter Calculation
    curr_range_pct = ((curr_high - curr_low) / curr_open) * 100.0 if curr_open > 0 else 0.0

    # 12-Month Average Candle Range of prior bars
    lookback_12 = min(12, len(prior_df))
    prior_12_df = prior_df.iloc[-lookback_12:]
    prior_12_ranges = ((prior_12_df["high"] - prior_12_df["low"]) / prior_12_df["open"]) * 100.0
    avg_range_12m_pct = (
        float(prior_12_ranges.mean()) if not prior_12_ranges.empty else curr_range_pct
    )

    range_expansion_ratio = (
        round(curr_range_pct / avg_range_12m_pct, 2) if avg_range_12m_pct > 0 else 1.0
    )
    is_exhaustion_passed = range_expansion_ratio <= max_exhaustion_ratio

    # 6. Consolidation Duration (in Monthly bars)
    curr_idx = len(m_df) - 1
    months_in_consolidation = int(curr_idx - prior_ath_idx)

    # 7. Setup Classification
    is_ath_breakout = bool(is_green and is_above_prior_ath and is_exhaustion_passed)
    ath_class: AthClass | None = None
    if is_ath_breakout:
        if months_in_consolidation > 30:
            ath_class = AthClass.A_CLASS
        else:
            ath_class = AthClass.B_CLASS

    # 8. Entry & Benchmark Levels
    trigger_entry_price = round(curr_high * 1.01, 2)  # High + 1% buffer
    sma_30_week = calculate_30_week_sma(w_df)

    # Distance to Prior ATH (%)
    distance_pct = (
        round(((ltp - prior_ath_price) / prior_ath_price) * 100.0, 2)
        if prior_ath_price > 0
        else 0.0
    )

    # Monthly Volume & RSI (with Daily fallback if monthly volume is 0 or RSI is None)
    volume_val = int(curr["volume"]) if "volume" in curr and pd.notna(curr["volume"]) else 0
    if volume_val <= 0 and "volume" in daily_df.columns and len(daily_df) > 0 and pd.notna(daily_df["volume"].iloc[-1]):
        volume_val = int(daily_df["volume"].iloc[-1])

    rsi_val = calculate_rsi(m_df["close"], period=14)
    if rsi_val is None and len(daily_df) >= 15:
        rsi_val = calculate_rsi(daily_df["close"], period=14)

    # Candle Signal badge
    if is_ath_breakout:
        if ath_class == AthClass.A_CLASS:
            candle_signal = f"🏆 A-Class (>{months_in_consolidation}m ATH)"
        else:
            candle_signal = f"⚡ B-Class ({months_in_consolidation}m ATH)"
    elif is_above_prior_ath and not is_exhaustion_passed:
        candle_signal = f"⚠️ Climax Exhaustion ({range_expansion_ratio:.1f}x)"
    elif is_above_prior_ath and not is_green:
        candle_signal = "🔻 Red Candle Above ATH"
    elif distance_pct >= -3.0:
        candle_signal = f"🎯 Near ATH ({distance_pct:+.1f}%)"
    else:
        candle_signal = f"Below ATH ({distance_pct:+.1f}%)"

    return AthBreakoutScanResult(
        symbol=symbol,
        security_id=security_id,
        ltp=round(ltp, 2),
        is_ath_breakout=is_ath_breakout,
        prior_ath_price=round(prior_ath_price, 2),
        prior_ath_date=prior_ath_date,
        months_in_consolidation=months_in_consolidation,
        ath_class=ath_class,
        breakout_candle_high=round(curr_high, 2),
        breakout_candle_low=round(curr_low, 2),
        breakout_candle_open=round(curr_open, 2),
        breakout_candle_close=round(curr_close, 2),
        trigger_entry_price=trigger_entry_price,
        sma_30_week=sma_30_week,
        candle_range_pct=round(curr_range_pct, 2),
        avg_range_12m_pct=round(avg_range_12m_pct, 2),
        range_expansion_ratio=range_expansion_ratio,
        is_exhaustion_passed=is_exhaustion_passed,
        distance_pct=distance_pct,
        candle_signal=candle_signal,
        monthly_bars_count=bars_count,
        volume=volume_val,
        rsi=rsi_val,
    )
