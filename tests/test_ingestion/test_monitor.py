"""Unit tests for NSEFilingMonitor and announcement models."""

import json
import unittest
from unittest.mock import MagicMock, patch
from news_based_strategy.core.models import Announcement
from news_based_strategy.ingestion.monitor import NSEFilingMonitor


SAMPLE_NSE_PAYLOAD = [
    {
        "seq_id": "1001",
        "symbol": "TATAMOTORS",
        "desc": "Outcome of Board Meeting",
        "attmntText": "Approval of audited financial results for Q3",
        "an_dt": "04-Sep-2026 10:15:00",
        "attmntFile": "TATA_results.pdf",
    },
    {
        "seq_id": "1002",
        "symbol": "BEL",
        "desc": "Receipt of Major Order",
        "attmntText": "Order worth Rs. 2,500 Crores received from Ministry of Defence",
        "an_dt": "04-Sep-2026 10:20:00",
        "attmntFile": "BEL_order.pdf",
    },
]


class TestAnnouncementModel(unittest.TestCase):
    """Test Announcement data container."""

    def test_formatted_summary(self):
        item = Announcement(
            seq_id="101",
            symbol="INFY",
            desc="Press Release",
            details="New client win in Europe",
            an_dt="04-Sep-2026 11:00:00",
        )
        summary = item.formatted_summary
        self.assertIn("INFY", summary)
        self.assertIn("Press Release", summary)
        self.assertIn("New client win", summary)

    def test_to_dict(self):
        item = Announcement(
            seq_id="102",
            symbol="TCS",
            desc="Dividend",
            details="Interim dividend declared",
            an_dt="04-Sep-2026 11:05:00",
        )
        d = item.to_dict()
        self.assertEqual(d["seq_id"], "102")
        self.assertEqual(d["symbol"], "TCS")


class TestNSEFilingMonitor(unittest.TestCase):
    """Test monitor polling, parsing, and deduplication logic."""

    def setUp(self):
        self.monitor = NSEFilingMonitor(auto_refresh=False)

    def test_fetch_latest_success(self):
        """Test parsing valid JSON payload into Announcement objects."""
        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(SAMPLE_NSE_PAYLOAD))
            items = self.monitor.fetch_latest()

            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].symbol, "TATAMOTORS")
            self.assertEqual(items[0].seq_id, "1001")
            self.assertEqual(items[1].symbol, "BEL")
            self.assertEqual(items[1].seq_id, "1002")
            self.assertEqual(items[1].attmnt_file, "BEL_order.pdf")

    def test_fetch_latest_dict_envelope(self):
        """Test parsing when NSE returns {'data': [...]} envelope."""
        envelope = {"data": SAMPLE_NSE_PAYLOAD}
        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(envelope))
            items = self.monitor.fetch_latest()

            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].symbol, "TATAMOTORS")

    def test_deduplication(self):
        """Test that get_new_announcements yields only newly discovered filings."""
        with patch.object(self.monitor, "_do_get") as mock_get:
            # Cycle 1: 2 announcements
            mock_get.return_value = (200, json.dumps(SAMPLE_NSE_PAYLOAD))
            cycle1 = self.monitor.get_new_announcements()
            self.assertEqual(len(cycle1), 2)

            # Cycle 2: Same 2 announcements -> 0 new
            cycle2 = self.monitor.get_new_announcements()
            self.assertEqual(len(cycle2), 0)

            # Cycle 3: 1 new announcement added
            payload_with_new = list(SAMPLE_NSE_PAYLOAD) + [
                {
                    "seq_id": "1003",
                    "symbol": "TITAN",
                    "desc": "Q3 Update",
                    "attmntText": "Retail sales grew 22%",
                    "an_dt": "04-Sep-2026 10:30:00",
                }
            ]
            mock_get.return_value = (200, json.dumps(payload_with_new))
            cycle3 = self.monitor.get_new_announcements()
            self.assertEqual(len(cycle3), 1)
            self.assertEqual(cycle3[0].symbol, "TITAN")

    def test_symbol_filtering(self):
        """Test filtering announcements by stock ticker."""
        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(SAMPLE_NSE_PAYLOAD))
            filtered = self.monitor.get_new_announcements(symbol_filter="BEL")

            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].symbol, "BEL")

    def test_session_refresh_on_401_or_403(self):
        """Test that monitor refreshes session and retries when encountering 401."""
        with patch.object(self.monitor, "_do_get") as mock_get, \
             patch.object(self.monitor, "refresh_session") as mock_refresh:

            # First call returns 401, second call returns 200 with data
            mock_get.side_effect = [
                (401, ""),
                (200, json.dumps(SAMPLE_NSE_PAYLOAD)),
            ]

    def test_fno_and_noise_filtering_in_monitor(self):
        """Test that get_new_announcements drops non-F&O stocks like SETCO and noise items."""
        mixed_payload = [
            # Eligible F&O stock with material news
            {
                "seq_id": "2001",
                "symbol": "BEL",
                "desc": "Receipt of Major Order",
                "attmntText": "Order worth Rs 1,500 Cr",
                "an_dt": "04-Sep-2026 12:00:00",
            },
            # Non-F&O stock (e.g. SETCO) -> should be dropped
            {
                "seq_id": "2002",
                "symbol": "SETCO",
                "desc": "General Updates",
                "attmntText": "Setco Automotive Limited",
                "an_dt": "04-Sep-2026 12:01:00",
            },
            # F&O stock but pure compliance noise -> should be dropped
            {
                "seq_id": "2003",
                "symbol": "TATAMOTORS",
                "desc": "Loss of Share Certificates",
                "attmntText": "Intimation under Regulation 39(3)",
                "an_dt": "04-Sep-2026 12:02:00",
            },
        ]
        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(mixed_payload))
            # By default fno_only=True, filter_noise=True
            results = self.monitor.get_new_announcements(fno_only=True, filter_noise=True, extract_pdf=False)

            # Only BEL should remain
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].symbol, "BEL")
            self.assertTrue(results[0].is_fno)

    def test_hal_screenshot_exact_schema_parsing(self):
        """Test exact keys from user screenshot: attchmntText and attchmntFile."""
        hal_payload = [
            {
                "seq_id": "3001",
                "symbol": "HAL",
                "sm_name": "Hindustan Aeronautics Limited",
                "desc": "Updates",
                "attchmntText": "Hindustan Aeronautics Limited has informed the Exchange regarding 'Revised Policy'.",
                "attchmntFile": "HAL_04092026133703.pdf",
                "an_dt": "04-Sep-2026 13:37:03",
            }
        ]
        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(hal_payload))
            items = self.monitor.fetch_latest()

            self.assertEqual(len(items), 1)
            hal = items[0]
            self.assertEqual(hal.symbol, "HAL")
            self.assertEqual(hal.desc, "Updates")
            self.assertEqual(
                hal.details,
                "Hindustan Aeronautics Limited has informed the Exchange regarding 'Revised Policy'.",
            )
            self.assertEqual(hal.attmnt_file, "HAL_04092026133703.pdf")
            self.assertEqual(
                hal.attachment_url,
                "https://nsearchives.nseindia.com/corporate/HAL_04092026133703.pdf",
            )
            self.assertIsNotNone(hal.raw_data)

    def test_on_noise_filtered_callback(self):
        """Test that noise filings invoke on_noise_filtered callback and are deduplicated."""
        dixon_payload = [
            {
                "seq_id": "4001",
                "symbol": "DIXON",
                "desc": "Copy of Newspaper Publication",
                "attchmntText": "Dixon Technologies (India) Limited has informed the Exchange about Copy of Newspaper Publication...",
                "an_dt": "04-Sep-2026 14:52:41",
            }
        ]
        dismissed = []

        def noise_cb(item, reason):
            dismissed.append((item.symbol, reason))

        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(dixon_payload))

            # Cycle 1: Should be caught, dismissed via callback, and return 0 tradeable items
            items = self.monitor.get_new_announcements(
                fno_only=True,
                filter_noise=True,
                on_noise_filtered=noise_cb,
            )
            self.assertEqual(len(items), 0)
            self.assertEqual(len(dismissed), 1)
            self.assertEqual(dismissed[0], ("DIXON", "Newspaper Publication"))

            # Cycle 2: Already seen, so callback should NOT be called again
            items2 = self.monitor.get_new_announcements(
                fno_only=True,
                filter_noise=True,
                on_noise_filtered=noise_cb,
            )
            self.assertEqual(len(items2), 0)
            self.assertEqual(len(dismissed), 1)

    def test_on_filtered_captures_fno_and_noise_rejections(self):
        """Test on_filtered callback captures both non-F&O rejection and noise rejection."""
        dismissed = []

        def filter_cb(item, reason):
            dismissed.append((item.symbol, reason))

        mixed_payload = [
            # 1. Non-F&O stock
            {"seq_id": "7001", "symbol": "SETCO", "desc": "Updates", "an_dt": "04-Sep-2026 10:00:00"},
            # 2. F&O stock but noise
            {"seq_id": "7002", "symbol": "TATAMOTORS", "desc": "Loss of Share Certificates", "an_dt": "04-Sep-2026 10:01:00"},
            # 3. F&O stock catalyst
            {"seq_id": "7003", "symbol": "BEL", "desc": "Order win of INR 1000 Cr", "an_dt": "04-Sep-2026 10:02:00"},
        ]

        with patch.object(self.monitor, "_do_get") as mock_get:
            mock_get.return_value = (200, json.dumps(mixed_payload))
            items = self.monitor.get_new_announcements(
                fno_only=True,
                filter_noise=True,
                extract_pdf=False,
                on_filtered=filter_cb,
            )
            # Only BEL passes
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].symbol, "BEL")
            # Filtered list contains both SETCO and TATAMOTORS
            self.assertEqual(len(dismissed), 2)
            self.assertEqual(dismissed[0], ("SETCO", "Not in F&O universe"))
            self.assertEqual(dismissed[1][0], "TATAMOTORS")
            self.assertIn("share certificate", dismissed[1][1].lower())

    def test_do_get_binary_payload_too_large(self):
        """Test _do_get_binary returns 413 when stream exceeds max_bytes."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "5000000"}  # 5 MB > 2 MB
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.object(self.monitor, "_use_requests", True), \
             patch.object(self.monitor, "_session") as mock_session:
            mock_session.get.return_value = mock_resp
            status, data = self.monitor._do_get_binary("http://example.com/huge.pdf", max_bytes=2*1024*1024)
            self.assertEqual(status, 413)
            self.assertEqual(data, b"")

    def test_do_get_binary_timeout(self):
        """Test _do_get_binary returns 408 on timeout."""
        import socket
        with patch.object(self.monitor, "_use_requests", True), \
             patch.object(self.monitor, "_session") as mock_session:
            mock_session.get.side_effect = socket.timeout("Timed out")
            status, data = self.monitor._do_get_binary("http://example.com/slow.pdf", timeout=3.0)
            self.assertEqual(status, 408)
            self.assertEqual(data, b"")


if __name__ == "__main__":
    unittest.main()


