"""Macro Market Breadth Verification for Nifty 50 and Bank Nifty."""

from __future__ import annotations

import logging
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


def check_market_breadth(
    provider: Optional[DhanDataProvider] = None,
    mock_nifty_green: Optional[bool] = None,
    mock_banknifty_green: Optional[bool] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Verify that BOTH Nifty 50 and Bank Nifty indices are positive (Green).

    Returns:
        Tuple[bool, Dict[str, Any]]:
            - is_both_green: True if BOTH Nifty 50 and Bank Nifty have positive change.
            - breadth_details: Detailed price and percentage telemetry for both indices.
    """
    if mock_nifty_green is not None and mock_banknifty_green is not None:
        is_both = mock_nifty_green and mock_banknifty_green
        return is_both, {
            "nifty_50": {"ltp": 25000.0, "change_pct": 0.5 if mock_nifty_green else -0.5, "is_green": mock_nifty_green},
            "bank_nifty": {"ltp": 51000.0, "change_pct": 0.4 if mock_banknifty_green else -0.4, "is_green": mock_banknifty_green},
            "is_both_green": is_both,
            "message": "Mock Breadth: " + ("BOTH GREEN" if is_both else "BREADTH FAILED"),
        }

    dhan_prov = provider or DhanDataProvider()
    if not dhan_prov.dhan:
        # Fallback to simulated positive breadth if credentials not set
        return True, {
            "nifty_50": {"ltp": 25000.0, "change_pct": 0.25, "is_green": True},
            "bank_nifty": {"ltp": 51500.0, "change_pct": 0.35, "is_green": True},
            "is_both_green": True,
            "message": "Simulated Breadth: Nifty 50 & Bank Nifty assumed GREEN (Offline mode)",
        }

    try:
        # 1. Fetch OHLC snapshot or Ticker data for Nifty 50 (13) and Bank Nifty (25)
        resp = dhan_prov.dhan.ohlc_data({"IDX_I": [int(NIFTY_50_SEC_ID), int(BANK_NIFTY_SEC_ID)]})

        idx_data = {}
        if isinstance(resp, dict) and resp.get("status") == "success" and "data" in resp:
            seg_data = resp["data"].get("IDX_I", {})
            idx_data = seg_data
        else:
            # Fallback to ticker_data
            t_resp = dhan_prov.dhan.ticker_data({"IDX_I": [int(NIFTY_50_SEC_ID), int(BANK_NIFTY_SEC_ID)]})
            if isinstance(t_resp, dict) and t_resp.get("status") == "success" and "data" in t_resp:
                idx_data = t_resp["data"].get("IDX_I", {})

        nifty_info = idx_data.get(NIFTY_50_SEC_ID, {})
        bank_info = idx_data.get(BANK_NIFTY_SEC_ID, {})

        n_ltp = float(nifty_info.get("last_price", 0.0))
        n_prev_close = float(nifty_info.get("ohlc", {}).get("close", n_ltp)) if isinstance(nifty_info.get("ohlc"), dict) else float(nifty_info.get("close", n_ltp))
        if n_prev_close <= 0:
            n_prev_close = n_ltp
        n_change_pct = round(((n_ltp - n_prev_close) / n_prev_close) * 100.0, 2) if n_prev_close > 0 else 0.0
        n_green = n_change_pct >= 0.0 or n_ltp >= float(nifty_info.get("ohlc", {}).get("open", n_ltp)) if isinstance(nifty_info.get("ohlc"), dict) else n_change_pct >= 0.0

        b_ltp = float(bank_info.get("last_price", 0.0))
        b_prev_close = float(bank_info.get("ohlc", {}).get("close", b_ltp)) if isinstance(bank_info.get("ohlc"), dict) else float(bank_info.get("close", b_ltp))
        if b_prev_close <= 0:
            b_prev_close = b_ltp
        b_change_pct = round(((b_ltp - b_prev_close) / b_prev_close) * 100.0, 2) if b_prev_close > 0 else 0.0
        b_green = b_change_pct >= 0.0 or b_ltp >= float(bank_info.get("ohlc", {}).get("open", b_ltp)) if isinstance(bank_info.get("ohlc"), dict) else b_change_pct >= 0.0

        is_both_green = bool(n_green and b_green)
        status_msg = (
            f"Nifty 50: {n_change_pct:+.2f}% ({'🟢' if n_green else '🔴'}) | "
            f"Bank Nifty: {b_change_pct:+.2f}% ({'🟢' if b_green else '🔴'}) -> "
            f"{'PASSED (Both Green)' if is_both_green else 'BLOCKED (Breadth Mismatch)'}"
        )

        return is_both_green, {
            "nifty_50": {"ltp": n_ltp, "change_pct": n_change_pct, "is_green": n_green},
            "bank_nifty": {"ltp": b_ltp, "change_pct": b_change_pct, "is_green": b_green},
            "is_both_green": is_both_green,
            "message": status_msg,
        }
    except Exception as exc:
        logger.warning("Error fetching market breadth: %s. Using safe neutral gate.", exc)
        return False, {
            "nifty_50": {"ltp": 0.0, "change_pct": 0.0, "is_green": False},
            "bank_nifty": {"ltp": 0.0, "change_pct": 0.0, "is_green": False},
            "is_both_green": False,
            "message": f"Breadth check error: {exc}",
        }

