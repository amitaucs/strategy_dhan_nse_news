from datetime import date
import unittest

from scanner_dhan import BacktestConfig


class TestConfig(unittest.TestCase):
    def test_config_rejects_reversed_dates(self) -> None:
        with self.assertRaises(ValueError):
            BacktestConfig(start_date=date(2025, 2, 1), end_date=date(2025, 1, 1))

