"""Pattern recognition engine for Head & Shoulders and Inverse Head & Shoulders."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import List, Optional, Tuple, Union

import numpy as np
import pandas as pd

try:
    from scipy.signal import argrelextrema
except ImportError:
    def argrelextrema(data: np.ndarray, comparator: Any, order: int = 1) -> Tuple[np.ndarray]:  # type: ignore
        n = len(data)
        results = []
        for i in range(order, n - order):
            window = data[i - order : i + order + 1]
            val = data[i]
            if comparator(val, window).all():
                if comparator is np.greater_equal:
                    if val > np.min(window):
                        results.append(i)
                elif comparator is np.less_equal:
                    if val < np.max(window):
                        results.append(i)
        return (np.array(results, dtype=int),)

from scanner_dhan.indicators.rsi import calculate_rsi
from scanner_dhan.scanner.head_and_shoulders.models import (
    ConfirmationStatus,
    ExtremaPoint,
    HeadAndShouldersPattern,
    HeadAndShouldersScanResult,
    PatternType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "find_extrema",
    "detect_head_and_shoulders",
    "detect_inverse_head_and_shoulders",
    "scan_stock_for_head_and_shoulders",
]


def _get_column(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Retrieve column case-insensitively from DataFrame."""
    for col in df.columns:
        if str(col).lower() == col_name.lower():
            return df[col]
    raise KeyError(f"Column '{col_name}' not found in DataFrame columns: {list(df.columns)}")


def find_extrema(
    data: Union[pd.DataFrame, pd.Series],
    order: int = 10,
) -> Union[List[ExtremaPoint], Tuple[np.ndarray, np.ndarray]]:
    """Compute local peaks and troughs using rolling relative extrema.
    
    If data is a pd.Series, returns (peak_indices, trough_indices) for direct series math.
    If data is a pd.DataFrame, computes on High/Low columns and returns a chronologically
    sorted list of ExtremaPoint instances.
    """
    if isinstance(data, pd.Series):
        values = data.values
        if len(values) < (2 * order + 1):
            return np.array([], dtype=int), np.array([], dtype=int)
        peak_idx = argrelextrema(values, np.greater_equal, order=order)[0]
        trough_idx = argrelextrema(values, np.less_equal, order=order)[0]
        return peak_idx, trough_idx

    df = data
    if len(df) < (2 * order + 1):
        return []

    high_series = _get_column(df, "high")
    low_series = _get_column(df, "low")

    highs = high_series.values
    lows = low_series.values

    # Find peak indices (local maxima of High)
    peak_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    # Find trough indices (local minima of Low)
    trough_idx = argrelextrema(lows, np.less_equal, order=order)[0]

    extrema: List[ExtremaPoint] = []

    for idx in peak_idx:
        ts = df.index[idx] if not isinstance(df.index, pd.RangeIndex) else (
            _get_column(df, "timestamp").iloc[idx] if "timestamp" in [str(c).lower() for c in df.columns] else datetime.now()
        )
        extrema.append(
            ExtremaPoint(
                index=int(idx),
                timestamp=ts if isinstance(ts, datetime) else pd.to_datetime(ts).to_pydatetime(),
                price=float(highs[idx]),
                point_type="PEAK",
            )
        )

    for idx in trough_idx:
        ts = df.index[idx] if not isinstance(df.index, pd.RangeIndex) else (
            _get_column(df, "timestamp").iloc[idx] if "timestamp" in [str(c).lower() for c in df.columns] else datetime.now()
        )
        extrema.append(
            ExtremaPoint(
                index=int(idx),
                timestamp=ts if isinstance(ts, datetime) else pd.to_datetime(ts).to_pydatetime(),
                price=float(lows[idx]),
                point_type="TROUGH",
            )
        )

    # Sort strictly by chronological bar index
    extrema.sort(key=lambda p: p.index)

    # Deduplicate consecutive same-type extrema (keep highest peak / lowest trough)
    clean_extrema: List[ExtremaPoint] = []
    for pt in extrema:
        if not clean_extrema:
            clean_extrema.append(pt)
            continue

        prev = clean_extrema[-1]
        if prev.point_type == pt.point_type:
            if pt.point_type == "PEAK" and pt.price > prev.price:
                clean_extrema[-1] = pt
            elif pt.point_type == "TROUGH" and pt.price < prev.price:
                clean_extrema[-1] = pt
        else:
            clean_extrema.append(pt)

    return clean_extrema


def detect_head_and_shoulders(
    df: pd.DataFrame,
    symbol: str = "STOCK",
    timeframe: str = "Daily",
    extrema: Optional[List[ExtremaPoint]] = None,
    order: int = 10,
    symmetry_tolerance: float = 0.03,
    shoulder_tolerance: Optional[float] = None,
    max_pattern_bars: int = 120,
    max_confirmation_bars: int = 30,
) -> List[HeadAndShouldersPattern]:
    """Detect regular (bearish breakdown) Head and Shoulders patterns."""
    tol = shoulder_tolerance if shoulder_tolerance is not None else symmetry_tolerance

    if extrema is None:
        extrema = find_extrema(df, order=order)

    patterns: List[HeadAndShouldersPattern] = []
    n_bars = len(df)
    close_series = _get_column(df, "close")
    closes = close_series.values

    for i in range(len(extrema) - 4):
        p1, p2, p3, p4, p5 = extrema[i : i + 5]

        # 1. Point types: PEAK -> TROUGH -> PEAK -> TROUGH -> PEAK
        if not (
            p1.point_type == "PEAK"
            and p2.point_type == "TROUGH"
            and p3.point_type == "PEAK"
            and p4.point_type == "TROUGH"
            and p5.point_type == "PEAK"
        ):
            continue

        a, b, c, d, e = p1.price, p2.price, p3.price, p4.price, p5.price

        # 2. Geometry: Head higher than shoulders, shoulders higher than neckline
        if not (c > a and c > e and a > b and a > d and e > b and e > d):
            continue

        # 3. Shoulder Symmetry (|A - E| / mean(A, E) <= tolerance)
        sh_mean = (a + e) / 2.0
        sh_sym_pct = abs(a - e) / sh_mean * 100.0
        if (abs(a - e) / sh_mean) > tol:
            continue

        # 4. Neckline Symmetry (|B - D| / mean(B, D) <= tolerance * 2.0)
        neck_mean = (b + d) / 2.0
        neck_sym_pct = abs(b - d) / neck_mean * 100.0
        if (abs(b - d) / neck_mean) > (tol * 2.0):
            continue

        # 5. Pattern span: Bars between Left Shoulder and Right Shoulder
        bar_span = p5.index - p1.index
        if bar_span > max_pattern_bars or bar_span < 5:
            continue

        # 6. Evaluate Confirmation / Status in subsequent bars after right shoulder (P5)
        status = ConfirmationStatus.FORMING
        conf_date = None
        conf_idx = None
        conf_price = None
        bars_since = n_bars - 1 - p5.index

        neckline_price = d
        head_height = c - d
        latest_close = float(closes[-1])

        # Search for breakdown below neckline
        for bar_i in range(p5.index + 1, min(n_bars, p5.index + 1 + max_confirmation_bars)):
            close_price = float(closes[bar_i])

            # Invalidation: If price rallies above Head price, pattern failed
            if close_price > c:
                status = ConfirmationStatus.INVALIDATED
                break

            # Confirmation: Candle closes below neckline (Point D)
            if close_price < neckline_price:
                status = ConfirmationStatus.CONFIRMED
                conf_idx = bar_i
                ts = df.index[bar_i] if not isinstance(df.index, pd.RangeIndex) else (
                    _get_column(df, "timestamp").iloc[bar_i] if "timestamp" in [str(col).lower() for col in df.columns] else datetime.now()
                )
                conf_date = ts if isinstance(ts, datetime) else pd.to_datetime(ts).to_pydatetime()
                conf_price = close_price
                break

        # If confirmation took more than max_confirmation_bars without breakdown, skip old completed patterns
        if status == ConfirmationStatus.FORMING and bars_since > max_confirmation_bars:
            continue

        # Trade Levels
        entry = conf_price if conf_price else neckline_price
        sl = round(e * 1.005, 2)  # 0.5% above Right Shoulder
        t1 = round(neckline_price - head_height, 2)
        t2 = round(neckline_price - (2.0 * head_height), 2)
        risk = abs(sl - entry)
        reward = abs(entry - t1)
        rr = round(reward / risk, 2) if risk > 0 else 0.0

        patterns.append(
            HeadAndShouldersPattern(
                pattern_type=PatternType.REGULAR_HS,
                symbol=symbol,
                timeframe=timeframe,
                left_shoulder=p1,
                neckline_1=p2,
                head=p3,
                neckline_2=p4,
                right_shoulder=p5,
                neckline_price=neckline_price,
                head_height=head_height,
                shoulder_symmetry_pct=sh_sym_pct,
                neckline_symmetry_pct=neck_sym_pct,
                pattern_bar_span=bar_span,
                status=status,
                confirmation_date=conf_date,
                confirmation_bar_index=conf_idx,
                confirmation_price=conf_price,
                bars_since_formation=bars_since,
                entry_price=entry,
                stop_loss=sl,
                target_1=t1,
                target_2=t2,
                risk_reward_ratio=rr,
                current_price=latest_close,
                breakout_date=conf_date.isoformat() if conf_date else None,
            )
        )

    return patterns


def detect_inverse_head_and_shoulders(
    df: pd.DataFrame,
    symbol: str = "STOCK",
    timeframe: str = "Daily",
    extrema: Optional[List[ExtremaPoint]] = None,
    order: int = 10,
    symmetry_tolerance: float = 0.03,
    shoulder_tolerance: Optional[float] = None,
    max_pattern_bars: int = 120,
    max_confirmation_bars: int = 30,
) -> List[HeadAndShouldersPattern]:
    """Detect inverse (bullish breakout) Head and Shoulders patterns."""
    tol = shoulder_tolerance if shoulder_tolerance is not None else symmetry_tolerance

    if extrema is None:
        extrema = find_extrema(df, order=order)

    patterns: List[HeadAndShouldersPattern] = []
    n_bars = len(df)
    close_series = _get_column(df, "close")
    closes = close_series.values

    for i in range(len(extrema) - 4):
        p1, p2, p3, p4, p5 = extrema[i : i + 5]

        # 1. Point types: TROUGH -> PEAK -> TROUGH -> PEAK -> TROUGH
        if not (
            p1.point_type == "TROUGH"
            and p2.point_type == "PEAK"
            and p3.point_type == "TROUGH"
            and p4.point_type == "PEAK"
            and p5.point_type == "TROUGH"
        ):
            continue

        a, b, c, d, e = p1.price, p2.price, p3.price, p4.price, p5.price

        # 2. Geometry: Head lower than shoulders, shoulders lower than neckline
        if not (c < a and c < e and a < b and a < d and e < b and e < d):
            continue

        # 3. Shoulder Symmetry (|A - E| / mean(A, E) <= tolerance)
        sh_mean = (a + e) / 2.0
        sh_sym_pct = abs(a - e) / sh_mean * 100.0
        if (abs(a - e) / sh_mean) > tol:
            continue

        # 4. Neckline Symmetry (|B - D| / mean(B, D) <= tolerance * 2.0)
        neck_mean = (b + d) / 2.0
        neck_sym_pct = abs(b - d) / neck_mean * 100.0
        if (abs(b - d) / neck_mean) > (tol * 2.0):
            continue

        # 5. Pattern span: Bars between Left Shoulder and Right Shoulder
        bar_span = p5.index - p1.index
        if bar_span > max_pattern_bars or bar_span < 5:
            continue

        # 6. Evaluate Confirmation / Status in subsequent bars after right shoulder (P5)
        status = ConfirmationStatus.FORMING
        conf_date = None
        conf_idx = None
        conf_price = None
        bars_since = n_bars - 1 - p5.index

        neckline_price = d
        head_height = d - c
        latest_close = float(closes[-1])

        # Search for breakout above neckline
        for bar_i in range(p5.index + 1, min(n_bars, p5.index + 1 + max_confirmation_bars)):
            close_price = float(closes[bar_i])

            # Invalidation: If price breaches below Head low, pattern failed
            if close_price < c:
                status = ConfirmationStatus.INVALIDATED
                break

            # Confirmation: Candle closes above neckline (Point D)
            if close_price > neckline_price:
                status = ConfirmationStatus.CONFIRMED
                conf_idx = bar_i
                ts = df.index[bar_i] if not isinstance(df.index, pd.RangeIndex) else (
                    _get_column(df, "timestamp").iloc[bar_i] if "timestamp" in [str(col).lower() for col in df.columns] else datetime.now()
                )
                conf_date = ts if isinstance(ts, datetime) else pd.to_datetime(ts).to_pydatetime()
                conf_price = close_price
                break

        # If confirmation took more than max_confirmation_bars without breakout, skip old patterns
        if status == ConfirmationStatus.FORMING and bars_since > max_confirmation_bars:
            continue

        # Trade Levels
        entry = conf_price if conf_price else neckline_price
        sl = round(e * 0.995, 2)  # 0.5% below Right Shoulder Low
        t1 = round(neckline_price + head_height, 2)
        t2 = round(neckline_price + (2.0 * head_height), 2)
        risk = abs(entry - sl)
        reward = abs(t1 - entry)
        rr = round(reward / risk, 2) if risk > 0 else 0.0

        patterns.append(
            HeadAndShouldersPattern(
                pattern_type=PatternType.INVERSE_HS,
                symbol=symbol,
                timeframe=timeframe,
                left_shoulder=p1,
                neckline_1=p2,
                head=p3,
                neckline_2=p4,
                right_shoulder=p5,
                neckline_price=neckline_price,
                head_height=head_height,
                shoulder_symmetry_pct=sh_sym_pct,
                neckline_symmetry_pct=neck_sym_pct,
                pattern_bar_span=bar_span,
                status=status,
                confirmation_date=conf_date,
                confirmation_bar_index=conf_idx,
                confirmation_price=conf_price,
                bars_since_formation=bars_since,
                entry_price=entry,
                stop_loss=sl,
                target_1=t1,
                target_2=t2,
                risk_reward_ratio=rr,
                current_price=latest_close,
                breakout_date=conf_date.isoformat() if conf_date else None,
            )
        )

    return patterns


def scan_stock_for_head_and_shoulders(
    df: pd.DataFrame,
    symbol: str,
    security_id: str,
    timeframe: str = "Daily",
    pattern_filter: str = "ALL",  # "ALL", "REGULAR_ONLY", "INVERSE_ONLY", "REGULAR_HS", "INVERSE_HS"
    pattern_type: Optional[str] = None,
    order: int = 10,
    symmetry_tolerance: float = 0.03,
    shoulder_tolerance: Optional[float] = None,
    max_pattern_bars: int = 120,
    max_confirmation_bars: int = 30,
) -> HeadAndShouldersScanResult:
    """Analyze a single stock dataframe and return a HeadAndShouldersScanResult."""
    tol = shoulder_tolerance if shoulder_tolerance is not None else symmetry_tolerance
    effective_pattern_filter = pattern_type if pattern_type is not None else pattern_filter
    now = datetime.now()

    if df.empty or len(df) < 25:
        return HeadAndShouldersScanResult(
            symbol=symbol,
            security_id=security_id,
            ltp=0.0,
            timeframe=timeframe,
            scanned_at=now,
            has_pattern=False,
            error="Insufficient data points (< 25 bars)",
        )

    close_series = _get_column(df, "close")
    ltp = float(close_series.iloc[-1])

    # Compute RSI 14
    latest_rsi = None
    try:
        rsi_series = calculate_rsi(close_series, period=14)
        latest_rsi = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else None
    except Exception:
        pass

    # Calculate extrema
    extrema = find_extrema(df, order=order)

    all_patterns: List[HeadAndShouldersPattern] = []

    if effective_pattern_filter in ("ALL", "REGULAR_ONLY", "REGULAR_HS"):
        regular_patterns = detect_head_and_shoulders(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            extrema=extrema,
            order=order,
            symmetry_tolerance=tol,
            max_pattern_bars=max_pattern_bars,
            max_confirmation_bars=max_confirmation_bars,
        )
        all_patterns.extend(regular_patterns)

    if effective_pattern_filter in ("ALL", "INVERSE_ONLY", "INVERSE_HS"):
        inverse_patterns = detect_inverse_head_and_shoulders(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            extrema=extrema,
            order=order,
            symmetry_tolerance=tol,
            max_pattern_bars=max_pattern_bars,
            max_confirmation_bars=max_confirmation_bars,
        )
        all_patterns.extend(inverse_patterns)

    vol = 0.0
    try:
        vol_series = _get_column(df, "volume")
        vol = float(vol_series.iloc[-1])
    except Exception:
        pass

    if not all_patterns:
        return HeadAndShouldersScanResult(
            symbol=symbol,
            security_id=security_id,
            ltp=ltp,
            timeframe=timeframe,
            scanned_at=now,
            has_pattern=False,
            rsi=latest_rsi,
            volume=vol,
        )

    # Prioritize CONFIRMED patterns first, then most recently formed
    all_patterns.sort(
        key=lambda p: (
            1 if p.status == ConfirmationStatus.CONFIRMED else 0,
            p.right_shoulder.index,
        ),
        reverse=True,
    )
    selected_pattern = all_patterns[0]

    return HeadAndShouldersScanResult(
        symbol=symbol,
        security_id=security_id,
        ltp=ltp,
        timeframe=timeframe,
        scanned_at=now,
        has_pattern=True,
        pattern=selected_pattern,
        rsi=latest_rsi,
        volume=vol,
    )
