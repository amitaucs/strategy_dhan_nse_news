"""Dashboard state management, feed buffering, live order handling, and SSE dispatch."""

import asyncio
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, TradeSignal
from news_based_strategy.execution.executor import (
    DhanExecutor,
    check_token_expiry,
    mask_client_id,
    parse_jwt_claims,
)
from news_based_strategy.execution.quote import get_live_market_ltp
from news_based_strategy.execution.risk import RiskManager, get_ist_now
from news_based_strategy.ingestion.extractor import is_pypdf_available
from news_based_strategy.ingestion.filter import NoiseFilter
from news_based_strategy.ingestion.universe import (
    get_fno_symbols,
    get_security_id_map,
    resolve_security_id,
    sync_dhan_fno_symbols,
)
from news_based_strategy.intelligence.analyzer import FilingAnalyzer
from news_based_strategy.storage.repository import StrategyStorage

logger = logging.getLogger(__name__)

class DashboardState:
    """In-memory state manager for live feed and SSE broadcast."""

    def __init__(self):
        self.storage = StrategyStorage()

        # Load credentials from config / environment (.env) with fallback to DB
        db_app_id = self.storage.get_setting("dhan_app_id")
        db_app_secret = self.storage.get_setting("dhan_app_secret")
        db_client_id = self.storage.get_setting("dhan_client_id")
        db_access_token = self.storage.get_setting("dhan_access_token")

        self.app_id = settings.dhan_app_id or db_app_id
        self.app_secret = settings.dhan_app_secret or db_app_secret
        eff_client_id = settings.dhan_client_id or db_client_id
        eff_access_token = db_access_token if db_access_token is not None else settings.dhan_access_token

        db_dry_run = self.storage.get_setting("dry_run")
        eff_dry_run = (db_dry_run.lower() in ("true", "1", "yes")) if db_dry_run is not None else settings.dry_run

        self.analyzer = FilingAnalyzer(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
            thinking_budget=settings.gemini_thinking_budget,
        )
        self.executor = DhanExecutor(
            client_id=eff_client_id,
            access_token=eff_access_token,
            dry_run=eff_dry_run,
            auto_order=settings.auto_order,
            capital_per_trade=settings.capital_per_trade,
            max_shares_per_trade=settings.max_shares_per_trade,
            max_orders_per_day=settings.max_orders_per_day,
            super_order_enabled=settings.super_order_enabled,
            target_profit_pct=settings.target_profit_pct,
            stop_loss_pct=settings.stop_loss_pct,
            trailing_jump_points=settings.trailing_jump_points,
            slippage_buffer_pct=settings.slippage_buffer_pct,
        )
        self.auth_url = settings.dhan_auth_url
        self.redirect_url = settings.dhan_redirect_url
        self.feed_items: List[Dict[str, Any]] = []
        self.subscribers: List[asyncio.Queue] = []
        self.auto_order = settings.auto_order

        # Initialize and sync Dhan F&O universe and numeric security IDs
        try:
            sync_dhan_fno_symbols()
            logger.info("Dhan F&O universe initialized with %d mapped SecIDs", len(get_security_id_map()))
        except Exception as exc:
            logger.warning("Could not sync Dhan F&O universe on state init: %s", exc)
        self._poller_task: Optional[asyncio.Task] = None
        self.poll_cycles_count: int = 0
        self.last_polled_at: Optional[datetime] = get_ist_now()
        self.suppressed_noise_count: int = 0
        self._last_square_off_date = None
        self._current_trading_date: str = RiskManager.get_ist_now().strftime("%Y-%m-%d")
        self._view_mode: str = "TODAY"

    def load_recent_audits_from_db(self, today_only: bool = True, date_str: Optional[str] = None) -> None:
        """Load recent actionable audits from database into feed_items, defaulting to current trading day."""
        recent_audits = self.storage.get_recent_audits(limit=50, today_only=today_only, date_str=date_str)
        loaded_items = []
        for audit in recent_audits:
            sent = audit.get("sentiment", "").upper()
            if sent not in ("BULLISH", "BUY", "BEARISH", "SELL"):
                continue
            is_bullish = sent in ("BULLISH", "BUY")
            sentiment_label = "BULLISH" if is_bullish else "BEARISH"
            action = "BUY" if is_bullish else "SELL"
            sym = audit.get("symbol", "")
            sec_id = resolve_security_id(sym) or "0"
            ltp = get_live_market_ltp(sym, security_id=sec_id, dhan_client=self.executor.dhan)

            entry_price, tp_price, sl_price = RiskManager.calculate_super_order_levels(
                ltp=ltp,
                action=action,
                target_pct=self.executor.target_profit_pct,
                sl_pct=self.executor.stop_loss_pct,
                slippage_buffer_pct=self.executor.slippage_buffer_pct,
            )
            qty = RiskManager.calculate_position_size(
                self.executor.capital_per_trade, ltp, max_quantity=self.executor.max_shares_per_trade
            )
            is_conviction = (
                audit.get("material_impact", False)
                and audit.get("confidence", 0) >= settings.confidence_threshold
            )
            effective_an_dt = audit.get("an_dt") or audit.get("created_at") or ""
            if " " in effective_an_dt:
                time_disp = effective_an_dt.split(" ")[1]
            elif len(effective_an_dt) >= 8:
                time_disp = effective_an_dt[-8:]
            else:
                time_disp = get_ist_now().strftime("%H:%M:%S")

            is_fresh, age = RiskManager.is_news_fresh(effective_an_dt, max_age_seconds=180)
            loaded_items.append({
                "seq_id": audit.get("seq_id", ""),
                "symbol": sym,
                "security_id": sec_id,
                "desc": f"Catalyst: {audit.get('catalyst_type', '')}",
                "details": audit.get("summary", ""),
                "an_dt": effective_an_dt,
                "timestamp": time_disp,
                "is_stale": not is_fresh,
                "age_seconds": int(age),
                "sentiment": sentiment_label,
                "confidence": audit.get("confidence", 0),
                "catalyst_type": audit.get("catalyst_type", ""),
                "material_impact": audit.get("material_impact", False),
                "summary": audit.get("summary", ""),
                "is_noise": False,
                "filter_reason": "",
                "order": {
                    "eligible": is_conviction,
                    "status": "RECORDED",
                    "placed": is_conviction,
                    "quantity": qty,
                    "ltp": ltp,
                    "entry_price": entry_price,
                    "target_price": tp_price,
                    "stop_loss_price": sl_price,
                    "trailing_jump": self.executor.trailing_jump_points,
                    "order_id": None,
                    "remarks": audit.get("summary", ""),
                },
            })
        self.feed_items = loaded_items

    async def start_background_poller(self) -> None:
        """Continuously poll NSE announcements in background and broadcast actionable catalysts."""
        from news_based_strategy.ingestion.monitor import NSEFilingMonitor

        monitor = NSEFilingMonitor(
            storage=self.storage,
            market_hours_only=settings.poll_market_hours_only,
            market_open_time=settings.market_open_time,
            market_close_time=settings.market_close_time,
        )
        mkt_desc = f"Market Hours Only: {settings.market_open_time} - {settings.market_close_time} IST" if settings.poll_market_hours_only else "24/7 Scanning"
        print(f"[{get_ist_now().strftime('%H:%M:%S IST')}] 📡 Background NSE Radar Poller initialized (Interval: {settings.poll_interval_seconds}s | {mkt_desc}). Watching {len(get_fno_symbols())} F&O stocks.", flush=True)
        while True:
            try:
                now = get_ist_now()
                today_str = now.strftime("%Y-%m-%d")

                # 🌅 Daily Rollover Check: When date changes at midnight IST, reset live table feed for new trading session
                if today_str != self._current_trading_date:
                    print(f"[{now.strftime('%H:%M:%S IST')}] 🌅 [DAY ROLLOVER] Date changed from {self._current_trading_date} to {today_str}. Refreshing GUI daily view for new trading session.", flush=True)
                    self._current_trading_date = today_str
                    self._last_square_off_date = None
                    self.suppressed_noise_count = 0
                    if self._view_mode == "TODAY":
                        self.feed_items.clear()
                    await self.broadcast_event("DAY_ROLLOVER", {
                        "new_date": today_str,
                        "message": f"Trading session refreshed for {today_str}."
                    })

                # ⏰ Check for automated 15:00 IST Square-Off
                today_date = now.date()
                if (
                    RiskManager.is_square_off_time(now, square_off_str=self.executor.square_off_time)
                    and self._last_square_off_date != today_date
                ):
                    self._last_square_off_date = today_date
                    sq_res = await asyncio.to_thread(self.executor.square_off_all_positions)
                    print(f"[{now.strftime('%H:%M:%S IST')}] ⏰ [15:00 AUTO SQUARE-OFF] Triggered automated square-off: {sq_res}", flush=True)
                    await self.broadcast_event("AUTO_SQUARE_OFF", sq_res)

                # Check if market hours gate is active and market is closed
                is_mkt_open = RiskManager.is_market_open(
                    now,
                    open_str=settings.market_open_time,
                    close_str=settings.market_close_time,
                )

                if settings.poll_market_hours_only and not is_mkt_open:
                    self.last_polled_at = get_ist_now()
                    if self.poll_cycles_count % 10 == 0:
                        print(f"[{now.strftime('%H:%M:%S IST')}] 🌙 [RADAR STANDBY] Market is closed ({settings.market_open_time} - {settings.market_close_time} IST / Mon-Fri). NSE news polling is paused.", flush=True)
                    await self.broadcast_event("POLL_CYCLE_COMPLETED", {
                        "cycle": self.poll_cycles_count,
                        "last_polled_time": self.last_polled_at.strftime("%H:%M:%S IST"),
                        "last_polled_ts": int(self.last_polled_at.timestamp()),
                        "suppressed_noise_count": self.suppressed_noise_count,
                        "is_market_open": False,
                        "radar_status": "STANDBY",
                    })
                else:
                    self.poll_cycles_count += 1
                    self.last_polled_at = get_ist_now()

                    def on_filtered(item: Announcement, reason: str):
                        self.suppressed_noise_count += 1
                        brief = (item.desc or item.details or "").strip().split()
                        brief_str = " ".join(brief[:5]) if brief else "Routine filing"
                        print(f"  ↳ [{item.symbol}] 🔇 Filtered out ({reason}) — {brief_str}", flush=True)

                        if not any(f.get("seq_id") == item.seq_id for f in self.feed_items):
                            noise_item = {
                                "seq_id": item.seq_id or f"NOISE_{self.suppressed_noise_count}",
                                "symbol": item.symbol,
                                "security_id": resolve_security_id(item.symbol) or "0",
                                "desc": item.desc or "Routine Filing",
                                "details": item.details or item.desc or "No additional content",
                                "an_dt": item.an_dt or get_ist_now().strftime("%d-%b-%Y %H:%M:%S"),
                                "timestamp": get_ist_now().strftime("%H:%M:%S IST"),
                                "is_stale": True,
                                "age_seconds": 0,
                                "sentiment": "FILTERED",
                                "confidence": 0,
                                "catalyst_type": reason,
                                "material_impact": False,
                                "summary": f"Suppressed: {reason}",
                                "is_noise": True,
                                "filter_reason": reason,
                                "order": {
                                    "eligible": False,
                                    "status": "FILTERED_NOISE",
                                    "placed": False,
                                    "quantity": 0,
                                    "ltp": 0.0,
                                    "entry_price": 0.0,
                                    "target_price": 0.0,
                                    "stop_loss_price": 0.0,
                                    "trailing_jump": 0.0,
                                    "order_id": None,
                                    "remarks": f"Filtered: {reason}",
                                },
                            }
                            self.feed_items.insert(0, noise_item)
                            if len(self.feed_items) > 300:
                                self.feed_items = self.feed_items[:300]

                    new_items = await asyncio.to_thread(monitor.get_new_announcements, on_filtered=on_filtered)
                    print(f"[{get_ist_now().strftime('%H:%M:%S IST')}] 📡 [RADAR] Cycle #{self.poll_cycles_count}: Polled NSE ({len(new_items)} tradeable catalysts, {self.suppressed_noise_count} total noise suppressed)", flush=True)
                    for ann in new_items:
                        processed = self.process_and_add_announcement(ann)
                        if processed:
                            await self.broadcast_event("NEW_CATALYST", processed)

                    await self.broadcast_event("POLL_CYCLE_COMPLETED", {
                        "cycle": self.poll_cycles_count,
                        "last_polled_time": self.last_polled_at.strftime("%H:%M:%S IST"),
                        "last_polled_ts": int(self.last_polled_at.timestamp()),
                        "suppressed_noise_count": self.suppressed_noise_count,
                        "is_market_open": True,
                        "radar_status": "ACTIVE",
                    })
            except Exception as e:
                logger.error("Error in GUI background poller: %s", e)
            await asyncio.sleep(settings.poll_interval_seconds)

    def toggle_auto_order(self, enabled: bool) -> bool:
        self.auto_order = enabled
        self.executor.auto_order = enabled
        return self.auto_order

    def toggle_dry_run(self, dry_run: bool) -> bool:
        self.executor.update_credentials(dry_run=dry_run)
        self.storage.set_setting("dry_run", "true" if dry_run else "false")
        return self.executor.dry_run

    async def broadcast_event(self, event_type: str, data: Any):
        payload = json.dumps({"type": event_type, "data": data})
        for q in list(self.subscribers):
            try:
                await q.put(payload)
            except Exception:
                if q in self.subscribers:
                    self.subscribers.remove(q)

    def process_and_add_announcement(self, ann: Announcement, bypass_market_hours: bool = False) -> Optional[Dict[str, Any]]:
        """Process an announcement: verify filter, check market trading hours, run Gemini, evaluate order trigger, and record item."""
        # 1. Reject if noise or not in F&O universe
        if not ann.is_fno:
            return None
        if NoiseFilter.is_noise(ann.desc, ann.details):
            return None

        sec_id = resolve_security_id(ann.symbol) or "0"
        ltp = get_live_market_ltp(ann.symbol, security_id=sec_id, dhan_client=self.executor.dhan)

        # 2. Gate Gemini LLM evaluation strictly to live market trading hours (09:15 to 14:45 IST cutoff)
        if not bypass_market_hours:
            ann_dt_obj = RiskManager.parse_exchange_timestamp(ann.an_dt) if ann.an_dt else RiskManager.get_ist_now()
            allowed, market_reason = RiskManager.is_trade_allowed(
                dt=ann_dt_obj,
                cutoff_str=self.executor.trade_cutoff_time,
                open_str=settings.market_open_time,
                close_str=settings.market_close_time,
            )
            if allowed:
                wall_allowed, wall_reason = RiskManager.is_trade_allowed(
                    dt=RiskManager.get_ist_now(),
                    cutoff_str=self.executor.trade_cutoff_time,
                    open_str=settings.market_open_time,
                    close_str=settings.market_close_time,
                )
                if not wall_allowed:
                    allowed = False
                    market_reason = wall_reason
            if not allowed:
                self.suppressed_noise_count += 1
                if not any(f.get("seq_id") == ann.seq_id for f in self.feed_items):
                    is_fresh, age = RiskManager.is_news_fresh(ann.an_dt, max_age_seconds=180)
                    closed_item = {
                        "seq_id": ann.seq_id,
                        "symbol": ann.symbol,
                        "security_id": sec_id,
                        "desc": ann.desc,
                        "details": ann.clean_content,
                        "an_dt": ann.an_dt,
                        "timestamp": get_ist_now().strftime("%H:%M:%S IST"),
                        "is_stale": not is_fresh,
                        "age_seconds": int(age),
                        "sentiment": "MARKET_CLOSED",
                        "confidence": 0,
                        "catalyst_type": "Market Closed",
                        "material_impact": False,
                        "summary": f"Skipped Gemini Evaluation: {market_reason}",
                        "is_noise": True,
                        "filter_reason": f"Market Closed ({market_reason})",
                        "order": {
                            "eligible": False,
                            "status": "MARKET_CLOSED",
                            "placed": False,
                            "quantity": 0,
                            "ltp": ltp,
                            "entry_price": 0.0,
                            "target_price": 0.0,
                            "stop_loss_price": 0.0,
                            "trailing_jump": 0.0,
                            "order_id": None,
                            "remarks": f"Market Closed: {market_reason}",
                        },
                    }
                    self.feed_items.insert(0, closed_item)
                    if len(self.feed_items) > 300:
                        self.feed_items = self.feed_items[:300]
                self.storage.mark_processed(ann.seq_id, ann.symbol, ann.an_dt)
                print(f"[{get_ist_now().strftime('%H:%M:%S IST')}] [{ann.symbol}] 🌙 Skipped Gemini LLM evaluation: {market_reason}", flush=True)
                return None

        # 3. Run Gemini AI reasoning
        audit = self.analyzer.audit(
            symbol=ann.symbol,
            headline=ann.desc,
            details=ann.clean_content,
        )
        if not audit:
            return None

        # Filter strictly to actionable Bullish or Bearish catalysts
        sentiment_upper = audit.sentiment.upper()
        if sentiment_upper not in ("BULLISH", "BUY", "BEARISH", "SELL"):
            if not any(f.get("seq_id") == ann.seq_id for f in self.feed_items):
                is_fresh, age = RiskManager.is_news_fresh(ann.an_dt, max_age_seconds=180)
                noise_item = {
                    "seq_id": ann.seq_id,
                    "symbol": ann.symbol,
                    "security_id": sec_id,
                    "desc": ann.desc,
                    "details": ann.clean_content,
                    "an_dt": ann.an_dt,
                    "timestamp": get_ist_now().strftime("%H:%M:%S IST"),
                    "is_stale": not is_fresh,
                    "age_seconds": int(age),
                    "sentiment": sentiment_upper,
                    "confidence": audit.confidence,
                    "catalyst_type": audit.catalyst_type,
                    "material_impact": audit.material_impact,
                    "summary": audit.summary,
                    "is_noise": True,
                    "filter_reason": f"AI Classified {sentiment_upper} ({audit.confidence}%)",
                    "order": {
                        "eligible": False,
                        "status": "FILTERED_NEUTRAL",
                        "placed": False,
                        "quantity": 0,
                        "ltp": ltp,
                        "entry_price": 0.0,
                        "target_price": 0.0,
                        "stop_loss_price": 0.0,
                        "trailing_jump": 0.0,
                        "order_id": None,
                        "remarks": f"AI classified {sentiment_upper}",
                    },
                }
                self.feed_items.insert(0, noise_item)
                if len(self.feed_items) > 300:
                    self.feed_items = self.feed_items[:300]
            return None

        is_bullish = sentiment_upper in ("BULLISH", "BUY")
        sentiment_label = "BULLISH" if is_bullish else "BEARISH"
        action = "BUY" if is_bullish else "SELL"
        product = RiskManager.get_safe_product_type(action)

        # Save AI audit to DB
        self.storage.save_audit(ann.seq_id, ann.symbol, audit)
        self.storage.mark_processed(ann.seq_id, ann.symbol, ann.an_dt)

        entry_price, tp_price, sl_price = RiskManager.calculate_super_order_levels(
            ltp=ltp,
            action=action,
            target_pct=self.executor.target_profit_pct,
            sl_pct=self.executor.stop_loss_pct,
            slippage_buffer_pct=self.executor.slippage_buffer_pct,
        )
        qty = RiskManager.calculate_position_size(
            self.executor.capital_per_trade, ltp, max_quantity=self.executor.max_shares_per_trade
        )

        is_conviction = (
            audit.material_impact
            and audit.confidence >= settings.confidence_threshold
        )

        order_data: Dict[str, Any] = {
            "eligible": is_conviction,
            "status": "NONE",
            "placed": False,
            "quantity": qty,
            "ltp": ltp,
            "entry_price": entry_price,
            "target_price": tp_price,
            "stop_loss_price": sl_price,
            "trailing_jump": self.executor.trailing_jump_points,
            "order_id": None,
            "remarks": "",
        }

        if is_conviction:
            if self.auto_order:
                # Place order automatically
                signal = TradeSignal(
                    symbol=ann.symbol,
                    security_id=sec_id,
                    action=action,
                    product_type=product,
                    confidence=audit.confidence,
                    catalyst_type=audit.catalyst_type,
                    summary=audit.summary,
                    exchange_time=ann.an_dt,
                )
                res = self.executor.execute_order(signal, ltp=ltp)
                self.storage.save_trade(res)
                order_data["status"] = "PLACED" if res.success else "REJECTED"
                order_data["placed"] = res.success
                order_data["order_id"] = res.order_id
                order_data["remarks"] = res.remarks
            else:
                order_data["status"] = "PENDING_APPROVAL"
                order_data["remarks"] = "Awaiting user manual approval (AUTO_ORDER=False)"
        else:
            order_data["status"] = "SKIPPED_LOW_CONFIDENCE"
            order_data["remarks"] = f"Confidence < {settings.confidence_threshold}% or non-material"

        ts = get_ist_now().strftime("%H:%M:%S IST")
        sec_id_str = f" [Dhan ID: {sec_id}]" if sec_id and sec_id != "0" else ""
        print(f"\n[{ts}] [{ann.symbol} [F&O]{sec_id_str}] 📢 {ann.desc}", flush=True)
        print(f"   ↳ Status: 🟢 PASSED ALL FILTERS ➔ Sent to AI Reasoning Engine", flush=True)
        if ann.an_dt:
            badge = ann.freshness_badge(max_age_seconds=180)
            badge_str = f" {badge}" if badge else ""
            print(f"   ↳ Exchange Time: {ann.an_dt}{badge_str}", flush=True)
        print(f"   🎯 VERDICT: {sentiment_label} (Confidence: {audit.confidence}% | Category: {audit.catalyst_type})", flush=True)
        print(f"   📝 AI Summary: \"{audit.summary}\"", flush=True)
        if is_conviction:
            print(f"   🚀 CONVICTION TRIGGER: {order_data['status']} ({qty} shares @ ₹{ltp} | TP: ₹{tp_price}, SL: ₹{sl_price})", flush=True)
        else:
            print(f"   ⏸️ ORDER: {order_data['status']} ({order_data['remarks']})", flush=True)

        is_fresh, age = RiskManager.is_news_fresh(ann.an_dt, max_age_seconds=180)
        feed_item = {
            "seq_id": ann.seq_id,
            "symbol": ann.symbol,
            "security_id": sec_id,
            "desc": ann.desc,
            "details": ann.clean_content,
            "an_dt": ann.an_dt,
            "timestamp": get_ist_now().strftime("%H:%M:%S IST"),
            "is_stale": not is_fresh,
            "age_seconds": int(age),
            "sentiment": sentiment_label,
            "confidence": audit.confidence,
            "catalyst_type": audit.catalyst_type,
            "material_impact": audit.material_impact,
            "summary": audit.summary,
            "is_noise": False,
            "filter_reason": "",
            "order": order_data,
        }

        # Prepend to feed
        self.feed_items.insert(0, feed_item)
        return feed_item


__all__ = ["DashboardState"]
