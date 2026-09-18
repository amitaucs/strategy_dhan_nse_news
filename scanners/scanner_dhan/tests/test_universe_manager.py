"""Unit tests for DhanUniverseManager and dynamic universe resolution."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure st14_bullish_ce and other workspace modules are importable
repo_root = Path(__file__).resolve().parents[3]
st14_src = repo_root / "strategies" / "st14_bullish_ce" / "src"
if str(st14_src) not in sys.path:
    sys.path.insert(0, str(st14_src))

from scanner_dhan.universe import (
    FNO_SYMBOLS,
    NIFTY_50_SYMBOLS,
    NIFTY_100_SYMBOLS,
    NIFTY_200_SYMBOLS,
    NIFTY_500_SYMBOLS,
    NIFTY_SMALLCAP_100_SYMBOLS,
    get_active_universe,
    get_fno_lot_size,
    is_fno_stock,
)
from scanner_dhan.universe.manager import DhanUniverseManager


class TestDhanUniverseManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.mgr = DhanUniverseManager(cache_dir=self.cache_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fno_lot_size_and_membership(self):
        # Seed fake FNO cache
        fno_data = {
            "universe": "ALL_F_AND_O",
            "count": 2,
            "last_updated": "2026-09-18 10:00:00",
            "symbols": ["RELIANCE", "TCS"],
            "lot_sizes": {"RELIANCE": 250, "TCS": 175},
            "security_ids": {"RELIANCE": "2885", "TCS": "11536"},
        }
        with open(self.cache_dir / "fno_universe.json", "w", encoding="utf-8") as f:
            json.dump(fno_data, f)

        mgr = DhanUniverseManager(cache_dir=self.cache_dir)
        self.assertTrue(mgr.is_fno_stock("RELIANCE"))
        self.assertTrue(mgr.is_fno_stock("TCS"))
        self.assertFalse(mgr.is_fno_stock("GNFC"))  # Not in FNO!
        self.assertEqual(mgr.get_lot_size("RELIANCE"), 250)
        self.assertEqual(mgr.get_lot_size("TCS"), 175)
        self.assertEqual(mgr.get_lot_size("UNKNOWN", default=250), 250)

    def test_get_active_universe_routing(self):
        # Seed NIFTY 200 cache
        n200_data = {
            "universe": "NIFTY_200",
            "count": 2,
            "last_updated": "2026-09-18 10:00:00",
            "symbols": ["ABB", "ACC"],
            "security_ids": {"ABB": "123", "ACC": "456"},
        }
        with open(self.cache_dir / "nifty200_universe.json", "w", encoding="utf-8") as f:
            json.dump(n200_data, f)

        mgr = DhanUniverseManager(cache_dir=self.cache_dir)
        name, symbols, sec_ids = mgr.get_universe("NIFTY_200")
        self.assertEqual(name, "NIFTY_200")
        self.assertIn("ABB", symbols)
        self.assertEqual(sec_ids.get("ACC"), "456")

    def test_options_disqualification_for_non_fno(self):
        from st14_bullish_ce.options import resolve_1otm_ce_contract

        # Seed FNO with RELIANCE only
        fno_data = {
            "universe": "ALL_F_AND_O",
            "count": 1,
            "last_updated": "2026-09-18 10:00:00",
            "symbols": ["RELIANCE"],
            "lot_sizes": {"RELIANCE": 250},
            "security_ids": {"RELIANCE": "2885"},
        }
        with open(self.cache_dir / "fno_universe.json", "w", encoding="utf-8") as f:
            json.dump(fno_data, f)

        mock_mgr = DhanUniverseManager(cache_dir=self.cache_dir)
        with patch("scanner_dhan.universe.manager.get_universe_manager", return_value=mock_mgr), \
             patch("st14_bullish_ce.options.get_universe_manager", return_value=mock_mgr), \
             patch("st14_bullish_ce.options.is_fno_stock", side_effect=mock_mgr.is_fno_stock):
            # GNFC should be None (disqualified)
            gnfc_contract = resolve_1otm_ce_contract(symbol="GNFC", underlying_ltp=590.0)
            self.assertIsNone(gnfc_contract)

            # RELIANCE should resolve to valid St14OptionContract
            rel_contract = resolve_1otm_ce_contract(symbol="RELIANCE", underlying_ltp=2500.0)
            self.assertIsNotNone(rel_contract)
            self.assertEqual(rel_contract.underlying_symbol, "RELIANCE")
            self.assertEqual(rel_contract.lot_size, 250)


if __name__ == "__main__":
    unittest.main()
