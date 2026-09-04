"""Unit tests for FilingAnalyzer."""

import unittest
from unittest.mock import MagicMock
from news_based_strategy.core.models import FilingAudit
from news_based_strategy.intelligence.analyzer import FilingAnalyzer, SYSTEM_PROMPT


class TestFilingAnalyzer(unittest.TestCase):
    """Test AI analyzer structured parsing, fallback behavior, and error resilience."""

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

    def test_analyzer_successful_bullish_classification(self):
        analyzer = FilingAnalyzer(api_key="mock_key", model_name="gemini-3.7-flash")
        mock_client = MagicMock()
        mock_response = MagicMock()
        expected_audit = FilingAudit(
            sentiment="BULLISH",
            confidence=92,
            catalyst_type="ORDER_WIN",
            material_impact=True,
            summary="Secured major defense export contract worth INR 1,500 Cr.",
        )
        mock_response.parsed = expected_audit
        mock_client.models.generate_content.return_value = mock_response
        analyzer.client = mock_client

        audit = analyzer.audit(
            symbol="BEL",
            headline="Major order win",
            details="Secured contract of 1500 Cr",
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.sentiment, "BULLISH")
        self.assertEqual(audit.confidence, 92)
        self.assertEqual(audit.catalyst_type, "ORDER_WIN")
        self.assertTrue(audit.material_impact)

    def test_analyzer_successful_json_string_parsing(self):
        analyzer = FilingAnalyzer(api_key="mock_key", model_name="gemini-3.7-flash")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_response.text = (
            '{"sentiment": "BEARISH", "confidence": 95, "catalyst_type": "REGULATORY_PENALTY", '
            '"material_impact": true, "summary": "RBI imposes severe penalty and business restriction."}'
        )
        mock_client.models.generate_content.return_value = mock_response
        analyzer.client = mock_client

        audit = analyzer.audit(
            symbol="BANKINDIA",
            headline="RBI Order",
            details="Penalty imposed",
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.sentiment, "BEARISH")
        self.assertEqual(audit.confidence, 95)
        self.assertTrue(audit.material_impact)

    def test_analyzer_handles_api_exception_gracefully(self):
        analyzer = FilingAnalyzer(api_key="mock_key", model_name="gemini-3.7-flash")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("Google API connection timeout")
        analyzer.client = mock_client

        audit = analyzer.audit("INFY", "Contract update", "Details")
        self.assertIsNone(audit)

    def test_analyzer_auto_fallback_on_404_deprecation(self):
        analyzer = FilingAnalyzer(api_key="mock_key", model_name="gemini-2.5-flash")
        mock_client = MagicMock()

        # First call fails with 404 is no longer available
        err = RuntimeError("404 NOT_FOUND: This model models/gemini-2.5-flash is no longer available to new users.")
        fallback_response = MagicMock()
        fallback_response.parsed = FilingAudit(
            sentiment="BULLISH",
            confidence=85,
            catalyst_type="CONTRACT",
            material_impact=True,
            summary="Fallback successfully classified",
        )
        mock_client.models.generate_content.side_effect = [err, fallback_response]
        analyzer.client = mock_client

        audit = analyzer.audit("TCS", "Contract update", "Details")
        self.assertIsNotNone(audit)
        self.assertEqual(audit.sentiment, "BULLISH")
        self.assertEqual(audit.confidence, 85)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)


if __name__ == "__main__":
    unittest.main()

