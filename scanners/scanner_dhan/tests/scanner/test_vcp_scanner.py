"""Unit and Integration Tests for Mark Minervini Volatility Contraction Pattern (VCP) Scanner."""

from __future__ import annotations

from datetime import datetime, timedelta
import unittest
import numpy as np
import pandas as pd

from scanner_dhan.scanner.vcp_scanner.engine import (
    detect_peaks_and_troughs,
    detect_vcp_pattern,
    evaluate_stage2_trend,
    scan_stock_for_vcp,
)
from scanner_dhan.scanner.vcp_scanner.models import (
    Stage2Metrics,
    VcpPattern,
    VcpScanResult,
    VcpSchematic,
    VcpStatus,
    VcpWave,
)
from scanner_dhan.scanner.vcp_scanner.scanner import (
    VcpScanner,
    format_vcp_dataframe,
)


def _generate_synthetic_stage2_vcp_df() -> pd.DataFrame:
    """Generate a realistic 280-day OHLCV DataFrame in Stage 2 mark-up forming a 3T VCP."""
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(280)]
    records = []

    # 1. Steady Stage 2 Uptrend for first 200 bars (50 -> 100)
    for i in range(200):
        base_price = 50.0 + (i * 0.25)
        records.append({
            "timestamp": dates[i],
            "open": base_price,
            "high": base_price + 1.5,
            "low": base_price - 1.0,
            "close": base_price + 0.5,
            "volume": 200000.0,
        })

    # 2. Peak 1 (Bar 200): Touches 100.0
    records.append({
        "timestamp": dates[200],
        "open": 98.0,
        "high": 100.0,  # Peak 1 = 100.0
        "low": 97.5,
        "close": 99.5,
        "volume": 350000.0,
    })

    # 3. Wave T1 Contraction: Dips to 86.0 (-14.0% depth) over 15 bars
    for i in range(201, 215):
        p = 100.0 - ((i - 200) * 1.0)
        records.append({
            "timestamp": dates[i],
            "open": p + 0.5,
            "high": p + 1.0,
            "low": p - 0.5,
            "close": p,
            "volume": 180000.0,
        })
    # Trough 1 at Bar 214: Low = 86.0
    records[-1]["low"] = 86.0
    records[-1]["close"] = 86.5

    # 4. Recovery to Peak 2 (Bar 228): Rallies back to 99.5
    for i in range(215, 229):
        p = 86.5 + ((i - 214) * 0.95)
        records.append({
            "timestamp": dates[i],
            "open": p - 0.5,
            "high": p + 0.8,
            "low": p - 0.5,
            "close": p,
            "volume": 220000.0,
        })
    records[-1]["high"] = 99.5  # Peak 2 = 99.5

    # 5. Wave T2 Contraction: Dips to 92.5 (-7.0% depth) over 12 bars with lower volume
    for i in range(229, 242):
        p = 99.5 - ((i - 228) * 0.55)
        records.append({
            "timestamp": dates[i],
            "open": p + 0.3,
            "high": p + 0.6,
            "low": p - 0.3,
            "close": p,
            "volume": 140000.0,
        })
    records[-1]["low"] = 92.5  # Trough 2 = 92.5
    records[-1]["close"] = 93.0

    # 6. Recovery to Peak 3 (Bar 255): Rallies to 99.0
    for i in range(242, 256):
        p = 93.0 + ((i - 241) * 0.45)
        records.append({
            "timestamp": dates[i],
            "open": p - 0.3,
            "high": p + 0.5,
            "low": p - 0.3,
            "close": p,
            "volume": 160000.0,
        })
    records[-1]["high"] = 99.0  # Peak 3 = 99.0

    # 7. Wave T3 Final Contraction: Dips to 96.0 (-3.0% depth) on DRY VOLUME (<70k)
    for i in range(256, 275):
        p = 99.0 - ((i - 255) * 0.16)
        records.append({
            "timestamp": dates[i],
            "open": p + 0.2,
            "high": p + 0.4,
            "low": p - 0.2,
            "close": p,
            "volume": 55000.0,  # Dry volume (VDU)
        })
    records[-1]["low"] = 96.0  # Trough 3 = 96.0
    records[-1]["close"] = 96.5

    # 8. Bars 275-279: Tight consolidation right at 98.2 near pivot
    for i in range(275, 280):
        records.append({
            "timestamp": dates[i],
            "open": 98.0,
            "high": 98.6,
            "low": 97.8,
            "close": 98.4,
            "volume": 60000.0,  # Tight dry volume
        })

    df = pd.DataFrame(records)
    df.set_index("timestamp", inplace=True)
    return df


class TestVcpScanner(unittest.TestCase):
    """Comprehensive test suite for Mark Minervini VCP detection engine and models."""

    def test_evaluate_stage2_trend_pass(self) -> None:
        """Test Stage 2 Trend Template evaluation on an established uptrend."""
        df = _generate_synthetic_stage2_vcp_df()
        metrics = evaluate_stage2_trend(df)
        self.assertTrue(metrics.is_stage2)
        self.assertGreater(metrics.sma_50, metrics.sma_150)
        self.assertGreater(metrics.sma_150, metrics.sma_200)
        self.assertGreaterEqual(metrics.sma_200_slope_pct, -0.25)
        self.assertGreaterEqual(metrics.pct_from_52w_high, -30.0)
        self.assertGreaterEqual(metrics.pct_from_52w_low, 25.0)

    def test_evaluate_stage2_trend_fail_downtrend(self) -> None:
        """Test Stage 2 Trend Template rejection on a downtrending stock."""
        dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(250)]
        records = []
        for i in range(250):
            p = 200.0 - (i * 0.5)  # Falling from 200 to 75
            records.append({
                "timestamp": dates[i],
                "open": p,
                "high": p + 1.0,
                "low": p - 1.0,
                "close": p - 0.2,
                "volume": 100000.0,
            })
        df = pd.DataFrame(records).set_index("timestamp")
        metrics = evaluate_stage2_trend(df)
        self.assertFalse(metrics.is_stage2)

    def test_detect_peaks_and_troughs(self) -> None:
        """Test extrema detection with price-scaled prominence."""
        df = _generate_synthetic_stage2_vcp_df()
        peaks, troughs = detect_peaks_and_troughs(df, lookback_bars=100, peak_distance=5)
        self.assertGreaterEqual(len(peaks), 2)
        self.assertGreaterEqual(len(troughs), 2)

    def test_detect_vcp_pattern_3t_clean_contraction(self) -> None:
        """Test detection of a clean 3T VCP pattern with monotonic decay and VDU."""
        df = _generate_synthetic_stage2_vcp_df()
        pattern = detect_vcp_pattern(df, lookback_bars=100, max_final_depth_pct=6.5)
        self.assertIsNotNone(pattern)
        self.assertGreaterEqual(pattern.contractions_count, 2)
        self.assertLessEqual(pattern.final_depth_pct, 6.5)
        self.assertTrue(pattern.is_vdu)
        self.assertGreaterEqual(pattern.pivot_level, 98.0)
        self.assertLessEqual(pattern.stop_loss, pattern.pivot_level)
        self.assertGreater(pattern.target_1, pattern.pivot_level)
        self.assertGreater(pattern.risk_reward_ratio, 0)
        self.assertIn(pattern.status, (VcpStatus.PRIMED_TIGHT, VcpStatus.BREAKOUT_ACTIVE))

    def test_vcp_rejected_if_wave_depth_expands(self) -> None:
        """Test that expanding or erratic wave depths are rejected."""
        df = _generate_synthetic_stage2_vcp_df()
        # Modify bars 256-270 to plunge way deeper to 80.0 (creating a 19% depth expansion)
        for i in range(256, 275):
            df.iloc[i, df.columns.get_loc("low")] = 78.0
            df.iloc[i, df.columns.get_loc("close")] = 79.0
        pattern = detect_vcp_pattern(df, lookback_bars=100)
        self.assertIsNone(pattern)

    def test_vcp_rejected_if_final_depth_exceeds_threshold(self) -> None:
        """Test that VCP is rejected if the final wave is too deep (>6.5%)."""
        df = _generate_synthetic_stage2_vcp_df()
        # Modify final wave trough to 90.0 (from peak of 99.0 -> depth ~9.1% > 6.5%)
        for i in range(256, 275):
            df.iloc[i, df.columns.get_loc("low")] = 90.0
            df.iloc[i, df.columns.get_loc("close")] = 90.5
        pattern = detect_vcp_pattern(df, lookback_bars=100, max_final_depth_pct=6.5)
        self.assertIsNone(pattern)

    def test_vcp_breakout_detection(self) -> None:
        """Test active breakout status when price crosses pivot with volume surge."""
        df = _generate_synthetic_stage2_vcp_df()
        # Modify last bar to break above pivot (100.5) on 500k volume
        df.iloc[-1, df.columns.get_loc("open")] = 98.5
        df.iloc[-1, df.columns.get_loc("high")] = 101.5
        df.iloc[-1, df.columns.get_loc("low")] = 98.2
        df.iloc[-1, df.columns.get_loc("close")] = 101.0
        df.iloc[-1, df.columns.get_loc("volume")] = 500000.0  # Surge

        pattern = detect_vcp_pattern(df, lookback_bars=100)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.status, VcpStatus.BREAKOUT_ACTIVE)
        self.assertIn("Breakout", pattern.candle_signal)

    def test_scan_stock_for_vcp_mocked(self) -> None:
        """Test single stock scanning with mocked provider."""
        df = _generate_synthetic_stage2_vcp_df()

        class MockProvider:
            def get_historical_data(self, **kwargs) -> pd.DataFrame:
                return df

        res = scan_stock_for_vcp(
            provider=MockProvider(),
            symbol="POLYCAB",
            security_id="9590",
            timeframe="Daily",
        )
        self.assertEqual(res.symbol, "POLYCAB")
        self.assertTrue(res.has_setup)
        self.assertTrue(res.is_at_support)
        self.assertIn("VCP", res.support_desc)
        d = res.to_dict()
        self.assertTrue(d["has_setup"])
        self.assertIn("pivot_level", d["setup"])

    def test_vcp_scanner_metadata(self) -> None:
        """Verify VcpScanner registry metadata and parameters."""
        scanner = VcpScanner()
        self.assertEqual(scanner.id, "vcp_contraction")
        self.assertEqual(scanner.name, "Volatility Contraction Pattern (VCP) Scanner")
        self.assertIn("Chart Patterns", scanner.category)

        param_names = [p.name for p in scanner.parameters]
        self.assertIn("universe", param_names)
        self.assertIn("timeframe", param_names)
        self.assertIn("max_final_depth_pct", param_names)
        self.assertIn("vdu_threshold", param_names)

        univ_param = next(p for p in scanner.parameters if p.name == "universe")
        self.assertEqual(univ_param.default, "NIFTY_500")
        univ_values = [opt["value"] for opt in univ_param.options]
        self.assertIn("NIFTY_500", univ_values)
        self.assertIn("NIFTY_MIDCAP_100", univ_values)

    def test_format_vcp_dataframe(self) -> None:
        """Verify presentation DataFrame output."""
        df = _generate_synthetic_stage2_vcp_df()

        class MockProvider:
            def get_historical_data(self, **kwargs) -> pd.DataFrame:
                return df

        res = scan_stock_for_vcp(
            provider=MockProvider(),
            symbol="TRENT",
            security_id="1964",
            timeframe="Daily",
        )
        df_table = format_vcp_dataframe([res], only_matched=True)
        self.assertFalse(df_table.empty)
        self.assertIn("Symbol", df_table.columns)
        self.assertIn("Pivot (₹)", df_table.columns)
        self.assertIn("Contractions", df_table.columns)
        self.assertIn("Depth Progression", df_table.columns)
        self.assertIn("VDU Ratio", df_table.columns)
        self.assertEqual(df_table.iloc[0]["Symbol"], "TRENT")


if __name__ == "__main__":
    unittest.main()

