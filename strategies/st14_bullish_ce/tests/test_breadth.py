"""Unit tests for Nifty 50 and Bank Nifty market breadth verifier."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from st14_bullish_ce.breadth import (
    BANK_NIFTY_SEC_ID,
    NIFTY_50_SEC_ID,
    check_market_breadth,
)


class TestMarketBreadth(unittest.TestCase):
    """Test suite for index market breadth checks."""

    def test_mock_breadth_both_green(self):
        """When both Nifty 50 and Bank Nifty are green, breadth passes."""
        is_both, info = check_market_breadth(mock_nifty_green=True, mock_banknifty_green=True)
        self.assertTrue(is_both)
        self.assertTrue(info["is_both_green"])
        self.assertTrue(info["nifty_50"]["is_green"])
        self.assertTrue(info["bank_nifty"]["is_green"])

    def test_mock_breadth_one_red(self):
        """When either Nifty 50 or Bank Nifty is red, breadth is blocked."""
        # Nifty Green, Bank Nifty Red
        is_both, info = check_market_breadth(mock_nifty_green=True, mock_banknifty_green=False)
        self.assertFalse(is_both)
        self.assertFalse(info["is_both_green"])

        # Nifty Red, Bank Nifty Green
        is_both2, info2 = check_market_breadth(mock_nifty_green=False, mock_banknifty_green=True)
        self.assertFalse(is_both2)

        # Both Red
        is_both3, _ = check_market_breadth(mock_nifty_green=False, mock_banknifty_green=False)
        self.assertFalse(is_both3)

    def test_dhan_api_breadth_mocked(self):
        """Test API parsing of OHLC snapshot response."""
        mock_provider = MagicMock()
        mock_provider.dhan.ohlc_data.return_value = {
            "status": "success",
            "data": {
                "IDX_I": {
                    NIFTY_50_SEC_ID: {"last_price": 25400.0, "close": 25300.0},
                    BANK_NIFTY_SEC_ID: {"last_price": 52300.0, "close": 52100.0},
                }
            },
        }

        is_both, info = check_market_breadth(provider=mock_provider)
        self.assertTrue(is_both)
        self.assertGreater(info["nifty_50"]["change_pct"], 0)
        self.assertGreater(info["bank_nifty"]["change_pct"], 0)


if __name__ == "__main__":
    unittest.main()

