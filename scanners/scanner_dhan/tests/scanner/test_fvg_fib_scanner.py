"""Unit and Integration Tests for Fair Value Gap + 0.618 Fibonacci Retracement Scanner."""

from __future__ import annotations

from datetime import datetime, timedelta
import pandas as pd
import unittest

from scanner_dhan.scanner.fvg_fibonacci.engine import (
    calculate_fibonacci_retracement,
    detect_fair_value_gaps,
    detect_fvg_fib_confluences,
    scan_stock_for_fvg_fib,
)
from scanner_dhan.scanner.fvg_fibonacci.models import (
    FairValueGap,
    FibonacciRetracement,
    FvgFibConfluenceSetup,
    FvgFibScanResult,
    FvgStatus,
    FvgType,
)
from scanner_dhan.scanner.fvg_fibonacci.scanner import (
    FvgFibonacciScanner,
    format_fvg_fib_dataframe,
)


def _generate_synthetic_bullish_fvg_df() -> pd.DataFrame:
    """Generate a clean OHLCV DataFrame containing a Bullish FVG and 0.618 Fib pullback."""
    dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(40)]
    records = []

    # 1. Base consolidating range around 100
    for i in range(20):
        records.append({
            "timestamp": dates[i],
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 100.5,
            "volume": 50000.0,
        })

    # Bar 20: Swing Low base before impulse (Candle 1)
    records.append({
        "timestamp": dates[20],
        "open": 99.0,
        "high": 103.0,  # Candle 1 High = 103.0
        "low": 98.5,
        "close": 102.5,
        "volume": 60000.0,
    })

    # Bar 21: Massive Green Displacement (Candle 2)
    records.append({
        "timestamp": dates[21],
        "open": 103.0,
        "high": 118.0,
        "low": 102.5,
        "close": 117.5,
        "volume": 250000.0,  # Surge
    })

    # Bar 22: Follow through (Candle 3)
    records.append({
        "timestamp": dates[22],
        "open": 118.0,
        "high": 125.0,
        "low": 110.0,  # Candle 3 Low = 110.0 -> FVG = [103.0, 110.0], CE = 106.5
        "close": 124.0,
        "volume": 120000.0,
    })

    # Bar 23: Peak Continuation to Swing High of 128.0
    records.append({
        "timestamp": dates[23],
        "open": 124.0,
        "high": 128.0,
        "low": 123.5,
        "close": 127.5,
        "volume": 90000.0,
    })
    # Peak at ~128.0 (Swing range: Low=98.5, High=128.0, Diff=29.5 -> Fib 0.618 = 128 - 18.23 = 109.77, lands in FVG [103, 110]!)

    # Bar 24-27: Direct Pullback into 109.5 (0.618 Fib + FVG zone)
    for i in range(24, 28):
        step = (i - 23) * 4.5
        price = max(128.0 - step, 109.5)
        records.append({
            "timestamp": dates[i],
            "open": price + 1.0,
            "high": price + 2.0,
            "low": price - 0.5,
            "close": price,
            "volume": 55000.0,
        })

    # Bar 28: Bullish Bounce / Hammer at 0.618 Fib Level
    records.append({
        "timestamp": dates[28],
        "open": 109.2,
        "high": 111.0,
        "low": 108.5,
        "close": 110.5,
        "volume": 85000.0,
    })

    df = pd.DataFrame(records)
    df.set_index("timestamp", inplace=True)
    return df


def _generate_synthetic_bearish_fvg_df() -> pd.DataFrame:
    """Generate a clean OHLCV DataFrame containing a Bearish FVG and 0.618 Fib pullback."""
    dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(40)]
    records = []

    # 1. Base range around 200
    for i in range(20):
        records.append({
            "timestamp": dates[i],
            "open": 200.0,
            "high": 203.0,
            "low": 197.0,
            "close": 199.5,
            "volume": 50000.0,
        })

    # Bar 20: Swing High base before drop (Candle 1)
    records.append({
        "timestamp": dates[20],
        "open": 201.0,
        "high": 203.0,
        "low": 196.0,  # Candle 1 Low = 196.0
        "close": 197.0,
        "volume": 60000.0,
    })

    # Bar 21: Massive Red Displacement (Candle 2)
    records.append({
        "timestamp": dates[21],
        "open": 196.0,
        "high": 196.5,
        "low": 180.0,
        "close": 181.0,
        "volume": 250000.0,
    })

    # Bar 22: Follow through (Candle 3)
    records.append({
        "timestamp": dates[22],
        "open": 180.5,
        "high": 188.0,  # Candle 3 High = 188.0 -> Bearish FVG = [188.0, 196.0], CE = 192.0
        "low": 172.0,
        "close": 173.0,
        "volume": 120000.0,
    })

    # Bar 23: Trough Continuation to Swing Low of 170.0
    records.append({
        "timestamp": dates[23],
        "open": 173.0,
        "high": 173.5,
        "low": 170.0,
        "close": 170.5,
        "volume": 90000.0,
    })
    # Trough at ~170.0 (Swing range: High=203.0, Low=170.0, Diff=33.0 -> Fib 0.618 = 170 + 20.39 = 190.39, lands in Bearish FVG [188, 196]!)

    # Bar 24-27: Retracement / Rally upward into 190.5 (0.618 Fib + FVG zone)
    for i in range(24, 28):
        step = (i - 23) * 5.0
        price = min(170.0 + step, 190.5)
        records.append({
            "timestamp": dates[i],
            "open": price - 1.0,
            "high": price + 0.5,
            "low": price - 2.0,
            "close": price,
            "volume": 55000.0,
        })

    # Bar 28: Bearish Rejection / Shooting Star at 0.618 Fib Level
    records.append({
        "timestamp": dates[28],
        "open": 190.8,
        "high": 192.5,
        "low": 189.5,
        "close": 189.8,
        "volume": 85000.0,
    })

    df = pd.DataFrame(records)
    df.set_index("timestamp", inplace=True)
    return df


class TestFvgFibonacciScanner(unittest.TestCase):
    """Test suite for FVG + 0.618 Fibonacci retracement scanner engine and models."""

    def test_calculate_fibonacci_retracement_bullish(self) -> None:
        """Test Bullish Fibonacci levels calculation."""
        fib = calculate_fibonacci_retracement(swing_low=100.0, swing_high=200.0, direction="BULLISH")
        self.assertEqual(fib.swing_low, 100.0)
        self.assertEqual(fib.swing_high, 200.0)
        self.assertEqual(fib.fib_0, 200.0)
        self.assertEqual(fib.fib_500, 150.0)
        self.assertAlmostEqual(fib.fib_618, 138.2, places=1)
        self.assertAlmostEqual(fib.fib_705, 129.5, places=1)
        self.assertAlmostEqual(fib.fib_786, 121.4, places=1)
        self.assertEqual(fib.fib_100, 100.0)
        self.assertAlmostEqual(fib.extension_272, 227.2, places=1)

    def test_calculate_fibonacci_retracement_bearish(self) -> None:
        """Test Bearish Fibonacci levels calculation."""
        fib = calculate_fibonacci_retracement(swing_low=100.0, swing_high=200.0, direction="BEARISH")
        self.assertEqual(fib.swing_low, 100.0)
        self.assertEqual(fib.swing_high, 200.0)
        self.assertEqual(fib.fib_0, 100.0)
        self.assertEqual(fib.fib_500, 150.0)
        self.assertAlmostEqual(fib.fib_618, 161.8, places=1)
        self.assertAlmostEqual(fib.fib_705, 170.5, places=1)
        self.assertAlmostEqual(fib.fib_786, 178.6, places=1)
        self.assertEqual(fib.fib_100, 200.0)
        self.assertAlmostEqual(fib.extension_272, 72.8, places=1)

    def test_detect_bullish_fair_value_gap(self) -> None:
        """Test Bullish FVG detection and Consequent Encroachment calculation."""
        df = _generate_synthetic_bullish_fvg_df()
        gaps = detect_fair_value_gaps(df, min_gap_pct=0.2, body_atr_mult=1.0, vol_mult=1.0)
        self.assertGreaterEqual(len(gaps), 1)
        bullish_gap = next((g for g in gaps if g.fvg_type == FvgType.BULLISH_FVG), None)
        self.assertIsNotNone(bullish_gap)
        self.assertEqual(bullish_gap.bottom_price, 103.0)
        self.assertEqual(bullish_gap.top_price, 110.0)
        self.assertEqual(bullish_gap.ce_price, 106.5)
        self.assertEqual(bullish_gap.gap_size, 7.0)

    def test_detect_bearish_fair_value_gap(self) -> None:
        """Test Bearish FVG detection and Consequent Encroachment calculation."""
        df = _generate_synthetic_bearish_fvg_df()
        gaps = detect_fair_value_gaps(df, min_gap_pct=0.2, body_atr_mult=1.0, vol_mult=1.0)
        self.assertGreaterEqual(len(gaps), 1)
        bearish_gap = next((g for g in gaps if g.fvg_type == FvgType.BEARISH_FVG), None)
        self.assertIsNotNone(bearish_gap)
        self.assertEqual(bearish_gap.bottom_price, 188.0)
        self.assertEqual(bearish_gap.top_price, 196.0)
        self.assertEqual(bearish_gap.ce_price, 192.0)
        self.assertEqual(bearish_gap.gap_size, 8.0)

    def test_detect_bullish_fvg_fib_confluence(self) -> None:
        """Test Bullish FVG + 0.618 Fib confluence setup detection."""
        df = _generate_synthetic_bullish_fvg_df()
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertGreaterEqual(len(setups), 1)
        setup = setups[0]
        self.assertEqual(setup.fvg.fvg_type, FvgType.BULLISH_FVG)
        self.assertTrue(setup.is_at_confluence)
        self.assertEqual(setup.status, FvgStatus.PULLBACK_AT_618)
        self.assertGreaterEqual(setup.target_1, 125.0)
        self.assertLessEqual(setup.stop_loss, setup.entry_price)
        self.assertGreater(setup.risk_reward_ratio, 0)

    def test_detect_bullish_fvg_falling_knife_is_watchlist(self) -> None:
        """Test that a pure waterfall/falling knife candle at 0.618 Fib is marked Watchlist, not Confirmed."""
        df = _generate_synthetic_bullish_fvg_df()
        # Overwrite last bar with a solid red falling knife bar (no lower wick, closing at low)
        df.iloc[-1, df.columns.get_loc("open")] = 111.0
        df.iloc[-1, df.columns.get_loc("high")] = 111.2
        df.iloc[-1, df.columns.get_loc("low")] = 109.5
        df.iloc[-1, df.columns.get_loc("close")] = 109.5

        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertGreaterEqual(len(setups), 1)
        setup = setups[0]
        self.assertFalse(setup.is_at_confluence)
        self.assertEqual(setup.status, FvgStatus.WATCHLIST_UNMITIGATED)
        self.assertIn("Waterfall", setup.candle_signal)

    def test_detect_bearish_fvg_fib_confluence(self) -> None:
        """Test Bearish FVG + 0.618 Fib confluence setup detection."""
        df = _generate_synthetic_bearish_fvg_df()
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertGreaterEqual(len(setups), 1)
        setup = setups[0]
        self.assertEqual(setup.fvg.fvg_type, FvgType.BEARISH_FVG)
        self.assertTrue(setup.is_at_confluence)
        self.assertEqual(setup.status, FvgStatus.PULLBACK_AT_618)
        self.assertLessEqual(setup.target_1, 175.0)
        self.assertGreaterEqual(setup.stop_loss, setup.entry_price)
        self.assertGreater(setup.risk_reward_ratio, 0)

    def test_scan_stock_for_fvg_fib_mocked(self) -> None:
        """Test single stock scanning with a mocked data provider."""
        df = _generate_synthetic_bullish_fvg_df()

        class MockProvider:
            def get_historical_data(self, **kwargs) -> pd.DataFrame:
                return df

        res = scan_stock_for_fvg_fib(
            provider=MockProvider(),
            symbol="TCS",
            security_id="11536",
            timeframe="Daily",
            confluence_tolerance_pct=2.5,
        )
        self.assertEqual(res.symbol, "TCS")
        self.assertTrue(res.has_setup)
        self.assertTrue(res.is_at_support)
        self.assertEqual(res.fvg_type, FvgType.BULLISH_FVG)
        self.assertIn("Bullish FVG + 0.618", res.support_desc)
        self.assertTrue(res.to_dict()["has_setup"])
        self.assertTrue(res.to_dict()["is_at_support"])

    def test_fvg_fibonacci_scanner_metadata(self) -> None:
        """Verify scanner metadata registration."""
        scanner = FvgFibonacciScanner()
        self.assertEqual(scanner.id, "fvg_fib_0618")
        self.assertEqual(scanner.name, "FVG + 0.618 Fib Confluence Scanner")
        self.assertEqual(scanner.category, "Smart Money Concepts")

        param_names = [p.name for p in scanner.parameters]
        self.assertIn("universe", param_names)
        self.assertIn("timeframe", param_names)
        self.assertIn("direction", param_names)
        self.assertIn("confluence_tolerance_pct", param_names)
        self.assertIn("min_gap_pct", param_names)

    def test_invalidated_by_close_below_fvg_bottom(self) -> None:
        """Test that a setup where price previously closed below FVG bottom is rejected."""
        df = _generate_synthetic_bullish_fvg_df()
        # Modify bar 25 to close below FVG bottom (103.0)
        df.iloc[25, df.columns.get_loc("close")] = 101.0
        df.iloc[25, df.columns.get_loc("low")] = 100.5
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertEqual(len(setups), 0)

    def test_disqualified_by_breach_and_overhead_retest(self) -> None:
        """Test that price plunging way below FVG and testing from underneath is disqualified."""
        df = _generate_synthetic_bullish_fvg_df()
        # Bar 25 dips deeply to 97.0 (below 103 * 0.985)
        df.iloc[25, df.columns.get_loc("low")] = 97.0
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertEqual(len(setups), 0)

    def test_bearish_invalidated_by_close_above_fvg_top(self) -> None:
        """Test that a bearish setup where price previously closed above FVG top is rejected."""
        df = _generate_synthetic_bearish_fvg_df()
        # Modify bar 25 to close above FVG top (196.0)
        df.iloc[25, df.columns.get_loc("close")] = 198.0
        df.iloc[25, df.columns.get_loc("high")] = 199.0
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertEqual(len(setups), 0)

    def test_disqualified_by_freak_wick_in_cycle(self) -> None:
        """Test that a setup containing a freak outlier wick (>2.0x ATR) is disqualified."""
        df = _generate_synthetic_bullish_fvg_df()
        # Insert a freak 15pt wick on bar 26 (ATR is ~4.5pt)
        df.iloc[26, df.columns.get_loc("high")] = 135.0  # Freak 20pt upper shadow
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertEqual(len(setups), 0)

    def test_disqualified_by_spinning_top_noise_in_cycle(self) -> None:
        """Test that erratic wide-range spinning tops with tiny bodies in cycle are disqualified."""
        df = _generate_synthetic_bullish_fvg_df()
        # Bar 25 has large range (8.0pt) but only 0.5pt body (<22% body ratio)
        df.iloc[25, df.columns.get_loc("open")] = 115.0
        df.iloc[25, df.columns.get_loc("high")] = 119.0
        df.iloc[25, df.columns.get_loc("low")] = 111.0
        df.iloc[25, df.columns.get_loc("close")] = 115.2
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertEqual(len(setups), 0)

    def test_bullish_trigger_disqualified_by_heavy_upper_selling_wick(self) -> None:
        """Test that a bullish trigger bar with a heavy upper selling shadow is rejected."""
        df = _generate_synthetic_bullish_fvg_df()
        # Modify trigger bar (Bar 28) to have large upper wick (e.g. open=109.5, high=114.0, low=109.0, close=110.0)
        # Range = 5.0, upper wick = 4.0 (80% of range)
        df.iloc[28, df.columns.get_loc("open")] = 109.5
        df.iloc[28, df.columns.get_loc("high")] = 114.0
        df.iloc[28, df.columns.get_loc("low")] = 109.0
        df.iloc[28, df.columns.get_loc("close")] = 110.0
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertGreaterEqual(len(setups), 1)
        self.assertFalse(setups[0].is_at_confluence)
        self.assertEqual(setups[0].status, FvgStatus.WATCHLIST_UNMITIGATED)

    def test_bearish_trigger_disqualified_by_heavy_lower_buying_wick(self) -> None:
        """Test that a bearish trigger bar with a heavy lower buying shadow is rejected."""
        df = _generate_synthetic_bearish_fvg_df()
        # Modify trigger bar (Bar 28) to have large lower wick (e.g. open=190.5, high=191.0, low=186.0, close=190.0)
        # Range = 5.0, lower wick = 4.0 (80% of range)
        df.iloc[28, df.columns.get_loc("open")] = 190.5
        df.iloc[28, df.columns.get_loc("high")] = 191.0
        df.iloc[28, df.columns.get_loc("low")] = 186.0
        df.iloc[28, df.columns.get_loc("close")] = 190.0
        setups = detect_fvg_fib_confluences(df, confluence_tolerance_pct=2.0)
        self.assertGreaterEqual(len(setups), 1)
        self.assertFalse(setups[0].is_at_confluence)
        self.assertEqual(setups[0].status, FvgStatus.WATCHLIST_UNMITIGATED)

    def test_format_fvg_fib_dataframe(self) -> None:
        """Verify DataFrame formatting output."""
        df_raw = _generate_synthetic_bullish_fvg_df()

        class MockProvider:
            def get_historical_data(self, **kwargs) -> pd.DataFrame:
                return df_raw

        res = scan_stock_for_fvg_fib(
            provider=MockProvider(),
            symbol="INFY",
            security_id="1594",
            timeframe="Daily",
            confluence_tolerance_pct=2.5,
        )
        df_table = format_fvg_fib_dataframe([res], only_matched=True)
        self.assertFalse(df_table.empty)
        self.assertIn("Symbol", df_table.columns)
        self.assertIn("0.618 Fib (₹)", df_table.columns)
        self.assertIn("FVG Range (₹)", df_table.columns)
        self.assertIn("50% CE (₹)", df_table.columns)
        self.assertEqual(df_table.iloc[0]["Symbol"], "INFY")
        self.assertIn("Bullish FVG", df_table.iloc[0]["Setup"])


if __name__ == "__main__":
    unittest.main()

