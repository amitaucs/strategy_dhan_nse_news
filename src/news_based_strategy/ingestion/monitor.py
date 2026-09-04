"""NSE Corporate Announcements feed monitor with cookie priming, F&O filtering, noise rejection, and PDF extraction."""

import json
import logging
from typing import Callable, Dict, List, Optional, Set
from news_based_strategy.config import DEFAULT_HEADERS
from news_based_strategy.core.models import Announcement
from news_based_strategy.ingestion.extractor import PDFExtractor
from news_based_strategy.ingestion.filter import NoiseFilter
from news_based_strategy.ingestion.universe import is_fno_stock

logger = logging.getLogger(__name__)


class NSEFilingMonitor:
    """Monitors NSE corporate announcements endpoint for equity filings."""

    def __init__(
        self,
        base_url: str = "https://www.nseindia.com",
        api_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
        auto_refresh: bool = True,
        pdf_extractor: Optional[PDFExtractor] = None,
        storage=None,
    ):
        self.base_url = base_url
        self.api_url = api_url or f"{base_url}/api/corporate-announcements?index=equities"
        self.headers = dict(headers or DEFAULT_HEADERS)
        self.timeout = timeout
        self.auto_refresh = auto_refresh
        self.storage = storage
        self.seen_seq_ids: Set[str] = set()

        if self.storage:
            try:
                preloaded = self.storage.get_processed_seq_ids()
                if preloaded:
                    self.seen_seq_ids.update(preloaded)
                    logger.info("Warmed up %d processed seq_ids from persistent storage.", len(preloaded))
            except Exception as e:
                logger.warning("Failed to warm up seen_seq_ids from storage: %s", e)

        self.pdf_extractor = pdf_extractor or PDFExtractor(timeout=3.0)

        self._session = None
        self._opener = None
        self._use_requests = False
        self._init_client()

    def _init_client(self) -> None:
        """Initialize HTTP client using requests if available, else urllib with CookieJar."""
        try:
            import requests

            self._session = requests.Session()
            self._use_requests = True
            logger.debug("NSEFilingMonitor using 'requests' library.")
        except ImportError:
            import http.cookiejar
            import urllib.request

            self._cookie_jar = http.cookiejar.CookieJar()
            self._opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self._cookie_jar)
            )
            self._use_requests = False
            logger.debug("NSEFilingMonitor using standard library 'urllib'.")

        if self.auto_refresh:
            self.refresh_session()

    def refresh_session(self) -> bool:
        """Seed required Akamai/NSE session cookies by hitting the homepage."""
        try:
            if self._use_requests and self._session:
                self._session.cookies.clear()
                resp = self._session.get(self.base_url, headers=self.headers, timeout=self.timeout)
                return resp.status_code == 200
            elif self._opener:
                import urllib.request

                req = urllib.request.Request(self.base_url, headers=self.headers)
                with self._opener.open(req, timeout=self.timeout) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning("NSE session refresh failed: %s", e)
            return False
        return False

    def _do_get(self, url: str) -> tuple[int, str]:
        """Perform a GET request and return (status_code, body_string)."""
        if self._use_requests and self._session:
            resp = self._session.get(url, headers=self.headers, timeout=self.timeout)
            return resp.status_code, resp.text
        elif self._opener:
            import urllib.error
            import urllib.request

            req = urllib.request.Request(url, headers=self.headers)
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return resp.status, body
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                return e.code, body
        return 0, ""

    def _do_get_binary(
        self,
        url: str,
        max_bytes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> tuple[int, bytes]:
        """Perform a GET request for binary content with optional bounded streaming and timeout."""
        effective_timeout = timeout if timeout is not None else self.timeout

        if self._use_requests and self._session:
            try:
                with self._session.get(
                    url, headers=self.headers, timeout=effective_timeout, stream=True
                ) as resp:
                    if resp.status_code != 200:
                        return resp.status_code, b""

                    cl = resp.headers.get("Content-Length")
                    if cl and max_bytes:
                        try:
                            if int(cl) > max_bytes:
                                return 413, b""
                        except (ValueError, TypeError):
                            pass

                    chunks = []
                    total_read = 0
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total_read += len(chunk)
                        if max_bytes and total_read > max_bytes:
                            return 413, b""
                    return resp.status_code, b"".join(chunks)
            except Exception as e:
                import socket
                try:
                    import requests
                    timeout_types = (requests.exceptions.Timeout, TimeoutError, socket.timeout)
                except ImportError:
                    timeout_types = (TimeoutError, socket.timeout)
                if isinstance(e, timeout_types):
                    return 408, b""
                logger.debug("Binary GET error (requests): %s", e)
                return 0, b""

        elif self._opener:
            import socket
            import urllib.error
            import urllib.request

            req = urllib.request.Request(url, headers=self.headers)
            try:
                with self._opener.open(req, timeout=effective_timeout) as resp:
                    if resp.status != 200:
                        return resp.status, b""

                    cl = resp.headers.get("Content-Length")
                    if cl and max_bytes:
                        try:
                            if int(cl) > max_bytes:
                                return 413, b""
                        except (ValueError, TypeError):
                            pass

                    chunks = []
                    total_read = 0
                    chunk_size = 64 * 1024
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total_read += len(chunk)
                        if max_bytes and total_read > max_bytes:
                            return 413, b""
                    return resp.status, b"".join(chunks)
            except (TimeoutError, socket.timeout):
                return 408, b""
            except urllib.error.HTTPError as e:
                body = e.read() if e.fp else b""
                return e.code, body
            except urllib.error.URLError as e:
                if isinstance(e.reason, (socket.timeout, TimeoutError)):
                    return 408, b""
                return 0, b""

        return 0, b""

    def fetch_latest(self) -> List[Announcement]:
        """Fetch latest announcements from NSE and parse into Announcement models."""
        try:
            status_code, body = self._do_get(self.api_url)

            # If unauthorized or forbidden, session cookies likely expired; refresh and retry once
            if status_code in (401, 403):
                logger.info("NSE session returned %s. Refreshing cookies and retrying...", status_code)
                self.refresh_session()
                status_code, body = self._do_get(self.api_url)

            if status_code == 200 and body:
                raw_data = json.loads(body)
                items = raw_data if isinstance(raw_data, list) else raw_data.get("data", [])
                announcements = []

                for item in items:
                    seq_id = str(
                        item.get("seq_id")
                        or item.get("an_dt")
                        or item.get("attmntFile")
                        or ""
                    ).strip()
                    symbol = (item.get("symbol") or "").strip().upper()
                    desc = (item.get("desc") or item.get("subject") or item.get("an_subject") or "").strip()

                    # 1. Resolve details: Prioritize actual disclosure text over company name
                    details = (
                        item.get("attchmntText")
                        or item.get("attmntText")
                        or item.get("details")
                        or item.get("an_details")
                        or item.get("an_desc")
                        or item.get("more_details")
                        or item.get("sm_name")
                        or ""
                    ).strip()

                    an_dt = item.get("an_dt", "") or ""

                    # 2. Resolve attachment: Check all keys dynamically
                    attmnt_file = None
                    for k, v in item.items():
                        if v and isinstance(v, str):
                            v_str = v.strip()
                            if ".pdf" in v_str.lower() or "nsearchives" in v_str.lower():
                                attmnt_file = v_str
                                break

                    if not attmnt_file:
                        for candidate_key in (
                            "attchmntFile", "attmntFile", "attachment", "attmnt_link",
                            "attachment_file", "file", "fileName", "an_attachment", "an_file"
                        ):
                            val = item.get(candidate_key)
                            if val and isinstance(val, str):
                                clean_val = val.strip()
                                if clean_val and clean_val not in ("-", "--", "NA", "N/A", "null", "none"):
                                    attmnt_file = clean_val
                                    break


                    if seq_id and symbol:
                        announcements.append(
                            Announcement(
                                seq_id=seq_id,
                                symbol=symbol,
                                desc=desc,
                                details=details,
                                an_dt=an_dt,
                                attmnt_file=attmnt_file,
                                is_fno=is_fno_stock(symbol),
                                raw_data=item,
                            )
                        )
                return announcements
            else:
                logger.warning("NSE announcements API returned HTTP %s", status_code)
        except Exception as e:
            logger.error("Error fetching announcements from NSE: %s", e)

        return []

    def get_new_announcements(
        self,
        symbol_filter: Optional[str] = None,
        fno_only: bool = True,
        filter_noise: bool = True,
        extract_pdf: bool = True,
        initial_mark_all_seen: bool = False,
        on_noise_filtered: Optional[Callable[[Announcement, str], None]] = None,
        on_filtered: Optional[Callable[[Announcement, str], None]] = None,
    ) -> List[Announcement]:
        """Fetch announcements and filter by F&O universe, noise rules, and deduplication."""
        all_announcements = self.fetch_latest()
        new_items: List[Announcement] = []
        is_first_run = len(self.seen_seq_ids) == 0

        for item in all_announcements:
            # Deduplication: only process filings not seen before
            if item.seq_id in self.seen_seq_ids:
                continue

            self.seen_seq_ids.add(item.seq_id)
            if self.storage:
                self.storage.mark_processed(item.seq_id, item.symbol, item.an_dt or "")

            if is_first_run and initial_mark_all_seen:
                continue

            if symbol_filter and item.symbol != symbol_filter.upper():
                if on_filtered:
                    on_filtered(item, f"Symbol filter (expected {symbol_filter.upper()})")
                continue

            if fno_only and not item.is_fno:
                if on_filtered:
                    on_filtered(item, "Not in F&O universe")
                continue

            # Check noise filtering
            noise_reason = NoiseFilter.explain_noise(item.desc, item.details)
            if filter_noise and noise_reason:
                if on_filtered:
                    on_filtered(item, noise_reason)
                elif on_noise_filtered:
                    on_noise_filtered(item, noise_reason)
                continue

            if extract_pdf and item.attmnt_file:
                extracted, status = self.pdf_extractor.fetch_and_extract(
                    item.attmnt_file,
                    do_get_binary_fn=self._do_get_binary,
                )
                if extracted:
                    item.extracted_text = extracted
                elif status != "SUCCESS":
                    item.extraction_error = status

            new_items.append(item)

        return new_items


__all__ = ["NSEFilingMonitor"]


