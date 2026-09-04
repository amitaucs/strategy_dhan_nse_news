"""Unit tests for dynamic DhanHQ F&O universe synchronization and caching."""

import json
import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

from news_based_strategy.ingestion.universe import (
    FALLBACK_FNO_SYMBOLS,
    FALLBACK_SECURITY_IDS,
    get_fno_symbols,
    get_security_id_map,
    is_fno_stock,
    parse_fno_symbols_from_csv,
    parse_security_ids_from_csv,
    resolve_security_id,
    sync_dhan_fno_symbols,
)

SAMPLE_DHAN_CSV = """SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_SMST_SECURITY_ID,SEM_CUSTOM_SYMBOL,SEM_TRADING_SYMBOL
NSE,FUTSTK,1001,CGPOWER,CGPOWER-26SEP2026-FUT
NSE,OPTSTK,1002,CGPOWER,CGPOWER-26SEP2026-700-CE
NSE,FUTSTK,1003,BANKINDIA,BANKINDIA-26SEP2026-FUT
NSE,FUTSTK,1004,RELIANCE,RELIANCE-26SEP2026-FUT
NSE,EQUITY,1005,TATASTEEL,TATASTEEL-EQ
BSE,FUTSTK,1006,SBIN,SBIN-BSE-FUT
MCX,FUTCOM,1007,GOLD,GOLD-FUT
"""


class TestDhanUniverseSync(unittest.TestCase):
    """Test dynamic DhanHQ F&O universe loading and caching."""

    def setUp(self):
        self.test_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "test_scratch",
        )
        os.makedirs(self.test_dir, exist_ok=True)
        self.cache_file = os.path.join(self.test_dir, "test_fno.json")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_fno_symbols_from_csv(self):
        """Verify parsing only NSE FUTSTK and OPTSTK rows."""
        symbols = parse_fno_symbols_from_csv(SAMPLE_DHAN_CSV)
        self.assertIn("CGPOWER", symbols)
        self.assertIn("BANKINDIA", symbols)
        self.assertIn("RELIANCE", symbols)
        # Non-F&O cash equity or non-NSE
        self.assertNotIn("TATASTEEL", symbols)  # EQUITY
        self.assertNotIn("GOLD", symbols)  # MCX

    def test_fallback_symbols_include_new_additions(self):
        """Verify fallback set includes recent NSE F&O additions."""
        self.assertIn("CGPOWER", FALLBACK_FNO_SYMBOLS)
        self.assertIn("BANKINDIA", FALLBACK_FNO_SYMBOLS)
        self.assertIn("BSE", FALLBACK_FNO_SYMBOLS)
        self.assertIn("HUDCO", FALLBACK_FNO_SYMBOLS)
        self.assertIn("IRFC", FALLBACK_FNO_SYMBOLS)
        self.assertIn("RVNL", FALLBACK_FNO_SYMBOLS)
        self.assertIn("SUZLON", FALLBACK_FNO_SYMBOLS)
        self.assertIn("ZOMATO", FALLBACK_FNO_SYMBOLS)
        self.assertTrue(is_fno_stock("CGPOWER"))
        self.assertTrue(is_fno_stock("BANKINDIA"))

    def test_sync_saves_and_reads_local_cache(self):
        """Verify that successful sync caches to file and reloads without network."""
        # Create mock response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        # Generate enough symbols so count >= 50
        extended_csv_lines = [
            "SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_SMST_SECURITY_ID,SEM_CUSTOM_SYMBOL,SEM_TRADING_SYMBOL"
        ]
        for i in range(60):
            extended_csv_lines.append(f"NSE,FUTSTK,{i},STOCK_{i},STOCK_{i}-FUT")
        extended_csv = "\n".join(extended_csv_lines)
        mock_resp.read.return_value = extended_csv.encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            synced = sync_dhan_fno_symbols(cache_path=self.cache_file, force_refresh=True)
            self.assertGreaterEqual(len(synced), 60)
            self.assertIn("STOCK_0", synced)
            self.assertTrue(os.path.exists(self.cache_file))

        # Second call: network fails, but cache is read
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            cached = sync_dhan_fno_symbols(cache_path=self.cache_file, force_refresh=False)
            self.assertIn("STOCK_0", cached)

    def test_parse_security_ids_from_csv(self):
        """Verify parsing NSE EQUITY security IDs."""
        mapping = parse_security_ids_from_csv(SAMPLE_DHAN_CSV)
        self.assertIn("TATASTEEL", mapping)
        self.assertEqual(mapping["TATASTEEL"], "1005")
        self.assertEqual(mapping["TATASTEEL-EQ"], "1005")
        # Non-equity or non-NSE should not be in equity map
        self.assertNotIn("GOLD", mapping)

    def test_resolve_security_id_fallback(self):
        """Verify known F&O tickers resolve from the fallback map."""
        self.assertEqual(resolve_security_id("RELIANCE"), "2885")
        self.assertEqual(resolve_security_id("BEL"), "383")
        self.assertEqual(resolve_security_id("CGPOWER"), "730")
        self.assertEqual(resolve_security_id("TCS"), "11536")
        self.assertEqual(resolve_security_id("INFY"), "1594")
        self.assertIsNone(resolve_security_id("NON_EXISTENT_STOCK_9999"))
        self.assertIsNone(resolve_security_id(""))

    def test_resolve_security_id_case_and_suffix(self):
        """Verify normalization handles case, spaces, and series suffixes."""
        self.assertEqual(resolve_security_id("reliance"), "2885")
        self.assertEqual(resolve_security_id("  bel  "), "383")
        self.assertEqual(resolve_security_id("TATAMOTORS-EQ"), "3456")
        self.assertEqual(resolve_security_id("tcs-eq"), "11536")

    def test_sync_persists_and_restores_security_ids(self):
        """Verify sync stores security_ids in cache and reloads them."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        csv_lines = [
            "SEM_EXM_EXCH_ID,SEM_INSTRUMENT_NAME,SEM_SMST_SECURITY_ID,SEM_CUSTOM_SYMBOL,SEM_TRADING_SYMBOL"
        ]
        for i in range(55):
            csv_lines.append(f"NSE,FUTSTK,{10000+i},FUT_{i},FUT_{i}-FUT")
        csv_lines.append("NSE,EQUITY,998877,TESTSYM,TESTSYM-EQ")
        mock_resp.read.return_value = "\n".join(csv_lines).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            sync_dhan_fno_symbols(cache_path=self.cache_file, force_refresh=True)

        self.assertEqual(resolve_security_id("TESTSYM"), "998877")

        # Check cache file content contains security_ids
        with open(self.cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("security_ids", data)
            self.assertEqual(data["security_ids"].get("TESTSYM"), "998877")


if __name__ == "__main__":
    unittest.main()

