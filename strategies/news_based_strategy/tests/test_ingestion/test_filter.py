"""Unit tests for F&O universe filtering and pre-LLM noise detection."""

import unittest
from news_based_strategy.ingestion.filter import NoiseFilter
from news_based_strategy.ingestion.universe import is_fno_stock, FNO_SYMBOLS


class TestUniverseFilter(unittest.TestCase):
    """Test F&O constituent verification."""

    def test_fno_symbols_membership(self):
        # Major F&O stocks
        self.assertTrue(is_fno_stock("TATAMOTORS"))
        self.assertTrue(is_fno_stock("BEL"))
        self.assertTrue(is_fno_stock("RELIANCE"))
        self.assertTrue(is_fno_stock("CGPOWER"))  # Recent F&O addition
        self.assertTrue(is_fno_stock("BANKINDIA"))  # Recent F&O addition
        self.assertTrue(is_fno_stock("infy"))  # Case insensitive
        self.assertTrue(is_fno_stock("  BAJAJ-AUTO  "))  # Strips whitespace

        # Non-F&O penny stocks / smallcaps
        self.assertFalse(is_fno_stock("SETCO"))
        self.assertFalse(is_fno_stock("SUZLON_FAKE"))
        self.assertFalse(is_fno_stock(""))
        self.assertFalse(is_fno_stock(None))

    def test_fno_symbols_count(self):
        # Verify healthy universe size
        self.assertGreater(len(FNO_SYMBOLS), 170)


class TestNoiseFilter(unittest.TestCase):
    """Test detection and suppression of routine compliance disclosures."""

    def test_trading_window_noise(self):
        self.assertTrue(NoiseFilter.is_noise("Closure of Trading Window", "Trading window is closed from 01-Jan"))
        self.assertTrue(NoiseFilter.is_noise("Intimation of Trading Window Closure"))
        self.assertTrue(NoiseFilter.is_noise("Trading window open"))

    def test_share_certificate_noise(self):
        self.assertTrue(NoiseFilter.is_noise("Loss of Share Certificates", "Intimation under Regulation 39(3)"))
        self.assertTrue(NoiseFilter.is_noise("Issue of duplicate share certificate"))
        self.assertTrue(NoiseFilter.is_noise("Confirmation Certificate under Regulation 74(5)"))

    def test_newspaper_publication_noise(self):
        self.assertTrue(NoiseFilter.is_noise("Newspaper Publication of Financial Results"))
        self.assertTrue(NoiseFilter.is_noise("Extract of Unaudited Financial Results in Newspaper"))

    def test_analyst_schedule_noise(self):
        self.assertTrue(NoiseFilter.is_noise("Schedule of Analyst / Institutional Investor Meeting"))
        self.assertTrue(NoiseFilter.is_noise("Intimation of Investor Meet"))
        self.assertTrue(
            NoiseFilter.is_noise(
                "Analysts/Institutional Investor Meet/Con. Call Updates",
                "Hindalco Industries Limited has informed the Exchange about Schedule of meet",
            )
        )
        self.assertTrue(NoiseFilter.is_noise("Investor Presentation on Q1 Results"))

    def test_material_overrides_not_noise(self):
        # Contract / Order win must NOT be noise
        self.assertFalse(NoiseFilter.is_noise("Receipt of Major Order", "Bagged contract worth Rs 2,000 Cr"))
        self.assertFalse(NoiseFilter.is_noise("Press Release", "Secured project from Ministry of Power"))

        # Dividend / Board meeting outcome
        self.assertFalse(NoiseFilter.is_noise("Outcome of Board Meeting", "Declared Interim Dividend of Rs 10"))
        self.assertFalse(NoiseFilter.is_noise("Financial Results", "Net profit grew 45% YoY"))

        # Corporate actions & management
        self.assertFalse(NoiseFilter.is_noise("Resignation of Chief Financial Officer", "CFO submitted resignation"))
        self.assertFalse(NoiseFilter.is_noise("Acquisition of 51% stake in XYZ Ltd"))
        self.assertFalse(NoiseFilter.is_noise("US FDA Approval received for generic drug"))

    def test_explain_noise_categories(self):
        # Exact DIXON screenshot case
        dixon_reason = NoiseFilter.explain_noise(
            "Copy of Newspaper Publication",
            "Dixon Technologies (India) Limited has informed the Exchange about Copy of Newspaper Publication of Notice to the Member...",
        )
        self.assertEqual(dixon_reason, "Newspaper Publication")

        # Exact CONCOR screenshot case
        concor_reason = NoiseFilter.explain_noise(
            "Shareholders meeting",
            "Container Corporation Of India Limited has informed the Exchange regarding Notice of Annual General Meeting to be held o...",
        )
        self.assertEqual(concor_reason, "AGM / Administrative Update")

        # Trading window
        self.assertEqual(
            NoiseFilter.explain_noise("Intimation of Trading Window Closure"),
            "Trading Window",
        )

        # Share certificates
        self.assertEqual(
            NoiseFilter.explain_noise("Loss of Share Certificates", "Regulation 39(3)"),
            "Share Certificate / Demat",
        )

        # Analyst meet
        self.assertEqual(
            NoiseFilter.explain_noise("Schedule of Analyst / Institutional Investor Meeting"),
            "Analyst Meet / Earnings Call Schedule",
        )

        # Material events should return None (not noise)
        self.assertIsNone(
            NoiseFilter.explain_noise("Receipt of Major Order", "Bagged contract worth Rs 2,000 Cr")
        )
        self.assertIsNone(
            NoiseFilter.explain_noise("Outcome of Board Meeting", "Declared Interim Dividend of Rs 10")
        )


if __name__ == "__main__":
    unittest.main()

