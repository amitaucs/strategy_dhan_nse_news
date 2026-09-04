"""In-memory PDF attachment downloader and text extractor for exchange disclosures."""

import io
import logging
import re
import socket
from typing import Optional, Tuple
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

NSE_ARCHIVES_BASE_URL = "https://nsearchives.nseindia.com/corporate"
DEFAULT_TIMEOUT: float = 3.0
DEFAULT_MAX_BYTES: int = 2 * 1024 * 1024  # 2 MB limit
DEFAULT_MAX_PAGES: int = 2
DEFAULT_MAX_CHARS: int = 2500


def is_pypdf_available() -> bool:
    """Check if pypdf library is installed and importable."""
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False


class PDFExtractor:
    """Downloads and extracts plain text from NSE corporate announcement PDF attachments."""

    def __init__(
        self,
        base_url: str = NSE_ARCHIVES_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_chars: int = DEFAULT_MAX_CHARS,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_pages = max_pages
        self.max_chars = max_chars

    def extract_text_from_bytes(
        self,
        pdf_bytes: bytes,
        max_pages: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> Tuple[Optional[str], str]:
        """Extract and clean text from raw PDF bytes using pypdf.
        
        Returns:
            Tuple of (extracted_text, status_message)
        """
        if not is_pypdf_available():
            return None, "PYPDF_NOT_INSTALLED (run: pip install pypdf)"

        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            return None, "INVALID_PDF_DATA"

        effective_max_pages = max_pages if max_pages is not None else self.max_pages
        effective_max_chars = max_chars if max_chars is not None else self.max_chars

        if len(pdf_bytes) > self.max_bytes:
            size_mb = len(pdf_bytes) / (1024 * 1024)
            limit_mb = self.max_bytes / (1024 * 1024)
            return None, f"FILE_TOO_LARGE ({size_mb:.1f} MB > {limit_mb:.1f} MB)"

        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            total_pages = len(reader.pages)
            pages_to_read = min(total_pages, effective_max_pages)

            extracted_chunks = []
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    extracted_chunks.append(page_text)

            raw_text = "\n".join(extracted_chunks).strip()
            if not raw_text:
                return None, "SCANNED_IMAGE_PDF (no selectable text)"

            cleaned = self.clean_text(raw_text, max_chars=effective_max_chars)
            return cleaned, "SUCCESS"
        except Exception as e:
            logger.warning("Error parsing PDF bytes: %s", e)
            return None, f"PARSE_ERROR: {e}"

    def fetch_and_extract(
        self,
        attmnt_file: str,
        do_get_binary_fn=None,
        max_pages: Optional[int] = None,
        max_chars: Optional[int] = None,
        max_bytes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[Optional[str], str]:
        """Download attachment from NSE archives and extract text in-memory.
        
        Returns:
            Tuple of (extracted_text, status_message)
        """
        if not attmnt_file:
            return None, "NO_ATTACHMENT"

        clean_filename = attmnt_file.strip()
        if clean_filename in ("-", "--", "NA", "N/A", "null", "none", ""):
            return None, "NO_ATTACHMENT"

        if not clean_filename.lower().endswith(".pdf"):
            return None, f"NON_PDF_FILE ({clean_filename})"

        if not is_pypdf_available():
            return None, "PYPDF_NOT_INSTALLED (run: pip install pypdf)"

        effective_timeout = timeout if timeout is not None else self.timeout
        effective_max_bytes = max_bytes if max_bytes is not None else self.max_bytes
        effective_max_pages = max_pages if max_pages is not None else self.max_pages
        effective_max_chars = max_chars if max_chars is not None else self.max_chars

        if clean_filename.startswith("http://") or clean_filename.startswith("https://"):
            url = clean_filename
        else:
            url = f"{self.base_url}/{clean_filename}"

        try:
            pdf_bytes = None
            if do_get_binary_fn:
                try:
                    status_code, pdf_bytes = do_get_binary_fn(
                        url, max_bytes=effective_max_bytes, timeout=effective_timeout
                    )
                except TypeError:
                    status_code, pdf_bytes = do_get_binary_fn(url)

                if status_code == 413:
                    limit_mb = effective_max_bytes / (1024 * 1024)
                    return None, f"FILE_TOO_LARGE (> {limit_mb:.1f} MB)"
                elif status_code == 408:
                    return None, f"DOWNLOAD_TIMEOUT (>{effective_timeout:.1f}s)"
                elif status_code != 200:
                    return None, f"DOWNLOAD_FAILED (HTTP {status_code})"
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                    cl = resp.headers.get("Content-Length")
                    if cl:
                        try:
                            cl_int = int(cl)
                            if cl_int > effective_max_bytes:
                                return (
                                    None,
                                    f"FILE_TOO_LARGE ({cl_int / (1024 * 1024):.1f} MB > {effective_max_bytes / (1024 * 1024):.1f} MB)",
                                )
                        except (ValueError, TypeError):
                            pass

                    if resp.status != 200:
                        return None, f"DOWNLOAD_FAILED (HTTP {resp.status})"

                    chunks = []
                    total_read = 0
                    chunk_size = 64 * 1024
                    while total_read <= effective_max_bytes:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total_read += len(chunk)

                    if total_read > effective_max_bytes:
                        limit_mb = effective_max_bytes / (1024 * 1024)
                        return None, f"FILE_TOO_LARGE (> {limit_mb:.1f} MB)"

                    pdf_bytes = b"".join(chunks)

            if pdf_bytes:
                if len(pdf_bytes) > effective_max_bytes:
                    size_mb = len(pdf_bytes) / (1024 * 1024)
                    limit_mb = effective_max_bytes / (1024 * 1024)
                    return None, f"FILE_TOO_LARGE ({size_mb:.1f} MB > {limit_mb:.1f} MB)"

                return self.extract_text_from_bytes(
                    pdf_bytes,
                    max_pages=effective_max_pages,
                    max_chars=effective_max_chars,
                )
        except (TimeoutError, socket.timeout):
            logger.debug("Download timeout (>%.1fs) fetching PDF from %s", effective_timeout, url)
            return None, f"DOWNLOAD_TIMEOUT (>{effective_timeout:.1f}s)"
        except Exception as e:
            if isinstance(e, urllib.error.URLError) and isinstance(e.reason, (socket.timeout, TimeoutError)):
                return None, f"DOWNLOAD_TIMEOUT (>{effective_timeout:.1f}s)"
            logger.debug("Failed to fetch/extract PDF from %s: %s", url, e)
            return None, f"FETCH_ERROR: {e}"

        return None, "EMPTY_PAYLOAD"

    @staticmethod
    def clean_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
        """Normalize whitespace, remove excess lines, and cap length."""
        if not text:
            return ""
        cleaned = re.sub(r"[ \t]+", " ", text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = cleaned.strip()

        if len(cleaned) > max_chars:
            return cleaned[:max_chars] + "... [TRUNCATED]"
        return cleaned


__all__ = [
    "PDFExtractor",
    "is_pypdf_available",
    "NSE_ARCHIVES_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_MAX_CHARS",
]
