"""Unit tests for multi-timeframe data fetching and resampling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from scanner_dhan.data.dhan_provider import DhanDataProvider


def _create_mock_1m_data(bars: int = 1500) -> dict:
    """Create synthetic 1-minute OHLCV data from 09:15 IST."""
    start_ts = int(pd.Timestamp("2026-08-01 09:15:00", tz="Asia/Kolkata").timestamp())
    timestamps = [start_ts + (i * 60) for i in range(bars)]
    return {
        "timestamp": timestamps,
        "open": [100.0 + (i * 0.05) for i in range(bars)],
        "high": [101.0 + (i * 0.05) for i in range(bars)],
        "low": [99.0 + (i * 0.05) for i in range(bars)],
        "close": [100.5 + (i * 0.05) for i in range(bars)],
        "volume": [1000 + i for i in range(bars)],
    }


def test_dhan_provider_fetch_bars_timeframes() -> None:
    """Test multi-timeframe resampling for 15M, 1H, 2H, and 1D."""
    provider = DhanDataProvider.__new__(DhanDataProvider)
    provider.request_delay = 0.0
    mock_dhan = MagicMock()
    provider.dhan = mock_dhan

    # Mock intraday minute response
    mock_1m = _create_mock_1m_data(bars=600)
    mock_dhan.intraday_minute_data.return_value = {
        "status": "success",
        "data": mock_1m,
    }

    # 1. 15-Minute Candles
    df_15m = provider.fetch_bars(security_id="1333", timeframe="15M")
    assert not df_15m.empty
    assert len(df_15m) > 10
    assert "timestamp" in df_15m.columns
    assert "open" in df_15m.columns
    assert "close" in df_15m.columns

    # 2. 1-Hour (60m) Candles
    df_1h = provider.fetch_bars(security_id="1333", timeframe="1H")
    assert not df_1h.empty
    assert len(df_1h) == 10  # 600m / 60m = 10 bars

    # 3. 2-Hour (120m) Candles
    df_2h = provider.fetch_bars(security_id="1333", timeframe="2H")
    assert not df_2h.empty
    assert len(df_2h) == 5  # 600m / 120m = 5 bars

    # 4. Daily Candles
    mock_dhan.historical_daily_data.return_value = {
        "status": "success",
        "data": {
            "timestamp": [1750000000 + i * 86400 for i in range(30)],
            "open": [100.0] * 30,
            "high": [105.0] * 30,
            "low": [95.0] * 30,
            "close": [102.0] * 30,
            "volume": [50000] * 30,
        },
    }
    df_1d = provider.fetch_bars(security_id="1333", timeframe="1D")
    assert len(df_1d) == 30
