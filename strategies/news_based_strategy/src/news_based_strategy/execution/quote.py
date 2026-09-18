"""Live Market Price (LTP) resolution module with multi-tier broker and exchange fallbacks."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    """Represents a market price quote with provenance, timestamps, and real-time validity."""
    price: float
    is_real_time: bool
    source: str  # "dhan" | "market_feed" | "cache" | "fallback" | "manual"
    last_trade_time: Optional[datetime] = None
    received_at: Optional[datetime] = None
    security_id: Optional[str] = None
    exchange_segment: str = "NSE_EQ"


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

# In-memory TTL cache: cache_key -> (PriceQuote, expiry_epoch)
_LTP_CACHE: Dict[str, Tuple[PriceQuote, float]] = {}
CACHE_TTL_SECONDS = 15.0


def _make_cache_key(symbol: str, security_id: Optional[str] = None, exchange_segment: str = "NSE_EQ") -> str:
    """Generate unambiguous cache key across exchange segments and instrument IDs."""
    clean_sym = (symbol or "").strip().upper()
    clean_sec = (str(security_id) if security_id and str(security_id) not in ("0", "None") else "").strip()
    clean_seg = (exchange_segment or "NSE_EQ").strip().upper()
    if clean_sec:
        return f"{clean_seg}:{clean_sec}"
    return f"{clean_seg}:{clean_sym}"


def _get_cached_quote(symbol: str, security_id: Optional[str] = None, exchange_segment: str = "NSE_EQ") -> Optional[PriceQuote]:
    """Return cached PriceQuote if not expired."""
    key = _make_cache_key(symbol, security_id, exchange_segment)
    sym_key = _make_cache_key(symbol, None, exchange_segment)
    now = time.time()

    for k in (key, sym_key, symbol.strip().upper()):
        if k in _LTP_CACHE:
            quote, expiry = _LTP_CACHE[k]
            if now < expiry:
                return quote
    return None


def _set_cached_quote(symbol: str, quote: PriceQuote, security_id: Optional[str] = None, exchange_segment: str = "NSE_EQ") -> None:
    """Store PriceQuote in in-memory cache with TTL under segmented cache keys."""
    if quote.price > 0:
        key = _make_cache_key(symbol, security_id, exchange_segment)
        sym_key = _make_cache_key(symbol, None, exchange_segment)
        expiry = time.time() + CACHE_TTL_SECONDS
        _LTP_CACHE[key] = (quote, expiry)
        _LTP_CACHE[sym_key] = (quote, expiry)
        _LTP_CACHE[symbol.strip().upper()] = (quote, expiry)


def _fetch_from_dhan(
    symbol: str,
    security_id: Optional[str],
    dhan_client: Any,
    exchange_segment: str = "NSE_EQ",
) -> Optional[Tuple[float, Optional[datetime]]]:
    """Fetch live quote from DhanHQ SDK with exchange last_trade_time."""
    if not dhan_client or not security_id:
        return None
    try:
        sec_int = int(security_id)
        if hasattr(dhan_client, "quote_data"):
            res = dhan_client.quote_data({exchange_segment: [sec_int]})
            if isinstance(res, dict) and res.get("status") == "success":
                data = res.get("data", {}).get(exchange_segment, {}).get(str(sec_int), {})
                last_price = data.get("last_price") or data.get("lastPrice")
                if not last_price:
                    ohlc = data.get("ohlc", {})
                    last_price = ohlc.get("close") or ohlc.get("last_price")
                if last_price and float(last_price) > 0:
                    ltt = None
                    ltt_raw = data.get("last_trade_time") or data.get("lastTradeTime")
                    if ltt_raw:
                        try:
                            if isinstance(ltt_raw, (int, float)):
                                ltt = datetime.fromtimestamp(ltt_raw, tz=timezone.utc)
                            elif isinstance(ltt_raw, str):
                                ltt = datetime.fromisoformat(ltt_raw)
                        except Exception:
                            pass
                    return float(last_price), ltt

        if hasattr(dhan_client, "ticker_data"):
            res = dhan_client.ticker_data({exchange_segment: [sec_int]})
            if isinstance(res, dict) and res.get("status") == "success":
                data = res.get("data", {}).get(exchange_segment, {}).get(str(sec_int), {})
                last_price = data.get("last_price")
                if last_price and float(last_price) > 0:
                    return float(last_price), None

        if hasattr(dhan_client, "ohlc_data"):
            res_ohlc = dhan_client.ohlc_data({exchange_segment: [sec_int]})
            if isinstance(res_ohlc, dict) and res_ohlc.get("status") == "success":
                data = res_ohlc.get("data", {}).get(exchange_segment, {}).get(str(sec_int), {}).get("ohlc", {})
                close_price = data.get("close") or data.get("last_price")
                if close_price and float(close_price) > 0:
                    return float(close_price), None
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
            ctx = ssl.create_default_context()
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
    exchange_segment: str = "NSE_EQ",
    default_price: float = 300.0,
) -> PriceQuote:
    """Resolve live market quote with provenance tracking and exchange timestamps.
    
    1. Check in-memory 15-second TTL cache (keyed by segment & security_id/symbol).
    2. Try DhanHQ Broker SDK (quote_data/ticker_data with exchange last_trade_time).
    3. Query live exchange market feed endpoint.
    4. Fallback to reference dictionary or provided default (marked is_real_time=False).
    """
    recv_time = datetime.now(timezone.utc)
    if not symbol:
        return PriceQuote(
            price=default_price,
            is_real_time=False,
            source="fallback",
            received_at=recv_time,
            security_id=security_id,
            exchange_segment=exchange_segment,
        )

    clean = symbol.strip().upper()

    # 1. Cache hit
    cached = _get_cached_quote(clean, security_id=security_id, exchange_segment=exchange_segment)
    if cached is not None:
        return cached

    # 2. Dhan Broker API
    dhan_res = _fetch_from_dhan(clean, security_id, dhan_client, exchange_segment=exchange_segment)
    if dhan_res is not None:
        dhan_price, last_trade_time = dhan_res
        if dhan_price > 0:
            quote = PriceQuote(
                price=round(dhan_price, 2),
                is_real_time=True,
                source="dhan",
                last_trade_time=last_trade_time,
                received_at=recv_time,
                security_id=security_id,
                exchange_segment=exchange_segment,
            )
            _set_cached_quote(clean, quote, security_id=security_id, exchange_segment=exchange_segment)
            return quote

    # 3. Live Exchange Market Feed
    feed_price = _fetch_from_market_feed(clean)
    if feed_price is not None and feed_price > 0:
        quote = PriceQuote(
            price=round(feed_price, 2),
            is_real_time=True,
            source="market_feed",
            received_at=recv_time,
            security_id=security_id,
            exchange_segment=exchange_segment,
        )
        _set_cached_quote(clean, quote, security_id=security_id, exchange_segment=exchange_segment)
        return quote

    # 4. Safe Reference Fallback (Tagged as NOT real-time)
    ref_price = DEFAULT_REFERENCE_LTPS.get(clean, default_price)
    quote = PriceQuote(
        price=ref_price,
        is_real_time=False,
        source="fallback",
        received_at=recv_time,
        security_id=security_id,
        exchange_segment=exchange_segment,
    )
    _set_cached_quote(clean, quote, security_id=security_id, exchange_segment=exchange_segment)
    return quote


def get_live_market_ltp(
    symbol: str,
    security_id: Optional[str] = None,
    dhan_client: Any = None,
    exchange_segment: str = "NSE_EQ",
    default_price: float = 300.0,
) -> float:
    """Resolve the latest traded price (LTP) float for backwards compatibility."""
    return get_live_market_quote(
        symbol=symbol,
        security_id=security_id,
        dhan_client=dhan_client,
        exchange_segment=exchange_segment,
        default_price=default_price,
    ).price


__all__ = ["PriceQuote", "get_live_market_quote", "get_live_market_ltp", "DEFAULT_REFERENCE_LTPS"]
