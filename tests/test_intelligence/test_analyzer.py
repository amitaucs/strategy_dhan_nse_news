"""Unit tests for FilingAnalyzer."""

import unittest
from news_based_strategy.intelligence.analyzer import FilingAnalyzer, SYSTEM_PROMPT


class TestFilingAnalyzer(unittest.TestCase):
    """Test AI analyzer fallback behavior and system prompt integrity."""

    def test_analyzer_fallback_without_api_key(self):
        analyzer = FilingAnalyzer(api_key="")
        audit = analyzer.audit("TATAMOTORS", "Q3 Financial Results", "Net profit grew 30%")

        self.assertIsNotNone(audit)
        self.assertEqual(audit.sentiment, "NEUTRAL")
        self.assertFalse(audit.material_impact)

    def test_system_prompt_guidelines(self):
        self.assertIn("BULLISH", SYSTEM_PROMPT)
        self.assertIn("BEARISH", SYSTEM_PROMPT)
        self.assertIn("material_impact", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()

