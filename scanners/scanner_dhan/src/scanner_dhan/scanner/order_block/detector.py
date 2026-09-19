"""Institutional Order Block Detection and Retest Engine."""

from __future__ import annotations

from typing import Any
import pandas as pd

from scanner_dhan.indicators.atr import calculate_atr, calculate_volume_sma
from scanner_dhan.indicators.rsi import calculate_rsi
from scanner_dhan.scanner.order_block.models import (
    OrderBlock,
    OrderBlockScanResult,
    OrderBlockType,
)
from scanner_dhan.scanner.wick_filter import check_candle_wick

__all__ = ["detect_order_blocks", "analyze_stock_order_block"]


def detect_order_blocks(
    df: pd.DataFrame,
    impulse_multiplier: float = 1.5,
    volume_multiplier: float = 1.5,
    atr_period: int = 14,
    volume_sma_period: int = 20,
) -> list[OrderBlock]:
    """Detect all institutional Order Blocks with displacement & volume surge."""
    min_len = max(atr_period, volume_sma_period) + 2
    if df.empty or len(df) < min_len:
        return []

    df = df.copy()
    atr_series = calculate_atr(df, period=atr_period)
    vol_series = df["volume"].astype(float)
    vol_sma_series = calculate_volume_sma(vol_series, window=volume_sma_period)

    order_blocks: list[OrderBlock] = []
    n = len(df)

    for i in range(max(atr_period, volume_sma_period), n):
        curr_open = float(df["open"].iloc[i])
        curr_close = float(df["close"].iloc[i])
        curr_vol = float(df["volume"].iloc[i])

        curr_atr = float(atr_series.iloc[i])
        curr_vol_sma = float(vol_sma_series.iloc[i])

        if curr_atr <= 0 or curr_vol_sma <= 0:
            continue

        body = abs(curr_close - curr_open)
        body_atr_ratio = body / curr_atr
        vol_ratio = curr_vol / curr_vol_sma

        # Check Displacement & Volume Expansion Rule
        is_impulse = (body_atr_ratio >= impulse_multiplier) and (vol_ratio >= volume_multiplier)
        if not is_impulse:
            continue

        prev_idx = i - 1
        prev_high = float(df["high"].iloc[prev_idx])
        prev_low = float(df["low"].iloc[prev_idx])

        time_val = (
            str(df["timestamp"].iloc[prev_idx]) if "timestamp" in df.columns else f"Bar {prev_idx}"
        )

        # 1. Bullish Order Block (Demand Base)
        if curr_close > curr_open:
            zone_top = float(prev_high)
            zone_bottom = float(prev_low)

            # Check if broken by subsequent candles (close below bottom)
            is_broken = False
            for j in range(i + 1, n):
                if float(df["close"].iloc[j]) < zone_bottom:
                    is_broken = True
                    break

            if not is_broken:
                order_blocks.append(
                    OrderBlock(
                        price_top=zone_top,
                        price_bottom=zone_bottom,
                        block_type=OrderBlockType.BULLISH_DEMAND,
                        candle_timestamp=time_val,
                        impulse_body_expansion=body_atr_ratio,
                        volume_expansion=vol_ratio,
                        is_mitigated=False,
                        description=(
                            f"Demand OB (₹{zone_bottom:,.1f}-₹{zone_top:,.1f} | "
                            f"{body_atr_ratio:.1f}x ATR, {vol_ratio:.1f}x Vol)"
                        ),
                    )
                )

        # 2. Bearish Order Block (Supply Base)
        elif curr_close < curr_open:
            zone_top = float(prev_high)
            zone_bottom = float(prev_low)

            # Check if broken by subsequent candles (close above top)
            is_broken = False
            for j in range(i + 1, n):
                if float(df["close"].iloc[j]) > zone_top:
                    is_broken = True
                    break

            if not is_broken:
                order_blocks.append(
                    OrderBlock(
                        price_top=zone_top,
                        price_bottom=zone_bottom,
                        block_type=OrderBlockType.BEARISH_SUPPLY,
                        candle_timestamp=time_val,
                        impulse_body_expansion=body_atr_ratio,
                        volume_expansion=vol_ratio,
                        is_mitigated=False,
                        description=(
                            f"Supply OB (₹{zone_bottom:,.1f}-₹{zone_top:,.1f} | "
                            f"{body_atr_ratio:.1f}x ATR, {vol_ratio:.1f}x Vol)"
                        ),
                    )
                )

    return order_blocks


def analyze_stock_order_block(
    df: pd.DataFrame,
    symbol: str,
    security_id: str,
    ltp: float | None = None,
    threshold_pct: float = 2.0,
    impulse_multiplier: float = 1.5,
    volume_multiplier: float = 1.5,
    atr_period: int = 14,
    volume_sma_period: int = 20,
    max_wick_pct: Any = "NA",
) -> OrderBlockScanResult:
    """Analyze a single stock for Order Blocks and current price retest status."""
    if df.empty or len(df) < 25:
        return OrderBlockScanResult(
            symbol=symbol,
            security_id=security_id,
            ltp=ltp or 0.0,
            nearest_order_block=None,
            distance_pct=999.0,
            is_at_order_block=False,
            is_fresh_impulse=False,
            all_order_blocks=[],
            volume=0,
            rsi=None,
            candle_signal="Insufficient Data",
        )

    current_price = float(ltp) if (ltp is not None and ltp > 0) else float(df["close"].iloc[-1])
    volume = int(df["volume"].iloc[-1]) if "volume" in df.columns else 0
    rsi = calculate_rsi(df["close"], period=14)

    # Detect Order Blocks
    order_blocks = detect_order_blocks(
        df,
        impulse_multiplier=impulse_multiplier,
        volume_multiplier=volume_multiplier,
        atr_period=atr_period,
        volume_sma_period=volume_sma_period,
    )

    # Check if latest candle itself is an impulse candle
    atr_series = calculate_atr(df, period=atr_period)
    vol_series = df["volume"].astype(float)
    vol_sma_series = calculate_volume_sma(vol_series, window=volume_sma_period)

    latest_body = abs(float(df["close"].iloc[-1]) - float(df["open"].iloc[-1]))
    latest_atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 else 1.0
    latest_vol = float(df["volume"].iloc[-1])
    latest_vol_sma = float(vol_sma_series.iloc[-1]) if len(vol_sma_series) > 0 else 1.0

    is_fresh_impulse = False
    if latest_atr > 0 and latest_vol_sma > 0:
        is_fresh_impulse = (
            latest_body >= impulse_multiplier * latest_atr
            and latest_vol >= volume_multiplier * latest_vol_sma
        )

    if not order_blocks:
        candle_signal = "⚡ Fresh Impulse (No Historical OB)" if is_fresh_impulse else "No Order Blocks"
        return OrderBlockScanResult(
            symbol=symbol,
            security_id=security_id,
            ltp=current_price,
            nearest_order_block=None,
            distance_pct=999.0,
            is_at_order_block=is_fresh_impulse,
            is_fresh_impulse=is_fresh_impulse,
            all_order_blocks=[],
            volume=volume,
            rsi=rsi,
            candle_signal=candle_signal,
        )

    # Find closest Order Block by distance to its zone
    candidates: list[tuple[OrderBlock, float]] = []
    for ob in order_blocks:
        if ob.block_type == OrderBlockType.BULLISH_DEMAND:
            # Distance from zone top or midpoint
            if current_price >= ob.price_top:
                dist = ((current_price - ob.price_top) / ob.price_top) * 100.0
            elif current_price < ob.price_bottom:
                dist = ((current_price - ob.price_bottom) / ob.price_bottom) * 100.0
            else:
                dist = 0.0  # Inside zone
        else:
            # Bearish Supply
            if current_price <= ob.price_bottom:
                dist = ((current_price - ob.price_bottom) / ob.price_bottom) * 100.0
            elif current_price > ob.price_top:
                dist = ((current_price - ob.price_top) / ob.price_top) * 100.0
            else:
                dist = 0.0

        candidates.append((ob, dist))

    candidates.sort(key=lambda x: abs(x[1]))
    best_ob, best_dist = candidates[0]

    # Proximity check: is price inside or within threshold% of zone
    is_at_ob_raw = abs(best_dist) <= threshold_pct or is_fresh_impulse

    # Opposing wick filter on latest candle
    is_bullish = best_ob.block_type == OrderBlockType.BULLISH_DEMAND
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

    is_at_ob = is_at_ob_raw and wick_ok

    # Signal description
    if is_fresh_impulse and best_ob.block_type == OrderBlockType.BULLISH_DEMAND:
        candle_signal = "⚡ Fresh Bullish Impulse (Breakout)"
    elif is_fresh_impulse and best_ob.block_type == OrderBlockType.BEARISH_SUPPLY:
        candle_signal = "⚡ Fresh Bearish Impulse (Breakdown)"
    elif best_ob.block_type == OrderBlockType.BULLISH_DEMAND:
        if best_dist == 0.0:
            candle_signal = "🎯 Inside Bullish Demand OB"
        else:
            candle_signal = "🟢 Retesting Bullish Demand OB"
    else:
        if best_dist == 0.0:
            candle_signal = "🎯 Inside Bearish Supply OB"
        else:
            candle_signal = "🔴 Retesting Bearish Supply OB"

    return OrderBlockScanResult(
        symbol=symbol,
        security_id=security_id,
        ltp=current_price,
        nearest_order_block=best_ob,
        distance_pct=round(best_dist, 2),
        is_at_order_block=is_at_ob,
        is_fresh_impulse=is_fresh_impulse,
        all_order_blocks=order_blocks,
        volume=volume,
        rsi=rsi,
        candle_signal=candle_signal,
    )
