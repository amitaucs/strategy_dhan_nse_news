"""Unit tests for DhanHQ rate limiting protection and automatic retry mechanism."""

from __future__ import annotations

from unittest.mock import MagicMock

from scanner_dhan.data.dhan_provider import DhanDataProvider


def test_dhan_provider_rate_limit_retry_success() -> None:
    """Verify that when DH-904 rate limit is encountered, the provider backs off and retries."""
    provider = DhanDataProvider.__new__(DhanDataProvider)
    provider.request_delay = 0.0
    provider.max_retries = 3
    mock_dhan = MagicMock()
    provider.dhan = mock_dhan

    rate_limit_err = {
        "error_code": "DH-904",
        "error_type": "Rate_Limit",
        "error_message": (
            "Too many requests on server from single user breaching rate limits. "
            "Try throttling API calls."
        ),
    }
    success_data = {
        "status": "success",
        "data": {
            "timestamp": [1750000000 + i * 86400 for i in range(10)],
            "open": [100.0] * 10,
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [102.0] * 10,
            "volume": [50000] * 10,
        },
    }

    # 1st call fails with DH-904, 2nd call succeeds
    mock_dhan.historical_daily_data.side_effect = [rate_limit_err, success_data]

    df = provider.fetch_daily_bars(security_id="1964", days=10)
    assert not df.empty
    assert len(df) == 10
    assert mock_dhan.historical_daily_data.call_count == 2


def test_dhan_provider_rate_limit_remarks_retry() -> None:
    """Verify rate limit detection inside remarks dictionary."""
    provider = DhanDataProvider.__new__(DhanDataProvider)
    provider.request_delay = 0.0
    provider.max_retries = 3
    mock_dhan = MagicMock()
    provider.dhan = mock_dhan

    rate_limit_remarks = {
        "status": "failure",
        "remarks": {
            "error_code": "DH-904",
            "error_type": "Rate_Limit",
            "error_message": "Too many requests",
        },
    }
    success_data = {
        "status": "success",
        "data": {
            "timestamp": [1750000000 + i * 86400 for i in range(5)],
            "open": [100.0] * 5,
            "high": [105.0] * 5,
            "low": [95.0] * 5,
            "close": [102.0] * 5,
            "volume": [10000] * 5,
        },
    }

    mock_dhan.historical_daily_data.side_effect = [rate_limit_remarks, success_data]

    df = provider.fetch_daily_bars(security_id="11532", days=5)
    assert not df.empty
    assert len(df) == 5
    assert mock_dhan.historical_daily_data.call_count == 2
