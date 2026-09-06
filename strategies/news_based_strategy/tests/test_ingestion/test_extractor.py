"""Unit tests for PDFExtractor."""

import unittest
from news_based_strategy.ingestion.extractor import PDFExtractor


class TestPDFExtractor(unittest.TestCase):
    """Test text cleaning, truncation, and fallback behavior."""

    def setUp(self):
        self.extractor = PDFExtractor()

    def test_clean_text_whitespace(self):
        raw = "Line 1   with    excessive   spaces\n\n\n\n\nLine 2"
        cleaned = PDFExtractor.clean_text(raw)
        self.assertEqual(cleaned, "Line 1 with excessive spaces\n\nLine 2")

    def test_clean_text_truncation(self):
        long_text = "A" * 3000
        cleaned = PDFExtractor.clean_text(long_text, max_chars=100)
        self.assertTrue(cleaned.endswith("... [TRUNCATED]"))
        self.assertEqual(len(cleaned), 100 + len("... [TRUNCATED]"))

    def test_extract_invalid_bytes(self):
        from unittest.mock import patch
        with patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.extract_text_from_bytes(b"not a valid pdf header")
            self.assertIsNone(text)
            self.assertIn("INVALID_PDF_DATA", status)

    def test_pypdf_not_installed_status(self):
        from unittest.mock import patch
        with patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=False):
            text, status = self.extractor.extract_text_from_bytes(b"%PDF-1.4 test")
            self.assertIsNone(text)
            self.assertIn("PYPDF_NOT_INSTALLED", status)

    def test_fetch_and_extract_non_pdf_extension(self):
        text, status = self.extractor.fetch_and_extract("document.docx")
        self.assertIsNone(text)
        self.assertIn("NON_PDF_FILE", status)

    def test_extract_file_too_large_in_bytes(self):
        from unittest.mock import patch
        # Default limit is 2 MB (2 * 1024 * 1024 bytes)
        oversized = b"%PDF" + b"0" * (2 * 1024 * 1024 + 100)
        with patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.extract_text_from_bytes(oversized)
            self.assertIsNone(text)
            self.assertIn("FILE_TOO_LARGE", status)

    def test_fetch_and_extract_status_413_payload_too_large(self):
        from unittest.mock import patch
        mock_get_binary = lambda url, **kwargs: (413, b"")
        with patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.fetch_and_extract(
                "huge_report.pdf", do_get_binary_fn=mock_get_binary
            )
            self.assertIsNone(text)
            self.assertIn("FILE_TOO_LARGE", status)

    def test_fetch_and_extract_status_408_timeout(self):
        from unittest.mock import patch
        mock_get_binary = lambda url, **kwargs: (408, b"")
        with patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.fetch_and_extract(
                "slow_report.pdf", do_get_binary_fn=mock_get_binary
            )
            self.assertIsNone(text)
            self.assertIn("DOWNLOAD_TIMEOUT", status)

    def test_fetch_and_extract_timeout_exception(self):
        import socket
        from unittest.mock import patch

        def mock_hanging_get(url, **kwargs):
            raise socket.timeout("Read timed out")

        with patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.fetch_and_extract(
                "timeout.pdf", do_get_binary_fn=mock_hanging_get
            )
            self.assertIsNone(text)
            self.assertIn("DOWNLOAD_TIMEOUT", status)

    def test_extract_multipage_bounded_to_2_pages(self):
        from unittest.mock import MagicMock, patch

        mock_page_1 = MagicMock()
        mock_page_1.extract_text.return_value = "Page 1: Order Win of Rs 500 Cr."
        mock_page_2 = MagicMock()
        mock_page_2.extract_text.return_value = "Page 2: Executive Signatures and Execution Timeline."
        mock_page_3 = MagicMock()
        mock_page_3.extract_text.return_value = "Page 3: Boilerplate Legal Disclaimers."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page_1, mock_page_2, mock_page_3]

        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader

        with patch.dict("sys.modules", {"pypdf": mock_pypdf}), \
             patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.extract_text_from_bytes(b"%PDF-1.4 valid dummy data")
            self.assertEqual(status, "SUCCESS")
            self.assertIn("Page 1: Order Win of Rs 500 Cr.", text)
            self.assertIn("Page 2: Executive Signatures and Execution Timeline.", text)
            self.assertNotIn("Page 3: Boilerplate Legal Disclaimers.", text)
            self.assertFalse(mock_page_3.extract_text.called)

    def test_extract_scanned_image_pdf(self):
        from unittest.mock import MagicMock, patch

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""  # No selectable text

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader

        with patch.dict("sys.modules", {"pypdf": mock_pypdf}), \
             patch("news_based_strategy.ingestion.extractor.is_pypdf_available", return_value=True):
            text, status = self.extractor.extract_text_from_bytes(b"%PDF-1.4 valid dummy data")
            self.assertIsNone(text)
            self.assertIn("SCANNED_IMAGE_PDF", status)


if __name__ == "__main__":
    unittest.main()

