"""ST07: Monthly Heikin Ashi + 89 EMA Technical Calculation Engine."""

from __future__ import annotations

import logging

import pandas as pd

from scanner_dhan.indicators import (
    calculate_ema_series,
    calculate_heikin_ashi,
    calculate_rsi,
)
from scanner_dhan.scanner.st07_scanner.models import St07Category, St07ScanResult

logger = logging.getLogger(__name__)

__all__ = [
    "resample_to_monthly",
    "calculate_monthly_ha_and_emas",
    "analyze_st07_stock",
]


def resample_to_monthly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV DataFrame into Monthly OHLCV candles."""
    if daily_df.empty or len(daily_df) < 5:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = daily_df.copy()
    if "timestamp" not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
        else:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values("timestamp").set_index("timestamp")

    # Resample by month start
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


def calculate_monthly_ha_and_emas(
    monthly_df: pd.DataFrame,
    ema_fast_span: int = 21,
    ema_slow_span: int = 89,
) -> pd.DataFrame:
    """Compute Monthly Heikin Ashi candles and 89/21 EMAs on HA Close.

    Appends columns:
    - ha_open, ha_high, ha_low, ha_close, is_green
    - ema_89, ema_21
    """
    if monthly_df.empty:
        return pd.DataFrame()

    ha_df = calculate_heikin_ashi(monthly_df)

    res = monthly_df.copy()
    res["ha_open"] = ha_df["ha_open"]
    res["ha_high"] = ha_df["ha_high"]
    res["ha_low"] = ha_df["ha_low"]
    res["ha_close"] = ha_df["ha_close"]
    res["ha_is_green"] = ha_df["is_green"]

    # Calculate 89 and 21 EMAs strictly on Monthly Heikin Ashi Close
    res["ema_89"] = calculate_ema_series(res["ha_close"], span=ema_slow_span)
    res["ema_21"] = calculate_ema_series(res["ha_close"], span=ema_fast_span)

    return res


def analyze_st07_stock(
    symbol: str,
    security_id: str,
    daily_or_monthly_df: pd.DataFrame,
    is_already_monthly: bool = False,
    min_monthly_bars: int = 90,
    ltp_override: float | None = None,
) -> St07ScanResult | None:
    """Analyze a single stock against ST07 Monthly Heikin Ashi + 89 EMA Crossover rules.

    Returns:
    - St07ScanResult if sufficient data exists, or None if skipped.
    """
    if daily_or_monthly_df.empty:
        return None

    # 1. Resample to Monthly if input is daily
    if is_already_monthly:
        m_df = daily_or_monthly_df.copy()
    else:
        m_df = resample_to_monthly(daily_or_monthly_df)

    # 2. Check sufficient history (requires at least min_monthly_bars for stable 89 EMA)
    bars_count = len(m_df)
    if bars_count < min_monthly_bars:
        logger.debug(
            "Skipping %s: insufficient monthly bars (%d < %d)",
            symbol,
            bars_count,
            min_monthly_bars,
        )
        return None

    # 3. Calculate Monthly HA and EMAs
    df_calc = calculate_monthly_ha_and_emas(m_df, ema_fast_span=21, ema_slow_span=89)
    if df_calc.empty or len(df_calc) < 2:
        return None

    curr = df_calc.iloc[-1]
    prev = df_calc.iloc[-2]

    # Raw / LTP values
    ltp = float(ltp_override if ltp_override is not None else curr["close"])
    raw_high = float(curr["high"])
    raw_low = float(curr["low"])

    ha_open = float(curr["ha_open"])
    ha_high = float(curr["ha_high"])
    ha_low = float(curr["ha_low"])
    ha_close = float(curr["ha_close"])

    ema_89 = float(curr["ema_89"])
    ema_21 = float(curr["ema_21"])
    ema_89_prev = float(prev["ema_89"])

    # Trend Condition: 89 EMA is rising
    is_ema_89_rising = ema_89 > ema_89_prev

    # Primary Trigger: Fresh Crossover
    # HA_Open < 89 EMA and HA_Close > 89 EMA with Rising 89 EMA
    is_fresh_crossover = bool(is_ema_89_rising and (ha_open < ema_89) and (ha_close > ema_89))

    # Secondary Trigger: Accumulation / Pullback
    # 89 EMA is rising, HA_Low <= 89 EMA and HA_Close >= 89 EMA (testing/touching 89 EMA)
    # Exclude fresh crossover for mutually exclusive classification
    is_accumulation_pullback = bool(
        is_ema_89_rising and (ha_low <= ema_89) and (ha_close >= ema_89) and not is_fresh_crossover
    )

    # Determine Scan Category
    scan_category: St07Category | None = None
    if is_fresh_crossover:
        scan_category = St07Category.FRESH_CROSSOVER
    elif is_accumulation_pullback:
        scan_category = St07Category.ACCUMULATION_PULLBACK

    # Buy Trigger Price (High of current candle) & Stop Loss (Low of current candle)
    buy_trigger_price = round(raw_high, 2)
    stop_loss = round(raw_low, 2)

    # Distance to 89 EMA (%)
    distance_pct = round(((ltp - ema_89) / ema_89) * 100.0, 2) if ema_89 > 0 else 0.0

    # Candle Signal badge string
    if is_fresh_crossover:
        candle_signal = "⚡ Fresh Crossover"
    elif is_accumulation_pullback:
        candle_signal = "🎯 Accumulation Pullback"
    elif is_ema_89_rising and ha_close > ema_89:
        candle_signal = "📈 Bullish Above 89 EMA"
    elif not is_ema_89_rising:
        candle_signal = "📉 89 EMA Falling"
    else:
        candle_signal = "Below 89 EMA"

    # Calculate Monthly RSI (14) with fallbacks
    rsi_val = calculate_rsi(m_df["close"], period=14)
    if rsi_val is None and "ha_close" in df_calc.columns:
        rsi_val = calculate_rsi(df_calc["ha_close"], period=14)
    if rsi_val is None and len(daily_df) >= 15:
        rsi_val = calculate_rsi(daily_df["close"], period=14)

    # Extract Volume (with Daily fallback)
    volume_val = int(curr["volume"]) if "volume" in curr and pd.notna(curr["volume"]) else 0
    if volume_val <= 0 and "volume" in daily_df.columns and len(daily_df) > 0 and pd.notna(daily_df["volume"].iloc[-1]):
        volume_val = int(daily_df["volume"].iloc[-1])

    return St07ScanResult(
        symbol=symbol,
        security_id=security_id,
        ltp=round(ltp, 2),
        scan_category=scan_category,
        is_fresh_crossover=is_fresh_crossover,
        is_accumulation_pullback=is_accumulation_pullback,
        ha_close=round(ha_close, 2),
        ha_open=round(ha_open, 2),
        ha_high=round(ha_high, 2),
        ha_low=round(ha_low, 2),
        ema_89=round(ema_89, 2),
        ema_21=round(ema_21, 2),
        ema_89_prev=round(ema_89_prev, 2),
        is_ema_89_rising=is_ema_89_rising,
        buy_trigger_price=buy_trigger_price,
        stop_loss=stop_loss,
        distance_pct=distance_pct,
        candle_signal=candle_signal,
        monthly_bars_count=bars_count,
        volume=volume_val,
        rsi=rsi_val,
    )
