"""Unit tests for 1-OTM Call Option contract and DhanHQ active expiry & option chain resolver."""

from __future__ import annotations

import datetime as dt
import unittest
from unittest.mock import MagicMock

from st14_bullish_ce.options import (
    calculate_strike_interval,
    get_monthly_expiry_date,
    resolve_1otm_ce_contract,
    resolve_otm1_strike,
    resolve_target_expiry,
    resolve_target_expiry_from_list,
)


class TestOptionsResolver(unittest.TestCase):
    """Test suite for option strike and expiry selection logic."""

    def test_monthly_expiry_calculation_last_tuesday(self):
        """Calculates correct last Tuesday for given month and year (NSE stock derivatives standard since Sept 2025)."""
        # September 2026: Last Tuesday is 29-Sep-2026
        exp_sep = get_monthly_expiry_date(2026, 9)
        self.assertEqual(exp_sep.weekday(), 1)  # Tuesday
        self.assertEqual(exp_sep.day, 29)

        # October 2026: Last Tuesday is 27-Oct-2026
        exp_oct = get_monthly_expiry_date(2026, 10)
        self.assertEqual(exp_oct.weekday(), 1)  # Tuesday
        self.assertEqual(exp_oct.day, 27)

    def test_resolve_target_expiry_from_list(self):
        """Validates selecting active dates from DhanHQ expiry_list API."""
        active_expiries = ["2026-09-29", "2026-10-27", "2026-11-24"]

        # 10-Sep-2026 (<= 15th) -> Current Month Expiry (2026-09-29)
        d10 = dt.date(2026, 9, 10)
        exp10, is_next10 = resolve_target_expiry_from_list(active_expiries, current_date=d10)
        self.assertFalse(is_next10)
        self.assertEqual(exp10.strftime("%Y-%m-%d"), "2026-09-29")

        # 16-Sep-2026 (> 15th) -> Next Month Expiry (2026-10-27)
        d16 = dt.date(2026, 9, 16)
        exp16, is_next16 = resolve_target_expiry_from_list(active_expiries, current_date=d16)
        self.assertTrue(is_next16)
        self.assertEqual(exp16.strftime("%Y-%m-%d"), "2026-10-27")

    def test_expiry_date_rule_15th_fallback(self):
        """Date <= 15th selects Current Month, Date > 15th selects Next Month in fallback."""
        # 10-Sep-2026 (<= 15th) -> September 2026 Expiry (29-Sep-2026)
        date_10 = dt.date(2026, 9, 10)
        exp_10, is_next_10 = resolve_target_expiry(date_10)
        self.assertFalse(is_next_10)
        self.assertEqual(exp_10.month, 9)
        self.assertEqual(exp_10.day, 29)

        # 15-Sep-2026 (<= 15th) -> September 2026 Expiry
        date_15 = dt.date(2026, 9, 15)
        exp_15, is_next_15 = resolve_target_expiry(date_15)
        self.assertFalse(is_next_15)
        self.assertEqual(exp_15.month, 9)
        self.assertEqual(exp_15.day, 29)

        # 16-Sep-2026 (> 15th) -> October 2026 Expiry (Theta Shield: 27-Oct-2026)
        date_16 = dt.date(2026, 9, 16)
        exp_16, is_next_16 = resolve_target_expiry(date_16)
        self.assertTrue(is_next_16)
        self.assertEqual(exp_16.month, 10)
        self.assertEqual(exp_16.day, 27)

        # 25-Sep-2026 (> 15th) -> October 2026 Expiry
        date_25 = dt.date(2026, 9, 25)
        exp_25, is_next_25 = resolve_target_expiry(date_25)
        self.assertTrue(is_next_25)
        self.assertEqual(exp_25.month, 10)
        self.assertEqual(exp_25.day, 27)

    def test_strike_interval_tiers(self):
        """Strike intervals follow NSE standards according to underlying price tier."""
        self.assertEqual(calculate_strike_interval(120.0), 2.5)
        self.assertEqual(calculate_strike_interval(300.0), 5.0)
        self.assertEqual(calculate_strike_interval(650.0), 10.0)
        self.assertEqual(calculate_strike_interval(1250.0), 20.0)
        self.assertEqual(calculate_strike_interval(2850.0), 50.0)
        self.assertEqual(calculate_strike_interval(4500.0), 100.0)

    def test_resolve_otm1_strike(self):
        """Resolves ATM strike and 1 Strike Out-of-the-money for Call options."""
        # Stock at ₹2,845 (Tier ₹50) -> ATM = 2,850, 1 OTM = 2,900 CE
        atm, otm1 = resolve_otm1_strike(underlying_ltp=2845.0)
        self.assertEqual(atm, 2850.0)
        self.assertEqual(otm1, 2900.0)

        # With explicit chain strikes: [2400, 2420, 2440, 2460, 2480, 2500]
        # Stock at ₹2,442 -> ATM = 2440, 1 OTM = 2460
        chain = [2400.0, 2420.0, 2440.0, 2460.0, 2480.0, 2500.0]
        atm2, otm2 = resolve_otm1_strike(underlying_ltp=2442.0, available_strikes=chain)
        self.assertEqual(atm2, 2440.0)
        self.assertEqual(otm2, 2460.0)

    def test_resolve_1otm_ce_contract_fallback(self):
        """Constructs complete St14OptionContract object in fallback mode."""
        contract = resolve_1otm_ce_contract(
            symbol="RELIANCE",
            underlying_ltp=2850.0,
            current_date=dt.date(2026, 9, 17),  # > 15th -> October Expiry
            mock_sec_id="OPT_RELIANCE_2900_CE",
            mock_lot_size=250,
        )

        self.assertEqual(contract.underlying_symbol, "RELIANCE")
        self.assertEqual(contract.strike_price, 2900.0)
        self.assertEqual(contract.option_type, "CE")
        self.assertTrue(contract.is_next_month)
        self.assertIn("OCT", contract.symbol)
        self.assertEqual(contract.security_id, "OPT_RELIANCE_2900_CE")
        self.assertEqual(contract.lot_size, 250)
        self.assertGreater(contract.ltp, 0)
        self.assertTrue(contract.is_synthetic)

    def test_resolve_with_dhan_expiry_list_and_option_chain(self):
        """Tests live resolution using DhanHQ expiry_list and option_chain."""
        mock_provider = MagicMock()
        mock_provider.dhan = MagicMock()
        mock_provider.fetch_expiry_list.return_value = ["2026-09-29", "2026-10-27"]
        mock_provider.fetch_option_chain.return_value = {
            "oc": {
                "2800.00": {"ce": {"security_id": "90001", "last_price": 60.0}},
                "2850.00": {"ce": {"security_id": "90002", "last_price": 45.5}},
                "2900.00": {"ce": {"security_id": "90003", "last_price": 32.0}},
            }
        }

        contract = resolve_1otm_ce_contract(
            symbol="RELIANCE",
            underlying_ltp=2840.0,
            provider=mock_provider,
            current_date=dt.date(2026, 9, 17),  # > 15th -> Next month expiry (2026-10-27)
        )

        self.assertIsNotNone(contract)
        self.assertEqual(contract.strike_price, 2900.0)
        self.assertEqual(contract.security_id, "90003")
        self.assertEqual(contract.ltp, 32.0)
        self.assertEqual(contract.expiry_date, "2026-10-27")
        self.assertFalse(contract.is_synthetic)

    def test_unverified_fno_lot_size_disqualifies_contract(self):
        """If a symbol has no verified lot size in the F&O master and no mock is provided, contract resolution must return None."""
        contract = resolve_1otm_ce_contract(
            symbol="NON_FNO_STOCK_XYZ",
            underlying_ltp=150.0,
            current_date=dt.date(2026, 9, 17),
        )
        self.assertIsNone(contract)


if __name__ == "__main__":
    unittest.main()

