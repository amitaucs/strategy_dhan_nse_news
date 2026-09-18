"""Candle ingestion and 2-Hour (120-min) time-bucket aggregation engine."""

from datetime import datetime, timedelta, time, timezone
import logging
import threading
import time as time_lib
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import pandas as pd

from st15_largecap.core.models import Candle

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def bucket_indian_market_2h(dt: datetime) -> Optional[datetime]:
    """Assign an intraday timestamp to its standard Indian market 2-Hour session slot.
    
    Session: 09:15 AM to 03:30 PM (IST)
      - Slot 1: 09:15 to 11:15 -> Bucket timestamp = 09:15
      - Slot 2: 11:15 to 13:15 -> Bucket timestamp = 11:15
      - Slot 3: 13:15 to 15:30 -> Bucket timestamp = 13:15
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(IST).replace(tzinfo=None)

    t = dt.time()
    t_min = t.hour * 60 + t.minute

    s1_start = 9 * 60 + 15   # 09:15 = 555
    s2_start = 11 * 60 + 15  # 11:15 = 675
    s3_start = 13 * 60 + 15  # 13:15 = 795
    market_close = 15 * 60 + 30 # 15:30 = 930

    if t_min < s1_start or t_min > market_close:
        return None

    date_part = dt.date()
    if t_min < s2_start:
        return datetime.combine(date_part, time(9, 15))
    elif t_min < s3_start:
        return datetime.combine(date_part, time(11, 15))
    else:
        return datetime.combine(date_part, time(13, 15))


def aggregate_to_2h_candles(minute_candles: List[Dict[str, Any]]) -> List[Candle]:
    """Convert minute/intraday candle dictionaries into standard 2-Hour session candles.
    
    Expected candle dict keys: 'timestamp', 'open', 'high', 'low', 'close', 'volume'
    """
    if not minute_candles:
        return []

    df = pd.DataFrame(minute_candles)
    if df.empty:
        return []

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    if getattr(df["timestamp"].dt, "tz", None) is not None:
        df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

    # Map each timestamp to its 2H bucket
    df["bucket"] = df["timestamp"].apply(bucket_indian_market_2h)
    df = df.dropna(subset=["bucket"])

    if df.empty:
        return []

    # Group by bucket
    grouped = df.groupby("bucket", as_index=False).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )

    grouped = grouped.sort_values("bucket")

    result: List[Candle] = []
    for _, row in grouped.iterrows():
        result.append(
            Candle(
                timestamp=row["bucket"].to_pydatetime() if hasattr(row["bucket"], "to_pydatetime") else row["bucket"],
                open=float(round(row["open"], 2)),
                high=float(round(row["high"], 2)),
                low=float(round(row["low"], 2)),
                close=float(round(row["close"], 2)),
                volume=float(round(row["volume"], 2)),
            )
        )

    return result


from st15_largecap.config import settings


class CandleFetcher:
    """Fetches intraday data from DhanHQ, caches historical candles, and transforms to 2H candles."""

    _rate_lock = threading.Lock()
    _last_call_time: float = 0.0

    def __init__(
        self,
        dhan_client: Optional[Any] = None,
        cache_ttl_seconds: int = 300,
    ):
        self.dhan = dhan_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, Tuple[datetime, List[Candle]]] = {}
        self._min_interval: float = 0.15  # Strict rate limit delay between calls

        if not self.dhan and settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
            try:
                from dhanhq import DhanContext, dhanhq
                ctx = DhanContext(settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN)
                self.dhan = dhanhq(ctx)
                logger.info("CandleFetcher initialized with DhanHQ client for ID: %s", settings.DHAN_CLIENT_ID)
            except Exception as e:
                logger.warning("Could not initialize DhanHQ client: %s", e)

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """Clear cached candles for a specific symbol or all symbols."""
        if symbol:
            sym_clean = symbol.upper().strip()
            keys_to_del = [k for k in self._cache if k.startswith(sym_clean)]
            for k in keys_to_del:
                self._cache.pop(k, None)
            logger.info("Candle cache cleared for %s", sym_clean)
        else:
            self._cache.clear()
            logger.info("Candle cache cleared for all symbols.")

    def fetch_2h_candles(
        self,
        security_id: str,
        symbol: str = "",
        exchange_segment: str = "NSE_EQ",
        instrument_type: str = "EQUITY",
        days: int = 180,
        force_refresh: bool = False,
    ) -> List[Candle]:
        """Fetch historical intraday data with atomic chunking (90-day intervals), caching and rate-limiting."""
        cache_key = f"{symbol or security_id}_{days}"
        now = datetime.now()

        # Check Cache
        if not force_refresh and cache_key in self._cache:
            cached_time, cached_candles = self._cache[cache_key]
            if (now - cached_time).total_seconds() < self.cache_ttl_seconds and cached_candles:
                return cached_candles

        if not self.dhan or not security_id:
            logger.warning("Cannot fetch real candles for %s: missing Dhan client or security_id.", symbol or "unknown")
            return []

        # Dhan intraday API has a 90-day maximum window per call (DH-905).
        # We split the requested days into 90-day chunks: [(180, 90), (90, 0)]
        chunks = []
        rem = days
        curr_offset = 0
        while rem > 0:
            step = min(90, rem)
            chunks.append((curr_offset + step, curr_offset))
            curr_offset += step
            rem -= step

        # Fetch older chunks first
        chunks = sorted(chunks, key=lambda c: c[0], reverse=True)
        all_records: List[Dict[str, Any]] = []
        all_chunks_succeeded = True

        for chunk_start, chunk_end in chunks:
            from_date = (now - timedelta(days=chunk_start)).strftime("%Y-%m-%d")
            to_date = (now - timedelta(days=chunk_end)).strftime("%Y-%m-%d")

            # Thread-safe Rate Limiting: enforce minimum interval between Dhan API calls
            with CandleFetcher._rate_lock:
                elapsed = time_lib.time() - CandleFetcher._last_call_time
                if elapsed < self._min_interval:
                    time_lib.sleep(self._min_interval - elapsed)
                CandleFetcher._last_call_time = time_lib.time()

            max_retries = 2
            chunk_success = False

            for attempt in range(max_retries + 1):
                try:
                    response = self.dhan.intraday_minute_data(
                        security_id=str(security_id),
                        exchange_segment=exchange_segment,
                        instrument_type=instrument_type,
                        from_date=from_date,
                        to_date=to_date,
                    )

                    # Check for rate limit response (DH-904)
                    if isinstance(response, dict) and response.get("error_code") == "DH-904":
                        if attempt < max_retries:
                            backoff = 1.0 * (attempt + 1)
                            logger.warning(
                                "Rate limited (DH-904) on %s [%s to %s]. Backing off %.1fs...",
                                symbol or security_id, from_date, to_date, backoff
                            )
                            time_lib.sleep(backoff)
                            continue

                    if isinstance(response, dict) and response.get("status") == "success":
                        data = response.get("data", {})
                        timestamps = data.get("timestamp", [])
                        opens = data.get("open", [])
                        highs = data.get("high", [])
                        lows = data.get("low", [])
                        closes = data.get("close", [])
                        volumes = data.get("volume", [0.0] * len(opens))

                        for i in range(len(timestamps)):
                            ts_val = timestamps[i]
                            if isinstance(ts_val, (int, float)):
                                dt = datetime.fromtimestamp(ts_val, tz=timezone.utc).astimezone(IST).replace(tzinfo=None)
                            else:
                                dt = pd.to_datetime(ts_val)
                                if getattr(dt, "tzinfo", None) is not None:
                                    dt = dt.astimezone(IST).replace(tzinfo=None)
                                elif hasattr(dt, "to_pydatetime"):
                                    dt = dt.to_pydatetime()

                            all_records.append({
                                "timestamp": dt,
                                "open": float(opens[i]),
                                "high": float(highs[i]),
                                "low": float(lows[i]),
                                "close": float(closes[i]),
                                "volume": float(volumes[i]) if i < len(volumes) else 0.0,
                            })
                        chunk_success = True
                        break

                    logger.debug("Dhan API chunk (%s to %s) returned non-success for %s: %s", from_date, to_date, symbol, response)
                    break
                except Exception as e:
                    logger.warning("Error fetching chunk (%s to %s) for %s: %s", from_date, to_date, symbol, e)
                    break

            if not chunk_success:
                logger.warning("Failed to fetch chunk [%s to %s] for %s (%s). Aborting partial candle assembly.", from_date, to_date, symbol, security_id)
                all_chunks_succeeded = False
                break

        if all_chunks_succeeded and all_records:
            # Deduplicate by timestamp and sort
            df_rec = pd.DataFrame(all_records)
            df_rec = df_rec.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            candles = aggregate_to_2h_candles(df_rec.to_dict("records"))
            if candles:
                self._cache[cache_key] = (now, candles)
                return candles

        # Fallback to cache only if NOT force_refresh and age is within reasonable bounds (<= 24h)
        if not force_refresh and cache_key in self._cache:
            cached_time, cached_candles = self._cache[cache_key]
            fallback_max_seconds = 86400  # 24 hours max fallback for non-force-refresh requests
            if (now - cached_time).total_seconds() <= fallback_max_seconds and cached_candles:
                logger.info("Using cached candles fallback (age: %.0fs) for %s", (now - cached_time).total_seconds(), symbol or security_id)
                return cached_candles

        logger.warning("No complete candles available for %s (SecID: %s).", symbol, security_id)
        return []

