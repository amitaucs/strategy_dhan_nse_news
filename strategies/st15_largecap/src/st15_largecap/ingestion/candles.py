"""Candle ingestion and 2-Hour (120-min) time-bucket aggregation engine."""

from datetime import datetime, timedelta, time
import logging
from typing import Any, Dict, List, Optional
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


class CandleFetcher:
    """Fetches intraday data from DhanHQ and transforms to 2H candles."""

    def __init__(self, dhan_client: Optional[Any] = None):
        self.dhan = dhan_client

    def fetch_2h_candles(
        self,
        security_id: str,
        symbol: str = "",
        exchange_segment: str = "NSE_EQ",
        instrument_type: str = "EQUITY",
        days: int = 60,
    ) -> List[Candle]:
        """Fetch historical intraday data for the past `days` and aggregate to 2H candles."""
        if not self.dhan:
            logger.debug("No Dhan client provided; generating synthetic 2H candles for testing.")
            return generate_mock_2h_candles(symbol=symbol, num_candles=80)

        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        from_str = from_date.strftime("%Y-%m-%d %H:%M:%S")
        to_str = to_date.strftime("%Y-%m-%d %H:%M:%S")

        try:
            response = self.dhan.intraday_minute_data(
                security_id=str(security_id),
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                from_date=from_str,
                to_date=to_str,
                interval=15,
            )

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
                logger.info(
                    "Fetched and aggregated %d 2H candles for %s (SecID: %s)",
                    len(candles), symbol or security_id, security_id
                )
                return candles
            else:
                logger.warning(
                    "Dhan API intraday data call failed for %s: %s",
                    symbol or security_id, response
                )
                return []
        except Exception as e:
            logger.error("Error fetching intraday candles for %s: %s", symbol or security_id, e)
            return []


def generate_mock_2h_candles(
    symbol: str = "TCS",
    base_price: float = 3500.0,
    num_candles: int = 100,
    bullish_trend: bool = True,
    pullback_at_end: bool = True,
) -> List[Candle]:
    """Generate realistic synthetic 2H candles for testing and dry-run verification."""
    candles: List[Candle] = []
    current_time = datetime.now() - timedelta(days=num_candles // 3 + 5)
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
                # Moderate pullback dip
                drift = -0.003
            elif pullback_at_end and i == num_candles - 1:
                # Strong first green candle bounce after dip
                drift = 0.020
            else:
                drift = 0.003
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
