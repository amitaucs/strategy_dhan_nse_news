"""Unit tests for Institutional Order Block Scanner (Smart Money Concepts)."""

from __future__ import annotations

import pandas as pd

from scanner_dhan.indicators.atr import calculate_atr, calculate_volume_sma
from scanner_dhan.scanner.order_block.detector import (
    analyze_stock_order_block,
    detect_order_blocks,
)
from scanner_dhan.scanner.order_block.models import (
    OrderBlock,
    OrderBlockScanResult,
    OrderBlockType,
)
from scanner_dhan.scanner.order_block.scanner import OrderBlockScanner


def _create_sample_ohlcv(bars: int = 50) -> pd.DataFrame:
    """Create synthetic OHLCV DataFrame."""
    bars = max(bars, 50)
    data = {
        "timestamp": pd.date_range("2026-01-01", periods=bars, freq="D"),
        "open": [100.0] * bars,
        "high": [102.0] * bars,
        "low": [98.0] * bars,
        "close": [100.0] * bars,
        "volume": [10000.0] * bars,
    }
    df = pd.DataFrame(data)

    # Insert a clear Bullish Displacement at bar 35
    # Bar 34 is the down origin candle (Order Block base)
    df.loc[34, "open"] = 100.0
    df.loc[34, "high"] = 101.0
    df.loc[34, "low"] = 97.0
    df.loc[34, "close"] = 98.0  # Red candle

    # Bar 35: Strong Green Expansion + Volume Surge
    df.loc[35, "open"] = 98.0
    df.loc[35, "high"] = 112.0
    df.loc[35, "low"] = 98.0
    df.loc[35, "close"] = 110.0  # +12 body expansion (ATR is ~4)
    df.loc[35, "volume"] = 35000.0  # 3.5x volume

    # Bar 49 (Latest): Pullback to test the demand zone around 99.0
    df.loc[49, "open"] = 101.0
    df.loc[49, "high"] = 102.0
    df.loc[49, "low"] = 99.0
    df.loc[49, "close"] = 99.5
    return df


def test_calculate_atr() -> None:
    """Verify ATR calculation."""
    df = _create_sample_ohlcv(50)
    atr = calculate_atr(df, period=14)
    assert len(atr) == 50
    assert atr.iloc[-1] > 0.0


def test_calculate_volume_sma() -> None:
    """Verify Volume SMA calculation."""
    df = _create_sample_ohlcv(50)
    vol_sma = calculate_volume_sma(df["volume"], window=20)
    assert len(vol_sma) == 50
    assert vol_sma.iloc[-1] > 0.0


def test_detect_order_blocks_bullish() -> None:
    """Verify detection of Bullish Demand Order Block."""
    df = _create_sample_ohlcv(50)
    obs = detect_order_blocks(df, impulse_multiplier=1.5, volume_multiplier=1.5)
    assert len(obs) >= 1
    bullish_obs = [ob for ob in obs if ob.block_type == OrderBlockType.BULLISH_DEMAND]
    assert len(bullish_obs) >= 1

    first_ob = bullish_obs[0]
    assert first_ob.price_top == 101.0
    assert first_ob.price_bottom == 97.0
    assert first_ob.impulse_body_expansion >= 1.5
    assert first_ob.volume_expansion >= 1.5


def test_analyze_stock_order_block() -> None:
    """Verify stock analysis identifies Order Block retest."""
    df = _create_sample_ohlcv(50)
    res = analyze_stock_order_block(
        df=df,
        symbol="TESTSTOCK",
        security_id="9999",
        ltp=99.5,
        threshold_pct=2.0,
        impulse_multiplier=1.5,
        volume_multiplier=1.5,
    )
    assert res.symbol == "TESTSTOCK"
    assert res.nearest_order_block is not None
    assert res.is_at_order_block is True
    assert res.distance_pct == 0.0  # Inside [97.0, 101.0] zone


def test_order_block_scanner_registration() -> None:
    """Verify OrderBlockScanner metadata and parameters."""
    scanner = OrderBlockScanner()
    assert scanner.id == "order_block"
    assert scanner.category == "Smart Money Concepts"
    param_names = [p.name for p in scanner.parameters]
    assert "universe" in param_names
    assert "timeframe" in param_names
    assert "block_type" in param_names
    assert "impulse_multiplier" in param_names
    assert "volume_multiplier" in param_names
    assert "threshold_pct" in param_names
    assert "lookback_days" in param_names


def test_order_block_scan_result_serialization() -> None:
    """Verify OrderBlockScanResult to_dict serialization."""
    ob = OrderBlock(
        price_top=101.0,
        price_bottom=97.0,
        block_type=OrderBlockType.BULLISH_DEMAND,
        candle_timestamp="2026-01-34",
        impulse_body_expansion=2.4,
        volume_expansion=3.1,
        is_mitigated=False,
        description="Demand OB (₹97.0-₹101.0 | 2.4x ATR)",
    )
    res = OrderBlockScanResult(
        symbol="RELIANCE",
        security_id="2885",
        ltp=99.5,
        nearest_order_block=ob,
        distance_pct=0.0,
        is_at_order_block=True,
        is_fresh_impulse=False,
        all_order_blocks=[ob],
        volume=50000,
        rsi=52.0,
        candle_signal="🎯 Inside Bullish Demand OB",
    )
    d = res.to_dict()
    assert d["symbol"] == "RELIANCE"
    assert d["is_at_support"] is True
    assert d["is_inside_demand_ob"] is True
    assert d["is_retesting_demand_ob"] is False
    assert d["is_inside_supply_ob"] is False
    assert d["is_retesting_supply_ob"] is False
    assert "Demand OB" in d["support_desc"]
    assert len(d["all_order_blocks"]) == 1


def test_order_block_scan_result_fresh_impulse_serialization() -> None:
    """Verify OrderBlockScanResult flags for fresh impulse breakout."""
    ob = OrderBlock(
        price_top=101.0,
        price_bottom=97.0,
        block_type=OrderBlockType.BULLISH_DEMAND,
        candle_timestamp="2026-01-34",
        impulse_body_expansion=2.4,
        volume_expansion=3.1,
        is_mitigated=False,
        description="Demand OB (₹97.0-₹101.0 | 2.4x ATR)",
    )
    res = OrderBlockScanResult(
        symbol="TCS",
        security_id="11536",
        ltp=105.0,
        nearest_order_block=ob,
        distance_pct=3.96,
        is_at_order_block=True,
        is_fresh_impulse=True,
        all_order_blocks=[ob],
        volume=120000,
        rsi=68.0,
        candle_signal="⚡ Fresh Bullish Impulse (Breakout)",
    )
    d = res.to_dict()
    assert d["symbol"] == "TCS"
    assert d["is_fresh_impulse"] is True
    assert d["is_at_support"] is True
    assert d["is_inside_demand_ob"] is False
    assert d["is_retesting_demand_ob"] is False
    assert d["is_inside_supply_ob"] is False
    assert d["is_retesting_supply_ob"] is False
