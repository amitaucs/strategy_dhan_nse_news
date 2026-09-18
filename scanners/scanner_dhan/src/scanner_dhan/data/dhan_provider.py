"""DhanHQ Historical and Real-time Market Data Provider with Rate Limiting and Explicit Error Handling."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
from dhanhq import DhanContext, dhanhq

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

__all__ = [
    "DhanDataProvider",
    "MarketQuoteTick",
    "DhanDataAPIError",
    "DhanDataAPISubscriptionError",
    "DhanAuthError",
    "DhanRateLimitError",
    "load_dhan_credentials",
]


@dataclass
class MarketQuoteTick:
    """Represents a structured market quote snapshot with provenance and timestamps."""
    security_id: str
    last_price: float
    last_trade_time: Optional[datetime] = None
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    volume: int = 0
    oi: int = 0
    exchange_segment: str = "NSE_EQ"
    is_real_time: bool = True


class DhanDataAPIError(Exception):
    """Base exception for DhanHQ data provider failures."""

    def __init__(self, message: str, error_code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details


class DhanDataAPISubscriptionError(DhanDataAPIError):
    """Raised when Dhan account has not subscribed to Historical Data APIs (DH-902 / HTTP 451)."""

    def __init__(
        self,
        message: str = (
            "Your Dhan account has not subscribed to the Historical Data API (DH-902 / HTTP 451). "
            "Please enable the Data API Plan in your Dhan portal at web.dhan.co -> DhanHQ -> API Plans."
        ),
        error_code: str = "DH-902",
        details: Any = None,
    ) -> None:
        super().__init__(message, error_code=error_code, details=details)


class DhanAuthError(DhanDataAPIError):
    """Raised when Dhan Client ID or Access Token is missing, invalid, or expired (DH-901 / 401)."""

    def __init__(
        self,
        message: str = (
            "Dhan Access Token is invalid or expired (DH-901 / 401). "
            "Please generate a fresh Access Token at web.dhan.co and update your configuration."
        ),
        error_code: str = "DH-901",
        details: Any = None,
    ) -> None:
        super().__init__(message, error_code=error_code, details=details)


class DhanRateLimitError(DhanDataAPIError):
    """Raised when Dhan rate limit is persistently breached (DH-904)."""

    def __init__(
        self,
        message: str = "Dhan API rate limit reached (DH-904). Please retry in a few moments.",
        error_code: str = "DH-904",
        details: Any = None,
    ) -> None:
        super().__init__(message, error_code=error_code, details=details)


def load_dhan_credentials(env_path: str = ".env") -> tuple[str, str]:
    """Load Dhan Client ID and Access Token from environment or .env file."""
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_path)
    except ImportError:
        pass

    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()

    if not client_id or client_id == "YOUR_CLIENT_ID_HERE":
        raise DhanAuthError("DHAN_CLIENT_ID is missing or not configured in .env or environment")
    if not access_token or access_token == "YOUR_ACCESS_TOKEN_HERE":
        raise DhanAuthError("DHAN_ACCESS_TOKEN is missing or not configured in .env or environment")

    return client_id, access_token


class DhanDataProvider:
    """Historical and snapshot market data provider using DhanHQ Data APIs with rate-limit protection."""

    _quote_lock = threading.Lock()
    _last_quote_time = 0.0
    _historical_lock = threading.Lock()
    _last_historical_time = 0.0
    _rest_lock = threading.Lock()
    _last_rest_time = 0.0

    _data_api_health_cache: tuple[float, dict[str, Any]] | None = None
    quote_delay: float = 1.0       # Dhan REST quote API strict limit: 1 request/sec
    historical_delay: float = 0.20 # Dhan historical data API limit: ~5 requests/sec
    rest_delay: float = 0.50       # Dhan general REST API: ~2 requests/sec
    max_retries: int = 4

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
        quote_delay: float = 1.0,
        historical_delay: float = 0.20,
        max_retries: int = 4,
    ) -> None:
        if not client_id or not access_token:
            try:
                cid, token = load_dhan_credentials()
                client_id = client_id or cid
                access_token = access_token or token
            except Exception:
                pass

        self.client_id = client_id or ""
        self.access_token = access_token or ""
        self.quote_delay = max(1.0, quote_delay)
        self.historical_delay = max(0.15, historical_delay)
        self.max_retries = max_retries

        if self.client_id and self.access_token:
            self.context = DhanContext(self.client_id, self.access_token)
            self.dhan = dhanhq(self.context)
        else:
            self.context = None
            self.dhan = None

    def _pace_quote_request(self) -> None:
        """Enforce strict 1 req/sec pacing for Dhan marketfeed snapshot/quote APIs."""
        with DhanDataProvider._quote_lock:
            now = time.monotonic()
            elapsed = now - DhanDataProvider._last_quote_time
            if elapsed < self.quote_delay:
                time.sleep(self.quote_delay - elapsed)
            DhanDataProvider._last_quote_time = time.monotonic()

    def _pace_historical_request(self) -> None:
        """Enforce thread-safe pacing for Dhan historical daily/minute data APIs."""
        with DhanDataProvider._historical_lock:
            now = time.monotonic()
            elapsed = now - DhanDataProvider._last_historical_time
            if elapsed < self.historical_delay:
                time.sleep(self.historical_delay - elapsed)
            DhanDataProvider._last_historical_time = time.monotonic()

    def _pace_rest_request(self) -> None:
        """Enforce thread-safe pacing for general Dhan REST APIs (option chain, expiry, funds)."""
        with DhanDataProvider._rest_lock:
            now = time.monotonic()
            elapsed = now - DhanDataProvider._last_rest_time
            if elapsed < self.rest_delay:
                time.sleep(self.rest_delay - elapsed)
            DhanDataProvider._last_rest_time = time.monotonic()

    def _pace_request(self) -> None:
        """Backwards-compatible alias for historical/general request pacing."""
        self._pace_historical_request()

    @staticmethod
    def _is_rate_limit_response(response: Any) -> bool:
        """Check if a response from DhanHQ indicates a rate limit breach (DH-904)."""
        if not isinstance(response, dict):
            resp_str = str(response).lower()
            return "rate_limit" in resp_str or "dh-904" in resp_str or "too many requests" in resp_str

        if response.get("error_code") == "DH-904" or response.get("error_type") == "Rate_Limit":
            return True

        remarks = response.get("remarks")
        if isinstance(remarks, dict):
            if remarks.get("error_code") == "DH-904" or remarks.get("error_type") == "Rate_Limit":
                return True
        elif isinstance(remarks, str):
            r_lower = remarks.lower()
            if "rate_limit" in r_lower or "dh-904" in r_lower or "too many requests" in r_lower:
                return True

        err_msg = str(response.get("error_message", "")).lower()
        if "rate limit" in err_msg or "too many requests" in err_msg or "throttling" in err_msg:
            return True

        return False

    @staticmethod
    def _is_data_api_unsubscribed(response: Any) -> bool:
        """Check if response indicates Dhan account has not subscribed to Data APIs (DH-902 / 451)."""
        if not isinstance(response, dict):
            resp_str = str(response).lower()
            return "dh-902" in resp_str or "data api" in resp_str or "451" in resp_str

        if response.get("error_code") in ("DH-902", "806") or response.get("error_type") in ("Invalid_Access", "Data_API_Invalid"):
            return True

        err_msg = str(response.get("error_message", "")).lower()
        if "data api" in err_msg or "http status 451" in err_msg or "dh-902" in err_msg or "not subscribed" in err_msg:
            return True

        remarks = response.get("remarks", {})
        if isinstance(remarks, dict):
            if remarks.get("error_code") in ("DH-902", "806") or remarks.get("error_type") in ("Invalid_Access", "Data_API_Invalid"):
                return True
        elif isinstance(remarks, str):
            r_lower = remarks.lower()
            if "data api" in r_lower or "http status 451" in r_lower or "dh-902" in r_lower or "not subscribed" in r_lower:
                return True

        return False

    @staticmethod
    def _is_auth_error(response: Any) -> bool:
        """Check if response indicates invalid or expired access token (DH-901 / 401)."""
        if not isinstance(response, dict):
            resp_str = str(response).lower()
            return "dh-901" in resp_str or "token expired" in resp_str or "invalid token" in resp_str or "401" in resp_str

        if response.get("error_code") in ("DH-901", "805", "401") or response.get("error_type") in ("Token_Expired", "Authentication_Error", "Invalid_Token"):
            return True

        err_msg = str(response.get("error_message", "")).lower()
        if "token expired" in err_msg or "invalid token" in err_msg or "unauthorized" in err_msg or "dh-901" in err_msg:
            return True

        remarks = response.get("remarks", {})
        if isinstance(remarks, dict):
            if remarks.get("error_code") in ("DH-901", "805", "401"):
                return True
        elif isinstance(remarks, str):
            r_lower = remarks.lower()
            if "token expired" in r_lower or "invalid token" in r_lower or "dh-901" in r_lower:
                return True

        return False

    def check_data_api_health(self, force_refresh: bool = False) -> dict[str, Any]:
        """Test Dhan Data API availability with a lightweight sample probe (cached for 60s)."""
        now = time.time()
        if not force_refresh and DhanDataProvider._data_api_health_cache is not None:
            cached_ts, cached_res = DhanDataProvider._data_api_health_cache
            if now - cached_ts < 60.0:
                return dict(cached_res)

        if not self.client_id or not self.access_token or self.dhan is None:
            result = {
                "active": False,
                "status": "missing_credentials",
                "error_code": "NO_CREDS",
                "message": "Dhan Client ID or Access Token is missing.",
            }
            DhanDataProvider._data_api_health_cache = (now, result)
            return result

        try:
            # Probe using Reliance (SecID 2885)
            to_date = date.today()
            from_date = to_date - timedelta(days=5)
            resp = self.dhan.historical_daily_data(
                security_id="2885",
                exchange_segment=dhanhq.NSE,
                instrument_type="EQUITY",
                from_date=from_date.strftime("%Y-%m-%d"),
                to_date=to_date.strftime("%Y-%m-%d"),
                expiry_code=0,
                oi=False,
            )

            if self._is_data_api_unsubscribed(resp):
                result = {
                    "active": False,
                    "status": "unsubscribed",
                    "error_code": "DH-902",
                    "message": "Dhan Data API plan is not active on this account (DH-902 / 451).",
                }
            elif self._is_auth_error(resp):
                result = {
                    "active": False,
                    "status": "token_expired",
                    "error_code": "DH-901",
                    "message": "Dhan Access Token is expired or invalid (DH-901).",
                }
            elif isinstance(resp, dict) and resp.get("status") == "success":
                result = {
                    "active": True,
                    "status": "active",
                    "error_code": None,
                    "message": "Dhan Data API is active and functioning.",
                }
            else:
                err_msg = resp.get("error_message") if isinstance(resp, dict) else str(resp)
                result = {
                    "active": False,
                    "status": "error",
                    "error_code": "UNKNOWN",
                    "message": f"Dhan API returned: {err_msg}",
                }
        except Exception as exc:
            result = {
                "active": False,
                "status": "error",
                "error_code": "EXCEPTION",
                "message": f"Connection check error: {exc}",
            }

        DhanDataProvider._data_api_health_cache = (now, result)
        return result

    def fetch_daily_bars(
        self,
        security_id: str,
        days: int = 150,
        exchange_segment: str = dhanhq.NSE,
        instrument_type: str = "EQUITY",
    ) -> pd.DataFrame:
        """Fetch historical daily OHLCV bars directly from DhanHQ with rate-limit and subscription error checks."""
        if self.dhan is None:
            raise DhanAuthError("Dhan client is not configured. Please provide DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.")

        to_date = date.today()
        from_date = to_date - timedelta(days=days)
        from_str = from_date.strftime("%Y-%m-%d")
        to_str = to_date.strftime("%Y-%m-%d")

        for attempt in range(1, self.max_retries + 1):
            self._pace_historical_request()
            try:
                response = self.dhan.historical_daily_data(
                    security_id=str(security_id),
                    exchange_segment=exchange_segment,
                    instrument_type=instrument_type,
                    from_date=from_str,
                    to_date=to_str,
                    expiry_code=0,
                    oi=False,
                )
            except Exception as exc:
                if attempt < self.max_retries:
                    backoff = (1.5**attempt) + random.uniform(0.2, 0.5)
                    time.sleep(backoff)
                    continue
                logger.error("Dhan daily fetch failed for %s: %s", security_id, exc)
                raise DhanDataAPIError(f"Dhan historical_daily_data connection error for {security_id}: {exc}") from exc

            # 1. Check for Unsubscribed Data Plan (DH-902)
            if self._is_data_api_unsubscribed(response):
                err_msg = (
                    "Dhan Data API (Historical Candle Data) is not active or subscribed on your account (DH-902 / HTTP 451). "
                    "Please enable the Data API Plan at web.dhan.co -> DhanHQ -> API Plans."
                )
                logger.error("Dhan Data API not subscribed for security %s: %s", security_id, response)
                raise DhanDataAPISubscriptionError(err_msg, details=response)

            # 2. Check for Token Expired (DH-901 / 401)
            if self._is_auth_error(response):
                err_msg = (
                    "Dhan Access Token is invalid or expired (DH-901 / 401). "
                    "Please generate a fresh token at web.dhan.co and update your configuration."
                )
                logger.error("Dhan Auth error for security %s: %s", security_id, response)
                raise DhanAuthError(err_msg, details=response)

            # 3. Check for Rate Limit (DH-904)
            if self._is_rate_limit_response(response):
                if attempt < self.max_retries:
                    backoff = (1.8**attempt) * 0.8 + random.uniform(0.3, 0.7)
                    time.sleep(backoff)
                    continue
                else:
                    logger.error("Rate limit exceeded fetching daily bars for %s: %s", security_id, response)
                    raise DhanRateLimitError(f"Rate limit exceeded while fetching daily bars for {security_id}.")

            if not isinstance(response, dict) or response.get("status") != "success":
                logger.warning("Dhan historical_daily_data unsuccessful for %s: %s", security_id, response)
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

            data = response.get("data", {})
            if not data or "timestamp" not in data or len(data["timestamp"]) == 0:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

            df = pd.DataFrame(data)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(
                    "Asia/Kolkata"
                )

            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df.sort_values("timestamp").reset_index(drop=True)

        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def fetch_ltp_batch(
        self,
        security_ids: list[str],
        exchange_segment: str = "NSE_EQ",
    ) -> dict[str, float]:
        """Fetch latest price for multiple securities in a single ticker request with retries and error checks."""
        if not security_ids or self.dhan is None:
            return {}

        int_ids: list[int] = []
        for sid in security_ids:
            try:
                int_ids.append(int(sid))
            except ValueError:
                continue

        if not int_ids:
            return {}

        ltp_map: dict[str, float] = {}
        for attempt in range(1, self.max_retries + 1):
            self._pace_quote_request()
            try:
                response = self.dhan.ticker_data({exchange_segment: int_ids})
                if self._is_data_api_unsubscribed(response):
                    raise DhanDataAPISubscriptionError()
                if self._is_auth_error(response):
                    raise DhanAuthError()
                if self._is_rate_limit_response(response):
                    if attempt < self.max_retries:
                        time.sleep(1.0)
                        continue
                if (
                    isinstance(response, dict)
                    and response.get("status") == "success"
                    and "data" in response
                ):
                    seg_data = response["data"].get(exchange_segment, {})
                    for sid_str, tick_info in seg_data.items():
                        if isinstance(tick_info, dict) and "last_price" in tick_info:
                            ltp_map[sid_str] = float(tick_info["last_price"])
                    return ltp_map
            except (DhanDataAPISubscriptionError, DhanAuthError):
                raise
            except Exception as exc:
                if attempt < self.max_retries:
                    time.sleep(0.5)
                    continue
                logger.error("Error fetching LTP batch: %s", exc)
                break

        return ltp_map

    def fetch_quote_batch(
        self,
        security_ids: list[str],
        exchange_segment: str = "NSE_EQ",
    ) -> dict[str, MarketQuoteTick]:
        """Fetch full quote packet (LTP, exchange last_trade_time, volume, OI) from Dhan /marketfeed/quote."""
        if not security_ids or self.dhan is None:
            return {}

        int_ids: list[int] = []
        for sid in security_ids:
            try:
                int_ids.append(int(sid))
            except ValueError:
                continue

        if not int_ids:
            return {}

        quote_map: dict[str, MarketQuoteTick] = {}
        recv_time = datetime.now(timezone.utc)
        for attempt in range(1, self.max_retries + 1):
            self._pace_quote_request()
            try:
                if hasattr(self.dhan, "quote_data"):
                    response = self.dhan.quote_data({exchange_segment: int_ids})
                else:
                    response = self.dhan.ticker_data({exchange_segment: int_ids})

                if self._is_data_api_unsubscribed(response):
                    raise DhanDataAPISubscriptionError()
                if self._is_auth_error(response):
                    raise DhanAuthError()
                if self._is_rate_limit_response(response):
                    if attempt < self.max_retries:
                        time.sleep(1.0)
                        continue

                if isinstance(response, dict) and response.get("status") == "success" and "data" in response:
                    seg_data = response["data"].get(exchange_segment, {})
                    for sid_str, tick_info in seg_data.items():
                        if isinstance(tick_info, dict):
                            l_price = float(tick_info.get("last_price") or tick_info.get("lastPrice") or 0.0)
                            if l_price <= 0:
                                ohlc = tick_info.get("ohlc", {})
                                l_price = float(ohlc.get("close") or ohlc.get("last_price") or 0.0)

                            if l_price > 0:
                                ltt = None
                                ltt_raw = tick_info.get("last_trade_time") or tick_info.get("lastTradeTime")
                                if ltt_raw:
                                    try:
                                        if isinstance(ltt_raw, (int, float)):
                                            ltt = datetime.fromtimestamp(ltt_raw, tz=timezone.utc)
                                        elif isinstance(ltt_raw, str):
                                            ltt = datetime.fromisoformat(ltt_raw)
                                    except Exception:
                                        pass

                                quote_map[sid_str] = MarketQuoteTick(
                                    security_id=sid_str,
                                    last_price=l_price,
                                    last_trade_time=ltt,
                                    received_at=recv_time,
                                    volume=int(tick_info.get("volume", 0)),
                                    oi=int(tick_info.get("oi", 0)),
                                    exchange_segment=exchange_segment,
                                    is_real_time=True,
                                )
                    return quote_map
            except (DhanDataAPISubscriptionError, DhanAuthError):
                raise
            except Exception as exc:
                if attempt < self.max_retries:
                    time.sleep(0.5)
                    continue
                logger.error("Error fetching quote batch: %s", exc)
                break

        return quote_map

    def fetch_expiry_list(
        self,
        under_security_id: str | int,
        under_exchange_segment: str = "NSE_EQ",
    ) -> list[str]:
        """Fetch real-time active derivative expiry dates from DhanHQ API (/optionchain/expirylist)."""
        if self.dhan is None or not under_security_id:
            return []

        for attempt in range(1, self.max_retries + 1):
            self._pace_rest_request()
            try:
                sec_int = int(under_security_id)
                response = self.dhan.expiry_list(
                    under_security_id=sec_int,
                    under_exchange_segment=under_exchange_segment,
                )
                if isinstance(response, dict) and response.get("status") == "success":
                    data = response.get("data")
                    if isinstance(data, list):
                        return [str(d).strip() for d in data if d]
                    elif isinstance(data, dict):
                        for k in ("expiry_dates", "list", "expiries"):
                            if k in data and isinstance(data[k], list):
                                return [str(d).strip() for d in data[k] if d]
                elif self._is_rate_limit_response(response):
                    if attempt < self.max_retries:
                        time.sleep(1.0)
                        continue
            except Exception as exc:
                if attempt < self.max_retries:
                    time.sleep(1.0)
                    continue
                logger.debug("Dhan expiry_list error for %s: %s", under_security_id, exc)
                break
        return []

    def fetch_option_chain(
        self,
        under_security_id: str | int,
        expiry: str,
        under_exchange_segment: str = "NSE_EQ",
    ) -> dict[str, Any]:
        """Fetch real-time option chain for an underlying instrument and expiry date from DhanHQ."""
        if self.dhan is None or not under_security_id or not expiry:
            return {}

        for attempt in range(1, self.max_retries + 1):
            self._pace_rest_request()
            try:
                sec_int = int(under_security_id)
                response = self.dhan.option_chain(
                    under_security_id=sec_int,
                    under_exchange_segment=under_exchange_segment,
                    expiry=str(expiry).strip(),
                )
                if isinstance(response, dict) and response.get("status") == "success":
                    return response.get("data", {})
                elif self._is_rate_limit_response(response):
                    if attempt < self.max_retries:
                        time.sleep(1.0)
                        continue
            except Exception as exc:
                if attempt < self.max_retries:
                    time.sleep(1.0)
                    continue
                logger.debug("Dhan option_chain error for %s (expiry %s): %s", under_security_id, expiry, exc)
                break
        return {}

    def fetch_fund_limits(self) -> dict[str, Any]:
        """Fetch real-time available fund limits from Dhan account."""
        if self.dhan is None:
            return {"status": "failure", "remarks": "Dhan client not initialized"}

        for attempt in range(1, self.max_retries + 1):
            self._pace_rest_request()
            try:
                if hasattr(self.dhan, "get_fund_limits"):
                    response = self.dhan.get_fund_limits()
                    if isinstance(response, dict):
                        return response
                    return {"status": "failure", "remarks": str(response)}
            except Exception as exc:
                if attempt < self.max_retries:
                    time.sleep(0.5)
                    continue
                logger.error("Dhan get_fund_limits error: %s", exc)
                return {"status": "failure", "remarks": str(exc)}
        return {"status": "failure", "remarks": "Failed to retrieve fund limits"}

    def fetch_intraday_minute_bars(
        self,
        security_id: str,
        days: int = 25,
        exchange_segment: str = "NSE_EQ",
        instrument_type: str = "EQUITY",
    ) -> pd.DataFrame:
        """Fetch raw 1-minute historical intraday bars directly from DhanHQ with error checks."""
        if self.dhan is None:
            raise DhanAuthError("Dhan client is not configured. Please provide DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.")

        safe_days = min(max(1, days), 30)
        to_date = date.today()
        from_date = to_date - timedelta(days=safe_days)
        from_str = from_date.strftime("%Y-%m-%d")
        to_str = to_date.strftime("%Y-%m-%d")

        for attempt in range(1, self.max_retries + 1):
            self._pace_historical_request()
            try:
                response = self.dhan.intraday_minute_data(
                    security_id=str(security_id),
                    exchange_segment=exchange_segment,
                    instrument_type=instrument_type,
                    from_date=from_str,
                    to_date=to_str,
                )
            except Exception as exc:
                if attempt < self.max_retries:
                    time.sleep(1.0)
                    continue
                logger.error("Dhan intraday minute fetch failed for %s: %s", security_id, exc)
                raise DhanDataAPIError(f"Dhan intraday_minute_data connection error for {security_id}: {exc}") from exc

            # 1. Check for Unsubscribed Data Plan (DH-902)
            if self._is_data_api_unsubscribed(response):
                err_msg = (
                    "Dhan Data API (Intraday Minute Data) is not active or subscribed on your account (DH-902 / HTTP 451). "
                    "Please enable the Data API Plan at web.dhan.co -> DhanHQ -> API Plans."
                )
                logger.error("Dhan Data API not subscribed for security %s: %s", security_id, response)
                raise DhanDataAPISubscriptionError(err_msg, details=response)

            # 2. Check for Token Expired (DH-901 / 401)
            if self._is_auth_error(response):
                err_msg = (
                    "Dhan Access Token is invalid or expired (DH-901 / 401). "
                    "Please generate a fresh token at web.dhan.co and update your configuration."
                )
                logger.error("Dhan Auth error for security %s: %s", security_id, response)
                raise DhanAuthError(err_msg, details=response)

            # 3. Check for Rate Limit (DH-904)
            if self._is_rate_limit_response(response):
                if attempt < self.max_retries:
                    time.sleep(1.0)
                    continue
                else:
                    logger.error("Rate limit exceeded fetching intraday bars for %s", security_id)
                    raise DhanRateLimitError(f"Rate limit exceeded while fetching intraday bars for {security_id}.")

            if not isinstance(response, dict) or response.get("status") != "success":
                logger.warning("Dhan intraday_minute_data unsuccessful for %s: %s", security_id, response)
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

            data = response.get("data", {})
            if not data or "timestamp" not in data or len(data["timestamp"]) == 0:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

            df = pd.DataFrame(data)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(
                    "Asia/Kolkata"
                )

            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df.sort_values("timestamp").reset_index(drop=True)

        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def fetch_1h_bars(
        self,
        security_id: str,
        days: int = 25,
        exclude_incomplete: bool = False,
    ) -> pd.DataFrame:
        """Fetch 1-minute bars from Dhan and resample into 1-Hour (60-minute) OHLCV candles aligned to 09:15 IST."""
        return self.fetch_resampled_bars(security_id=security_id, rule="60min", days=min(days, 30), exclude_incomplete=exclude_incomplete)

    def fetch_2h_bars(
        self,
        security_id: str,
        days: int = 25,
        exclude_incomplete: bool = False,
    ) -> pd.DataFrame:
        """Fetch 1-minute bars from Dhan and resample into 2-Hour OHLCV candles aligned to 09:15 IST."""
        return self.fetch_resampled_bars(security_id=security_id, rule="120min", days=min(days, 30), exclude_incomplete=exclude_incomplete)

    def fetch_resampled_bars(
        self,
        security_id: str,
        rule: str = "15min",
        days: int = 25,
        exclude_incomplete: bool = False,
    ) -> pd.DataFrame:
        """Fetch 1-minute bars from Dhan and resample into custom OHLCV candles aligned to 09:15 IST.
        
        Session: 09:15 to 15:30 IST.
        When exclude_incomplete is True:
          Drops candles with partial minutes (e.g. 15:15 1H bar which only has 15 minutes, or in-progress bars).
        """
        safe_days = min(days, 30)
        m_df = self.fetch_intraday_minute_bars(security_id=security_id, days=safe_days)
        if m_df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        m_df = m_df.set_index("timestamp")
        resampled = (
            m_df.resample(rule, origin="start_day", offset="9h15min")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
            .reset_index()
        )
        if exclude_incomplete and not resampled.empty:
            counts = m_df.resample(rule, origin="start_day", offset="9h15min")["close"].count().reset_index()
            counts.columns = ["timestamp", "bar_count"]
            resampled = pd.merge(resampled, counts, on="timestamp")
            expected_minutes = 60 if rule in ("60min", "1H", "1h") else (120 if rule in ("120min", "2H", "2h") else 15)
            resampled = resampled[resampled["bar_count"] >= expected_minutes].drop(columns=["bar_count"])

        return resampled

    def fetch_monthly_bars(
        self,
        security_id: str,
        days: int = 4500,
    ) -> pd.DataFrame:
        """Fetch daily historical bars from Dhan and resample to Monthly OHLCV candles."""
        daily_df = self.fetch_daily_bars(security_id=security_id, days=days)
        if daily_df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = daily_df.copy()
        if "timestamp" not in df.columns:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = df.set_index("timestamp")
        monthly = (
            df.resample("MS")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        return monthly

    def fetch_weekly_bars(
        self,
        security_id: str,
        days: int = 7500,
    ) -> pd.DataFrame:
        """Fetch daily historical bars from Dhan and resample to Weekly OHLCV candles."""
        daily_df = self.fetch_daily_bars(security_id=security_id, days=days)
        if daily_df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = daily_df.copy()
        if "timestamp" not in df.columns:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = df.set_index("timestamp")
        weekly = (
            df.resample("W-FRI")
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        return weekly

    def fetch_bars(
        self,
        security_id: str,
        timeframe: str = "1D",
        days: int | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV candles for any supported timeframe (1M, 1W, 1D, 2H, 1H, 15M)."""
        tf = str(timeframe).strip().upper()
        if tf in ("1M", "M", "MONTH", "MONTHLY"):
            return self.fetch_monthly_bars(security_id, days=days or 4500)
        elif tf in ("1W", "W", "WEEK", "WEEKLY"):
            return self.fetch_weekly_bars(security_id, days=days or 7500)
        elif tf in ("15M", "15MIN", "15_MIN"):
            return self.fetch_resampled_bars(security_id, rule="15min", days=min(days or 25, 30))
        elif tf in ("1H", "60M", "60MIN", "1_HOUR"):
            return self.fetch_resampled_bars(security_id, rule="60min", days=min(days or 25, 30))
        elif tf in ("2H", "120M", "120MIN", "2_HOUR"):
            return self.fetch_2h_bars(security_id, days=min(days or 25, 30))
        else:
            return self.fetch_daily_bars(security_id, days=days or 150)
