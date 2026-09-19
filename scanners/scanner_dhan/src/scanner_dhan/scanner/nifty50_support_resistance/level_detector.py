"""Support and Resistance Level Detection Engine."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from scanner_dhan.indicators import (
    calculate_ema,
    calculate_floor_pivots,
    calculate_rsi,
    calculate_sma,
    identify_candlestick_patterns,
)
from scanner_dhan.scanner.nifty50_support_resistance.models import (
    StockSupportScan,
    SupportLevel,
    SupportType,
)
from scanner_dhan.scanner.wick_filter import check_candle_wick

__all__ = [
    "get_configured_ema_periods",
    "detect_swing_supports",
    "detect_support_confluences",
    "detect_swing_resistances",
    "detect_resistance_confluences",
    "detect_ma_supports",
    "detect_pivot_supports",
    "detect_pivot_resistances",
    "detect_52w_low_support",
    "detect_52w_high_resistance",
    "analyze_stock_support",
    "analyze_stock_resistance",
]


def get_configured_ema_periods() -> list[int]:
    """Load configured EMA periods from environment or .env file (default: [20, 50, 100, 200])."""
    raw = os.getenv("EMA_PERIODS", "20,50,100,200").strip()
    periods: list[int] = []
    for item in raw.split(","):
        item_clean = item.strip()
        if item_clean.isdigit():
            val = int(item_clean)
            if val > 0:
                periods.append(val)
    return periods or [20, 50, 100, 200]


def detect_swing_supports(
    df: pd.DataFrame,
    window: int = 5,
    cluster_pct: float = 0.018,
    min_bounce_pct: float = 0.03,
    min_touch_separation: int = 5,
) -> list[SupportLevel]:
    """Detect fractal swing lows with bounce displacement and cluster into Major Zones."""
    if len(df) < window * 2 + 1:
        return []

    lows = df["low"].values
    highs = df["high"].values
    n = len(lows)

    # Store tuples of (bar_index, low_price)
    swing_points: list[tuple[int, float]] = []

    for i in range(window, n - window):
        current_low = float(lows[i])
        # 1. Fractal check: local minimum in [-window, +window]
        if current_low == min(lows[i - window : i + window + 1]):
            # 2. Bounce Displacement check: ensure price rallied away from this low
            subsequent_highs = highs[i + 1 : min(n, i + window * 3 + 1)]
            if len(subsequent_highs) > 0:
                max_subsequent = float(max(subsequent_highs))
                bounce_pct = (max_subsequent - current_low) / current_low
                if bounce_pct >= min_bounce_pct:
                    swing_points.append((i, current_low))
            else:
                # Close to right edge
                swing_points.append((i, current_low))

    if not swing_points:
        return []

    # Sort swing points by price
    swing_points.sort(key=lambda x: x[1])

    # Cluster points that are within cluster_pct of each other
    clusters: list[list[tuple[int, float]]] = []

    for idx, pt_price in swing_points:
        matched = False
        for cl in clusters:
            avg_price = sum(p for _, p in cl) / len(cl)
            if abs(pt_price - avg_price) / avg_price <= cluster_pct:
                # Check temporal separation with existing points in this cluster
                too_close = any(abs(idx - ex_idx) < min_touch_separation for ex_idx, _ in cl)
                if not too_close:
                    cl.append((idx, pt_price))
                    matched = True
                    break
                else:
                    # Update with lowest low from same local base
                    min_existing_idx = min(range(len(cl)), key=lambda k: cl[k][1])
                    if pt_price < cl[min_existing_idx][1]:
                        cl[min_existing_idx] = (idx, pt_price)
                    matched = True
                    break
        if not matched:
            clusters.append([(idx, pt_price)])

    supports: list[SupportLevel] = []
    for cl in clusters:
        prices = [p for _, p in cl]
        avg_p = float(round(sum(prices) / len(prices), 2))
        touch_count = len(cl)
        min_p = float(round(min(prices), 2))
        max_p = float(round(max(prices), 2))

        if touch_count >= 2:
            desc = f"🏛️ Major Support Zone ({touch_count} Bounces | ₹{min_p}-₹{max_p})"
            level_type = SupportType.MAJOR_SUPPORT_ZONE
            strength = 3 + touch_count
        else:
            desc = f"Swing Low (1 Bounce | ₹{avg_p})"
            level_type = SupportType.SWING_LOW
            strength = 2

        supports.append(
            SupportLevel(
                price=avg_p,
                level_type=level_type,
                strength=strength,
                description=desc,
            )
        )

    return supports


def detect_support_confluences(
    supports: list[SupportLevel],
    tolerance_pct: float = 0.015,
) -> list[SupportLevel]:
    """Detect confluences where horizontal support zones converge with EMAs or Pivots."""
    if len(supports) < 2:
        return []

    confluences: list[SupportLevel] = []
    used_pairs: set[tuple[int, int]] = set()

    for i in range(len(supports)):
        s1 = supports[i]
        for j in range(i + 1, len(supports)):
            s2 = supports[j]
            # Don't pair identical level types
            if s1.level_type == s2.level_type:
                continue

            dist_between = abs(s1.price - s2.price) / min(s1.price, s2.price)
            if dist_between <= tolerance_pct:
                pair_key = (min(i, j), max(i, j))
                if pair_key in used_pairs:
                    continue
                used_pairs.add(pair_key)

                avg_price = float(round((s1.price + s2.price) / 2.0, 2))
                combined_strength = max(s1.strength, s2.strength) + 2
                desc1 = s1.description.split("(")[0].strip()
                desc2 = s2.description.split("(")[0].strip()
                confluences.append(
                    SupportLevel(
                        price=avg_price,
                        level_type=SupportType.CONFLUENCE_SUPPORT,
                        strength=combined_strength,
                        description=f"🔥 Confluence: {desc1} + {desc2}",
                    )
                )

    return confluences


def detect_swing_resistances(
    df: pd.DataFrame,
    window: int = 5,
    cluster_pct: float = 0.018,
    min_rejection_pct: float = 0.03,
    min_touch_separation: int = 5,
) -> list[SupportLevel]:
    """Detect fractal swing highs with rejection drop and cluster into Major Zones."""
    if len(df) < window * 2 + 1:
        return []

    highs = df["high"].values
    lows = df["low"].values
    n = len(highs)

    # Store tuples of (bar_index, high_price)
    swing_points: list[tuple[int, float]] = []

    for i in range(window, n - window):
        current_high = float(highs[i])
        # 1. Fractal check: local maximum in [-window, +window]
        if current_high == max(highs[i - window : i + window + 1]):
            # 2. Rejection Displacement check: ensure price dropped away from this high
            subsequent_lows = lows[i + 1 : min(n, i + window * 3 + 1)]
            if len(subsequent_lows) > 0:
                min_subsequent = float(min(subsequent_lows))
                drop_pct = (current_high - min_subsequent) / current_high
                if drop_pct >= min_rejection_pct:
                    swing_points.append((i, current_high))
            else:
                swing_points.append((i, current_high))

    if not swing_points:
        return []

    swing_points.sort(key=lambda x: x[1])
    clusters: list[list[tuple[int, float]]] = []

    for idx, pt_price in swing_points:
        matched = False
        for cl in clusters:
            avg_price = sum(p for _, p in cl) / len(cl)
            if abs(pt_price - avg_price) / avg_price <= cluster_pct:
                too_close = any(abs(idx - ex_idx) < min_touch_separation for ex_idx, _ in cl)
                if not too_close:
                    cl.append((idx, pt_price))
                    matched = True
                    break
                else:
                    max_existing_idx = max(range(len(cl)), key=lambda k: cl[k][1])
                    if pt_price > cl[max_existing_idx][1]:
                        cl[max_existing_idx] = (idx, pt_price)
                    matched = True
                    break
        if not matched:
            clusters.append([(idx, pt_price)])

    resistances: list[SupportLevel] = []
    for cl in clusters:
        prices = [p for _, p in cl]
        avg_p = float(round(sum(prices) / len(prices), 2))
        touch_count = len(cl)
        min_p = float(round(min(prices), 2))
        max_p = float(round(max(prices), 2))

        if touch_count >= 2:
            desc = f"🏛️ Major Resistance Zone ({touch_count} Rejections | ₹{min_p}-₹{max_p})"
            level_type = SupportType.MAJOR_RESISTANCE_ZONE
            strength = 3 + touch_count
        else:
            desc = f"Swing High (1 Rejection | ₹{avg_p})"
            level_type = SupportType.SWING_HIGH
            strength = 2

        resistances.append(
            SupportLevel(
                price=avg_p,
                level_type=level_type,
                strength=strength,
                description=desc,
            )
        )

    return resistances


def detect_resistance_confluences(
    resistances: list[SupportLevel],
    tolerance_pct: float = 0.015,
) -> list[SupportLevel]:
    """Detect confluences where horizontal resistance zones converge with EMAs or Pivots."""
    if len(resistances) < 2:
        return []

    confluences: list[SupportLevel] = []
    used_pairs: set[tuple[int, int]] = set()

    for i in range(len(resistances)):
        s1 = resistances[i]
        for j in range(i + 1, len(resistances)):
            s2 = resistances[j]
            if s1.level_type == s2.level_type:
                continue

            dist_between = abs(s1.price - s2.price) / min(s1.price, s2.price)
            if dist_between <= tolerance_pct:
                pair_key = (min(i, j), max(i, j))
                if pair_key in used_pairs:
                    continue
                used_pairs.add(pair_key)

                avg_price = float(round((s1.price + s2.price) / 2.0, 2))
                combined_strength = max(s1.strength, s2.strength) + 2
                desc1 = s1.description.split("(")[0].strip()
                desc2 = s2.description.split("(")[0].strip()
                confluences.append(
                    SupportLevel(
                        price=avg_price,
                        level_type=SupportType.CONFLUENCE_RESISTANCE,
                        strength=combined_strength,
                        description=f"🔥 Confluence: {desc1} + {desc2}",
                    )
                )

    return confluences


def detect_ma_supports(
    df: pd.DataFrame,
    ema_periods: list[int] | None = None,
    sma_periods: list[int] | None = None,
) -> list[SupportLevel]:
    """Calculate key Exponential Moving Average (EMA) support levels."""
    supports: list[SupportLevel] = []
    if "close" not in df.columns or len(df) < 5:
        return supports

    close = df["close"]
    emas = ema_periods if ema_periods is not None else get_configured_ema_periods()

    for span in emas:
        ema_val = calculate_ema(close, span=span)
        if ema_val is not None:
            type_name = f"EMA_{span}"
            level_type = (
                SupportType(type_name) if type_name in SupportType.__members__ else type_name
            )
            strength = 2 if span <= 50 else (3 if span <= 100 else 4)
            supports.append(
                SupportLevel(
                    price=ema_val,
                    level_type=level_type,
                    strength=strength,
                    description=f"{span} EMA Support",
                )
            )

    if sma_periods:
        for window in sma_periods:
            sma_val = calculate_sma(close, window=window)
            if sma_val is not None:
                type_name = f"SMA_{window}"
                level_type = (
                    SupportType(type_name) if type_name in SupportType.__members__ else type_name
                )
                supports.append(
                    SupportLevel(
                        price=sma_val,
                        level_type=level_type,
                        strength=3 if window <= 100 else 4,
                        description=f"{window} SMA Support",
                    )
                )

    return supports


def detect_pivot_supports(df: pd.DataFrame) -> list[SupportLevel]:
    """Calculate Classic Floor Pivot S1 and S2."""
    supports: list[SupportLevel] = []
    pivots = calculate_floor_pivots(df)
    if not pivots:
        return supports

    s1 = pivots.get("s1", 0.0)
    s2 = pivots.get("s2", 0.0)

    if s1 > 0:
        supports.append(
            SupportLevel(
                price=s1,
                level_type=SupportType.PIVOT_S1,
                strength=2,
                description="Monthly Pivot S1",
            )
        )
    if s2 > 0:
        supports.append(
            SupportLevel(
                price=s2,
                level_type=SupportType.PIVOT_S2,
                strength=3,
                description="Monthly Pivot S2",
            )
        )

    return supports


def detect_pivot_resistances(df: pd.DataFrame) -> list[SupportLevel]:
    """Calculate Classic Floor Pivot R1 and R2."""
    resistances: list[SupportLevel] = []
    pivots = calculate_floor_pivots(df)
    if not pivots:
        return resistances

    r1 = pivots.get("r1", 0.0)
    r2 = pivots.get("r2", 0.0)

    if r1 > 0:
        resistances.append(
            SupportLevel(
                price=r1,
                level_type=SupportType.PIVOT_R1,
                strength=2,
                description="Monthly Pivot R1",
            )
        )
    if r2 > 0:
        resistances.append(
            SupportLevel(
                price=r2,
                level_type=SupportType.PIVOT_R2,
                strength=3,
                description="Monthly Pivot R2",
            )
        )

    return resistances


def detect_52w_low_support(df: pd.DataFrame) -> SupportLevel | None:
    """Calculate 52-week low."""
    if len(df) < 50:
        return None
    min_low = float(round(df["low"].min(), 2))
    return SupportLevel(
        price=min_low,
        level_type=SupportType.LOW_52W,
        strength=4,
        description="52-Week / Lookback Low",
    )


def detect_52w_high_resistance(df: pd.DataFrame) -> SupportLevel | None:
    """Calculate 52-week high."""
    if len(df) < 50:
        return None
    max_high = float(round(df["high"].max(), 2))
    return SupportLevel(
        price=max_high,
        level_type=SupportType.HIGH_52W,
        strength=4,
        description="52-Week / Lookback High",
    )


def analyze_stock_support(
    df: pd.DataFrame,
    symbol: str,
    security_id: str,
    ltp: float | None = None,
    threshold_pct: float = 2.0,
    target_level: str = "ALL",
    ema_periods: list[int] | None = None,
    sma_periods: list[int] | None = None,
    max_wick_pct: Any = "NA",
) -> StockSupportScan:
    """Run full technical support scan on historical OHLCV data."""
    if df.empty or len(df) < 5:
        return StockSupportScan(
            symbol=symbol,
            security_id=security_id,
            ltp=ltp or 0.0,
            nearest_support=None,
            distance_pct=999.0,
            all_supports=[],
            rsi=None,
            candle_signal="Insufficient Data",
            is_at_support=False,
        )

    current_price = ltp if (ltp is not None and ltp > 0) else float(df["close"].iloc[-1])
    volume = (
        int(df["volume"].iloc[-1])
        if ("volume" in df.columns and len(df) > 0 and pd.notna(df["volume"].iloc[-1]))
        else 0
    )

    base_supports: list[SupportLevel] = []
    base_supports.extend(detect_swing_supports(df))
    base_supports.extend(detect_ma_supports(df, ema_periods=ema_periods, sma_periods=sma_periods))
    base_supports.extend(detect_pivot_supports(df))

    low_52w = detect_52w_low_support(df)
    if low_52w:
        base_supports.append(low_52w)

    confluences = detect_support_confluences(base_supports)

    # Confluences are placed first to give them top priority
    supports: list[SupportLevel] = []
    supports.extend(confluences)
    supports.extend(base_supports)

    rsi = calculate_rsi(df["close"], period=14)
    candle_signal = identify_candlestick_patterns(df)

    if not supports:
        return StockSupportScan(
            symbol=symbol,
            security_id=security_id,
            ltp=current_price,
            nearest_support=None,
            distance_pct=999.0,
            all_supports=[],
            rsi=rsi,
            candle_signal=candle_signal,
            is_at_support=False,
            volume=volume,
        )

    target_level_clean = (target_level or "ALL").upper().strip()
    eval_supports = supports
    if target_level_clean != "ALL":
        if target_level_clean in ("MAJOR_ZONES", "MAJOR_ZONE", "MAJOR_SUPPORT_ZONE"):
            eval_supports = [
                s
                for s in supports
                if s.level_type in (SupportType.MAJOR_SUPPORT_ZONE, SupportType.CONFLUENCE_SUPPORT)
            ]
        elif target_level_clean in ("CONFLUENCE", "CONFLUENCES", "CONFLUENCE_SUPPORT"):
            eval_supports = [s for s in supports if s.level_type == SupportType.CONFLUENCE_SUPPORT]
        elif target_level_clean in ("EMA_20", "20_EMA", "20 EMA"):
            eval_supports = [s for s in supports if "20 EMA" in s.description]
        elif target_level_clean in ("EMA_50", "50_EMA", "50 EMA"):
            eval_supports = [s for s in supports if "50 EMA" in s.description]
        elif target_level_clean in ("EMA_100", "100_EMA", "100 EMA"):
            eval_supports = [s for s in supports if "100 EMA" in s.description]
        elif target_level_clean in ("EMA_200", "200_EMA", "200 EMA"):
            eval_supports = [s for s in supports if "200 EMA" in s.description]
        elif target_level_clean in ("SWING_LOW", "SWING_LOWS", "SWING"):
            eval_supports = [
                s
                for s in supports
                if s.level_type in (SupportType.SWING_LOW, SupportType.MAJOR_SUPPORT_ZONE)
            ]
        elif target_level_clean in ("PIVOTS", "PIVOT", "PIVOT_S1", "PIVOT_S2"):
            eval_supports = [
                s for s in supports if s.level_type in (SupportType.PIVOT_S1, SupportType.PIVOT_S2)
            ]
        elif target_level_clean in ("LOW_52W", "52W_LOW"):
            eval_supports = [s for s in supports if s.level_type == SupportType.LOW_52W]

    if not eval_supports:
        eval_supports = supports

    valid_candidates = []
    for s in eval_supports:
        dist_pct = ((current_price - s.price) / s.price) * 100.0
        if -1.0 <= dist_pct <= 15.0:
            valid_candidates.append((abs(dist_pct), dist_pct, s))

    if valid_candidates:
        valid_candidates.sort(key=lambda x: (x[0], -x[2].strength))
        _, best_dist_pct, nearest_support = valid_candidates[0]
    else:
        all_candidates = [
            (
                abs(((current_price - s.price) / s.price) * 100.0),
                ((current_price - s.price) / s.price) * 100.0,
                s,
            )
            for s in eval_supports
        ]
        all_candidates.sort(key=lambda x: x[0])
        _, best_dist_pct, nearest_support = all_candidates[0]

    last_o = float(df["open"].iloc[-1])
    last_h = float(df["high"].iloc[-1])
    last_l = float(df["low"].iloc[-1])
    last_c = float(df["close"].iloc[-1])
    wick_ok, _ = check_candle_wick(
        open_price=last_o,
        high_price=last_h,
        low_price=last_l,
        close_price=last_c,
        is_bullish_setup=True,
        max_wick_pct_param=max_wick_pct,
    )

    is_at_support = (abs(best_dist_pct) <= threshold_pct) and wick_ok

    return StockSupportScan(
        symbol=symbol,
        security_id=security_id,
        ltp=current_price,
        nearest_support=nearest_support,
        distance_pct=round(best_dist_pct, 2),
        all_supports=supports,
        rsi=rsi,
        candle_signal=candle_signal,
        is_at_support=is_at_support,
        volume=volume,
    )


def analyze_stock_resistance(
    df: pd.DataFrame,
    symbol: str,
    security_id: str,
    ltp: float | None = None,
    threshold_pct: float = 2.0,
    target_level: str = "ALL",
    max_wick_pct: Any = "NA",
) -> StockSupportScan:
    """Run full technical resistance scan on historical OHLCV data."""
    if df.empty or len(df) < 5:
        return StockSupportScan(
            symbol=symbol,
            security_id=security_id,
            ltp=ltp or 0.0,
            nearest_support=None,
            distance_pct=999.0,
            all_supports=[],
            rsi=None,
            candle_signal="Insufficient Data",
            is_at_support=False,
        )

    current_price = ltp if (ltp is not None and ltp > 0) else float(df["close"].iloc[-1])
    volume = (
        int(df["volume"].iloc[-1])
        if ("volume" in df.columns and len(df) > 0 and pd.notna(df["volume"].iloc[-1]))
        else 0
    )

    base_resistances: list[SupportLevel] = []
    base_resistances.extend(detect_swing_resistances(df))
    base_resistances.extend(detect_ma_supports(df))
    base_resistances.extend(detect_pivot_resistances(df))

    high_52w = detect_52w_high_resistance(df)
    if high_52w:
        base_resistances.append(high_52w)

    confluences = detect_resistance_confluences(base_resistances)

    resistances: list[SupportLevel] = []
    resistances.extend(confluences)
    resistances.extend(base_resistances)

    rsi = calculate_rsi(df["close"], period=14)
    candle_signal = identify_candlestick_patterns(df)

    if not resistances:
        return StockSupportScan(
            symbol=symbol,
            security_id=security_id,
            ltp=current_price,
            nearest_support=None,
            distance_pct=999.0,
            all_supports=[],
            rsi=rsi,
            candle_signal=candle_signal,
            is_at_support=False,
            volume=volume,
        )

    target_level_clean = (target_level or "ALL").upper().strip()
    eval_resistances = resistances
    if target_level_clean != "ALL":
        if target_level_clean in ("MAJOR_ZONES", "MAJOR_ZONE", "MAJOR_RESISTANCE_ZONE"):
            eval_resistances = [
                r
                for r in resistances
                if r.level_type
                in (SupportType.MAJOR_RESISTANCE_ZONE, SupportType.CONFLUENCE_RESISTANCE)
            ]
        elif target_level_clean in ("CONFLUENCE", "CONFLUENCES", "CONFLUENCE_RESISTANCE"):
            eval_resistances = [
                r for r in resistances if r.level_type == SupportType.CONFLUENCE_RESISTANCE
            ]
        elif target_level_clean in ("EMA_20", "20_EMA", "20 EMA"):
            eval_resistances = [r for r in resistances if "20 EMA" in r.description]
        elif target_level_clean in ("EMA_50", "50_EMA", "50 EMA"):
            eval_resistances = [r for r in resistances if "50 EMA" in r.description]
        elif target_level_clean in ("EMA_100", "100_EMA", "100 EMA"):
            eval_resistances = [r for r in resistances if "100 EMA" in r.description]
        elif target_level_clean in ("EMA_200", "200_EMA", "200 EMA"):
            eval_resistances = [r for r in resistances if "200 EMA" in r.description]
        elif target_level_clean in ("SWING_HIGH", "SWING_HIGHS", "SWING"):
            eval_resistances = [
                r
                for r in resistances
                if r.level_type in (SupportType.SWING_HIGH, SupportType.MAJOR_RESISTANCE_ZONE)
            ]
        elif target_level_clean in ("PIVOTS", "PIVOT", "PIVOT_R1", "PIVOT_R2"):
            eval_resistances = [
                r
                for r in resistances
                if r.level_type in (SupportType.PIVOT_R1, SupportType.PIVOT_R2)
            ]
        elif target_level_clean in ("HIGH_52W", "52W_HIGH"):
            eval_resistances = [r for r in resistances if r.level_type == SupportType.HIGH_52W]

    if not eval_resistances:
        eval_resistances = resistances

    valid_candidates = []
    for r in eval_resistances:
        dist_pct = ((r.price - current_price) / current_price) * 100.0
        if -1.0 <= dist_pct <= 15.0:
            valid_candidates.append((abs(dist_pct), dist_pct, r))

    if valid_candidates:
        valid_candidates.sort(key=lambda x: (x[0], -x[2].strength))
        _, best_dist_pct, nearest_res = valid_candidates[0]
    else:
        all_candidates = [
            (
                abs(((r.price - current_price) / current_price) * 100.0),
                ((r.price - current_price) / current_price) * 100.0,
                r,
            )
            for r in eval_resistances
        ]
        all_candidates.sort(key=lambda x: x[0])
        _, best_dist_pct, nearest_res = all_candidates[0]

    last_o = float(df["open"].iloc[-1])
    last_h = float(df["high"].iloc[-1])
    last_l = float(df["low"].iloc[-1])
    last_c = float(df["close"].iloc[-1])
    wick_ok, _ = check_candle_wick(
        open_price=last_o,
        high_price=last_h,
        low_price=last_l,
        close_price=last_c,
        is_bullish_setup=False,
        max_wick_pct_param=max_wick_pct,
    )

    is_at_res = (abs(best_dist_pct) <= threshold_pct) and wick_ok

    return StockSupportScan(
        symbol=symbol,
        security_id=security_id,
        ltp=current_price,
        nearest_support=nearest_res,
        distance_pct=round(best_dist_pct, 2),
        all_supports=resistances,
        rsi=rsi,
        candle_signal=candle_signal,
        is_at_support=is_at_res,
        volume=volume,
    )
