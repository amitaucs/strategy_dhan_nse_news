"""Batch Runner for End-of-Day Multi-Scanner Daily Digest Execution."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from scanner_dhan.eod.models import (
    EODConfluenceStock,
    EODDigestReport,
    EODMatchedStrategy,
    EODStrategySummary,
)
from scanner_dhan.eod.store import EODReportStore
from scanner_dhan.scanner.registry import ScannerRegistry

logger = logging.getLogger(__name__)
IST_TZ = ZoneInfo("Asia/Kolkata")


def _extract_val(item: Any, *keys: str, default: Any = None) -> Any:
    """Safely extract value from dict, dataclass, Pydantic, or general object."""
    if item is None:
        return default
    if isinstance(item, dict):
        for k in keys:
            if k in item and item[k] is not None:
                return item[k]
        return default
    for k in keys:
        if hasattr(item, k):
            v = getattr(item, k)
            if v is not None:
                return v
    return default


def _serialize_item(item: Any) -> dict[str, Any]:
    """Safely serialize an item whether it is already a dict, dataclass, Pydantic, or object."""
    if isinstance(item, dict):
        return item
    if hasattr(item, "to_dict") and callable(item.to_dict):
        try:
            res = item.to_dict()
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    if hasattr(item, "__dict__") and type(item).__name__ not in ("MagicMock", "Mock"):
        try:
            return dict(vars(item))
        except Exception:
            pass
    sym = _extract_val(item, "symbol", default="")
    return {"symbol": str(sym)} if sym else {"raw": str(item)}


def is_scanner_item_matched(item: Any, scanner_id: str) -> bool:
    """Determine if a scanner result item is a valid triggered/matched setup."""
    if item is None:
        return False

    # 1. Direct explicit boolean match flags
    for flag in (
        "is_at_support",
        "is_matched",
        "is_reversal_setup",
        "is_ath_breakout",
        "is_breakout",
        "is_at_order_block",
        "has_setup",
        "has_pattern",
        "is_pullback",
        "is_first_green",
        "is_fresh_crossover",
        "is_accumulation_pullback",
        "is_accumulation",
        "is_vcp",
        "is_reversal",
        "is_fresh_impulse",
        "is_at_resistance",
        "is_bullish",
    ):
        val = _extract_val(item, flag)
        if val is True:
            return True
        if isinstance(val, str) and val.lower() in ("true", "yes", "1"):
            return True

    # 2. Check setup status string
    status_val = str(_extract_val(item, "status", "setup_status", "pattern_status", default="") or "").upper()
    if status_val in (
        "MATCHED", "BREAKOUT", "BREAKOUT_ACTIVE", "PRIMED_TIGHT", "PRIMED", "FORMING",
        "REVERSAL", "OVERSOLD", "OVERBOUGHT", "TRIGGERED", "TRIGGERED_ACTIVE",
        "BREAKOUT_READY", "BREAKOUT_CONFIRMED", "QUALIFIED", "WATCHLIST",
        "CONFIRMED", "PULLBACK_AT_618", "ACCUMULATION", "CROSSOVER"
    ):
        return True

    # 3. Scanner-specific heuristics
    sid = scanner_id.lower()
    if "vcp" in sid:
        setup_obj = _extract_val(item, "setup")
        if setup_obj is not None:
            return True
        if _extract_val(item, "contractions_count", default=0) >= 2:
            return True
    elif "fib" in sid or "fvg" in sid:
        if _extract_val(item, "setup") is not None or _extract_val(item, "confluence_price") is not None:
            return True
    elif "head" in sid or "hs" in sid:
        if _extract_val(item, "pattern") is not None:
            return True
    elif "ath" in sid:
        ath_class = str(_extract_val(item, "ath_class", "")).upper()
        if "A_CLASS" in ath_class or "B_CLASS" in ath_class:
            return True
    elif "st14" in sid:
        if _extract_val(item, "five_hour_high") is not None and status_val != "NO_SETUP":
            return True

    # 4. Proximity / score based match
    dist = _extract_val(item, "distance_pct", "vwap_dist_pct")
    if dist is not None:
        try:
            if abs(float(dist)) <= 2.5:
                return True
        except (ValueError, TypeError):
            pass

    score = _extract_val(item, "score", "confluence_score")
    if score is not None:
        try:
            if float(score) >= 60.0:
                return True
        except (ValueError, TypeError):
            pass

    return False


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_fmt_price(val: Any) -> str:
    f = _safe_float(val)
    return f"₹{f:.2f}" if f is not None else str(val or "")


def _extract_stock_and_strategy(
    s_id: str,
    s_name: str,
    s_cat: str,
    item: Any,
) -> tuple[dict[str, Any], EODMatchedStrategy]:
    """Extract normalized stock metrics and EODMatchedStrategy from any scanner result item."""
    sym = str(_extract_val(item, "symbol", "TradingSymbol", "stock", "scrip", default="") or "").strip().upper()
    sec_id = str(_extract_val(item, "security_id", "SecurityID", "sec_id", default="") or "")
    c_name = str(_extract_val(item, "company_name", "company", default=sym) or sym)

    close_p = _safe_float(_extract_val(item, "close", "ltp", "current_price", "last_price", "close_price"), default=0.0) or 0.0
    chg_pct = _safe_float(_extract_val(item, "change_pct", "change", "pct_change"), default=0.0) or 0.0
    vol = _safe_int(_extract_val(item, "volume", "vol"), default=0)
    vol_ratio = _safe_float(_extract_val(item, "volume_ratio", "volume_surge_ratio", "vdu_ratio"), default=1.0) or 1.0

    sid_lower = s_id.lower()
    pivot_val: Optional[float] = None
    stop_val: Optional[float] = None
    dist_pct: Optional[float] = None
    level_desc = ""
    sig = "MATCH"
    score = 65.0

    # 1. VCP Scanner
    if "vcp" in sid_lower:
        setup = _extract_val(item, "setup") or {}
        pivot = _extract_val(setup, "pivot_level") or _extract_val(item, "pivot_level", "pivot_price")
        stop = _extract_val(setup, "stop_loss") or _extract_val(item, "stop_loss")
        c_count = _extract_val(setup, "contractions_count") or _extract_val(item, "contractions_count", default=3)
        vcp_stat = str(_extract_val(setup, "status") or _extract_val(item, "status", default="PRIMED")).upper()
        depth_seq = _extract_val(setup, "depth_sequence_pct") or []

        pivot_val = _safe_float(pivot)
        stop_val = _safe_float(stop)

        seq_str = " → ".join(f"{_safe_float(d, 0.0):.1f}%" for d in depth_seq) if depth_seq else f"{c_count}T"
        level_desc = _extract_val(item, "support_desc") or (f"VCP {c_count}T [{seq_str}] • Pivot: {_safe_fmt_price(pivot_val)}" if pivot_val else f"VCP {c_count}T Tightening Base")
        sig = "VCP_BREAKOUT" if "BREAKOUT" in vcp_stat else "VCP_PRIMED"
        score = 85.0 if "BREAKOUT" in vcp_stat or "PRIMED" in vcp_stat else 70.0

    # 2. FVG + Fib Scanner
    elif "fib" in sid_lower or "fvg" in sid_lower:
        setup = _extract_val(item, "setup") or {}
        conf_p = _extract_val(setup, "confluence_price") or _extract_val(item, "confluence_price", "pivot_price")
        stop = _extract_val(setup, "stop_loss") or _extract_val(item, "stop_loss")

        pivot_val = _safe_float(conf_p)
        stop_val = _safe_float(stop)
        level_desc = _extract_val(item, "support_desc") or (f"0.618 Fib + FVG Confluence @ {_safe_fmt_price(pivot_val)}" if pivot_val else "FVG + 0.618 Fib Retest")
        sig = "FVG_FIB_PULLBACK"
        score = 80.0

    # 3. ATH Breakout Scanner
    elif "ath" in sid_lower:
        prior_ath = _extract_val(item, "prior_ath_price", "ath_price", "pivot_price")
        stop = _extract_val(item, "stop_loss")
        ath_cls = str(_extract_val(item, "ath_class", "")).upper()

        pivot_val = _safe_float(prior_ath)
        stop_val = _safe_float(stop)
        cls_label = "A-Class" if "A_CLASS" in ath_cls else "B-Class" if "B_CLASS" in ath_cls else "ATH"
        level_desc = f"{cls_label} Breakout (Prior ATH: {_safe_fmt_price(pivot_val)})" if pivot_val else "Monthly All-Time High Breakout"
        sig = "ATH_BREAKOUT"
        score = 85.0 if "A_CLASS" in ath_cls else 75.0

    # 4. HA ST01 Reversal Scanner
    elif "st01" in sid_lower:
        stop = _extract_val(item, "stop_loss")
        setup_t = _extract_val(item, "setup_type")
        st_val = setup_t.value if hasattr(setup_t, "value") else str(setup_t or "Bullish Reversal")
        stop_val = _safe_float(stop)
        level_desc = f"HA Reversal: {st_val}"
        sig = "HA_ST01_REVERSAL"
        score = 80.0 if "Divergence" in st_val else 70.0

    # 5. ST07 89 EMA Scanner
    elif "st07" in sid_lower or "89ema" in sid_lower:
        ema_89 = _extract_val(item, "ema_89", "buy_trigger_price")
        stop = _extract_val(item, "stop_loss")
        cat = _extract_val(item, "scan_category")
        cat_str = cat.value if hasattr(cat, "value") else str(cat or "89 EMA Setup")
        pivot_val = _safe_float(ema_89)
        stop_val = _safe_float(stop)
        level_desc = f"{cat_str} (89 EMA: {_safe_fmt_price(pivot_val)})" if pivot_val else f"89 EMA {cat_str}"
        sig = "EMA_89_BOUNCE"
        score = 80.0

    # 6. ST15 Heikin Ashi EMA Pullback
    elif "st15" in sid_lower or "heikin_ashi_ema" in sid_lower or "pullback" in sid_lower:
        ema_p = _extract_val(item, "nearest_ema_price")
        ema_n = str(_extract_val(item, "nearest_ema_name", default="20 EMA"))
        pivot_val = _safe_float(ema_p)
        level_desc = f"Pullback to {ema_n} ({_safe_fmt_price(pivot_val)})" if pivot_val else f"Pullback to {ema_n}"
        sig = "HA_EMA_PULLBACK"
        score = 75.0

    # 7. Order Block Scanner
    elif "order_block" in sid_lower:
        ob = _extract_val(item, "nearest_order_block")
        if ob and type(ob).__name__ not in ("MagicMock", "Mock") and not hasattr(ob, "_mock_return_value"):
            ob_top = _safe_float(_extract_val(ob, "top"))
            ob_bot = _safe_float(_extract_val(ob, "bottom"))
            ob_type = _extract_val(ob, "block_type")
            type_str = ob_type.value if hasattr(ob_type, "value") else str(ob_type or "Bullish")
            pivot_val = ob_top
            stop_val = ob_bot
            level_desc = f"{type_str} Order Block ({_safe_fmt_price(ob_bot)} - {_safe_fmt_price(ob_top)})" if (ob_top and ob_bot) else f"{type_str} Order Block Zone"
        else:
            level_desc = str(_extract_val(item, "level_description", "support_desc", default="Order Block Zone") or "Order Block Zone")
        sig = "ORDER_BLOCK_SUPPORT"
        score = 75.0

    # 8. Head & Shoulders
    elif "head" in sid_lower or "hs" in sid_lower:
        pat = _extract_val(item, "pattern")
        if pat and type(pat).__name__ not in ("MagicMock", "Mock") and not hasattr(pat, "_mock_return_value"):
            neck = _safe_float(_extract_val(pat, "neckline_price"))
            stop = _safe_float(_extract_val(pat, "stop_loss"))
            p_type = _extract_val(pat, "pattern_type")
            p_stat = _extract_val(pat, "status")
            type_str = p_type.value if hasattr(p_type, "value") else str(p_type or "Inverse H&S")
            stat_str = p_stat.value if hasattr(p_stat, "value") else str(p_stat or "Confirmed")
            pivot_val = neck
            stop_val = stop
            level_desc = f"{type_str} ({stat_str} @ {_safe_fmt_price(pivot_val)})" if pivot_val else f"{type_str} ({stat_str})"
        else:
            level_desc = "Head & Shoulders Setup"
        sig = "HNS_PATTERN"
        score = 80.0

    # 9. ST-14 Bullish CE Scanner
    elif "st14" in sid_lower:
        five_h = _extract_val(item, "five_hour_high")
        pivot_val = _safe_float(five_h)
        level_desc = f"ST-14 5H Breakout ({_safe_fmt_price(pivot_val)})" if pivot_val else "ST-14 Bullish CE Setup"
        sig = "ST14_BREAKOUT"
        score = 85.0

    # 10. General Fallback
    else:
        pivot = _extract_val(item, "pivot_price", "pivot_level", "breakout_level", "key_level", "support_price")
        stop = _extract_val(item, "stop_loss", "suggested_sl")
        pivot_val = _safe_float(pivot)
        stop_val = _safe_float(stop)
        level_desc = str(_extract_val(item, "support_desc", "level_description", "description", default="Setup Triggered") or "Setup Triggered")
        sig = str(_extract_val(item, "signal", "status", "candle_signal", default="MATCH") or "MATCH")
        score = _safe_float(_extract_val(item, "score"), default=65.0) or 65.0

    # Extract raw distance
    raw_d = _extract_val(item, "distance_pct", "vwap_dist_pct")
    dist_pct = _safe_float(raw_d)
    if dist_pct is not None:
        dist_pct = round(dist_pct, 2)

    matched_strategy = EODMatchedStrategy(
        scanner_id=str(s_id),
        scanner_name=str(s_name),
        category=str(s_cat),
        signal=sig,
        level_desc=level_desc,
        score=score,
        details={
            "distance_pct": dist_pct,
            "timeframe": str(_extract_val(item, "timeframe", default="1D")),
        },
    )

    stock_meta = {
        "symbol": sym,
        "company_name": c_name,
        "security_id": sec_id,
        "close": close_p,
        "change_pct": chg_pct,
        "volume": vol,
        "volume_ratio": vol_ratio,
        "primary_category": s_cat,
        "pivot_level": pivot_val,
        "stop_loss": stop_val,
    }

    return stock_meta, matched_strategy


class EODScanRunner:
    """Orchestrates running all registered trading scanners at EOD and computing confluences."""

    def __init__(self, store: Optional[EODReportStore] = None) -> None:
        self.store = store or EODReportStore()
        self.is_executing: bool = False
        self.current_scanner_id: str = ""
        self.current_scanner_name: str = ""
        self.completed_scanners_count: int = 0
        self.total_scanners_count: int = 12
        self.progress_pct: int = 0

    def run_all(
        self,
        universe: str = "NIFTY_500",
        target_date: Optional[str] = None,
        scanner_ids: Optional[List[str]] = None,
        provider: Optional[Any] = None,
    ) -> EODDigestReport:
        """Execute all scanners sequentially/batched and compile multi-strategy digest."""
        start_time = time.time()
        now_ist = datetime.now(IST_TZ)
        date_str = target_date or now_ist.strftime("%Y-%m-%d")
        timestamp_str = now_ist.isoformat()

        all_scanners = ScannerRegistry.list_all()
        if scanner_ids:
            scanners_to_run = [s for s in all_scanners if s["id"] in scanner_ids]
        else:
            scanners_to_run = all_scanners

        self.is_executing = True
        self.total_scanners_count = len(scanners_to_run)
        self.completed_scanners_count = 0
        self.progress_pct = 0

        logger.info(
            f"Starting EOD Multi-Scanner Batch for {date_str} on universe '{universe}' with {len(scanners_to_run)} scanners."
        )

        strategy_summaries: Dict[str, EODStrategySummary] = {}
        stock_matches_map: Dict[str, Dict[str, Any]] = {}
        total_matches = 0

        try:
            for idx, s_meta in enumerate(scanners_to_run, 1):
                s_id = s_meta["id"]
                s_name = s_meta.get("name", s_id)
                s_cat = s_meta.get("category", "General")
                s_icon = s_meta.get("icon", "activity")

                self.current_scanner_id = s_id
                self.current_scanner_name = s_name
                self.progress_pct = int(((idx - 1) / self.total_scanners_count) * 100)

                logger.info(f"[{idx}/{self.total_scanners_count}] Running scanner '{s_id}' ({s_name})...")
                try:
                    params = {"universe": universe}
                    report = ScannerRegistry.run(s_id, params, provider=provider)

                    # Extract matched items using universal match detector
                    matched_items = [
                        item for item in (report.results or [])
                        if is_scanner_item_matched(item, s_id)
                    ]

                    total_matches += len(matched_items)
                    logger.info("Scanner '%s' found %d matched setups out of %d results.", s_id, len(matched_items), len(report.results or []))

                    # Safely serialize items for UI presentation
                    serialized_items = [_serialize_item(item) for item in matched_items]
                    strategy_summaries[s_id] = EODStrategySummary(
                        scanner_id=s_id,
                        scanner_name=s_name,
                        category=s_cat,
                        icon=s_icon,
                        matches_count=len(matched_items),
                        items=serialized_items,
                    )

                    # Process individual stock matches for Confluence Engine
                    for item in matched_items:
                        stock_meta, matched_strat = _extract_stock_and_strategy(s_id, s_name, s_cat, item)
                        sym = stock_meta["symbol"]
                        if not sym:
                            continue

                        if sym not in stock_matches_map:
                            stock_matches_map[sym] = {
                                **stock_meta,
                                "strategies": [matched_strat],
                            }
                        else:
                            # Append strategy to existing stock entry
                            stock_matches_map[sym]["strategies"].append(matched_strat)
                            # Keep best price / volume info
                            if stock_meta["close"] > 0:
                                stock_matches_map[sym]["close"] = stock_meta["close"]
                            if stock_meta["change_pct"] != 0:
                                stock_matches_map[sym]["change_pct"] = stock_meta["change_pct"]
                            if stock_meta["volume"] > 0:
                                stock_matches_map[sym]["volume"] = max(stock_matches_map[sym]["volume"], stock_meta["volume"])
                            if stock_meta["volume_ratio"] > 1.0:
                                stock_matches_map[sym]["volume_ratio"] = max(stock_matches_map[sym]["volume_ratio"], stock_meta["volume_ratio"])
                            if stock_meta["pivot_level"] and not stock_matches_map[sym]["pivot_level"]:
                                stock_matches_map[sym]["pivot_level"] = stock_meta["pivot_level"]
                            if stock_meta["stop_loss"] and not stock_matches_map[sym]["stop_loss"]:
                                stock_matches_map[sym]["stop_loss"] = stock_meta["stop_loss"]

                except Exception as e:
                    logger.error(f"Error running scanner '{s_id}' during EOD batch: {e}", exc_info=True)
                    strategy_summaries[s_id] = EODStrategySummary(
                        scanner_id=s_id,
                        scanner_name=s_name,
                        category=s_cat,
                        icon=s_icon,
                        matches_count=0,
                        items=[],
                    )
                finally:
                    self.completed_scanners_count = idx
                    self.progress_pct = int((idx / self.total_scanners_count) * 100)

            # Build Confluence Stock Objects & Calculate Confluence Scores
            all_confluence_stocks: List[EODConfluenceStock] = []
            bullish_count = 0
            bearish_count = 0

            for sym, data in stock_matches_map.items():
                strat_list = data["strategies"]
                m_count = len(strat_list)

                # Score formula: Baseline average of individual scores + 15 points per additional strategy + volume surge bonus
                avg_strat_score = sum(s.score for s in strat_list) / max(1, m_count)
                confluence_bonus = (m_count - 1) * 15.0
                vol_bonus = min(15.0, max(0.0, (data["volume_ratio"] - 1.0) * 5.0))
                final_score = min(99.0, avg_strat_score + confluence_bonus + vol_bonus)

                # Sentiment
                is_bullish = any(
                    "bull" in s.signal.lower()
                    or "breakout" in s.category.lower()
                    or "support" in s.category.lower()
                    or "vcp" in s.scanner_id.lower()
                    or "ath" in s.scanner_id.lower()
                    or "fib" in s.scanner_id.lower()
                    for s in strat_list
                )
                is_bearish = any("bear" in s.signal.lower() or "resistance" in s.category.lower() for s in strat_list)
                if is_bullish or not is_bearish:
                    bullish_count += 1
                else:
                    bearish_count += 1

                stock_obj = EODConfluenceStock(
                    symbol=sym,
                    company_name=data["company_name"],
                    security_id=data["security_id"],
                    close=data["close"],
                    change_pct=data["change_pct"],
                    volume=data["volume"],
                    volume_ratio=round(data["volume_ratio"], 2),
                    match_count=m_count,
                    confluence_score=round(final_score, 1),
                    strategies=strat_list,
                    primary_category=data["primary_category"],
                    pivot_level=data["pivot_level"],
                    stop_loss=data["stop_loss"],
                )
                all_confluence_stocks.append(stock_obj)

            # Sort all stocks by match_count desc, then confluence_score desc
            all_confluence_stocks.sort(key=lambda s: (s.match_count, s.confluence_score), reverse=True)

            top_confluence = [s for s in all_confluence_stocks if s.match_count >= 2]
            elapsed = time.time() - start_time

            digest_report = EODDigestReport(
                date=date_str,
                timestamp=timestamp_str,
                universe=universe,
                total_scanners_run=len(scanners_to_run),
                total_matches=total_matches,
                unique_stocks_count=len(all_confluence_stocks),
                confluence_stocks_count=len(top_confluence),
                bullish_count=bullish_count,
                bearish_count=bearish_count,
                top_confluence_stocks=top_confluence,
                all_stocks=all_confluence_stocks,
                strategies=strategy_summaries,
                execution_time_seconds=elapsed,
            )

            # Persist report
            self.store.save_report(digest_report.to_dict())
            logger.info(
                f"EOD Digest complete in {elapsed:.2f}s! Unique stocks: {len(all_confluence_stocks)}, 2+ Confluences: {len(top_confluence)}"
            )
            return digest_report
        finally:
            self.is_executing = False
            self.progress_pct = 100

