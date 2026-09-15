from datetime import date

import pytest

from scanner_dhan import BacktestConfig


def test_config_rejects_reversed_dates() -> None:
    with pytest.raises(ValueError, match="end_date"):
        BacktestConfig(start_date=date(2025, 2, 1), end_date=date(2025, 1, 1))
