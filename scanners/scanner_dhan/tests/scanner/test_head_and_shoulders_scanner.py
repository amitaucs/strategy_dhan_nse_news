"""Unit tests for Head & Shoulders and Inverse Head & Shoulders Pattern Scanner."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scanner_dhan.scanner.head_and_shoulders.engine import (
    detect_head_and_shoulders,
    detect_inverse_head_and_shoulders,
    find_extrema,
    scan_stock_for_head_and_shoulders,
)
from scanner_dhan.scanner.head_and_shoulders.models import (
    ConfirmationStatus,
    ExtremaPoint,
    HeadAndShouldersPattern,
    HeadAndShouldersScanResult,
    PatternType,
)
from scanner_dhan.scanner.head_and_shoulders.scanner import (
    HeadAndShouldersScanner,
    format_head_and_shoulders_dataframe,
)


def _create_regular_hs_df(confirmed: bool = False) -> pd.DataFrame:
    """Create synthetic OHLCV DataFrame with a Classical Head and Shoulders pattern."""
    n_bars = 45
    dates = pd.date_range("2026-01-01", periods=n_bars, freq="D")
    
    # Points:
    # 5: A (Left Shoulder peak) = 110
    # 10: B (Neckline 1 trough) = 90
    # 15: C (Head peak) = 130
    # 20: D (Neckline 2 trough) = 91
    # 25: E (Right Shoulder peak) = 111
    prices = np.full(n_bars, 80.0)
    
    # Left shoulder rise & fall
    prices[1:5] = np.linspace(80, 105, 4)
    prices[5] = 110.0  # Peak A
    prices[6:10] = np.linspace(105, 92, 4)
    prices[10] = 90.0  # Trough B
    
    # Head rise & fall
    prices[11:15] = np.linspace(95, 125, 4)
    prices[15] = 130.0  # Peak C (Head)
    prices[16:20] = np.linspace(125, 95, 4)
    prices[20] = 91.0  # Trough D
    
    # Right shoulder rise & fall
    prices[21:25] = np.linspace(95, 108, 4)
    prices[25] = 111.0  # Peak E (Right shoulder, ~1% from A)
    prices[26:30] = np.linspace(108, 95, 4)
    
    if confirmed:
        # Breakdown below neckline 91.0
        prices[30:35] = np.linspace(90, 85, 5)
        prices[35:45] = 84.0
    else:
        # Forming / above neckline
        prices[30:45] = 98.0
        
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices - 0.5,
        "high": prices + 1.0,
        "low": prices - 1.0,
        "close": prices,
        "volume": np.full(n_bars, 50000.0),
    })
    return df


def _create_inverse_hs_df(confirmed: bool = False) -> pd.DataFrame:
    """Create synthetic OHLCV DataFrame with an Inverse Head and Shoulders pattern."""
    n_bars = 45
    dates = pd.date_range("2026-01-01", periods=n_bars, freq="D")
    
    # Points:
    # 5: A (Left Shoulder trough) = 90
    # 10: B (Neckline 1 peak) = 110
    # 15: C (Head trough) = 70
    # 20: D (Neckline 2 peak) = 109
    # 25: E (Right Shoulder trough) = 89
    prices = np.full(n_bars, 120.0)
    
    # Left shoulder dip & rise
    prices[1:5] = np.linspace(120, 95, 4)
    prices[5] = 90.0  # Trough A
    prices[6:10] = np.linspace(95, 105, 4)
    prices[10] = 110.0  # Peak B
    
    # Head dip & rise
    prices[11:15] = np.linspace(105, 75, 4)
    prices[15] = 70.0  # Trough C (Head)
    prices[16:20] = np.linspace(75, 105, 4)
    prices[20] = 109.0  # Peak D
    
    # Right shoulder dip & rise
    prices[21:25] = np.linspace(105, 92, 4)
    prices[25] = 89.0  # Trough E (~1.1% from A)
    prices[26:30] = np.linspace(92, 104, 4)
    
    if confirmed:
        # Breakout above neckline 109.0
        prices[30:35] = np.linspace(106, 115, 5)
        prices[35:45] = 118.0
    else:
        # Forming / below neckline
        prices[30:45] = 102.0
        
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices - 0.5,
        "high": prices + 1.0,
        "low": prices - 1.0,
        "close": prices,
        "volume": np.full(n_bars, 50000.0),
    })
    return df


def test_find_extrema() -> None:
    """Verify extrema finding produces correct peak and trough indices."""
    df = _create_regular_hs_df()
    max_idx, min_idx = find_extrema(df["close"], order=3)
    
    assert 5 in max_idx   # Left shoulder peak
    assert 15 in max_idx  # Head peak
    assert 25 in max_idx  # Right shoulder peak
    assert 10 in min_idx  # Neckline 1
    assert 20 in min_idx  # Neckline 2

    # Also test DataFrame overload
    extrema_pts = find_extrema(df, order=3)
    assert len(extrema_pts) >= 5


def test_detect_regular_head_and_shoulders_forming() -> None:
    """Verify detection of forming Regular Bearish Head & Shoulders pattern."""
    df = _create_regular_hs_df(confirmed=False)
    patterns = detect_head_and_shoulders(df, order=3, shoulder_tolerance=0.03)
    
    assert len(patterns) >= 1
    p = patterns[0]
    assert p.pattern_type == PatternType.REGULAR_HS
    assert p.status == ConfirmationStatus.FORMING
    assert p.left_shoulder.price == pytest.approx(111.0, abs=1.0)  # High = Close + 1.0
    assert p.head.price == pytest.approx(131.0, abs=1.0)
    assert p.right_shoulder.price == pytest.approx(112.0, abs=1.0)
    assert p.neckline_1.price == pytest.approx(89.0, abs=1.0)      # Low = Close - 1.0
    assert p.neckline_2.price == pytest.approx(90.0, abs=1.0)
    assert p.shoulder_diff_pct < 0.03
    # Target 1 = Neckline - (Head - Neckline)
    assert p.target_1 > 0.0
    assert p.stop_loss > p.right_shoulder.price


def test_detect_regular_head_and_shoulders_confirmed() -> None:
    """Verify detection of confirmed breakdown in Regular Head & Shoulders pattern."""
    df = _create_regular_hs_df(confirmed=True)
    patterns = detect_head_and_shoulders(df, order=3, shoulder_tolerance=0.03)
    
    assert len(patterns) >= 1
    p = patterns[0]
    assert p.pattern_type == PatternType.REGULAR_HS
    assert p.status == ConfirmationStatus.CONFIRMED
    assert p.current_price < p.neckline_level


def test_detect_inverse_head_and_shoulders_forming() -> None:
    """Verify detection of forming Inverse Bullish Head & Shoulders pattern."""
    df = _create_inverse_hs_df(confirmed=False)
    patterns = detect_inverse_head_and_shoulders(df, order=3, shoulder_tolerance=0.03)
    
    assert len(patterns) >= 1
    p = patterns[0]
    assert p.pattern_type == PatternType.INVERSE_HS
    assert p.status == ConfirmationStatus.FORMING
    assert p.left_shoulder.price == pytest.approx(89.0, abs=1.0)   # Low = Close - 1.0
    assert p.head.price == pytest.approx(69.0, abs=1.0)
    assert p.right_shoulder.price == pytest.approx(88.0, abs=1.0)
    assert p.neckline_1.price == pytest.approx(111.0, abs=1.0)     # High = Close + 1.0
    assert p.neckline_2.price == pytest.approx(110.0, abs=1.0)
    assert p.shoulder_diff_pct < 0.03
    assert p.target_1 > 0.0
    assert p.stop_loss < p.right_shoulder.price


def test_detect_inverse_head_and_shoulders_confirmed() -> None:
    """Verify detection of confirmed breakout in Inverse Head & Shoulders pattern."""
    df = _create_inverse_hs_df(confirmed=True)
    patterns = detect_inverse_head_and_shoulders(df, order=3, shoulder_tolerance=0.03)
    
    assert len(patterns) >= 1
    p = patterns[0]
    assert p.pattern_type == PatternType.INVERSE_HS
    assert p.status == ConfirmationStatus.CONFIRMED
    assert p.current_price > p.neckline_level


def test_rejection_due_to_asymmetry() -> None:
    """Verify patterns with shoulder asymmetry > tolerance are rejected."""
    df = _create_regular_hs_df()
    # Change Right Shoulder to 125 (Left Shoulder is 110 -> ~13% diff)
    df.loc[25, "close"] = 125.0
    df.loc[25, "high"] = 126.0
    
    # Strict tolerance (3%)
    patterns_strict = detect_head_and_shoulders(df, order=3, shoulder_tolerance=0.03)
    assert len(patterns_strict) == 0
    
    # Loose tolerance (20%)
    patterns_loose = detect_head_and_shoulders(df, order=3, shoulder_tolerance=0.20)
    assert len(patterns_loose) >= 1


def test_rejection_due_to_head_below_shoulder() -> None:
    """Verify pattern is rejected if Head is lower than Left Shoulder in Regular H&S."""
    df = _create_regular_hs_df()
    # Lower entire Head region to below A (which is at 111.0)
    df.loc[11:19, "close"] = 98.0
    df.loc[11:19, "high"] = 99.0
    df.loc[15, "close"] = 100.0
    df.loc[15, "high"] = 101.0
    # Keep right-side continuation flat and low so right shoulder cannot act as a head
    df.loc[26:, "close"] = 80.0
    df.loc[26:, "high"] = 81.0
    df.loc[26:, "low"] = 79.0
    
    patterns = detect_head_and_shoulders(df, order=3, shoulder_tolerance=0.05)
    assert len(patterns) == 0


def test_scan_stock_for_head_and_shoulders() -> None:
    """Verify stock analysis helper returns valid HeadAndShouldersScanResult."""
    df = _create_regular_hs_df(confirmed=True)
    res = scan_stock_for_head_and_shoulders(
        df=df,
        symbol="TATASTEEL",
        security_id="3499",
        order=3,
        shoulder_tolerance=0.03,
        pattern_type="ALL",
    )
    assert res.symbol == "TATASTEEL"
    assert res.security_id == "3499"
    assert res.pattern is not None
    assert res.status == ConfirmationStatus.CONFIRMED
    assert res.pattern_type == PatternType.REGULAR_HS
    assert res.target_1 > 0.0
    assert "Breakdown" in res.signal_desc or "REGULAR_HS" in str(res.pattern_type)


def test_scanner_registration_and_parameters() -> None:
    """Verify HeadAndShouldersScanner is registered and has correct parameters."""
    scanner = HeadAndShouldersScanner()
    assert scanner.id == "head_and_shoulders"
    assert "Head" in scanner.name and "Shoulders" in scanner.name
    assert "Patterns" in scanner.category
    
    param_names = [p.name for p in scanner.parameters]
    assert "universe" in param_names
    assert "pattern_type" in param_names
    assert "status_filter" in param_names
    assert "timeframe" in param_names
    assert "extrema_order" in param_names
    assert "symmetry_tolerance_pct" in param_names


def test_format_head_and_shoulders_dataframe() -> None:
    """Verify DataFrame formatting for UI and CLI."""
    df_raw = _create_regular_hs_df(confirmed=True)
    res = scan_stock_for_head_and_shoulders(
        df=df_raw,
        symbol="INFY",
        security_id="1594",
        order=3,
        shoulder_tolerance=0.03,
    )
    
    df_all = format_head_and_shoulders_dataframe([res], only_matched=False)
    assert not df_all.empty
    assert "Symbol" in df_all.columns
    assert "Pattern" in df_all.columns
    assert "Status" in df_all.columns
    assert "Target 1 (₹)" in df_all.columns
    assert "Stop Loss (₹)" in df_all.columns
    assert df_all.iloc[0]["Symbol"] == "INFY"


def test_scan_result_serialization() -> None:
    """Verify HeadAndShouldersScanResult serialization to dictionary."""
    extrema_a = ExtremaPoint(index=5, timestamp="2026-01-05", price=110.0, point_name="A")
    extrema_b = ExtremaPoint(index=10, timestamp="2026-01-10", price=90.0, point_name="B")
    extrema_c = ExtremaPoint(index=15, timestamp="2026-01-15", price=130.0, point_name="C")
    extrema_d = ExtremaPoint(index=20, timestamp="2026-01-20", price=91.0, point_name="D")
    extrema_e = ExtremaPoint(index=25, timestamp="2026-01-25", price=111.0, point_name="E")
    
    pat = HeadAndShouldersPattern(
        pattern_type=PatternType.REGULAR_HS,
        symbol="HDFCBANK",
        timeframe="Daily",
        status=ConfirmationStatus.CONFIRMED,
        left_shoulder=extrema_a,
        neckline_1=extrema_b,
        head=extrema_c,
        neckline_2=extrema_d,
        right_shoulder=extrema_e,
        neckline_price=91.0,
        head_height=39.0,
        shoulder_symmetry_pct=0.9,
        neckline_symmetry_pct=1.1,
        pattern_bar_span=20,
        target_1=52.0,
        stop_loss=111.5,
        current_price=84.0,
        breakout_date="2026-01-30",
    )
    
    res = HeadAndShouldersScanResult(
        symbol="HDFCBANK",
        security_id="1333",
        pattern=pat,
        status=ConfirmationStatus.CONFIRMED,
        pattern_type=PatternType.REGULAR_HS,
        neckline=91.0,
        head_price=130.0,
        current_price=84.0,
        target_1=52.0,
        stop_loss=111.5,
        shoulder_symmetry_pct=0.9,
        signal_desc="⚡ Confirmed Breakdown below Neckline ₹91.00",
    )
    
    d = res.to_dict()
    assert d["symbol"] == "HDFCBANK"
    assert d["pattern_type"] == "REGULAR_HS"
    assert d["status"] == "CONFIRMED"
    assert d["target_1"] == 52.0
    assert d["stop_loss"] == 111.5
    assert d["pattern"]["head"]["price"] == 130.0


def test_head_and_shoulders_scanner_run_mocked(monkeypatch) -> None:
    """Verify scanner.run executes end-to-end with mocked data provider."""
    from unittest.mock import MagicMock
    from scanner_dhan.data.dhan_provider import DhanDataProvider
    
    scanner = HeadAndShouldersScanner()
    mock_provider = MagicMock(spec=DhanDataProvider)
    df_sample = _create_regular_hs_df(confirmed=True)
    mock_provider.fetch_bars.return_value = df_sample
    mock_provider.fetch_daily_bars.return_value = df_sample
    mock_provider.fetch_daily_ohlcv.return_value = df_sample
    
    report = scanner.run(
        params={
            "universe": "NIFTY_50",
            "pattern_type": "ALL",
            "status_filter": "ALL",
            "order": 3,
            "shoulder_tolerance": 0.03,
            "max_workers": 2,
        },
        provider=mock_provider,
    )
    
    assert report.status == "success"
    assert report.scanner_id == "head_and_shoulders"
    assert report.total_scanned > 0
    assert len(report.results) > 0


