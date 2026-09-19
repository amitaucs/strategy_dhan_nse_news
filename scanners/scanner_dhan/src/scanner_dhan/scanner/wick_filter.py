"""Reusable Candle Wick Filtering Utilities for Trading Scanners."""

from __future__ import annotations

from typing import Any
from scanner_dhan.scanner.base import ScannerParameter

__all__ = ["get_wick_parameter", "check_candle_wick", "calculate_wick_percentages"]


def get_wick_parameter(default: str = "NA") -> ScannerParameter:
    """Return a standardized ScannerParameter for adjustable Opposing Wick filtering."""
    return ScannerParameter(
        name="max_wick_pct",
        label="Max Rejection Wick Filter",
        param_type="select",
        default=default,
        description=(
            "Filter out candidates with long opposing wicks (e.g. upper rejection wick on "
            "bullish setups or lower rejection wick on bearish setups). Select N/A to disable."
        ),
        options=[
            {"value": "NA", "label": "N/A (No Wick Filter)"},
            {"value": "20", "label": "Max 20% Opposing Wick (Strict ⚡)"},
            {"value": "30", "label": "Max 30% Opposing Wick (Standard ⭐)"},
            {"value": "40", "label": "Max 40% Opposing Wick (Moderate)"},
            {"value": "50", "label": "Max 50% Opposing Wick (Lenient)"},
        ],
    )


def calculate_wick_percentages(
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
) -> tuple[float, float, float]:
    """Calculate upper wick %, lower wick %, and body % of total candle range.

    Returns:
        (upper_wick_pct, lower_wick_pct, body_pct)
    """
    candle_range = high_price - low_price
    if candle_range <= 1e-6:
        return 0.0, 0.0, 100.0

    body = abs(close_price - open_price)
    upper_wick = high_price - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low_price

    upper_wick_pct = (upper_wick / candle_range) * 100.0
    lower_wick_pct = (lower_wick / candle_range) * 100.0
    body_pct = (body / candle_range) * 100.0

    return round(upper_wick_pct, 2), round(lower_wick_pct, 2), round(body_pct, 2)


def check_candle_wick(
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    is_bullish_setup: bool = True,
    max_wick_pct_param: Any = "NA",
) -> tuple[bool, float]:
    """Check if a candle satisfies the maximum opposing rejection wick constraint.

    Args:
        open_price: Candle Open
        high_price: Candle High
        low_price: Candle Low
        close_price: Candle Close
        is_bullish_setup: True if setup is bullish (checks upper rejection wick),
                          False if setup is bearish (checks lower rejection wick).
        max_wick_pct_param: User-selected threshold ('NA', '20', '30', '40', '50', or numeric).

    Returns:
        (is_passed, opposing_wick_pct)
    """
    if max_wick_pct_param is None or str(max_wick_pct_param).strip().upper() in ("NA", "NONE", "0", ""):
        return True, 0.0

    try:
        max_pct = float(max_wick_pct_param)
        if max_pct <= 0 or max_pct >= 100:
            return True, 0.0
    except (ValueError, TypeError):
        return True, 0.0

    upper_pct, lower_pct, _ = calculate_wick_percentages(
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
    )

    opposing_pct = upper_pct if is_bullish_setup else lower_pct
    is_passed = opposing_pct <= max_pct

    return is_passed, opposing_pct

