"""Candle ingestion and 2-Hour (120-min) time-bucket aggregation engine."""

from datetime import datetime, timedelta, time
import logging
import time as time_lib
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from st15_largecap.core.models import Candle

logger = logging.getLogger(__name__)


def bucket_indian_market_2h(dt: datetime) -> Optional[datetime]:
    """Assign an intraday timestamp to its standard Indian market 2-Hour session slot.
    
    Session: 09:15 AM to 03:30 PM (IST)
      - Slot 1: 09:15 to 11:15 -> Bucket timestamp = 09:15
      - Slot 2: 11:15 to 13:15 -> Bucket timestamp = 11:15
      - Slot 3: 13:15 to 15:30 -> Bucket timestamp = 13:15
    """
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

    def __init__(
        self,
        dhan_client: Optional[Any] = None,
        cache_ttl_seconds: int = 300,
    ):
        self.dhan = dhan_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, Tuple[datetime, List[Candle]]] = {}
        self._last_call_time: float = 0.0
        self._min_interval: float = 0.12  # Max ~8 requests/sec to honor Dhan rate limits

        if not self.dhan and settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
            try:
                from dhanhq import DhanContext, dhanhq
                ctx = DhanContext(settings.DHAN_CLIENT_ID, settings.DHAN_ACCESS_TOKEN)
                self.dhan = dhanhq(ctx)
                logger.info("CandleFetcher initialized with DhanHQ client for ID: %s", settings.DHAN_CLIENT_ID)
            except Exception as e:
                logger.warning("Could not initialize DhanHQ client: %s", e)

    def fetch_2h_candles(
        self,
        security_id: str,
        symbol: str = "",
        exchange_segment: str = "NSE_EQ",
        instrument_type: str = "EQUITY",
        days: int = 60,
        force_refresh: bool = False,
    ) -> List[Candle]:
        """Fetch historical intraday data with smart caching and rate-limiting."""
        cache_key = f"{symbol or security_id}_{days}"
        now = datetime.now()

        # Check Cache
        if not force_refresh and cache_key in self._cache:
            cached_time, cached_candles = self._cache[cache_key]
            if (now - cached_time).total_seconds() < self.cache_ttl_seconds and cached_candles:
                return cached_candles

        if not self.dhan or not security_id:
            logger.debug("Generating realistic synthetic 2H candles for %s (SecID: %s)", symbol, security_id)
            mock_candles = generate_mock_2h_candles(symbol=symbol, num_candles=80)
            self._cache[cache_key] = (now, mock_candles)
            return mock_candles

        to_date = now
        from_date = to_date - timedelta(days=days)
        from_str = from_date.strftime("%Y-%m-%d")
        to_str = to_date.strftime("%Y-%m-%d")

        # Rate Limiting: enforce minimum interval between Dhan API calls
        elapsed = time_lib.time() - self._last_call_time
        if elapsed < self._min_interval:
            time_lib.sleep(self._min_interval - elapsed)

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                self._last_call_time = time_lib.time()
                response = self.dhan.intraday_minute_data(
                    security_id=str(security_id),
                    exchange_segment=exchange_segment,
                    instrument_type=instrument_type,
                    from_date=from_str,
                    to_date=to_str,
                )

                # Check for rate limit response (DH-904)
                if isinstance(response, dict) and response.get("error_code") == "DH-904":
                    if attempt < max_retries:
                        backoff = 1.0 * (attempt + 1)
                        logger.warning(
                            "Rate limited (DH-904) on %s. Backing off %.1fs before retry %d/%d...",
                            symbol or security_id, backoff, attempt + 1, max_retries
                        )
                        time_lib.sleep(backoff)
                        continue
                    elif cache_key in self._cache:
                        logger.warning("Rate limited on %s. Serving cached candles.", symbol or security_id)
                        return self._cache[cache_key][1]

                if isinstance(response, dict) and response.get("status") == "success":
                    data = response.get("data", {})
                    timestamps = data.get("timestamp", [])
                    opens = data.get("open", [])
                    highs = data.get("high", [])
                    lows = data.get("low", [])
                    closes = data.get("close", [])
                    volumes = data.get("volume", [0.0] * len(opens))

                    records = []
                    for i in range(len(timestamps)):
                        ts_val = timestamps[i]
                        if isinstance(ts_val, (int, float)):
                            dt = datetime.fromtimestamp(ts_val)
                        else:
                            dt = pd.to_datetime(ts_val)

                        records.append({
                            "timestamp": dt,
                            "open": float(opens[i]),
                            "high": float(highs[i]),
                            "low": float(lows[i]),
                            "close": float(closes[i]),
                            "volume": float(volumes[i]) if i < len(volumes) else 0.0,
                        })

                    candles = aggregate_to_2h_candles(records)
                    if candles:
                        self._cache[cache_key] = (now, candles)
                        return candles

                logger.warning(
                    "Dhan API returned empty data for %s (SecID: %s): %s. Falling back to synthetic/cached candles.",
                    symbol or security_id, security_id, response.get("remarks") or response.get("error_message") if isinstance(response, dict) else response
                )
                if cache_key in self._cache:
                    return self._cache[cache_key][1]
                mock_candles = generate_mock_2h_candles(symbol=symbol, num_candles=80)
                self._cache[cache_key] = (now, mock_candles)
                return mock_candles
            except Exception as e:
                logger.error("Error fetching intraday candles for %s: %s", symbol or security_id, e)
                if cache_key in self._cache:
                    return self._cache[cache_key][1]
                mock_candles = generate_mock_2h_candles(symbol=symbol, num_candles=80)
                self._cache[cache_key] = (now, mock_candles)
                return mock_candles


def generate_mock_2h_candles(
    symbol: str = "TCS",
    base_price: Optional[float] = None,
    num_candles: int = 100,
    bullish_trend: Optional[bool] = None,
    pullback_at_end: Optional[bool] = None,
) -> List[Candle]:
    """Generate realistic synthetic 2H candles for testing and dry-run verification."""
    candles: List[Candle] = []
    current_time = datetime.now() - timedelta(days=num_candles // 3 + 5)

    hash_val = abs(hash(symbol or "STOCK"))
    if base_price is None:
        # Deterministic distinct price based on symbol name
        base_price = round(200.0 + (hash_val % 3800) + ((hash_val % 99) * 0.1), 2)

    if bullish_trend is None:
        # ~70% bullish, ~30% bearish across the universe
        bullish_trend = (hash_val % 10) < 7

    if pullback_at_end is None:
        # ~20% currently triggering a qualified bounce after dip
        pullback_at_end = (hash_val % 10) in (0, 1)

    current_price = base_price
    slots = [time(9, 15), time(11, 15), time(13, 15)]
    slot_idx = 0

    for i in range(num_candles):
        while current_time.weekday() >= 5:  # Skip weekends
            current_time += timedelta(days=1)

        candle_time = datetime.combine(current_time.date(), slots[slot_idx])
        slot_idx += 1
        if slot_idx >= len(slots):
            slot_idx = 0
            current_time += timedelta(days=1)

        # Price progression
        if bullish_trend:
            if pullback_at_end and num_candles - 4 <= i < num_candles - 1:
                drift = -0.003
            elif pullback_at_end and i == num_candles - 1:
                drift = 0.015
            else:
                drift = 0.002
        else:
            drift = -0.002

        o = current_price
        c = o * (1.0 + drift)
        h = max(o, c) * 1.004
        l = min(o, c) * 0.996
        v = 100000.0 + (i * 500.0)

        candles.append(
            Candle(
                timestamp=candle_time,
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
                volume=round(v, 2),
            )
        )
        current_price = c

    return candles
