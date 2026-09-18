"""Live Market Price (LTP) resolution module with multi-tier broker and exchange fallbacks."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import ssl
import time
from typing import Any, Dict, Optional, Tuple
import urllib.request

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

logger = logging.getLogger(__name__)


@dataclass
class PriceQuote:
    """Represents a market price quote with provenance and real-time validity."""
    price: float
    is_real_time: bool
    source: str  # "dhan" | "market_feed" | "cache" | "fallback" | "manual"


# Fallback reference prices strictly for offline / test environments
DEFAULT_REFERENCE_LTPS: Dict[str, float] = {
    "BEL": 300.0,
    "BANKINDIA": 120.0,
    "TATASTEEL": 150.0,
    "INFY": 1850.0,
    "RELIANCE": 1280.0,
    "HDFCBANK": 1650.0,
    "TATAMOTORS": 700.0,
    "SBIN": 800.0,
    "HAL": 4700.0,
    "BHEL": 280.0,
    "ICICIPRULI": 465.0,
    "ICICIBANK": 1250.0,
    "AXISBANK": 1150.0,
    "KOTAKBANK": 1800.0,
    "LT": 3600.0,
    "TCS": 3500.0,
    "ZOMATO": 250.0,
}

# In-memory TTL cache: symbol -> (PriceQuote, expiry_epoch)
_LTP_CACHE: Dict[str, Tuple[PriceQuote, float]] = {}
CACHE_TTL_SECONDS = 15.0


def _get_cached_quote(symbol: str) -> Optional[PriceQuote]:
    """Return cached PriceQuote if not expired."""
    clean = symbol.strip().upper()
    if clean in _LTP_CACHE:
        quote, expiry = _LTP_CACHE[clean]
        if time.time() < expiry:
            return quote
    return None


def _set_cached_quote(symbol: str, quote: PriceQuote) -> None:
    """Store PriceQuote in in-memory cache with TTL."""
    if quote.price > 0:
        clean = symbol.strip().upper()
        _LTP_CACHE[clean] = (quote, time.time() + CACHE_TTL_SECONDS)


def _fetch_from_dhan(symbol: str, security_id: Optional[str], dhan_client: Any) -> Optional[float]:
    """Fetch live ticker from DhanHQ SDK."""
    if not dhan_client or not security_id:
        return None
    try:
        sec_int = int(security_id)
        if hasattr(dhan_client, "ticker_data"):
            res = dhan_client.ticker_data({"NSE_EQ": [sec_int]})
            if isinstance(res, dict) and res.get("status") == "success":
                data = res.get("data", {}).get("NSE_EQ", {}).get(str(sec_int), {})
                last_price = data.get("last_price")
                if last_price and float(last_price) > 0:
                    return float(last_price)
        if hasattr(dhan_client, "ohlc_data"):
            res_ohlc = dhan_client.ohlc_data({"NSE_EQ": [sec_int]})
            if isinstance(res_ohlc, dict) and res_ohlc.get("status") == "success":
                data = res_ohlc.get("data", {}).get("NSE_EQ", {}).get(str(sec_int), {}).get("ohlc", {})
                close_price = data.get("close") or data.get("last_price")
                if close_price and float(close_price) > 0:
                    return float(close_price)
    except Exception as err:
        logger.debug("Dhan ticker fetch failed for %s (SecID %s): %s", symbol, security_id, err)
    return None


def _fetch_from_market_feed(symbol: str) -> Optional[float]:
    """Fetch live real-time price from exchange market feed endpoint."""
    clean = symbol.strip().upper()
    ticker_sym = f"{clean}.NS"
    endpoints = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_sym}?interval=1m&range=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker_sym}?interval=1m&range=1d",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    for url in endpoints:
        if _HAS_REQUESTS:
            try:
                resp = requests.get(url, headers=headers, timeout=3.0)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("chart", {}).get("result")
                    if result and len(result) > 0:
                        meta = result[0].get("meta", {})
                        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
                        if price and float(price) > 0:
                            return float(price)
            except Exception:
                pass

        try:
            req = urllib.request.Request(url, headers=headers)
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ctx, timeout=3.0) as resp_obj:
                if resp_obj.status == 200:
                    data = json.loads(resp_obj.read().decode("utf-8"))
                    result = data.get("chart", {}).get("result")
                    if result and len(result) > 0:
                        meta = result[0].get("meta", {})
                        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
                        if price and float(price) > 0:
                            return float(price)
        except Exception:
            pass

    return None


def get_live_market_quote(
    symbol: str,
    security_id: Optional[str] = None,
    dhan_client: Any = None,
    default_price: float = 300.0,
) -> PriceQuote:
    """Resolve live market quote with provenance tracking (real-time vs fallback).
    
    1. Check in-memory 15-second TTL cache.
    2. Try DhanHQ Broker SDK (if client supplied and data API permitted).
    3. Query live exchange market feed endpoint.
    4. Fallback to reference dictionary or provided default (marked is_real_time=False).
    """
    if not symbol:
        return PriceQuote(price=default_price, is_real_time=False, source="fallback")

    clean = symbol.strip().upper()

    # 1. Cache hit
    cached = _get_cached_quote(clean)
    if cached is not None:
        return cached

    # 2. Dhan Broker API
    dhan_price = _fetch_from_dhan(clean, security_id, dhan_client)
    if dhan_price is not None and dhan_price > 0:
        quote = PriceQuote(price=round(dhan_price, 2), is_real_time=True, source="dhan")
        _set_cached_quote(clean, quote)
        return quote

    # 3. Live Exchange Market Feed
    feed_price = _fetch_from_market_feed(clean)
    if feed_price is not None and feed_price > 0:
        quote = PriceQuote(price=round(feed_price, 2), is_real_time=True, source="market_feed")
        _set_cached_quote(clean, quote)
        return quote

    # 4. Safe Reference Fallback (Tagged as NOT real-time)
    ref_price = DEFAULT_REFERENCE_LTPS.get(clean, default_price)
    quote = PriceQuote(price=ref_price, is_real_time=False, source="fallback")
    _set_cached_quote(clean, quote)
    return quote


def get_live_market_ltp(
    symbol: str,
    security_id: Optional[str] = None,
    dhan_client: Any = None,
    default_price: float = 300.0,
) -> float:
    """Resolve the latest traded price (LTP) float for backwards compatibility."""
    return get_live_market_quote(
        symbol=symbol,
        security_id=security_id,
        dhan_client=dhan_client,
        default_price=default_price,
    ).price


__all__ = ["PriceQuote", "get_live_market_quote", "get_live_market_ltp", "DEFAULT_REFERENCE_LTPS"]
