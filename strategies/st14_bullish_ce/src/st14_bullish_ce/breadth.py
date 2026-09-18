"""Macro Market Breadth Verification for Nifty 50 and Bank Nifty."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from scanner_dhan.data.dhan_provider import DhanDataProvider

logger = logging.getLogger(__name__)

__all__ = [
    "NIFTY_50_SEC_ID",
    "BANK_NIFTY_SEC_ID",
    "check_market_breadth",
]

NIFTY_50_SEC_ID = "13"
BANK_NIFTY_SEC_ID = "25"


def _fetch_index_quote_dhan(dhan_client: Any, sec_id: str) -> Optional[Tuple[float, float, bool]]:
    """Fetch index quote from DhanHQ SDK."""
    if not dhan_client:
        return None
    try:
        sec_int = int(sec_id)
        for seg in ("IDX_I", "NSE_INDEX", "NSE_FNO", "NSE"):
            if hasattr(dhan_client, "ticker_data"):
                res = dhan_client.ticker_data({seg: [sec_int]})
                if isinstance(res, dict) and res.get("status") == "success":
                    data = res.get("data", {}).get(seg, {}).get(str(sec_int), {})
                    ltp = float(data.get("last_price", 0.0))
                    prev_close = float(data.get("close", data.get("prev_close", ltp)))
                    if ltp > 0:
                        chg_pct = round(((ltp - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                        return ltp, chg_pct, (chg_pct >= 0.0)
            if hasattr(dhan_client, "ohlc_data"):
                res = dhan_client.ohlc_data({seg: [sec_int]})
                if isinstance(res, dict) and res.get("status") == "success":
                    data = res.get("data", {}).get(seg, {}).get(str(sec_int), {})
                    ohlc = data.get("ohlc", {}) if isinstance(data.get("ohlc"), dict) else data
                    ltp = float(data.get("last_price", ohlc.get("close", 0.0)))
                    prev_close = float(ohlc.get("close", ohlc.get("prev_close", ltp)))
                    if ltp > 0:
                        chg_pct = round(((ltp - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                        return ltp, chg_pct, (chg_pct >= 0.0)
    except Exception as err:
        logger.debug("Dhan index quote failed for SecID %s: %s", sec_id, err)
    return None


def _fetch_index_quote_market_feed(ticker: str) -> Optional[Tuple[float, float, bool]]:
    """Fetch live real-time index price and change percentage from market feed."""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    ctx = ssl.create_default_context()
    endpoints = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d",
    ]

    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                ltp = float(meta.get("regularMarketPrice") or meta.get("chartPreviousClose") or 0.0)
                prev_close = float(meta.get("chartPreviousClose") or ltp)
                if ltp > 0:
                    chg_pct = round(((ltp - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                    return round(ltp, 2), chg_pct, (chg_pct >= 0.0)
        except Exception:
            pass
    return None


def check_market_breadth(
    provider: Optional[DhanDataProvider] = None,
    mock_nifty_green: Optional[bool] = None,
    mock_banknifty_green: Optional[bool] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Verify that BOTH Nifty 50 and Bank Nifty indices are positive (Green).

    Returns:
        Tuple[bool, Dict[str, Any]]:
            - is_both_green: True if BOTH Nifty 50 and Bank Nifty have positive change.
            - breadth_details: Detailed price, percentage, and boolean telemetry.
    """
    if mock_nifty_green is not None and mock_banknifty_green is not None:
        is_both = bool(mock_nifty_green and mock_banknifty_green)
        n_chg = 0.5 if mock_nifty_green else -0.5
        b_chg = 0.4 if mock_banknifty_green else -0.4
        return is_both, {
            "nifty_50": {"ltp": 25000.0, "change_pct": n_chg, "is_green": mock_nifty_green},
            "bank_nifty": {"ltp": 51000.0, "change_pct": b_chg, "is_green": mock_banknifty_green},
            "nifty50_green": mock_nifty_green,
            "banknifty_green": mock_banknifty_green,
            "nifty50_change_pct": n_chg,
            "banknifty_change_pct": b_chg,
            "nifty50_ltp": 25000.0,
            "banknifty_ltp": 51000.0,
            "is_both_green": is_both,
            "message": "Mock Breadth: " + ("BOTH GREEN" if is_both else "BREADTH FAILED"),
            "updated_at": datetime.now().strftime("%H:%M:%S IST"),
        }

    dhan_prov = provider or DhanDataProvider()
    dhan_client = getattr(dhan_prov, "dhan", None)

    # 1. Resolve NIFTY 50
    nifty_quote = _fetch_index_quote_dhan(dhan_client, NIFTY_50_SEC_ID)
    if nifty_quote is None:
        nifty_quote = _fetch_index_quote_market_feed("%5ENSEI")

    # 2. Resolve BANK NIFTY
    bank_quote = _fetch_index_quote_dhan(dhan_client, BANK_NIFTY_SEC_ID)
    if bank_quote is None:
        bank_quote = _fetch_index_quote_market_feed("%5ENSEBANK")

    # 3. Fail CLOSED if either quote is unavailable
    if nifty_quote is None or bank_quote is None:
        missing = []
        if nifty_quote is None:
            missing.append("Nifty 50")
        if bank_quote is None:
            missing.append("Bank Nifty")
        missing_str = " & ".join(missing)
        status_msg = f"❌ [DATA_UNAVAILABLE] Market breadth feeds failed for {missing_str}. Blocking new trades."
        logger.warning(status_msg)

        breadth_data = {
            "status": "DATA_UNAVAILABLE",
            "is_data_available": False,
            "nifty_50": {
                "ltp": nifty_quote[0] if nifty_quote else 0.0,
                "change_pct": nifty_quote[1] if nifty_quote else 0.0,
                "is_green": nifty_quote[2] if nifty_quote else False,
            },
            "bank_nifty": {
                "ltp": bank_quote[0] if bank_quote else 0.0,
                "change_pct": bank_quote[1] if bank_quote else 0.0,
                "is_green": bank_quote[2] if bank_quote else False,
            },
            "nifty50_green": nifty_quote[2] if nifty_quote else False,
            "banknifty_green": bank_quote[2] if bank_quote else False,
            "nifty50_change_pct": nifty_quote[1] if nifty_quote else 0.0,
            "banknifty_change_pct": bank_quote[1] if bank_quote else 0.0,
            "nifty50_ltp": nifty_quote[0] if nifty_quote else 0.0,
            "banknifty_ltp": bank_quote[0] if bank_quote else 0.0,
            "is_both_green": False,
            "message": status_msg,
            "updated_at": datetime.now().strftime("%H:%M:%S IST"),
        }
        return False, breadth_data

    n_ltp, n_change_pct, n_green = nifty_quote
    b_ltp, b_change_pct, b_green = bank_quote
    is_both_green = bool(n_green and b_green)
    status_msg = (
        f"Nifty 50: {n_change_pct:+.2f}% ({'🟢' if n_green else '🔴'}) | "
        f"Bank Nifty: {b_change_pct:+.2f}% ({'🟢' if b_green else '🔴'}) -> "
        f"{'PASSED (Both Green)' if is_both_green else 'BLOCKED (Breadth Mismatch)'}"
    )

    breadth_data = {
        "status": "OK",
        "is_data_available": True,
        "nifty_50": {"ltp": n_ltp, "change_pct": n_change_pct, "is_green": n_green},
        "bank_nifty": {"ltp": b_ltp, "change_pct": b_change_pct, "is_green": b_green},
        "nifty50_green": n_green,
        "banknifty_green": b_green,
        "nifty50_change_pct": n_change_pct,
        "banknifty_change_pct": b_change_pct,
        "nifty50_ltp": n_ltp,
        "banknifty_ltp": b_ltp,
        "is_both_green": is_both_green,
        "message": status_msg,
        "updated_at": datetime.now().strftime("%H:%M:%S IST"),
    }

    return is_both_green, breadth_data


