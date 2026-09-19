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
                    # Default parameters for EOD scan
                    params = {"universe": universe}
                    report = ScannerRegistry.run(s_id, params)

                    matched_items = [
                        item for item in report.results
                        if getattr(item, "status", None) in ("matched", "breakout", "reversal", "oversold", "overbought", "triggered")
                        or getattr(item, "is_fresh_crossover", False)
                        or getattr(item, "is_accumulation", False)
                        or getattr(item, "is_ath_breakout", False)
                        or getattr(item, "is_vcp", False)
                        or getattr(item, "pattern_status", None) == "breakout_ready"
                    ]

                    # If no status filter matched, use all returned results with valid triggers
                    if not matched_items and report.results:
                        matched_items = [
                            item for item in report.results
                            if getattr(item, "distance_pct", 99.0) <= 3.0 or getattr(item, "score", 0.0) >= 50.0
                        ]

                    total_matches += len(matched_items)

                    # Record Strategy Summary
                    serialized_items = [item.to_dict() if hasattr(item, "to_dict") else vars(item) for item in matched_items]
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
                        sym = getattr(item, "symbol", "").strip().upper()
                        if not sym:
                            continue

                        sec_id = getattr(item, "security_id", "")
                        c_name = getattr(item, "company_name", sym)
                        close_p = float(getattr(item, "current_price", getattr(item, "close", getattr(item, "ltp", 0.0))) or 0.0)
                        chg_pct = float(getattr(item, "change_pct", 0.0) or 0.0)
                        vol = int(getattr(item, "volume", 0) or 0)
                        vol_ratio = float(getattr(item, "volume_ratio", getattr(item, "volume_surge_ratio", 1.0)) or 1.0)
                        level_desc = str(getattr(item, "level_description", getattr(item, "pattern_notes", getattr(item, "breakout_level", ""))) or "")
                        sig = str(getattr(item, "signal", getattr(item, "scan_mode", getattr(item, "status", "MATCH"))) or "MATCH")
                        score = float(getattr(item, "score", getattr(item, "vcp_score", 60.0)) or 60.0)

                        pivot = getattr(item, "pivot_price", getattr(item, "breakout_level", getattr(item, "key_level", None)))
                        stop = getattr(item, "stop_loss", getattr(item, "suggested_sl", None))

                        raw_dist = getattr(item, "distance_pct", None)
                        dist_pct = float(raw_dist) if raw_dist is not None and isinstance(raw_dist, (int, float)) else None

                        matched_strat = EODMatchedStrategy(
                            scanner_id=str(s_id),
                            scanner_name=str(s_name),
                            category=str(s_cat),
                            signal=sig,
                            level_desc=level_desc,
                            score=score,
                            details={
                                "distance_pct": dist_pct,
                                "timeframe": str(getattr(item, "timeframe", "1D")),
                            },
                        )

                        pivot_val = float(pivot) if pivot is not None and isinstance(pivot, (int, float)) else None
                        stop_val = float(stop) if stop is not None and isinstance(stop, (int, float)) else None

                        if sym not in stock_matches_map:
                            stock_matches_map[sym] = {
                                "symbol": sym,
                                "company_name": c_name,
                                "security_id": sec_id,
                                "close": close_p,
                                "change_pct": chg_pct,
                                "volume": vol,
                                "volume_ratio": vol_ratio,
                                "strategies": [matched_strat],
                                "primary_category": s_cat,
                                "pivot_level": pivot_val,
                                "stop_loss": stop_val,
                            }
                        else:
                            # Append strategy to existing stock entry
                            stock_matches_map[sym]["strategies"].append(matched_strat)
                            # Keep best close / volume info if previously 0
                            if close_p > 0:
                                stock_matches_map[sym]["close"] = close_p
                            if chg_pct != 0:
                                stock_matches_map[sym]["change_pct"] = chg_pct
                            if vol > 0:
                                stock_matches_map[sym]["volume"] = max(stock_matches_map[sym]["volume"], vol)
                            if vol_ratio > 1.0:
                                stock_matches_map[sym]["volume_ratio"] = max(stock_matches_map[sym]["volume_ratio"], vol_ratio)
                            if pivot and not stock_matches_map[sym]["pivot_level"]:
                                stock_matches_map[sym]["pivot_level"] = float(pivot)
                            if stop and not stock_matches_map[sym]["stop_loss"]:
                                stock_matches_map[sym]["stop_loss"] = float(stop)

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
                is_bullish = any("bull" in s.signal.lower() or "breakout" in s.category.lower() or "support" in s.category.lower() or "vcp" in s.scanner_id for s in strat_list)
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

