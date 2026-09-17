"""Unit tests for ST-14 Bullish CE Intraday Setup Scanner."""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from scanner_dhan.indicators.vwap import (
    calculate_intraday_vwap_series,
    calculate_vwap_slope_and_angle,
)
from scanner_dhan.scanner.registry import ScannerRegistry
from scanner_dhan.scanner.st14_scanner import (
    BullishCeIntradayScanner,
    St14ScanResult,
    St14Status,
    analyze_st14_stock,
    check_timing_constraint,
    compute_indicators,
    evaluate_bullish_conditions,
    format_st14_dataframe,
)


def _generate_synthetic_candles(
    n_bars: int = 50,
    base_price: float = 500.0,
    trend: str = "bullish",
    breakout: bool = True,
) -> pd.DataFrame:
    """Generate synthetic OHLCV candle DataFrame for testing."""
    dates = pd.date_range("2026-08-01", periods=n_bars, freq="D")
    data = []
    price = base_price

    for i in range(n_bars):
        if trend == "bullish":
            price += 1.5 + (i * 0.1)
        else:
            price -= 1.0

        o = price - 1.0
        c = price + 1.0
        h = max(o, c) + 2.0
        l = min(o, c) - 2.0
        v = 100000 + i * 500
        data.append({"timestamp": dates[i], "open": o, "high": h, "low": l, "close": c, "volume": v})

    df = pd.DataFrame(data)

    if breakout and n_bars > 6:
        # Guarantee last close exceeds previous 5-bar high
        prev_5_high = df["high"].iloc[-6:-1].max()
        df.loc[df.index[-1], "close"] = prev_5_high + 5.0
        df.loc[df.index[-1], "high"] = prev_5_high + 8.0

    return df


class TestSt14Scanner(unittest.TestCase):
    """Test suite for ST-14 Bullish CE Scanner."""

    def test_timing_constraint(self):
        """Timing constraint validates >= 10:15 AM IST properly."""
        ist = ZoneInfo("Asia/Kolkata")

        # 10:15 AM IST -> Valid
        dt_1015 = datetime(2026, 9, 17, 10, 15, tzinfo=ist)
        is_valid, msg = check_timing_constraint(dt_1015)
        self.assertTrue(is_valid)
        self.assertIn("Valid entry window", msg)

        # 11:30 AM IST -> Valid
        dt_1130 = datetime(2026, 9, 17, 11, 30, tzinfo=ist)
        is_valid2, _ = check_timing_constraint(dt_1130)
        self.assertTrue(is_valid2)

        # 09:30 AM IST -> Blocked
        dt_0930 = datetime(2026, 9, 17, 9, 30, tzinfo=ist)
        is_valid3, msg3 = check_timing_constraint(dt_0930)
        self.assertFalse(is_valid3)
        self.assertIn("Early session", msg3)

    def test_compute_indicators(self):
        """compute_indicators calculates EMA20, VWAP, and 5-bar window highs."""
        df = _generate_synthetic_candles(n_bars=40, trend="bullish", breakout=True)
        ind_df = compute_indicators(df, ema_period=20, total_window_bars=5)

        self.assertIn("ema20", ind_df.columns)
        self.assertIn("vwap", ind_df.columns)
        self.assertIn("prior_window_high", ind_df.columns)
        self.assertIn("total_5_high", ind_df.columns)

        last_row = ind_df.iloc[-1]
        self.assertTrue(pd.notna(last_row["ema20"]))
        self.assertTrue(pd.notna(last_row["vwap"]))
        self.assertTrue(pd.notna(last_row["prior_window_high"]))
        self.assertGreater(last_row["close"], last_row["prior_window_high"])

    def test_vwap_slope_and_angle(self):
        """calculate_vwap_slope_and_angle computes slope, degree angle, and rising status."""
        vwap_series = pd.Series([100.0, 100.5, 101.2, 102.0])
        slope_pct, angle_deg, is_rising = calculate_vwap_slope_and_angle(vwap_series)

        self.assertGreater(slope_pct, 0)
        self.assertGreater(angle_deg, 0)
        self.assertTrue(is_rising)

    def test_evaluate_bullish_conditions_qualified(self):
        """Strong trending daily and hourly candles with VWAP proximity trigger QUALIFIED status."""
        df_daily = _generate_synthetic_candles(n_bars=45, base_price=1000.0, trend="bullish", breakout=True)
        df_hourly = _generate_synthetic_candles(n_bars=45, base_price=1000.0, trend="bullish", breakout=True)

        res = evaluate_bullish_conditions(
            df_daily=df_daily,
            df_hourly=df_hourly,
            vwap_min_dist_pct=-1.0,
            vwap_max_dist_pct=5.0,
            require_rising_vwap=True,
            enforce_timing=False,
        )

        self.assertTrue(res["is_valid"])
        self.assertTrue(res["is_daily_bullish"])
        self.assertTrue(res["is_hourly_bullish"])
        self.assertTrue(res["is_vwap_valid"])
        self.assertEqual(res["status"], St14Status.QUALIFIED)
        self.assertTrue(res["is_5d_breakout"])
        self.assertTrue(res["is_5h_breakout"])

    def test_evaluate_bullish_conditions_failed_breakout(self):
        """When 5-day breakout fails (close < 5-day high), stock is not qualified."""
        df_daily = _generate_synthetic_candles(n_bars=45, base_price=500.0, trend="bullish", breakout=False)
        # Suppress last daily close below previous high
        df_daily.loc[df_daily.index[-1], "close"] = df_daily["high"].iloc[-5:].min() - 5.0

        df_hourly = _generate_synthetic_candles(n_bars=45, base_price=500.0, trend="bullish", breakout=True)

        res = evaluate_bullish_conditions(
            df_daily=df_daily,
            df_hourly=df_hourly,
            enforce_timing=False,
        )

        self.assertTrue(res["is_valid"])
        self.assertFalse(res["is_daily_bullish"])
        self.assertFalse(res["is_5d_breakout"])
        self.assertNotEqual(res["status"], St14Status.QUALIFIED)

    def test_analyze_st14_stock(self):
        """analyze_st14_stock returns St14ScanResult with complete fields and VWAP metrics."""
        df_daily = _generate_synthetic_candles(n_bars=45, base_price=750.0, trend="bullish", breakout=True)
        df_hourly = _generate_synthetic_candles(n_bars=45, base_price=750.0, trend="bullish", breakout=True)

        result = analyze_st14_stock(
            symbol="RELIANCE",
            security_id="2885",
            df_daily=df_daily,
            df_hourly=df_hourly,
            vwap_min_dist_pct=-1.0,
            vwap_max_dist_pct=5.0,
            require_rising_vwap=True,
            enforce_timing=False,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.symbol, "RELIANCE")
        self.assertEqual(result.security_id, "2885")
        self.assertEqual(result.status, St14Status.QUALIFIED)
        self.assertTrue(result.is_at_support)
        self.assertIn("BULLISH CE TRIGGER", result.candle_signal)
        self.assertGreater(result.daily_close, 0)
        self.assertGreater(result.hourly_close, 0)
        self.assertGreater(result.vwap, 0)

        # Test dictionary serialization
        d = result.to_dict()
        self.assertEqual(d["symbol"], "RELIANCE")
        self.assertEqual(d["status"], "QUALIFIED")
        self.assertTrue(d["matched"])
        self.assertIn("vwap", d)
        self.assertIn("vwap_dist_pct", d)

    def test_scanner_registry_discovery(self):
        """ST-14 Bullish CE scanner is registered in ScannerRegistry with streamlined params."""
        scanner = ScannerRegistry.get("st14_bullish_ce")
        self.assertIsNotNone(scanner)
        self.assertEqual(scanner.id, "st14_bullish_ce")
        self.assertIn("Bullish CE", scanner.name)
        self.assertEqual(scanner.category, "Options / Intraday Momentum")

        # Verify parameter definitions
        param_names = [p.name for p in scanner.parameters]
        self.assertIn("universe", param_names)
        self.assertIn("vwap_min_dist_pct", param_names)
        self.assertIn("vwap_max_dist_pct", param_names)
        self.assertIn("require_rising_vwap", param_names)
        self.assertIn("enforce_timing", param_names)
        # Ensure RSI is not in parameters
        self.assertNotIn("daily_rsi_min", param_names)
        self.assertNotIn("hourly_rsi_min", param_names)

    def test_scanner_run_mocked(self):
        """BullishCeIntradayScanner.run executes properly with mocked provider."""
        scanner = BullishCeIntradayScanner()
        mock_provider = MagicMock()
        mock_provider.fetch_daily_bars.return_value = _generate_synthetic_candles(n_bars=45, trend="bullish", breakout=True)
        mock_provider.fetch_1h_bars.return_value = _generate_synthetic_candles(n_bars=45, trend="bullish", breakout=True)

        report = scanner.run(
            params={
                "universe": "NIFTY_50",
                "vwap_min_dist_pct": -1.0,
                "vwap_max_dist_pct": 5.0,
                "enforce_timing": False,
                "max_workers": 2,
            },
            provider=mock_provider,
        )

        self.assertEqual(report.scanner_id, "st14_bullish_ce")
        self.assertEqual(report.total_scanned, 50)
        self.assertGreaterEqual(len(report.results), 1)
        self.assertGreaterEqual(report.matched_count, 1)

        # Test DataFrame formatting
        df = format_st14_dataframe(report.results)
        self.assertFalse(df.empty)
        self.assertIn("Symbol", df.columns)
        self.assertIn("VWAP", df.columns)
        self.assertIn("VWAP Dist (%)", df.columns)
        self.assertIn("VWAP Angle", df.columns)
        self.assertIn("5D Breakout", df.columns)
        self.assertIn("5H Breakout", df.columns)
        self.assertIn("Status", df.columns)


if __name__ == "__main__":
    unittest.main()
