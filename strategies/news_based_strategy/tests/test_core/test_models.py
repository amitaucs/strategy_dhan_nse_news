"""Unit tests for core models."""

import unittest
from news_based_strategy.core.models import (
    Announcement,
    FilingAudit,
    TradeResult,
    TradeSignal,
)


class TestCoreModels(unittest.TestCase):
    """Test core domain data models."""

    def test_announcement_clean_content_prefers_extracted(self):
        item = Announcement(
            seq_id="1",
            symbol="TATAMOTORS",
            desc="Outcome of Board Meeting",
            details="Generic details",
            an_dt="04-Sep-2026",
            extracted_text="The Board approved a quarterly dividend of Rs 15 per share.",
        )
        self.assertEqual(item.clean_content, "The Board approved a quarterly dividend of Rs 15 per share.")

    def test_announcement_clean_content_fallback(self):
        item = Announcement(
            seq_id="2",
            symbol="BEL",
            desc="Press Release",
            details="Order worth Rs 1000 Cr",
            an_dt="04-Sep-2026",
            extracted_text=None,
        )
        self.assertEqual(item.clean_content, "Order worth Rs 1000 Cr")

    def test_filing_audit_creation(self):
        audit = FilingAudit(
            sentiment="BULLISH",
            confidence=95,
            catalyst_type="ORDER_WIN",
            material_impact=True,
            summary="Large defense contract won.",
        )
        self.assertEqual(audit.sentiment, "BULLISH")
        self.assertTrue(audit.material_impact)

    def test_trade_signal_and_result(self):
        sig = TradeSignal(
            symbol="INFY",
            security_id="123",
            action="BUY",
            product_type="INTRADAY",
            confidence=85,
            catalyst_type="EARNINGS_BEAT",
            summary="Revenue beat estimates",
        )
        res = TradeResult(
            success=True,
            symbol=sig.symbol,
            action=sig.action,
            quantity=10,
            product_type=sig.product_type,
            dry_run=True,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.symbol, "INFY")

    def test_announcement_llm_payload(self):
        item = Announcement(
            seq_id="3",
            symbol="HAL",
            desc="Updates",
            details="Hindustan Aeronautics Limited",
            an_dt="04-Sep-2026 13:37:03",
            attmnt_file="HAL_notice.pdf",
            extracted_text="MoD signs contract for 12 Su-30MKI fighter jets worth Rs 11,000 Cr.",
        )
        payload = item.llm_payload
        self.assertIn("TICKER: HAL", payload)
        self.assertIn("HEADLINE: Updates", payload)
        self.assertIn("https://nsearchives.nseindia.com/corporate/HAL_notice.pdf", payload)
        self.assertIn("12 Su-30MKI fighter jets", payload)

    def test_announcement_freshness_badge(self):
        from datetime import datetime
        ref_time = datetime(2026, 9, 4, 15, 20, 0)

        # Fresh announcement (20s latency)
        fresh_item = Announcement(
            seq_id="4",
            symbol="CGPOWER",
            desc="Capacity addition",
            details="New unit",
            an_dt="04-Sep-2026 15:19:40",
        )
        fresh_badge = fresh_item.freshness_badge(max_age_seconds=180, reference_time=ref_time)
        self.assertIn("Latency: 20s", fresh_badge)
        self.assertIn("⚡ Fresh", fresh_badge)

        # Stale announcement (300s latency)
        stale_item = Announcement(
            seq_id="5",
            symbol="CGPOWER",
            desc="Capacity addition",
            details="New unit",
            an_dt="04-Sep-2026 15:15:00",
        )
        stale_badge = stale_item.freshness_badge(max_age_seconds=180, reference_time=ref_time)
        self.assertIn("Latency: 300s", stale_badge)
        self.assertIn("⚠️ STALE > 180s", stale_badge)


if __name__ == "__main__":
    unittest.main()


