"""Unit tests for support level scanner and technical indicators."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from scanner_dhan.indicators import calculate_rsi
from scanner_dhan.scanner.nifty50_support_resistance import (
    SupportType,
    analyze_stock_support,
    detect_ma_supports,
    detect_pivot_supports,
    detect_swing_supports,
)
from scanner_dhan.universe.nifty50 import NIFTY_50_SYMBOLS, resolve_nifty50_securities


def _generate_synthetic_df(n_bars: int = 150, base_price: float = 1000.0) -> pd.DataFrame:
    """Generate reproducible synthetic OHLCV dataframe."""
    np.random.seed(42)
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(n_bars)]

    # Create random walk with periodic bounces off base_price
    prices = [base_price + 50.0]
    for i in range(1, n_bars):
        change = np.random.normal(0.5, 5.0)
        new_price = max(base_price, prices[-1] + change)
        # Every 30 bars, dip to base_price to create swing lows
        if i in (30, 60, 90, 120):
            new_price = base_price
        prices.append(new_price)

    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [p + 2.0 for p in prices],
            "high": [p + 8.0 for p in prices],
            "low": [max(base_price, p - 3.0) for p in prices],
            "close": prices,
            "volume": [10000.0] * n_bars,
        }
    )
    return df


def test_nifty50_resolution() -> None:
    """Verify Nifty 50 resolution contains all 50 symbols."""
    resolved = resolve_nifty50_securities()
    assert len(resolved) >= 50
    for sym in NIFTY_50_SYMBOLS:
        assert sym in resolved
        assert resolved[sym] != ""


def test_calculate_rsi_edge_cases() -> None:
    """Test RSI with short series and constant prices."""
    short_series = pd.Series([100.0, 102.0, 101.0])
    assert calculate_rsi(short_series, period=14) is None

    # Continuously rising series should approach 100
    rising = pd.Series([100.0 + i * 2.0 for i in range(30)])
    rsi = calculate_rsi(rising, period=14)
    assert rsi is not None
    assert rsi == 100.0


def test_detect_swing_supports() -> None:
    """Test fractal swing low detection and clustering into Major Support Zones."""
    df = _generate_synthetic_df(n_bars=150, base_price=1000.0)
    supports = detect_swing_supports(df, window=4, cluster_pct=0.02)

    assert len(supports) > 0
    # There should be a clustered major support zone near 1000
    near_base = [s for s in supports if abs(s.price - 1000.0) <= 20.0]
    assert len(near_base) > 0
    assert near_base[0].level_type == SupportType.MAJOR_SUPPORT_ZONE
    assert near_base[0].strength >= 4
    assert "Major Support Zone" in near_base[0].description


def test_detect_ma_supports() -> None:
    """Test exponential moving average support calculations."""
    df = _generate_synthetic_df(n_bars=220, base_price=1000.0)
    ma_supports = detect_ma_supports(df)

    types = {s.level_type for s in ma_supports}
    assert SupportType.EMA_20 in types
    assert SupportType.EMA_50 in types
    assert SupportType.EMA_100 in types
    assert SupportType.EMA_200 in types


def test_detect_ma_supports_custom_periods() -> None:
    """Test moving average calculation with custom configured periods."""
    df = _generate_synthetic_df(n_bars=220, base_price=1000.0)
    ma_supports = detect_ma_supports(df, ema_periods=[9, 21])

    descriptions = [s.description for s in ma_supports]
    assert "9 EMA Support" in descriptions
    assert "21 EMA Support" in descriptions


def test_detect_pivot_supports() -> None:
    """Test floor pivot S1 and S2 support calculation."""
    df = _generate_synthetic_df(n_bars=50, base_price=1000.0)
    pivots = detect_pivot_supports(df)

    types = {s.level_type for s in pivots}
    assert SupportType.PIVOT_S1 in types
    assert SupportType.PIVOT_S2 in types


def test_analyze_stock_support_at_support() -> None:
    """Test detection when stock LTP is within threshold of support."""
    df = _generate_synthetic_df(n_bars=150, base_price=1000.0)

    # Test price 1008 when support is near 1000 (distance ~0.8% <= 2.0%)
    scan = analyze_stock_support(
        df=df,
        symbol="TESTSTOCK",
        security_id="1234",
        ltp=1008.0,
        threshold_pct=2.0,
    )

    assert scan.symbol == "TESTSTOCK"
    assert scan.nearest_support is not None
    assert scan.is_at_support is True
    assert scan.distance_pct <= 2.0


def test_analyze_stock_support_far_from_support() -> None:
    """Test detection when stock LTP is far above support."""
    df = _generate_synthetic_df(n_bars=150, base_price=1000.0)

    # Test price 1250 when support is near 1000 (distance ~25% > 2.0%)
    scan = analyze_stock_support(
        df=df,
        symbol="TESTSTOCK",
        security_id="1234",
        ltp=1250.0,
        threshold_pct=2.0,
    )

    assert scan.is_at_support is False
    assert scan.distance_pct > 2.0


def test_fno_universe_resolution() -> None:
    """Verify F&O resolution contains major F&O stocks."""
    from scanner_dhan.universe import FNO_SYMBOLS, resolve_fno_securities

    assert len(FNO_SYMBOLS) >= 150
    resolved = resolve_fno_securities()
    assert len(resolved) >= 150
    for sym in ("RELIANCE", "INFY", "TATAMOTORS", "SBIN", "HDFCBANK"):
        assert sym in resolved
        assert resolved[sym] != ""


def test_get_active_universe_config() -> None:
    """Test get_active_universe with NIFTY_50 and ALL_F_AND_O."""
    from scanner_dhan.universe import get_active_universe

    name, symbols, sec_map = get_active_universe("NIFTY_50")
    assert name == "NIFTY_50"
    assert len(symbols) == 50
    assert "INFY" in symbols

    fno_name, fno_symbols, fno_sec_map = get_active_universe("ALL_F_AND_O")
    assert fno_name == "ALL_F_AND_O"
    assert len(fno_symbols) >= 150
    assert "RELIANCE" in fno_symbols


def test_volume_extraction_in_scan() -> None:
    """Test that volume is extracted from daily bars and populated in scan result."""
    df = _generate_synthetic_df(n_bars=150, base_price=1000.0)
    df["volume"] = 1250000.0

    scan = analyze_stock_support(
        df=df,
        symbol="INFY",
        security_id="1594",
        ltp=1005.0,
    )

    assert scan.volume == 1250000
    d = scan.to_dict()
    assert d["volume"] == 1250000


def test_detect_support_confluences() -> None:
    """Test confluence detection between Major Support Zone and 200 EMA."""
    from scanner_dhan.scanner.nifty50_support_resistance.level_detector import (
        detect_support_confluences,
    )
    from scanner_dhan.scanner.nifty50_support_resistance.models import SupportLevel

    supports = [
        SupportLevel(
            price=1000.0,
            level_type=SupportType.MAJOR_SUPPORT_ZONE,
            strength=5,
            description="🏛️ Major Support Zone (3 Bounces | ₹995-₹1005)",
        ),
        SupportLevel(
            price=1008.0,
            level_type=SupportType.EMA_200,
            strength=4,
            description="200 EMA Major Trend Support",
        ),
    ]

    confluences = detect_support_confluences(supports, tolerance_pct=0.015)
    assert len(confluences) == 1
    assert confluences[0].level_type == SupportType.CONFLUENCE_SUPPORT
    assert confluences[0].price == 1004.0
    assert confluences[0].strength >= 6
    assert "Confluence" in confluences[0].description


def test_bounce_displacement_filters_fake_swings() -> None:
    """Test that minor flat consolidation without bounce displacement is ignored."""
    # Create flat series without >=3% bounce
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(50)]
    df_flat = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [100.0] * 50,
            "high": [100.5] * 50,
            "low": [99.5] * 50,
            "close": [100.0] * 50,
            "volume": [5000.0] * 50,
        }
    )
    # Dip at bar 25 but never rallies by 3%
    df_flat.loc[25, "low"] = 98.0
    df_flat.loc[25, "close"] = 98.5

    supports = detect_swing_supports(df_flat, window=5, min_bounce_pct=0.03)
    # The dip from 98.0 with max subsequent of 100.5 is only 2.5% move (< 3%), so filtered out
    assert len(supports) == 0


def test_analyze_stock_support_major_zones_filter() -> None:
    """Test analyze_stock_support with target_level='MAJOR_ZONES'."""
    df = _generate_synthetic_df(n_bars=150, base_price=1000.0)

    scan = analyze_stock_support(
        df=df,
        symbol="RELIANCE",
        security_id="2885",
        ltp=1005.0,
        target_level="MAJOR_ZONES",
    )

    assert scan.nearest_support is not None
    assert scan.nearest_support.level_type in (
        SupportType.MAJOR_SUPPORT_ZONE,
        SupportType.CONFLUENCE_SUPPORT,
    )


def test_detect_swing_resistances_major_zones() -> None:
    """Test detect_swing_resistances identifies Major Resistance Zones with 2+ rejections."""
    from scanner_dhan.scanner.nifty50_support_resistance.level_detector import (
        detect_swing_resistances,
    )

    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(100)]
    # Peaks at 1100 at bar 20 and bar 60, with drops to 1000 in between
    prices = [1000.0] * 100
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [10000.0] * 100,
        }
    )
    # Peak 1 at bar 20: 1100, drops back to 1000 at bar 35
    df.loc[20, "high"] = 1100.0
    df.loc[20, "close"] = 1090.0

    # Peak 2 at bar 60: 1105, drops back to 1000 at bar 75
    df.loc[60, "high"] = 1105.0
    df.loc[60, "close"] = 1095.0

    resistances = detect_swing_resistances(df, window=5, cluster_pct=0.02, min_rejection_pct=0.03)
    assert len(resistances) >= 1
    major_res = [r for r in resistances if r.level_type == SupportType.MAJOR_RESISTANCE_ZONE]
    assert len(major_res) >= 1
    assert major_res[0].strength >= 4
    assert "Major Resistance Zone" in major_res[0].description


def test_detect_resistance_confluences() -> None:
    """Test resistance confluence between Major Resistance Zone and 200 EMA."""
    from scanner_dhan.scanner.nifty50_support_resistance.level_detector import (
        detect_resistance_confluences,
    )
    from scanner_dhan.scanner.nifty50_support_resistance.models import SupportLevel

    resistances = [
        SupportLevel(
            price=1100.0,
            level_type=SupportType.MAJOR_RESISTANCE_ZONE,
            strength=5,
            description="🏛️ Major Resistance Zone (3 Rejections | ₹1095-₹1105)",
        ),
        SupportLevel(
            price=1108.0,
            level_type=SupportType.EMA_200,
            strength=4,
            description="200 EMA Major Trend Resistance",
        ),
    ]

    confluences = detect_resistance_confluences(resistances, tolerance_pct=0.015)
    assert len(confluences) == 1
    assert confluences[0].level_type == SupportType.CONFLUENCE_RESISTANCE
    assert confluences[0].price == 1104.0
    assert confluences[0].strength >= 6
    assert "Confluence" in confluences[0].description


def test_analyze_stock_resistance_major_zones() -> None:
    """Test analyze_stock_resistance with target_level='MAJOR_ZONES'."""
    from scanner_dhan.scanner.nifty50_support_resistance.level_detector import (
        analyze_stock_resistance,
    )

    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(100)]
    prices = [1000.0] * 100
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [10000.0] * 100,
        }
    )
    df.loc[20, "high"] = 1100.0
    df.loc[60, "high"] = 1102.0

    scan = analyze_stock_resistance(
        df=df,
        symbol="TCS",
        security_id="11536",
        ltp=1090.0,
        target_level="MAJOR_ZONES",
    )

    assert scan.nearest_support is not None
    assert scan.nearest_support.level_type in (
        SupportType.MAJOR_RESISTANCE_ZONE,
        SupportType.CONFLUENCE_RESISTANCE,
    )
