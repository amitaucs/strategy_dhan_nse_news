import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
import requests
from pydantic import BaseModel
from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, TradeSignal
from news_based_strategy.execution.executor import (
    DhanExecutor,
    check_token_expiry,
    mask_client_id,
    parse_jwt_claims,
)
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

SIMULATED_LTPS: dict[str, float] = {
    "BEL": 300.0,
    "BANKINDIA": 120.0,
    "TATASTEEL": 150.0,
    "INFY": 1850.0,
    "RELIANCE": 2950.0,
    "HDFCBANK": 1650.0,
    "TATAMOTORS": 1050.0,
    "SBIN": 820.0,
    "HAL": 4700.0,
    "BHEL": 280.0,
}


class AppLoginRequest(BaseModel):
    username: str
    password: str


class PlaceOrderRequest(BaseModel):
    seq_id: str
    symbol: str
    action: str = "BUY"
    product_type: str = "INTRADAY"
    confidence: int = 90
    catalyst_type: str = "ORDER_WIN"
    summary: str = ""
    ltp: Optional[float] = None


class ToggleAutoOrderRequest(BaseModel):
    auto_order: bool


class ToggleDryRunRequest(BaseModel):
    dry_run: bool


class UpdateTokenRequest(BaseModel):
    access_token: str
    client_id: Optional[str] = None
    dry_run: Optional[bool] = None


class SaveApiKeysRequest(BaseModel):
    client_id: Optional[str] = None
    app_id: str
    app_secret: str


class LoadHistoryRequest(BaseModel):
    today_only: bool = False
    date_str: Optional[str] = None



def generate_dhan_consent_url(
    client_id: str,
    app_id: str,
    app_secret: str,
    auth_url: str = "https://auth.dhan.co",
) -> tuple[bool, str]:
    """Call Dhan /app/generate-consent to obtain the consentAppId and login redirect URL."""
    try:
        url = f"{auth_url.rstrip('/')}/app/generate-consent?client_id={client_id}"
        headers = {
            "app_id": app_id,
            "app_secret": app_secret,
            "Accept": "application/json",
        }
        resp = requests.post(url, headers=headers, timeout=10)
        data = resp.json()
        consent_id = data.get("consentAppId") or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("consentAppId")
        if consent_id:
            login_url = f"{auth_url.rstrip('/')}/login/consentApp-login?consentAppId={consent_id}"
            return True, login_url
        error_msg = data.get("remarks") or data.get("message") or str(data)
        return False, f"Dhan Consent generation failed: {error_msg}"
    except Exception as e:
        return False, f"Dhan Auth connection error: {str(e)}"


def consume_dhan_consent(
    token_id: str,
    app_id: str,
    app_secret: str,
    auth_url: str = "https://auth.dhan.co",
) -> tuple[bool, str, dict]:
    """Exchange tokenId for accessToken via Dhan /app/consumeApp-consent."""
    try:
        url = f"{auth_url.rstrip('/')}/app/consumeApp-consent?tokenId={token_id}"
        headers = {
            "app_id": app_id,
            "app_secret": app_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = requests.post(url, headers=headers, json={"tokenId": token_id}, timeout=10)
        data = resp.json()
        access_token = data.get("accessToken") or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("accessToken")
        if access_token:
            return True, access_token, data
        error_msg = data.get("remarks") or data.get("message") or str(data)
        return False, f"Dhan token exchange failed: {error_msg}", data
    except Exception as e:
        return False, f"Dhan Auth connection error: {str(e)}", {}


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
            ltp = SIMULATED_LTPS.get(sym.upper(), 300.0)

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
            created_time_str = str(audit.get("created_at") or "")
            time_disp = created_time_str[-8:] if len(created_time_str) >= 8 else get_ist_now().strftime("%H:%M:%S")
            is_fresh, age = RiskManager.is_news_fresh(audit.get("created_at"), max_age_seconds=180)
            loaded_items.append({
                "seq_id": audit.get("seq_id", ""),
                "symbol": sym,
                "security_id": sec_id,
                "desc": f"Catalyst: {audit.get('catalyst_type', '')}",
                "details": audit.get("summary", ""),
                "an_dt": audit.get("created_at", ""),
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

        monitor = NSEFilingMonitor(storage=self.storage)
        print(f"[{get_ist_now().strftime('%H:%M:%S IST')}] 📡 Background NSE Radar Poller initialized (Interval: {settings.poll_interval_seconds}s). Watching {len(get_fno_symbols())} F&O stocks.", flush=True)
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
        ltp = SIMULATED_LTPS.get(ann.symbol.upper(), 300.0)

        # 2. Gate Gemini LLM evaluation strictly to live market trading hours (09:15 to 14:45 IST cutoff)
        if not bypass_market_hours:
            allowed, market_reason = RiskManager.is_trade_allowed(cutoff_str=self.executor.trade_cutoff_time)
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


def get_login_html() -> str:
    """Return dedicated application login page HTML matching reference UI."""
    return """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign In | NSE Catalyst Trading Terminal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 500: '#10b981', 600: '#059669', 700: '#047857' },
          }
        }
      }
    }
  </script>
</head>
<body class="bg-[#0b0f19] text-gray-200 font-sans antialiased min-h-screen flex items-center justify-center p-4">
  <div class="max-w-md w-full">
    
    <!-- Header / Brand -->
    <div class="text-center mb-6">
      <div class="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-black text-2xl mb-3 shadow-lg shadow-emerald-500/10">
        ⚡
      </div>
      <h1 class="text-lg font-bold text-white tracking-wide uppercase">NSE Catalyst Trading Terminal</h1>
      <p class="text-xs text-gray-400 mt-1">Sign in to access real-time execution grid</p>
    </div>

    <!-- Login Card Container -->
    <div class="bg-[#111827] border border-gray-800 rounded-2xl p-7 shadow-2xl space-y-5">
      
      <!-- Error / Status Alert Banner -->
      <div id="login-alert" class="hidden text-xs p-3 rounded-xl border transition-all"></div>

      <!-- Credentials Login Form -->
      <form id="login-form" onsubmit="handleCredentialsLogin(event)" class="space-y-4">
        <div>
          <label class="block text-xs font-semibold text-gray-300 mb-1.5" for="username">Username or Email</label>
          <div class="relative">
            <input type="text" id="username" name="username" required autofocus placeholder="Enter username (e.g. amit)" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-xl pl-9 pr-3 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition font-medium">
            <span class="absolute left-3 top-3 text-xs text-gray-400">👤</span>
          </div>
        </div>

        <div>
          <label class="block text-xs font-semibold text-gray-300 mb-1.5" for="password">Password</label>
          <div class="relative">
            <input type="password" id="password" name="password" required placeholder="Enter password" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-xl pl-9 pr-10 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition font-medium">
            <span class="absolute left-3 top-3 text-xs text-gray-400">🔒</span>
            <button type="button" onclick="togglePasswordVisibility()" class="absolute right-3 top-2.5 text-gray-400 hover:text-gray-200 text-xs">
              <span id="pwd-toggle-icon">👁️</span>
            </button>
          </div>
        </div>

        <!-- Primary Blue Sign In Button -->
        <button type="submit" id="btn-submit" class="w-full bg-blue-600 hover:bg-blue-500 active:scale-95 text-white font-bold text-xs py-3 px-4 rounded-xl shadow-lg shadow-blue-600/30 transition flex items-center justify-center gap-2">
          <span>Sign In</span>
        </button>
      </form>

      <!-- Horizontal Divider with "or" -->
      <div class="flex items-center gap-3 my-4">
        <div class="flex-1 h-px bg-gray-700/60"></div>
        <span class="text-xs text-gray-400 font-medium">or</span>
        <div class="flex-1 h-px bg-gray-700/60"></div>
      </div>

      <!-- Dedicated "Log In with Dhan" Button (Matching Diagram) -->
      <button type="button" onclick="handleDhanSSO()" id="btn-dhan-sso" class="w-full bg-white hover:bg-gray-100 active:scale-95 text-gray-800 font-semibold text-xs py-2.5 px-4 rounded-xl border border-gray-300 shadow-sm transition flex items-center justify-center gap-2.5">
        <span class="w-5 h-5 rounded-md bg-[#00b060] flex items-center justify-center text-white font-bold text-xs shadow-inner">
          ध
        </span>
        <span class="text-[13px] font-medium text-gray-800">Log In with Dhan</span>
      </button>

      <!-- Footer: Don't have an account? Create One -->
      <div class="pt-2 text-center text-xs text-gray-400">
        <span>Don't have an account?</span>
        <a href="https://join.dhan.co/?invite=VEVQU13117" target="_blank" rel="noopener noreferrer" class="text-blue-500 hover:underline font-semibold ml-1">Create One</a>
      </div>

    </div>

    <!-- Sub-footer -->
    <div class="text-center mt-6 text-[11px] text-gray-500 font-mono">
      <span>Protected by NSE Quantitative Strategy Engine • v0.3.0</span>
    </div>

  </div>

  <script>
    function togglePasswordVisibility() {
      const pwdInput = document.getElementById('password');
      const icon = document.getElementById('pwd-toggle-icon');
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        icon.textContent = '🙈';
      } else {
        pwdInput.type = 'password';
        icon.textContent = '👁️';
      }
    }

    function showAlert(msg, isError = true) {
      const alertBox = document.getElementById('login-alert');
      alertBox.className = isError 
        ? 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-3 rounded-xl' 
        : 'block bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs p-3 rounded-xl';
      alertBox.textContent = msg;
    }

    async function handleCredentialsLogin(event) {
      event.preventDefault();
      const username = document.getElementById('username').value.trim();
      const password = document.getElementById('password').value;
      const btn = document.getElementById('btn-submit');

      if (!username || !password) {
        showAlert('Please enter both username and password.');
        return;
      }

      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<span>Verifying credentials...</span>';

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          showAlert('Login successful! Redirecting to terminal...', false);
          const params = new URLSearchParams(window.location.search);
          const next = params.get('next') || '/';
          setTimeout(() => {
            window.location.href = next;
          }, 300);
        } else {
          showAlert(data.message || 'Invalid username or password.');
        }
      } catch (err) {
        showAlert('Connection error. Please try again.');
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<span>Sign In</span>';
      }
    }

    async function handleDhanSSO() {
      const btn = document.getElementById('btn-dhan-sso');
      btn.disabled = true;
      btn.classList.add('opacity-50');

      try {
        const res = await fetch('/api/auth/dhan/sso');
        const data = await res.json();

        if (res.ok && data.success && data.login_url) {
          showAlert('Redirecting to Dhan OAuth login portal...', false);
          setTimeout(() => {
            window.location.href = data.login_url;
          }, 200);
        } else {
          showAlert(data.message || 'Unable to initiate Dhan SSO. Please configure Dhan App ID & Secret, or login with username & password.');
        }
      } catch (err) {
        showAlert('Connection error initiating Dhan SSO.');
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
      }
    }

    window.onload = function() {
      const params = new URLSearchParams(window.location.search);
      if (params.get('error')) {
        showAlert(params.get('error'));
      } else if (params.get('logged_out')) {
        showAlert('You have been successfully logged out from the application session.', false);
      }
    };
  </script>
</body>
</html>
"""


def get_dashboard_html(is_simulate_feed: bool = False) -> str:
    """Return a sleek, high-density Trading Terminal Table Grid dashboard."""
    sim_header_btn = """
          <!-- Simulation Button -->
          <button onclick="triggerSimulation()" id="sim-btn" class="bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white text-xs font-bold px-3 py-2 rounded-lg transition border border-indigo-400/40 shadow-md flex items-center gap-1.5">
            <span>⚡</span>
            <span>Simulate Feed</span>
          </button>
""" if is_simulate_feed else ""

    sim_empty_btn = """
        <div>
          <button onclick="triggerSimulation()" class="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 active:scale-95 rounded-lg transition shadow-md border border-indigo-400/30">
            <span>⚡ Test / Simulate Sample Catalyst Feed</span>
          </button>
        </div>
""" if is_simulate_feed else ""

    html = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSE Catalyst Trading Terminal | Real-Time Execution Grid</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 500: '#10b981', 600: '#059669', 700: '#047857' },
          }
        }
      }
    }
  </script>
  <style>
    @keyframes pulse-subtle { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .animate-pulse-subtle { animation: pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
    .custom-scrollbar::-webkit-scrollbar-track { background: #0f172a; }
    .custom-scrollbar::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    tbody tr:hover { background-color: rgba(30, 41, 59, 0.5) !important; }
  </style>
</head>
<body class="bg-[#0b0f19] text-gray-200 font-sans antialiased min-h-screen flex flex-col custom-scrollbar">

  <!-- TOP APP BAR -->
  <header class="bg-[#111827] border-b border-gray-800 sticky top-0 z-50 px-6 py-3 shadow-md">
    <div class="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-4">
      
      <!-- Brand & Telemetry -->
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-black text-lg">
          ⚡
        </div>
        <div>
          <div class="flex items-center gap-2.5">
            <h1 class="text-sm font-bold text-white tracking-wide uppercase">NSE Catalyst Trading Terminal</h1>
            <!-- Dynamic Market Status Badge (Green when Open, Red when Closed) -->
            <span id="market-status-badge" class="px-2.5 py-0.5 text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-full flex items-center gap-1.5 shadow-sm transition-all duration-300" title="NSE Trading Hours (Mon-Fri 09:15 - 15:30 IST)">
              <span id="market-status-dot" class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
              <span id="market-status-text">MARKET CLOSED</span>
            </span>
            <!-- Dynamic Cutoff Status Badge -->
            <span id="cutoff-status-badge" class="px-2.5 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-300 border border-gray-700 rounded-full flex items-center gap-1.5 shadow-sm transition-all duration-300" title="New Trades Cutoff: 14:45 IST | Intraday Square-Off: 15:00 IST">
              <span id="cutoff-status-dot" class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span id="cutoff-status-text">CUTOFF 14:45</span>
            </span>
          </div>
          <div class="text-[11px] text-gray-400 flex items-center gap-2 mt-0.5">
            <span>Model: <span class="text-indigo-400 font-mono font-semibold">gemini-3.7-flash</span></span>
            <span>•</span>
            <span>Broker: <span id="mode-text" class="text-amber-400 font-mono font-semibold">VIRTUAL</span></span>
            <span>•</span>
            <span>Token: <span id="telemetry-token-status" class="text-emerald-400 font-mono font-bold">Active</span></span>
          </div>
        </div>
      </div>

      <!-- Controls & Actions (Separated Strategy Controls & Dedicated Dhan Token Widget) -->
      <div class="flex items-center gap-3.5">
        
        <!-- Strategy Controls Group -->
        <div class="flex items-center gap-2.5">
          <!-- EXECUTION MODE (VIRTUAL / LIVE) Toggle Switch -->
          <div class="flex items-center gap-2 bg-[#1e293b]/80 border border-gray-700/80 px-3 py-1.5 rounded-lg shadow-sm">
            <span class="text-xs font-semibold text-gray-300">EXECUTION:</span>
            <button id="toggle-mode-btn" onclick="toggleExecutionMode()" class="px-2.5 py-1 text-xs font-bold rounded transition flex items-center gap-1.5 shadow" title="Click to toggle between VIRTUAL (Simulated) and LIVE TRADING">
              <span id="mode-status-indicator" class="w-2 h-2 rounded-full"></span>
              <span id="mode-status-label">VIRTUAL</span>
            </button>
          </div>

          <!-- AUTO_ORDER Toggle Switch -->
          <div class="flex items-center gap-2 bg-[#1e293b]/80 border border-gray-700/80 px-3 py-1.5 rounded-lg shadow-sm">
            <span class="text-xs font-semibold text-gray-300">AUTO ORDER:</span>
            <button id="toggle-auto-btn" onclick="toggleAutoOrder()" class="px-2.5 py-1 text-xs font-bold rounded transition flex items-center gap-1.5 shadow">
              <span id="auto-status-indicator" class="w-2 h-2 rounded-full"></span>
              <span id="auto-status-label">LOADING...</span>
            </button>
          </div>

          <!-- Audio Synthesizer Toggle -->
          <button onclick="toggleAudioSound()" id="sound-toggle-btn" class="bg-gray-800 hover:bg-gray-700 active:scale-95 text-emerald-400 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition border border-gray-700 flex items-center gap-1.5 shadow" title="Toggle Synthesized Audio Chimes for Catalysts">
            <span id="sound-icon">🔊</span>
            <span id="sound-label" class="hidden md:inline font-mono">Audio ON</span>
          </button>

          <!-- Shortcuts Cheat Sheet Button -->
          <button onclick="openHotkeysModal()" class="bg-gray-800 hover:bg-gray-700 active:scale-95 text-gray-300 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition border border-gray-700 flex items-center gap-1 shadow" title="Keyboard Shortcuts Cheat Sheet (?)">
            <span>⌨️</span>
            <span class="hidden lg:inline text-gray-400 font-mono text-[11px]">[?]</span>
          </button>

          <!-- Emergency Square-Off Button -->
          <button onclick="confirmEmergencySquareOff()" id="square-off-btn" class="bg-rose-950/70 hover:bg-rose-900 active:scale-95 text-rose-300 hover:text-white text-xs font-bold px-2.5 py-1.5 rounded-lg transition border border-rose-700/60 shadow flex items-center gap-1.5" title="Close all open intraday positions and cancel open orders immediately (Shift + Q)">
            <span>🛑</span>
            <span>Square Off (15:00)</span>
          </button>

          __SIM_HEADER_BTN__

          <!-- Refresh Button -->
          <button onclick="fetchFeed()" class="bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold p-2 rounded-lg transition border border-gray-700" title="Refresh Table">
            🔄
          </button>
        </div>

        <!-- Vertical Divider -->
        <div class="h-8 w-px bg-gray-700/60 hidden sm:block"></div>

        <!-- RIGHT-TOP USER LOGIN & ACCOUNT WIDGET -->
        <div class="relative" id="user-account-container">
          <!-- Unauthenticated Login Button -->
          <button onclick="openLoginScreen()" id="btn-header-login" class="hidden bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs px-3.5 py-2 rounded-xl shadow-lg shadow-emerald-700/30 border border-emerald-400/40 flex items-center gap-2 transition active:scale-95">
            <span>🔐</span>
            <span>Login with Dhan</span>
          </button>

          <!-- Authenticated User Profile Button -->
          <div id="user-profile-widget" class="flex items-center gap-2">
            <button onclick="toggleUserMenu()" id="token-btn" class="group bg-[#162032] hover:bg-[#1f293d] active:scale-95 border border-emerald-500/40 hover:border-emerald-400/70 px-3.5 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2.5" title="Manage Dhan Account & Session">
              <div class="w-7 h-7 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-xs shadow-inner">
                👤
              </div>
              <div class="text-left">
                <div class="text-[10px] font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                  <span id="user-client-id-label">DHAN USER</span>
                  <span id="token-indicator-dot" class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                </div>
                <div id="header-token-mask" class="text-xs font-mono font-bold text-emerald-400 group-hover:text-emerald-300">
                  Active
                </div>
              </div>
              <span class="text-[10px] text-gray-400 group-hover:text-white transition ml-1">▼</span>
            </button>

            <!-- User Menu Dropdown -->
            <div id="user-menu-dropdown" class="hidden absolute right-0 top-12 w-64 bg-[#111827] border border-gray-700/80 rounded-xl shadow-2xl p-3 z-50 space-y-2.5 text-xs">
              <div class="border-b border-gray-800 pb-2">
                <div class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Trading Account (Broker)</div>
                <div id="menu-client-id" class="text-xs font-mono font-bold text-white mt-0.5">Client ID: --</div>
                <div id="menu-expiry-info" class="text-[10px] text-emerald-400 font-mono mt-0.5">Active Session</div>
              </div>
              <div class="space-y-1">
                <button onclick="openLoginScreen(); toggleUserMenu();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-gray-800 text-gray-300 hover:text-white flex items-center gap-2 transition">
                  <span>🔄</span> Manage Dhan Token
                </button>
                <button onclick="logoutDhan(); toggleUserMenu();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-rose-950/40 text-rose-400 hover:text-rose-300 flex items-center gap-2 transition font-semibold">
                  <span>🚪</span> Disconnect Dhan Token
                </button>
              </div>
              <div class="border-t border-gray-800 pt-2 space-y-1">
                <div class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">App User Session</div>
                <button onclick="logoutApp();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-rose-900/50 bg-rose-950/30 text-rose-300 hover:text-white flex items-center gap-2 transition font-bold border border-rose-500/20">
                  <span>🔒</span> Sign Out (App Logout)
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </header>

  <!-- METRICS RIBBON -->
  <div class="bg-[#0e1422] border-b border-gray-800/80 px-6 py-2.5">
    <div class="max-w-[1600px] mx-auto grid grid-cols-2 md:grid-cols-6 gap-3 text-center">
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between">
        <span class="text-[11px] text-gray-400 font-medium">FILTERED CATALYSTS</span>
        <span id="stat-total" class="text-base font-bold text-white font-mono">0</span>
      </div>
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between">
        <span class="text-[11px] text-emerald-400 font-medium">🟢 BULLISH SIGNALS</span>
        <span id="stat-bullish" class="text-base font-bold text-emerald-400 font-mono">0</span>
      </div>
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between">
        <span class="text-[11px] text-rose-400 font-medium">🔴 BEARISH SIGNALS</span>
        <span id="stat-bearish" class="text-base font-bold text-rose-400 font-mono">0</span>
      </div>
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between">
        <span class="text-[11px] text-indigo-400 font-medium">SUPER ORDERS PLACED</span>
        <span id="stat-placed" class="text-base font-bold text-indigo-300 font-mono">0</span>
      </div>
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between">
        <span class="text-[11px] text-amber-400 font-medium">PENDING APPROVAL</span>
        <span id="stat-pending" class="text-base font-bold text-amber-300 font-mono">0</span>
      </div>
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between col-span-2 md:col-span-1">
        <span class="text-[11px] text-cyan-400 font-medium">🛡️ ORDERS RISK GAUGE</span>
        <div class="flex items-center gap-1.5 font-mono">
          <span id="risk-gauge-dots" class="text-emerald-400 font-bold text-xs tracking-wider">[■ ■ ■]</span>
          <span id="risk-gauge-text" class="text-gray-300 text-[11px] font-bold">0/3</span>
        </div>
      </div>
    </div>
  </div>

  <!-- LIVE FEED MONITORING RADAR BAR -->
  <div class="bg-[#0b101d] border-b border-gray-800/90 px-6 py-2 shadow-inner">
    <div class="max-w-[1600px] mx-auto flex flex-wrap items-center justify-between gap-3 text-xs">
      
      <!-- Left: Poller Status & Universe -->
      <div class="flex items-center gap-3">
        <div class="inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3 py-1 rounded-full font-bold shadow-sm" id="radar-badge-container">
          <span class="relative flex h-2.5 w-2.5">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
          </span>
          <span id="poller-status-badge">NSE RADAR ACTIVE</span>
        </div>
        <div class="text-gray-300 flex items-center gap-1.5 font-medium">
          <span>Watching <b id="poller-fno-count" class="text-white font-mono font-bold">228</b> F&O Stocks</span>
          <span class="text-gray-600">•</span>
          <span>Poll Interval: <span id="poller-interval-val" class="text-gray-200 font-mono font-semibold">60s</span></span>
        </div>
      </div>

      <!-- Right: Real-Time Telemetry Counters -->
      <div class="flex items-center gap-4 text-gray-400">
        <div class="flex items-center gap-1.5">
          <span>Last Exchange Check (IST):</span>
          <span id="poller-last-time" class="text-emerald-400 font-mono font-bold">Just now</span>
          <span id="poller-elapsed-tag" class="text-[10px] text-emerald-300 bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 rounded font-mono font-semibold">0s ago</span>
        </div>
        <div class="flex items-center gap-1.5 border-l border-gray-800 pl-3">
          <span>Compliance Noise Suppressed:</span>
          <span id="poller-noise-count" class="text-amber-400 font-mono font-bold">0</span>
        </div>
      </div>

    </div>
  </div>

  <!-- TABLE TOOLBAR (TABS & SEARCH) -->
  <div class="max-w-[1600px] mx-auto w-full px-6 pt-5 pb-3 flex flex-wrap items-center justify-between gap-3">
    
    <!-- Filter Dropdown & Scope Indicator -->
    <div class="flex items-center flex-wrap gap-2.5">
      <div class="relative flex items-center">
        <span class="absolute left-2.5 text-xs text-gray-400 pointer-events-none">🎯</span>
        <select id="feed-filter-select" onchange="setFilter(this.value)" class="bg-[#111827] border border-gray-700/80 hover:border-emerald-500/60 text-xs font-semibold text-gray-200 rounded-lg pl-7 pr-8 py-1.5 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 shadow-sm transition appearance-none cursor-pointer" title="Filter table signals by conviction verdict or noise">
          <option value="ALL" id="opt-filter-all">⚡ All Actionable (0)</option>
          <option value="BULLISH" id="opt-filter-bullish">🟢 Bullish Only (0)</option>
          <option value="BEARISH" id="opt-filter-bearish">🔴 Bearish Only (0)</option>
          <option value="PENDING" id="opt-filter-pending">⏳ Pending Approval (0)</option>
          <option value="NOISE" id="opt-filter-noise">🔇 Noise Suppressed (0)</option>
        </select>
        <span class="absolute right-2.5 text-[10px] text-gray-400 pointer-events-none">▼</span>
      </div>

      <!-- Scope Indicator Badge -->
      <div class="flex items-center gap-1.5 bg-[#111827] border border-gray-800 px-2.5 py-1.5 rounded-lg shadow-sm">
        <span class="text-xs text-gray-400 flex items-center gap-1">
          <span>📅</span>
          <span>Scope:</span>
        </span>
        <span id="session-scope-badge" class="px-2 py-0.5 text-[11px] font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 rounded flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          <span id="session-scope-text">Today Only</span>
        </span>
      </div>
    </div>

    <!-- Search input & View Controls -->
    <div class="flex items-center flex-wrap gap-2.5">
      <div class="relative">
        <input type="text" id="search-input" onkeyup="renderFeed()" placeholder="Search symbol or catalyst..." class="bg-[#111827] border border-gray-800 text-xs text-gray-200 placeholder-gray-500 rounded-lg pl-8 pr-3 py-1.5 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 w-52 sm:w-60 transition">
        <span class="absolute left-2.5 top-2 text-xs text-gray-500">🔍</span>
      </div>
      
      <!-- Toggle: Today's Signals Only Button -->
      <button onclick="loadTodaySignals()" id="btn-today-signals" class="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-600 transition flex items-center gap-1.5 shadow-sm active:scale-95" title="Filter to today's trading session signals only">
        <span>📅</span>
        <span>Today Only</span>
      </button>

      <!-- Load All History Button -->
      <button onclick="loadFeedHistory()" id="btn-load-history" class="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-[#1f293d] text-gray-300 hover:text-white border border-gray-700/80 hover:border-gray-600 transition flex items-center gap-1.5 shadow-sm active:scale-95" title="Load all past evaluated signals from database">
        <span>📜</span>
        <span>Show History (DB)</span>
      </button>

      <!-- Clear Display Button -->
      <button onclick="clearFeedList()" id="btn-clear-feed" class="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-rose-950/40 text-gray-300 hover:text-rose-200 border border-gray-700/80 hover:border-rose-500/50 transition flex items-center gap-1.5 shadow-sm active:scale-95" title="Clear displayed table list from screen (Database remains untouched)">
        <span>🗑️</span>
        <span>Clear Display</span>
      </button>

      <span class="text-xs text-gray-500 hidden xl:inline">Auto-Refreshes Daily</span>
    </div>

  </div>

  <!-- TABLE CONTAINER -->
  <main class="max-w-[1600px] mx-auto w-full px-6 pb-8 flex-1 flex flex-col">
    <div class="bg-[#111827] border border-gray-800 rounded-xl shadow-xl overflow-hidden flex-1 flex flex-col">
      <div class="overflow-x-auto custom-scrollbar flex-1">
        <table class="w-full text-left border-collapse min-w-[1100px]" id="feed-table">
          
          <!-- TABLE HEADER -->
          <thead>
            <tr class="bg-[#162032] border-b border-gray-800 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              <th class="py-3.5 px-4 w-32">Symbol / SecID</th>
              <th class="py-3.5 px-4 w-36">Date / Time</th>
              <th class="py-3.5 px-4">Catalyst & AI Rationale</th>
              <th class="py-3.5 px-4 w-44 text-center">LLM Verdict</th>
              <th class="py-3.5 px-4 w-52 text-right">Bracket Pricing</th>
              <th class="py-3.5 px-4 w-56 text-center">Order Status / Action</th>
            </tr>
          </thead>

          <!-- TABLE BODY -->
          <tbody id="table-body" class="divide-y divide-gray-800/80 text-xs">
            <!-- Dynamic Rows -->
          </tbody>

        </table>
      </div>

      <!-- EMPTY STATE -->
      <div id="empty-state" class="p-14 text-center bg-[#111827] my-auto">
        <div class="relative w-16 h-16 mx-auto mb-4 flex items-center justify-center">
          <span class="absolute w-16 h-16 rounded-full bg-emerald-500/10 animate-ping"></span>
          <span class="absolute w-12 h-12 rounded-full bg-emerald-500/20 animate-pulse"></span>
          <div class="w-10 h-10 rounded-full bg-[#162032] border border-emerald-500/40 flex items-center justify-center text-xl shadow-lg">
            📡
          </div>
        </div>
        <h3 class="text-sm font-bold text-white uppercase tracking-wider flex items-center justify-center gap-2">
          <span>Live Radar Active — Scanning NSE Corporate Feed</span>
        </h3>
        <p class="text-xs text-gray-400 max-w-md mx-auto mt-1.5 mb-3 leading-relaxed">
          Actively monitoring 228 F&O tickers on NSE. The AI filter automatically discards routine compliance noise and will alert here the moment an actionable market catalyst breaks.
        </p>
        <div class="inline-flex items-center gap-2 bg-[#0e1422] border border-gray-800 px-3.5 py-1.5 rounded-lg text-[11px] text-gray-300 font-mono mb-4 shadow-sm">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Last Exchange Scan: <span id="empty-last-check" class="text-emerald-400 font-bold">Just now</span></span>
          <span class="text-gray-600">•</span>
          <span>Status: <span class="text-indigo-300 font-semibold">Listening for catalysts...</span></span>
        </div>
        __SIM_EMPTY_BTN__
      </div>

    </div>
  </main>

  <!-- SLIDE-OUT DETAILS DRAWER (RIGHT OVERLAY) -->
  <div id="details-drawer-backdrop" onclick="closeDrawer()" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 opacity-0 pointer-events-none transition-opacity duration-300"></div>
  <aside id="details-drawer" class="fixed inset-y-0 right-0 w-full sm:w-[540px] bg-[#111827] border-l border-gray-700/80 shadow-2xl z-50 transform translate-x-full transition-transform duration-300 flex flex-col">
    <!-- Drawer Header -->
    <div class="px-5 py-4 border-b border-gray-800 flex items-center justify-between bg-[#162032]/80">
      <div class="flex items-center gap-2.5">
        <span id="drawer-symbol-badge" class="text-sm font-black px-2.5 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded tracking-wider">TICKER</span>
        <span id="drawer-sec-id" class="text-xs font-mono text-cyan-300 bg-cyan-950/80 px-2 py-0.5 border border-cyan-800/60 rounded">#0</span>
        <span id="drawer-sentiment-badge" class="text-xs font-bold px-2 py-0.5 rounded font-mono">BULLISH</span>
      </div>
      <div class="flex items-center gap-2">
        <button onclick="copyFilingText()" class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition" title="Copy Announcement Text">📋</button>
        <button onclick="closeDrawer()" class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 text-lg font-bold leading-none transition" title="Close Drawer (Esc)">✕</button>
      </div>
    </div>

    <!-- Drawer Content (Scrollable) -->
    <div class="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-4">
      
      <!-- Timing & Freshness Banner -->
      <div class="bg-[#0e1422] border border-gray-800 rounded-xl p-3 flex items-center justify-between text-xs font-mono">
        <div>
          <span class="text-gray-400">Filed Time:</span>
          <span id="drawer-time" class="text-white font-bold ml-1">--:--:--</span>
        </div>
        <div id="drawer-freshness-pill" class="px-2 py-0.5 rounded text-[11px] font-bold">
          Freshness
        </div>
      </div>

      <!-- Financial Metric Tags -->
      <div>
        <h4 class="text-[11px] font-bold uppercase text-gray-400 tracking-wider mb-1.5 flex items-center gap-1.5">
          <span>📊</span>
          <span>Extracted Financial Metrics</span>
        </h4>
        <div id="drawer-metric-badges" class="flex flex-wrap gap-1.5">
          <span class="text-xs text-gray-500 italic">No structured metrics extracted</span>
        </div>
      </div>

      <!-- AI Catalyst Analysis -->
      <div class="bg-indigo-950/30 border border-indigo-500/30 rounded-xl p-3.5 space-y-2">
        <div class="flex items-center justify-between border-b border-indigo-500/20 pb-2">
          <span class="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
            <span>🧠</span>
            <span id="drawer-catalyst-category">AI CATALYST AUDIT</span>
          </span>
          <span id="drawer-confidence-pill" class="text-xs font-mono font-bold text-indigo-200 bg-indigo-500/20 px-2 py-0.5 rounded">95% Conf</span>
        </div>
        <p id="drawer-summary" class="text-xs text-gray-200 leading-relaxed font-sans">
          Summary
        </p>
      </div>

      <!-- Complete Filing Text -->
      <div>
        <div class="flex items-center justify-between mb-1.5">
          <h4 class="text-[11px] font-bold uppercase text-gray-400 tracking-wider flex items-center gap-1.5">
            <span>📄</span>
            <span>Raw Exchange Announcement</span>
          </h4>
          <span id="drawer-seq-id" class="text-[10px] text-gray-500 font-mono">Seq ID: --</span>
        </div>
        <div class="bg-[#0b0f19] border border-gray-800 rounded-xl p-3.5">
          <p id="drawer-raw-text" class="text-gray-300 font-mono text-xs whitespace-pre-wrap leading-relaxed max-h-[280px] overflow-y-auto custom-scrollbar select-text">
            Text
          </p>
        </div>
      </div>

      <!-- Bracket Pricing Matrix -->
      <div class="bg-[#131b2e] border border-gray-800 rounded-xl p-3.5 space-y-2">
        <h4 class="text-[11px] font-bold uppercase text-gray-400 tracking-wider flex items-center gap-1.5">
          <span>🎯</span>
          <span>Super Order Execution Matrix</span>
        </h4>
        <div class="grid grid-cols-3 gap-2 font-mono text-center">
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-gray-800">
            <div class="text-[10px] text-gray-400">ENTRY LIMIT</div>
            <div id="drawer-entry-price" class="text-xs font-bold text-white mt-0.5">₹0.00</div>
          </div>
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-emerald-500/20">
            <div class="text-[10px] text-emerald-400">TARGET (3%)</div>
            <div id="drawer-target-price" class="text-xs font-bold text-emerald-400 mt-0.5">₹0.00</div>
          </div>
          <div class="bg-[#0b0f19] p-2 rounded-lg border border-rose-500/20">
            <div class="text-[10px] text-rose-400">STOP LOSS (1%)</div>
            <div id="drawer-sl-price" class="text-xs font-bold text-rose-400 mt-0.5">₹0.00</div>
          </div>
        </div>
        <div class="text-[10px] text-gray-500 font-mono flex items-center justify-between pt-1">
          <span id="drawer-qty-info">Position: -- sh</span>
          <span>Trailing Jump: 5.0 pts</span>
        </div>
      </div>

    </div>

    <!-- Drawer Footer Actions -->
    <div id="drawer-footer" class="p-4 border-t border-gray-800 bg-[#162032]/90 flex items-center justify-between gap-3">
      <button onclick="closeDrawer()" class="px-4 py-2 text-xs font-bold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition">Close</button>
      <div id="drawer-action-btn-container" class="flex-1 flex justify-end">
        <!-- Dynamic Action Button -->
      </div>
    </div>
  </aside>

  <!-- SAFETY EMERGENCY SQUARE-OFF MODAL -->
  <div id="squareoff-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 opacity-0 pointer-events-none transition-all duration-300">
    <div class="bg-[#111827] border border-rose-600/70 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 transform scale-95 transition-all duration-300 ring-2 ring-rose-500/30" id="squareoff-modal-card">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400 font-black text-xl">
          🛑
        </div>
        <div>
          <h3 class="text-sm font-bold text-white uppercase tracking-wider">Confirm Emergency Square-Off</h3>
          <p class="text-[11px] text-rose-300 mt-0.5">Flatten all active intraday positions immediately</p>
        </div>
      </div>
      <p class="text-xs text-gray-300 leading-relaxed bg-[#0b0f19] border border-rose-900/50 p-3 rounded-xl">
        This action will <b>immediately cancel all pending limit orders</b> and <b>market-close all open Dhan trading positions</b>. This cannot be undone.
      </p>
      <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-gray-800">
        <button onclick="closeSquareOffModal()" class="px-4 py-2 text-xs font-semibold text-gray-400 hover:text-white rounded-lg hover:bg-gray-800 transition">
          Cancel (Esc)
        </button>
        <button onclick="executeConfirmedSquareOff()" id="btn-confirm-squareoff" class="bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs px-4 py-2 rounded-lg transition shadow-lg shadow-rose-600/40 active:scale-95 flex items-center gap-1.5">
          <span>🛑 Yes, Square-Off All</span>
        </button>
      </div>
    </div>
  </div>

  <!-- KEYBOARD SHORTCUTS MODAL -->
  <div id="hotkeys-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 opacity-0 pointer-events-none transition-all duration-300">
    <div class="bg-[#111827] border border-gray-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 transform scale-95 transition-all duration-300" id="hotkeys-modal-card">
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <div class="flex items-center gap-2.5">
          <span class="text-lg">⌨️</span>
          <h3 class="text-sm font-bold text-white uppercase tracking-wider">Keyboard Hotkeys Cheat Sheet</h3>
        </div>
        <button onclick="closeHotkeysModal()" class="text-gray-400 hover:text-white text-lg font-bold p-1 rounded-lg hover:bg-gray-800 transition">✕</button>
      </div>
      <div class="grid grid-cols-2 gap-2.5 text-xs">
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Navigate Feed Down</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-emerald-400 border border-gray-700 rounded font-mono font-bold">J</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Navigate Feed Up</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-emerald-400 border border-gray-700 rounded font-mono font-bold">K</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Open Details Drawer</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-white border border-gray-700 rounded font-mono font-bold">Enter / Space</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Approve Buy Order</span>
          <kbd class="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded font-mono font-bold">A or B</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Approve Short Sell</span>
          <kbd class="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800 rounded font-mono font-bold">S</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Emergency Square-Off</span>
          <kbd class="px-2 py-0.5 bg-rose-900 text-white border border-rose-600 rounded font-mono font-bold">Shift + Q</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Toggle Mute Audio</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-gray-300 border border-gray-700 rounded font-mono font-bold">M</kbd>
        </div>
        <div class="bg-[#0b0f19] p-2.5 rounded-lg border border-gray-800 flex items-center justify-between">
          <span class="text-gray-300">Close Modals / Drawer</span>
          <kbd class="px-2 py-0.5 bg-gray-800 text-gray-300 border border-gray-700 rounded font-mono font-bold">Esc</kbd>
        </div>
      </div>
      <div class="flex justify-end pt-2 border-t border-gray-800">
        <button onclick="closeHotkeysModal()" class="px-4 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition">Got It</button>
      </div>
    </div>
  </div>

  <!-- DHAN LOGIN & AUTHENTICATION MODAL / SCREEN -->
  <div id="token-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 opacity-0 pointer-events-none transition-all duration-300">
    <div class="bg-[#111827] border border-gray-700/90 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5 transform scale-95 transition-all duration-300 max-h-[90vh] overflow-y-auto custom-scrollbar" id="token-modal-card">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-gray-800 pb-3.5">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-teal-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-lg shadow-inner">
            🔐
          </div>
          <div>
            <h3 class="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span>Login with DhanHQ</span>
              <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full font-mono">Broker Auth</span>
            </h3>
            <p class="text-[11px] text-gray-400 mt-0.5">Authenticate your Dhan trading account for live execution</p>
          </div>
        </div>
        <button onclick="closeTokenModal()" class="text-gray-400 hover:text-white text-lg font-bold p-1 rounded-lg hover:bg-gray-800 transition" title="Dismiss">✕</button>
      </div>

      <!-- Session Expired Alert Banner (Dynamic) -->
      <div id="login-session-alert" class="hidden text-xs p-3 rounded-xl border shadow-inner"></div>

      <!-- Option 1: 1-Click Login with Dhan (OAuth 2.0) -->
      <div class="bg-gradient-to-r from-emerald-950/40 via-teal-950/30 to-slate-900 border border-emerald-500/30 rounded-xl p-4 space-y-3 shadow-inner">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-base">⚡</span>
            <h4 class="text-xs font-bold text-emerald-300 uppercase tracking-wide">Option 1: 1-Click Login with Dhan</h4>
          </div>
          <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full font-mono">OAuth 2.0</span>
        </div>
        <p class="text-[11px] text-gray-300 leading-relaxed">
          Redirects to Dhan to log in securely via Mobile + OTP/TOTP. Token is automatically fetched & activated with zero copy-pasting.
        </p>

        <div class="pt-1">
          <button onclick="launchDhanOAuth()" id="btn-oauth-login" class="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs py-2.5 px-4 rounded-lg shadow-lg shadow-emerald-700/30 border border-emerald-400/40 flex items-center justify-center gap-2 transition active:scale-95">
            <span>🚀 Log In via Dhan Portal</span>
          </button>
        </div>
      </div>

      <!-- Divider -->
      <div class="flex items-center gap-3 my-2">
        <div class="flex-1 h-px bg-gray-800"></div>
        <span class="text-[10px] text-gray-500 font-mono uppercase tracking-wider">OR PASTE DIRECTLY</span>
        <div class="flex-1 h-px bg-gray-800"></div>
      </div>

      <!-- Option 2: Paste Access Token Manually -->
      <div class="bg-gray-900/80 border border-gray-800 rounded-xl p-3.5 space-y-2.5">
        <div class="flex items-center justify-between">
          <h4 class="text-xs font-bold text-gray-300 uppercase tracking-wide">Option 2: Paste Access Token</h4>
          <a href="https://web.dhan.co" target="_blank" rel="noopener noreferrer" class="text-[10px] text-blue-400 hover:underline">Get from web.dhan.co ↗</a>
        </div>
        <div class="flex gap-2">
          <input type="password" id="modal-manual-token" placeholder="Paste 24-hr Access Token (JWT)..." class="flex-1 bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-lg px-3 py-2 focus:outline-none focus:border-emerald-500 font-mono placeholder:text-gray-600">
          <button onclick="saveManualToken()" id="btn-save-manual-token" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs px-3.5 py-2 rounded-lg transition shadow">Save</button>
        </div>
      </div>

      <!-- Modal Status Feedback -->
      <div id="modal-feedback" class="hidden text-xs p-2.5 rounded-lg"></div>

      <!-- Modal Actions -->
      <div class="flex items-center justify-end gap-2.5 pt-2 border-t border-gray-800">
        <button onclick="closeTokenModal()" class="text-xs font-semibold text-gray-400 hover:text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-800 transition">
          <span>Close</span>
        </button>
      </div>

    </div>
  </div>

  <!-- TOAST NOTIFICATION -->
  <div id="toast" class="fixed bottom-5 right-5 bg-gray-900 border border-gray-700 text-white text-xs px-4 py-3 rounded-lg shadow-2xl transition-all duration-300 opacity-0 translate-y-4 pointer-events-none z-50 flex items-center gap-2">
    <span id="toast-icon">ℹ️</span>
    <span id="toast-msg">Notification</span>
  </div>

  <!-- JAVASCRIPT LOGIC -->
  <script>
    let isAutoOrder = true;
    let isDryRun = true;
    let feedItems = [];
    let currentFilter = 'ALL';
    let expandedRows = new Set();
    let selectedRowIndex = -1;
    let activeDrawerItem = null;

    // --- WEB AUDIO API SYNTHESIZER ---
    class WebAudioSynth {
      constructor() {
        this.ctx = null;
        this.enabled = localStorage.getItem('sound_enabled') !== 'false';
      }
      init() {
        if (!this.ctx) {
          const AudioContext = window.AudioContext || window.webkitAudioContext;
          if (AudioContext) this.ctx = new AudioContext();
        }
        if (this.ctx && this.ctx.state === 'suspended') {
          this.ctx.resume();
        }
      }
      playTone(freq, type, duration, gainVal = 0.15) {
        if (!this.enabled) return;
        try {
          this.init();
          if (!this.ctx) return;
          const osc = this.ctx.createOscillator();
          const gain = this.ctx.createGain();
          osc.type = type;
          osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
          gain.gain.setValueAtTime(gainVal, this.ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + duration);
          osc.connect(gain);
          gain.connect(this.ctx.destination);
          osc.start();
          osc.stop(this.ctx.currentTime + duration);
        } catch(e) {}
      }
      playBullishChime() {
        if (!this.enabled) return;
        this.playTone(523.25, 'triangle', 0.15, 0.2); // C5
        setTimeout(() => this.playTone(659.25, 'triangle', 0.2, 0.25), 100); // E5
        setTimeout(() => this.playTone(783.99, 'triangle', 0.35, 0.3), 200); // G5
      }
      playBearishChime() {
        if (!this.enabled) return;
        this.playTone(587.33, 'sawtooth', 0.15, 0.15); // D5
        setTimeout(() => this.playTone(493.88, 'sawtooth', 0.2, 0.2), 100); // B4
        setTimeout(() => this.playTone(415.30, 'sawtooth', 0.35, 0.25), 200); // G#4
      }
      playWarningChime() {
        if (!this.enabled) return;
        this.playTone(440, 'square', 0.15, 0.1);
        setTimeout(() => this.playTone(440, 'square', 0.2, 0.15), 150);
      }
      playOrderChime() {
        if (!this.enabled) return;
        this.playTone(587.33, 'sine', 0.12, 0.2);
        setTimeout(() => this.playTone(880, 'sine', 0.25, 0.25), 80);
      }
    }
    const synth = new WebAudioSynth();

    function updateSoundUI() {
      const btn = document.getElementById('sound-toggle-btn');
      const icon = document.getElementById('sound-icon');
      const label = document.getElementById('sound-label');
      if (!btn) return;
      if (synth.enabled) {
        btn.className = 'bg-emerald-950/60 hover:bg-emerald-900/60 active:scale-95 text-emerald-300 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition border border-emerald-500/50 flex items-center gap-1.5 shadow-sm';
        if (icon) icon.textContent = '🔊';
        if (label) label.textContent = 'Audio ON';
      } else {
        btn.className = 'bg-gray-800 hover:bg-gray-700 active:scale-95 text-gray-400 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition border border-gray-700 flex items-center gap-1.5 shadow';
        if (icon) icon.textContent = '🔇';
        if (label) label.textContent = 'Muted';
      }
    }

    function toggleAudioSound() {
      synth.init();
      synth.enabled = !synth.enabled;
      localStorage.setItem('sound_enabled', synth.enabled ? 'true' : 'false');
      updateSoundUI();
      if (synth.enabled) {
        synth.playBullishChime();
        showToast('🔊 Synthesized audio chimes enabled', '🔔');
      } else {
        showToast('🔇 Audio chimes muted', '🔕');
      }
    }

    // --- DESKTOP NOTIFICATIONS & TAB BLINKER ---
    function initDesktopNotifications() {
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
      }
    }

    function sendDesktopNotification(title, body) {
      if ('Notification' in window && Notification.permission === 'granted') {
        try {
          new Notification(title, { body: body });
        } catch(e) {}
      }
    }

    let originalDocTitle = document.title;
    let blinkInterval = null;
    function triggerTabAlert(symbol, sentiment) {
      if (document.hasFocus()) return;
      if (blinkInterval) clearInterval(blinkInterval);
      let state = false;
      let count = 0;
      blinkInterval = setInterval(() => {
        count++;
        document.title = state ? `🚨 [${sentiment}] ${symbol} CATALYST!` : originalDocTitle;
        state = !state;
        if (count > 24 || document.hasFocus()) {
          clearInterval(blinkInterval);
          blinkInterval = null;
          document.title = originalDocTitle;
        }
      }, 750);
    }
    window.addEventListener('focus', () => {
      if (blinkInterval) {
        clearInterval(blinkInterval);
        blinkInterval = null;
        document.title = originalDocTitle;
      }
    });

    // --- FINANCIAL METRICS REGEX EXTRACTOR ---
    function extractFinancialMetrics(text) {
      if (!text) return [];
      const metrics = [];
      const inrMatches = text.match(/(?:Rs\.?|₹|INR)\s*[\d,]+(?:\.\d+)?\s*(?:Cr(?:ore)?|Lakh|mn|bn)?/gi);
      if (inrMatches) inrMatches.forEach(m => metrics.push({ type: 'currency', value: m.trim() }));
      const usdMatches = text.match(/\$\s*[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B|mn|bn)?/gi);
      if (usdMatches) usdMatches.forEach(m => metrics.push({ type: 'currency', value: m.trim() }));
      const pctMatches = text.match(/[+-]?\d+(?:\.\d+)?%/g);
      if (pctMatches) pctMatches.forEach(m => metrics.push({ type: 'percent', value: m.trim() }));
      const keywords = ['USFDA', 'FDA Approval', 'EIR', 'Bonus Issue', 'Dividend', 'Contract Win', 'Order Win', 'Acquisition', 'Demerger', 'Patent Granted'];
      keywords.forEach(kw => {
        if (new RegExp('\\b' + kw + '\\b', 'i').test(text)) {
          metrics.push({ type: 'keyword', value: kw });
        }
      });
      const seen = new Set();
      return metrics.filter(item => {
        const key = item.value.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, 5);
    }

    // --- 180s FRESHNESS ENGINE ---
    function getFreshnessState(anDt) {
      if (!anDt) return { isStale: false, ageSec: 0, text: 'FRESH', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', remainingSec: 180 };
      try {
        let parsed = null;
        if (anDt.includes(' ')) {
          const parts = anDt.split(' ');
          const dateParts = parts[0].split('-');
          const timeParts = parts[1].split(':');
          if (dateParts.length === 3 && timeParts.length >= 2) {
            const y = parseInt(dateParts[0]), m = parseInt(dateParts[1]) - 1, d = parseInt(dateParts[2]);
            const hr = parseInt(timeParts[0]), min = parseInt(timeParts[1]), sec = parseInt(timeParts[2] || 0);
            parsed = new Date(y, m, d, hr, min, sec);
          }
        }
        if (!parsed || isNaN(parsed.getTime())) {
          parsed = new Date(anDt);
        }
        if (isNaN(parsed.getTime())) {
          return { isStale: false, ageSec: 0, text: 'FRESH', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', remainingSec: 180 };
        }
        const now = new Date();
        const ageSec = Math.max(0, Math.floor((now.getTime() - parsed.getTime()) / 1000));
        const remainingSec = Math.max(0, 180 - ageSec);
        const isStale = ageSec > 180;
        let text = '';
        let badgeClass = '';
        if (isStale) {
          text = `⏱️ Stale (+${ageSec}s)`;
          badgeClass = 'bg-gray-800 text-gray-500 border-gray-700';
        } else if (remainingSec >= 120) {
          text = `⚡ ${remainingSec}s left`;
          badgeClass = 'bg-emerald-950/80 text-emerald-300 border-emerald-500/50 shadow-sm';
        } else if (remainingSec >= 45) {
          text = `⏳ ${remainingSec}s left`;
          badgeClass = 'bg-amber-950/80 text-amber-300 border-amber-500/50 shadow-sm';
        } else {
          text = `🔥 ${remainingSec}s left`;
          badgeClass = 'bg-rose-950/80 text-rose-300 border-rose-500/50 shadow-sm animate-pulse';
        }
        return { isStale, ageSec, remainingSec, text, badgeClass };
      } catch (e) {
        return { isStale: false, ageSec: 0, text: 'FRESH', badgeClass: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', remainingSec: 180 };
      }
    }

    function updateCountdowns() {
      const badges = document.querySelectorAll('.timer-badge');
      badges.forEach(badge => {
        const anDt = badge.getAttribute('data-andt');
        const fresh = getFreshnessState(anDt);
        badge.textContent = fresh.text;
        badge.className = `timer-badge px-2 py-0.5 rounded text-[10px] font-mono font-bold border transition-colors ${fresh.badgeClass}`;
      });

      // Update drawer freshness pill if drawer is currently open
      if (activeDrawerItem) {
        const drawerPill = document.getElementById('drawer-freshness-pill');
        if (drawerPill) {
          const fresh = getFreshnessState(activeDrawerItem.an_dt);
          drawerPill.textContent = fresh.text;
          drawerPill.className = `px-2 py-0.5 rounded text-[11px] font-bold border ${fresh.badgeClass}`;
        }
      }
    }

    // --- RISK BUDGET GAUGE ---
    function updateRiskBudgetGauge(placedCount) {
      const maxOrders = 3;
      const dotsEl = document.getElementById('risk-gauge-dots');
      const textEl = document.getElementById('risk-gauge-text');
      if (!dotsEl || !textEl) return;
      const count = Math.min(placedCount, maxOrders);
      let dots = '';
      for (let i = 0; i < maxOrders; i++) {
        dots += (i < count) ? '■ ' : '□ ';
      }
      dotsEl.textContent = `[${dots.trim()}]`;
      textEl.textContent = `${count}/${maxOrders} Orders`;
      if (count >= maxOrders) {
        dotsEl.className = 'text-rose-400 font-bold text-xs tracking-wider';
        textEl.className = 'text-rose-300 text-[11px] font-bold';
      } else if (count > 0) {
        dotsEl.className = 'text-amber-400 font-bold text-xs tracking-wider';
        textEl.className = 'text-amber-300 text-[11px] font-bold';
      } else {
        dotsEl.className = 'text-emerald-400 font-bold text-xs tracking-wider';
        textEl.className = 'text-gray-300 text-[11px] font-bold';
      }
    }

    function showToast(msg, icon = '✅') {
      const toast = document.getElementById('toast');
      document.getElementById('toast-icon').textContent = icon;
      document.getElementById('toast-msg').textContent = msg;
      toast.classList.remove('opacity-0', 'translate-y-4', 'pointer-events-none');
      toast.classList.add('opacity-100', 'translate-y-0');
      setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-4', 'pointer-events-none');
        toast.classList.remove('opacity-100', 'translate-y-0');
      }, 3500);
    }

    // --- MODALS CONTROLLER ---
    function openHotkeysModal() {
      const modal = document.getElementById('hotkeys-modal');
      const card = document.getElementById('hotkeys-modal-card');
      if (!modal || !card) return;
      modal.classList.remove('opacity-0', 'pointer-events-none');
      modal.classList.add('opacity-100');
      card.classList.remove('scale-95');
      card.classList.add('scale-100');
    }

    function closeHotkeysModal() {
      const modal = document.getElementById('hotkeys-modal');
      const card = document.getElementById('hotkeys-modal-card');
      if (!modal || !card) return;
      modal.classList.add('opacity-0', 'pointer-events-none');
      modal.classList.remove('opacity-100');
      card.classList.add('scale-95');
      card.classList.remove('scale-100');
    }

    function openSquareOffModal() {
      const modal = document.getElementById('squareoff-modal');
      const card = document.getElementById('squareoff-modal-card');
      if (!modal || !card) return;
      synth.playWarningChime();
      modal.classList.remove('opacity-0', 'pointer-events-none');
      modal.classList.add('opacity-100');
      card.classList.remove('scale-95');
      card.classList.add('scale-100');
    }

    function closeSquareOffModal() {
      const modal = document.getElementById('squareoff-modal');
      const card = document.getElementById('squareoff-modal-card');
      if (!modal || !card) return;
      modal.classList.add('opacity-0', 'pointer-events-none');
      modal.classList.remove('opacity-100');
      card.classList.add('scale-95');
      card.classList.remove('scale-100');
    }

    async function executeConfirmedSquareOff() {
      closeSquareOffModal();
      const btn = document.getElementById('square-off-btn');
      if (btn) {
        btn.disabled = true;
        btn.classList.add('opacity-50');
      }
      showToast('Initiating intraday square-off sequence...', '🛑');
      try {
        const res = await fetch('/api/trades/square-off', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          const closedCount = (data.result && data.result.closed_positions) ? data.result.closed_positions.length : 0;
          const cancelledCount = (data.result && data.result.cancelled_orders) ? data.result.cancelled_orders.length : 0;
          showToast(`Square-off completed: ${cancelledCount} orders cancelled, ${closedCount} positions closed.`, '✅');
          fetchFeed();
        } else {
          const err = await res.json().catch(() => ({ detail: 'Square-off failed' }));
          showToast(`Square-off error: ${err.detail || 'Failed'}`, '❌');
        }
      } catch (err) {
        showToast('Failed to trigger square-off request', '❌');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('opacity-50');
        }
      }
    }

    function confirmEmergencySquareOff() {
      openSquareOffModal();
    }

    // --- DETAILS DRAWER CONTROLLER ---
    function openDrawer(seqId) {
      const item = feedItems.find(i => i.seq_id === seqId);
      if (!item) return;
      activeDrawerItem = item;
      
      const drawer = document.getElementById('details-drawer');
      const backdrop = document.getElementById('details-drawer-backdrop');
      if (!drawer || !backdrop) return;
      
      document.getElementById('drawer-symbol-badge').textContent = item.symbol;
      document.getElementById('drawer-sec-id').textContent = item.security_id && item.security_id !== '0' ? `#${item.security_id}` : '#0';
      
      const sentimentBadge = document.getElementById('drawer-sentiment-badge');
      const isBullish = item.sentiment === 'BULLISH';
      const isBearish = item.sentiment === 'BEARISH';
      const isNoise = !!item.is_noise;
      const isMarketClosed = item.sentiment === 'MARKET_CLOSED';
      
      if (isMarketClosed) {
        sentimentBadge.textContent = '🌙 MARKET CLOSED';
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-amber-950/70 text-amber-300 border border-amber-800/60';
      } else if (isNoise) {
        sentimentBadge.textContent = '🔇 NOISE';
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-gray-800 text-gray-400 border border-gray-700';
      } else if (isBullish) {
        sentimentBadge.textContent = `🟢 BULLISH (${item.confidence}%)`;
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40';
      } else {
        sentimentBadge.textContent = `🔴 BEARISH (${item.confidence}%)`;
        sentimentBadge.className = 'text-xs font-bold px-2 py-0.5 rounded font-mono bg-rose-500/20 text-rose-300 border border-rose-500/40';
      }
      
      document.getElementById('drawer-time').textContent = item.an_dt || item.timestamp || '--:--:--';
      const fresh = getFreshnessState(item.an_dt);
      const freshnessPill = document.getElementById('drawer-freshness-pill');
      freshnessPill.textContent = fresh.text;
      freshnessPill.className = `px-2 py-0.5 rounded text-[11px] font-bold border ${fresh.badgeClass}`;
      
      // Extracted metrics
      const metricsContainer = document.getElementById('drawer-metric-badges');
      const metrics = extractFinancialMetrics(`${item.desc} ${item.details || ''}`);
      if (metrics.length > 0) {
        metricsContainer.innerHTML = metrics.map(m => {
          if (m.type === 'currency') {
            return `<span class="px-2 py-0.5 text-xs font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 rounded-lg shadow-sm">💰 ${m.value}</span>`;
          } else if (m.type === 'percent') {
            return `<span class="px-2 py-0.5 text-xs font-mono font-bold bg-indigo-950/80 text-indigo-300 border border-indigo-700/60 rounded-lg shadow-sm">📈 ${m.value}</span>`;
          } else {
            return `<span class="px-2 py-0.5 text-xs font-mono font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-700/60 rounded-lg shadow-sm">🏆 ${m.value}</span>`;
          }
        }).join('');
      } else {
        metricsContainer.innerHTML = `<span class="text-xs text-gray-500 italic">No structured numerical metrics found</span>`;
      }
      
      document.getElementById('drawer-catalyst-category').textContent = (item.catalyst_type || 'GENERAL').toUpperCase();
      document.getElementById('drawer-confidence-pill').textContent = `${item.confidence || 0}% Conf`;
      document.getElementById('drawer-summary').textContent = item.summary || item.filter_reason || 'No summary available.';
      
      document.getElementById('drawer-seq-id').textContent = `Seq ID: ${item.seq_id}`;
      document.getElementById('drawer-raw-text').textContent = item.details || item.desc || 'No announcement details.';
      
      const order = item.order || {};
      document.getElementById('drawer-entry-price').textContent = `₹${order.entry_price ? order.entry_price.toFixed(2) : (order.ltp ? order.ltp.toFixed(2) : '0.00')}`;
      document.getElementById('drawer-target-price').textContent = `₹${order.target_price ? order.target_price.toFixed(2) : '0.00'}`;
      document.getElementById('drawer-sl-price').textContent = `₹${order.stop_loss_price ? order.stop_loss_price.toFixed(2) : '0.00'}`;
      document.getElementById('drawer-qty-info').textContent = `Position: ${order.quantity || 0} sh`;
      
      // Footer Action Button
      const btnContainer = document.getElementById('drawer-action-btn-container');
      if (isNoise || isMarketClosed) {
        btnContainer.innerHTML = `<span class="text-xs font-mono text-gray-500 italic">${item.filter_reason || 'Not Actionable'}</span>`;
      } else if (order.placed) {
        btnContainer.innerHTML = `
          <span class="px-3 py-1.5 text-xs font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-lg flex items-center gap-1.5 shadow-sm">
            <span>✅</span> Order Placed (${order.order_id || 'SIMULATED'})
          </span>
        `;
      } else if (order.status === 'PENDING_APPROVAL') {
        if (item.is_stale) {
          btnContainer.innerHTML = `
            <button disabled class="bg-gray-800 text-gray-500 font-bold text-xs px-4 py-2 rounded-lg border border-gray-700 cursor-not-allowed flex items-center gap-1.5 opacity-60">
              <span>⏱️ Window Expired (>180s)</span>
            </button>
          `;
        } else {
          const act = isBullish ? 'BUY' : 'SELL';
          const btnBg = isBullish ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/40 border-emerald-400/40' : 'bg-rose-600 hover:bg-rose-500 shadow-rose-600/40 border-rose-400/40';
          const label = isBullish ? '🚀 Approve Buy Order [A]' : '🔻 Approve Short Sell [S]';
          btnContainer.innerHTML = `
            <button onclick="placeOrder('${item.seq_id}', '${item.symbol}', '${act}', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}'); closeDrawer();" class="${btnBg} text-white font-bold text-xs px-4 py-2 rounded-lg transition shadow-lg active:scale-95 flex items-center gap-1.5 border">
              <span>${label}</span>
            </button>
          `;
        }
      } else {
        btnContainer.innerHTML = `<span class="text-xs font-mono text-gray-500">Status: ${order.status || 'SKIPPED'}</span>`;
      }
      
      drawer.classList.remove('translate-x-full');
      backdrop.classList.remove('opacity-0', 'pointer-events-none');
      backdrop.classList.add('opacity-100');
    }

    function closeDrawer() {
      const drawer = document.getElementById('details-drawer');
      const backdrop = document.getElementById('details-drawer-backdrop');
      if (drawer) drawer.classList.add('translate-x-full');
      if (backdrop) {
        backdrop.classList.remove('opacity-100');
        backdrop.classList.add('opacity-0', 'pointer-events-none');
      }
      activeDrawerItem = null;
    }

    function copyFilingText() {
      if (activeDrawerItem) {
        const text = `${activeDrawerItem.symbol} [${activeDrawerItem.an_dt || ''}]\n${activeDrawerItem.desc}\n\n${activeDrawerItem.details || ''}`;
        navigator.clipboard.writeText(text).then(() => {
          showToast('📋 Copied announcement to clipboard!', '📋');
        }).catch(() => {
          showToast('Failed copying to clipboard', '❌');
        });
      }
    }

    // --- KEYBOARD HOTKEYS EVENT LISTENER ---
    function updateRowSelection() {
      const rows = document.querySelectorAll('#table-body tr.feed-row');
      rows.forEach((r, idx) => {
        if (idx === selectedRowIndex) {
          r.classList.add('ring-2', 'ring-emerald-400', 'bg-[#1e293b]');
          r.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          r.classList.remove('ring-2', 'ring-emerald-400', 'bg-[#1e293b]');
        }
      });
    }

    document.addEventListener('keydown', function(e) {
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
      const key = e.key.toUpperCase();
      const isShift = e.shiftKey;
      
      if (key === 'ESCAPE') {
        closeDrawer();
        closeHotkeysModal();
        closeSquareOffModal();
        closeTokenModal();
        return;
      }
      if (key === '?' || (e.key === '?' && isShift)) {
        openHotkeysModal();
        return;
      }
      if (key === 'Q' && isShift) {
        confirmEmergencySquareOff();
        return;
      }
      if (key === 'M') {
        toggleAudioSound();
        return;
      }
      
      const rows = document.querySelectorAll('#table-body tr.feed-row');
      if (rows.length === 0) return;
      
      if (key === 'J' || e.key === 'ArrowDown') {
        selectedRowIndex = Math.min(rows.length - 1, selectedRowIndex + 1);
        updateRowSelection();
        e.preventDefault();
      } else if (key === 'K' || e.key === 'ArrowUp') {
        selectedRowIndex = Math.max(0, selectedRowIndex - 1);
        updateRowSelection();
        e.preventDefault();
      } else if (key === 'ENTER' || e.key === ' ') {
        if (selectedRowIndex >= 0 && selectedRowIndex < rows.length) {
          const seqId = rows[selectedRowIndex].getAttribute('data-seq-id');
          if (seqId) openDrawer(seqId);
          e.preventDefault();
        }
      } else if (key === 'A' || key === 'B') {
        if (selectedRowIndex >= 0 && selectedRowIndex < rows.length) {
          const seqId = rows[selectedRowIndex].getAttribute('data-seq-id');
          const item = feedItems.find(i => i.seq_id === seqId);
          if (item && item.order && item.order.status === 'PENDING_APPROVAL' && !item.is_stale) {
            placeOrder(item.seq_id, item.symbol, 'BUY', item.order.ltp || 300.0, item.confidence, item.catalyst_type);
            synth.playOrderChime();
            e.preventDefault();
          }
        }
      } else if (key === 'S') {
        if (selectedRowIndex >= 0 && selectedRowIndex < rows.length) {
          const seqId = rows[selectedRowIndex].getAttribute('data-seq-id');
          const item = feedItems.find(i => i.seq_id === seqId);
          if (item && item.order && item.order.status === 'PENDING_APPROVAL' && !item.is_stale) {
            placeOrder(item.seq_id, item.symbol, 'SELL', item.order.ltp || 300.0, item.confidence, item.catalyst_type);
            synth.playOrderChime();
            e.preventDefault();
          }
        }
      }
    });

    async function launchDhanOAuth() {
      const feedback = document.getElementById('modal-feedback');
      const btn = document.getElementById('btn-oauth-login');

      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<span>⏳ Connecting to Dhan...</span>';

      try {
        const res = await fetch('/api/auth/dhan/login');
        const data = await res.json();

        if (res.ok && data.success && data.login_url) {
          showToast('Redirecting to official Dhan login portal...', '⚡');
          setTimeout(() => {
            window.location.href = data.login_url;
          }, 400);
        } else {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = `❌ ${data.message || 'Failed to initiate login. Please check server .env configuration.'}`;
        }
      } catch (err) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '❌ Failed connecting to Dhan login service.';
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<span>🚀 Log In via Dhan Portal</span>';
      }
    }

    function toggleUserMenu() {
      const dropdown = document.getElementById('user-menu-dropdown');
      if (dropdown) dropdown.classList.toggle('hidden');
    }

    document.addEventListener('click', function(e) {
      const container = document.getElementById('user-account-container');
      const dropdown = document.getElementById('user-menu-dropdown');
      if (dropdown && container && !container.contains(e.target)) {
        dropdown.classList.add('hidden');
      }
    });

    async function logoutDhan() {
      try {
        const res = await fetch('/api/auth/logout', { method: 'POST' });
        if (res.ok) {
          showToast('👋 Logged out from Dhan trading session.', 'ℹ️');
          fetchTokenStatus();
          setTimeout(() => {
            openLoginScreen();
          }, 300);
        } else {
          showToast('Logout request failed', '❌');
        }
      } catch (err) {
        showToast('Logout request failed', '❌');
      }
    }

    async function logoutApp() {
      try {
        await fetch('/api/auth/app-logout', { method: 'POST' });
        window.location.href = '/login?logged_out=true';
      } catch (err) {
        window.location.href = '/login?logged_out=true';
      }
    }

    function openLoginScreen() {
      openTokenModal();
    }

    async function fetchTokenStatus() {
      try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
          const data = await res.json();
          const badge = document.getElementById('telemetry-token-status');
          const headerMask = document.getElementById('header-token-mask');
          const dot = document.getElementById('token-indicator-dot');
          const currentBadge = document.getElementById('current-token-badge');
          const tokenBtn = document.getElementById('token-btn');
          const headerLoginBtn = document.getElementById('btn-header-login');
          const userProfileWidget = document.getElementById('user-profile-widget');
          const userClientIdLabel = document.getElementById('user-client-id-label');
          const menuClientId = document.getElementById('menu-client-id');
          const menuExpiry = document.getElementById('menu-expiry-info');
          const sessionAlert = document.getElementById('login-session-alert');

          if (data.authenticated) {
            if (headerLoginBtn) headerLoginBtn.classList.add('hidden');
            if (userProfileWidget) userProfileWidget.classList.remove('hidden');
            if (userClientIdLabel) userClientIdLabel.textContent = data.client_id ? `DHAN ${data.client_id}` : 'DHAN USER';
            if (menuClientId) menuClientId.textContent = `Client ID: ${data.client_id || 'N/A'}`;
            if (menuExpiry) {
              menuExpiry.textContent = data.expiry_message || '🟢 Active Session';
              menuExpiry.className = 'text-[10px] text-emerald-400 font-mono mt-0.5';
            }
            if (badge) {
              badge.textContent = 'Active';
              badge.className = 'text-emerald-400 font-mono font-bold';
            }
            if (headerMask) {
              headerMask.textContent = 'Active';
              headerMask.className = 'text-xs font-mono font-bold text-emerald-400 group-hover:text-emerald-300';
            }
            if (dot) {
              dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
            }
            if (tokenBtn) {
              tokenBtn.className = 'group bg-[#162032] hover:bg-[#1f293d] active:scale-95 border border-emerald-500/40 hover:border-emerald-400/70 px-3.5 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2.5';
            }
            if (currentBadge) {
              currentBadge.innerHTML = `<span class="text-emerald-400 font-bold">🟢 Active</span> <span class="text-gray-400 text-[10px]">(${data.expiry_message || 'Valid session'})</span>`;
            }
            if (sessionAlert) {
              sessionAlert.className = 'hidden';
            }
          } else if (data.is_expired) {
            const expText = data.expiry_message || 'Token Expired';
            if (headerLoginBtn) headerLoginBtn.classList.remove('hidden');
            if (userProfileWidget) userProfileWidget.classList.add('hidden');
            if (badge) {
              badge.textContent = 'Expired';
              badge.className = 'text-rose-400 font-mono font-bold';
            }
            if (headerMask) {
              headerMask.textContent = 'Expired';
              headerMask.className = 'text-xs font-mono font-bold text-rose-400 group-hover:text-rose-300';
            }
            if (dot) {
              dot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-ping';
            }
            if (tokenBtn) {
              tokenBtn.className = 'group bg-rose-950/40 hover:bg-rose-900/50 active:scale-95 border border-rose-500/70 hover:border-rose-400 px-3.5 py-1.5 rounded-xl transition-all shadow-lg shadow-rose-950/50 flex items-center gap-2.5 ring-2 ring-rose-500/30';
            }
            if (currentBadge) {
              currentBadge.innerHTML = `<span class="text-rose-400 font-bold">⚠️ Expired</span> <span class="text-gray-400 text-[10px]">(${expText})</span>`;
            }
            if (sessionAlert) {
              sessionAlert.className = 'block bg-rose-500/15 border border-rose-500/40 text-rose-200 text-xs p-3 rounded-xl font-medium shadow-inner';
              sessionAlert.innerHTML = `⚠️ <b>Dhan Session Expired:</b> ${expText}. Please 1-Click Login to reconnect live trading.`;
            }
            if (!window._hasAlertedExpiry) {
              window._hasAlertedExpiry = true;
              showToast(`❌ Dhan Session EXPIRED: ${expText}. Please login.`, '⚠️');
              if (!window._hasDismissedModal) {
                openLoginScreen();
              }
            }
          } else {
            if (headerLoginBtn) headerLoginBtn.classList.remove('hidden');
            if (userProfileWidget) userProfileWidget.classList.add('hidden');
            if (badge) {
              badge.textContent = 'Not Logged In';
              badge.className = 'text-amber-400 font-mono font-semibold';
            }
            if (headerMask) {
              headerMask.textContent = 'Not Logged In';
              headerMask.className = 'text-xs font-mono font-bold text-amber-400/80 group-hover:text-amber-300';
            }
            if (dot) {
              dot.className = 'w-2 h-2 rounded-full bg-amber-400';
            }
            if (tokenBtn) {
              tokenBtn.className = 'group bg-[#162032] hover:bg-[#1f293d] active:scale-95 border border-gray-700 hover:border-gray-500 px-3.5 py-1.5 rounded-xl transition-all shadow-md flex items-center gap-2.5';
            }
            if (currentBadge) {
              currentBadge.textContent = 'Current: Not Configured';
            }
            if (sessionAlert) {
              sessionAlert.className = 'block bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs p-3 rounded-xl font-medium';
              sessionAlert.innerHTML = `ℹ️ <b>Dhan Login Required:</b> Connect your DhanHQ trading account via 1-Click OAuth.`;
            }
          }
        }
      } catch (err) {
        console.error('Failed fetching token status:', err);
      }
    }

    function openTokenModal() {
      const modal = document.getElementById('token-modal');
      const card = document.getElementById('token-modal-card');
      const feedback = document.getElementById('modal-feedback');
      if (feedback) feedback.className = 'hidden text-xs p-2.5 rounded-lg';
      fetchTokenStatus();
      modal.classList.remove('opacity-0', 'pointer-events-none');
      modal.classList.add('opacity-100');
      card.classList.remove('scale-95');
      card.classList.add('scale-100');
    }

    function closeTokenModal() {
      const modal = document.getElementById('token-modal');
      const card = document.getElementById('token-modal-card');
      modal.classList.add('opacity-0', 'pointer-events-none');
      modal.classList.remove('opacity-100');
      card.classList.add('scale-95');
      card.classList.remove('scale-100');
    }

    async function saveManualToken() {
      const tokenInput = document.getElementById('modal-manual-token');
      const token = tokenInput ? tokenInput.value.trim() : '';
      const feedback = document.getElementById('modal-feedback');
      const btn = document.getElementById('btn-save-manual-token');

      if (!token) {
        if (feedback) {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = 'Please paste a valid Dhan Access Token.';
        }
        return;
      }

      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Saving...';
      }

      try {
        const res = await fetch('/api/settings/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_token: token,
            client_id: '1104872040',
            dry_run: isDryRun
          })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          if (feedback) {
            feedback.className = 'block bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs p-2.5 rounded-lg';
            feedback.textContent = '✅ Access Token updated and active in production!';
          }
          showToast('✅ Dhan Access Token updated!', '🔑');
          tokenInput.value = '';
          fetchTokenStatus();
          setTimeout(() => { closeTokenModal(); }, 1200);
        } else {
          if (feedback) {
            feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
            feedback.textContent = `❌ ${data.expiry_message || 'Failed to update token.'}`;
          }
        }
      } catch (err) {
        if (feedback) {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = '❌ Failed to connect to server.';
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = 'Save';
        }
      }
    }

    function updateExecutionModeUI() {
      const btn = document.getElementById('toggle-mode-btn');
      const label = document.getElementById('mode-status-label');
      const indicator = document.getElementById('mode-status-indicator');
      const modeText = document.getElementById('mode-text');

      if (!btn || !label || !indicator) return;

      if (isDryRun) {
        btn.className = 'px-2.5 py-1 text-xs font-bold rounded transition flex items-center gap-1.5 shadow bg-amber-600/90 text-amber-100 hover:bg-amber-600 border border-amber-500/40';
        label.textContent = 'VIRTUAL';
        indicator.className = 'w-2 h-2 rounded-full bg-amber-300';
        if (modeText) {
          modeText.textContent = 'VIRTUAL (Simulated)';
          modeText.className = 'text-amber-400 font-mono font-semibold';
        }
      } else {
        btn.className = 'px-2.5 py-1 text-xs font-bold rounded transition flex items-center gap-1.5 shadow bg-emerald-600 text-white hover:bg-emerald-500 border border-emerald-400/40 animate-pulse-subtle';
        label.textContent = 'LIVE';
        indicator.className = 'w-2 h-2 rounded-full bg-white animate-pulse';
        if (modeText) {
          modeText.textContent = 'LIVE (Real Orders)';
          modeText.className = 'text-emerald-400 font-mono font-bold';
        }
      }
    }

    async function toggleExecutionMode() {
      const targetDryRun = !isDryRun;

      if (!targetDryRun) {
        try {
          const res = await fetch('/api/settings/token');
          if (res.ok) {
            const data = await res.json();
            if (!data.is_configured || data.is_expired) {
              showToast('⚠️ Cannot enable Live Trading: Dhan token is missing or expired!', '⚠️');
              openTokenModal();
              return;
            }
          }
        } catch (e) {}
      }

      try {
        const res = await fetch('/api/toggle-dry-run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dry_run: targetDryRun })
        });
        if (res.ok) {
          const data = await res.json();
          isDryRun = data.dry_run;
          updateExecutionModeUI();
          if (!isDryRun) {
            showToast('🚨 LIVE TRADING ENABLED! Real Dhan market orders will be placed.', '⚡');
          } else {
            showToast('🛡️ Switched to VIRTUAL mode (Simulated execution).', 'ℹ️');
          }
        } else {
          showToast('Failed to toggle Execution Mode', '❌');
        }
      } catch (err) {
        showToast('Failed to toggle Execution Mode', '❌');
      }
    }

    let lastPolledTimestamp = Date.now();

    function updatePollerTimer() {
      const elapsedSec = Math.max(0, Math.floor((Date.now() - lastPolledTimestamp) / 1000));
      const tag = document.getElementById('poller-elapsed-tag');
      const emptyTag = document.getElementById('empty-last-check');
      const elapsedStr = elapsedSec <= 1 ? 'Just now' : `${elapsedSec}s ago`;
      if (tag) {
        tag.textContent = elapsedStr;
        if (elapsedSec > 120) {
          tag.className = 'text-[10px] text-amber-300 bg-amber-950/60 border border-amber-500/30 px-2 py-0.5 rounded font-mono font-semibold';
        } else {
          tag.className = 'text-[10px] text-emerald-300 bg-emerald-950/60 border border-emerald-500/30 px-2 py-0.5 rounded font-mono font-semibold';
        }
      }
      if (emptyTag) emptyTag.textContent = elapsedStr;
    }

    function computeMarketStatusClient() {
      try {
        const now = new Date();
        const istOffset = 5.5 * 60 * 60 * 1000;
        const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
        const istDate = new Date(utc + istOffset);
        
        const day = istDate.getDay();
        if (day === 0 || day === 6) {
          return false;
        }
        const hour = istDate.getHours();
        const min = istDate.getMinutes();
        const totalMinutes = hour * 60 + min;
        const marketOpenMinutes = 9 * 60 + 15;
        const marketCloseMinutes = 15 * 60 + 30;
        return totalMinutes >= marketOpenMinutes && totalMinutes <= marketCloseMinutes;
      } catch (e) {
        return false;
      }
    }

    function renderMarketStatusUI(isOpen) {
      const badge = document.getElementById('market-status-badge');
      const dot = document.getElementById('market-status-dot');
      const text = document.getElementById('market-status-text');

      if (!badge || !dot || !text) return;

      if (isOpen) {
        badge.className = 'px-2.5 py-0.5 text-[10px] font-bold rounded-full flex items-center gap-1.5 shadow-sm border bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
        badge.title = 'NSE Equity Market is OPEN (09:15 to 15:30 IST)';
        dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
        text.textContent = 'MARKET OPEN';
      } else {
        badge.className = 'px-2.5 py-0.5 text-[10px] font-bold rounded-full flex items-center gap-1.5 shadow-sm border bg-rose-500/20 text-rose-300 border-rose-500/40';
        badge.title = 'NSE Equity Market is CLOSED (Regular hours: Mon-Fri 09:15 to 15:30 IST)';
        dot.className = 'w-2 h-2 rounded-full bg-rose-400';
        text.textContent = 'MARKET CLOSED';
      }
    }

    function renderCutoffUI(isAllowed, cutoffTime, reason) {
      const badge = document.getElementById('cutoff-status-badge');
      const dot = document.getElementById('cutoff-status-dot');
      const text = document.getElementById('cutoff-status-text');
      if (!badge || !dot || !text) return;

      if (isAllowed) {
        badge.className = 'px-2.5 py-0.5 text-[10px] font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 rounded-full flex items-center gap-1.5 shadow-sm';
        dot.className = 'w-1.5 h-1.5 rounded-full bg-emerald-400';
        text.textContent = `CUTOFF ${cutoffTime || '14:45'}`;
        badge.title = `Trades allowed until ${cutoffTime || '14:45'} IST. Auto Square-off at 15:00 IST.`;
      } else {
        badge.className = 'px-2.5 py-0.5 text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full flex items-center gap-1.5 shadow-sm';
        dot.className = 'w-1.5 h-1.5 rounded-full bg-amber-400';
        text.textContent = 'TRADES CUTOFF (14:45)';
        badge.title = reason || `Trades blocked past ${cutoffTime || '14:45'} IST cutoff.`;
      }
    }

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const data = await res.json();
          isAutoOrder = data.auto_order;
          isDryRun = data.dry_run;
          updateAutoOrderUI();
          updateExecutionModeUI();
          const isOpen = (typeof data.is_market_open === 'boolean') ? data.is_market_open : computeMarketStatusClient();
          renderMarketStatusUI(isOpen);
          if (data.is_trade_allowed !== undefined) {
            renderCutoffUI(data.is_trade_allowed, data.trade_cutoff_time, data.trade_allowed_reason);
          }
          const dbStatus = document.getElementById('db-status');
          if (dbStatus && data.db_description) {
            dbStatus.textContent = data.db_description;
          }
          if (data.last_polled_ts) {
            lastPolledTimestamp = data.last_polled_ts * 1000;
          }
          if (document.getElementById('poller-last-time') && data.last_polled_time) {
            document.getElementById('poller-last-time').textContent = data.last_polled_time;
          }
          if (document.getElementById('poller-noise-count')) {
            document.getElementById('poller-noise-count').textContent = data.suppressed_noise_count || '0';
          }
          if (document.getElementById('poller-fno-count') && data.fno_universe_size) {
            document.getElementById('poller-fno-count').textContent = data.fno_universe_size;
          }
          if (document.getElementById('poller-interval-val') && data.poll_interval_seconds) {
            document.getElementById('poller-interval-val').textContent = `${data.poll_interval_seconds}s`;
          }
          if (data.view_mode) {
            updateScopeUI(data.view_mode === 'TODAY');
          }
          updatePollerTimer();
        }
      } catch (err) {
        console.error('Failed fetching status:', err);
      }
    }

    function updateAutoOrderUI() {
      const btn = document.getElementById('toggle-auto-btn');
      const label = document.getElementById('auto-status-label');
      const indicator = document.getElementById('auto-status-indicator');
      
      if (isAutoOrder) {
        btn.className = 'px-2.5 py-1 text-xs font-bold rounded transition bg-emerald-600 text-white hover:bg-emerald-500 shadow flex items-center gap-1.5';
        label.textContent = 'ENABLED (Auto-Place)';
        indicator.className = 'w-2 h-2 rounded-full bg-white animate-pulse';
      } else {
        btn.className = 'px-2.5 py-1 text-xs font-bold rounded transition bg-amber-600 text-white hover:bg-amber-500 shadow flex items-center gap-1.5';
        label.textContent = 'MANUAL (Prompt Approval)';
        indicator.className = 'w-2 h-2 rounded-full bg-amber-200';
      }
    }

    async function toggleAutoOrder() {
      try {
        const newStatus = !isAutoOrder;
        const res = await fetch('/api/toggle-auto-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_order: newStatus })
        });
        if (res.ok) {
          const data = await res.json();
          isAutoOrder = data.auto_order;
          updateAutoOrderUI();
          showToast(`Auto-Order set to: ${isAutoOrder ? 'ENABLED (Auto-Place)' : 'MANUAL APPROVAL'}`, '⚙️');
          fetchFeed();
        }
      } catch (err) {
        showToast('Failed to toggle Auto-Order', '❌');
      }
    }

    function setFilter(filter) {
      currentFilter = filter || 'ALL';
      const select = document.getElementById('feed-filter-select');
      if (select && select.value !== currentFilter) {
        select.value = currentFilter;
      }
      selectedRowIndex = -1;
      renderFeed();
    }

    function toggleRowDetails(seqId) {
      openDrawer(seqId);
    }

    let currentScope = 'TODAY';

    function updateScopeUI(isTodayOnly) {
      currentScope = isTodayOnly ? 'TODAY' : 'ALL_HISTORY';
      const badge = document.getElementById('session-scope-badge');
      const text = document.getElementById('session-scope-text');
      const btnToday = document.getElementById('btn-today-signals');
      const btnHist = document.getElementById('btn-load-history');

      if (badge && text) {
        if (isTodayOnly) {
          badge.className = 'px-2 py-0.5 text-[11px] font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 rounded flex items-center gap-1';
          text.textContent = 'Today Only';
        } else {
          badge.className = 'px-2 py-0.5 text-[11px] font-mono font-bold bg-indigo-950/80 text-indigo-300 border border-indigo-800/80 rounded flex items-center gap-1';
          text.textContent = 'Full History';
        }
      }

      if (btnToday && btnHist) {
        if (isTodayOnly) {
          btnToday.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-950/80 text-emerald-300 border border-emerald-600 transition flex items-center gap-1.5 shadow-sm';
          btnHist.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-[#1f293d] text-gray-300 hover:text-white border border-gray-700/80 hover:border-gray-600 transition flex items-center gap-1.5 shadow-sm active:scale-95';
        } else {
          btnToday.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-[#1f293d] text-gray-300 hover:text-white border border-gray-700/80 hover:border-gray-600 transition flex items-center gap-1.5 shadow-sm active:scale-95';
          btnHist.className = 'px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-950/80 text-indigo-300 border border-indigo-600 transition flex items-center gap-1.5 shadow-sm';
        }
      }
    }

    async function clearFeedList() {
      if (!feedItems || feedItems.length === 0) {
        showToast('Table display is already empty.', 'ℹ️');
        return;
      }
      try {
        const res = await fetch('/api/feed/clear', { method: 'POST' });
        if (res.ok) {
          feedItems = [];
          expandedRows.clear();
          selectedRowIndex = -1;
          renderFeed();
          showToast('🧹 Display cleared! All signals & orders remain safely stored in DB for audit.', '✅');
        } else {
          showToast('Failed to clear feed list', '❌');
        }
      } catch (err) {
        showToast('Failed to clear feed list', '❌');
      }
    }

    async function loadTodaySignals() {
      showToast("Loading today's trading signals...", "📅");
      try {
        const res = await fetch('/api/feed/load-history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ today_only: true })
        });
        if (res.ok) {
          const data = await res.json();
          await fetchFeed();
          updateScopeUI(true);
          showToast(`Loaded ${data.count} signals for today's session.`, '✅');
        } else {
          showToast("Failed to load today's signals", '❌');
        }
      } catch (err) {
        showToast("Error connecting to server", '❌');
      }
    }

    async function loadFeedHistory() {
      showToast('Loading all evaluated historical signals from database...', '📜');
      try {
        const res = await fetch('/api/feed/load-history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ today_only: false })
        });
        if (res.ok) {
          const data = await res.json();
          await fetchFeed();
          updateScopeUI(false);
          showToast(`Loaded ${data.count} total historical signals from database.`, '✅');
        } else {
          showToast('Failed to load past signals', '❌');
        }
      } catch (err) {
        showToast('Error loading signals from database', '❌');
      }
    }

    async function fetchFeed() {
      try {
        const res = await fetch('/api/feed');
        if (res.ok) {
          feedItems = await res.json();
          renderFeed();
        }
      } catch (err) {
        console.error('Failed fetching feed:', err);
      }
    }

    function renderFeed() {
      const tbody = document.getElementById('table-body');
      const emptyState = document.getElementById('empty-state');
      const searchVal = (document.getElementById('search-input').value || '').toLowerCase().trim();

      // Counts
      let totalBullish = 0, totalBearish = 0, totalPlaced = 0, totalPending = 0, totalNoise = 0, totalPassed = 0;
      feedItems.forEach(item => {
        if (item.is_noise) {
          totalNoise++;
        } else {
          totalPassed++;
          if (item.sentiment === 'BULLISH') totalBullish++;
          if (item.sentiment === 'BEARISH') totalBearish++;
          if (item.order && item.order.placed) totalPlaced++;
          if (item.order && item.order.status === 'PENDING_APPROVAL') totalPending++;
        }
      });

      document.getElementById('stat-total').textContent = totalPassed;
      document.getElementById('stat-bullish').textContent = totalBullish;
      document.getElementById('stat-bearish').textContent = totalBearish;
      document.getElementById('stat-placed').textContent = totalPlaced;
      document.getElementById('stat-pending').textContent = totalPending;

      // Update Pill Count Badges
      if (document.getElementById('badge-count-all')) document.getElementById('badge-count-all').textContent = totalPassed;
      if (document.getElementById('badge-count-bullish')) document.getElementById('badge-count-bullish').textContent = totalBullish;
      if (document.getElementById('badge-count-bearish')) document.getElementById('badge-count-bearish').textContent = totalBearish;
      if (document.getElementById('badge-count-pending')) document.getElementById('badge-count-pending').textContent = totalPending;
      if (document.getElementById('badge-count-noise')) document.getElementById('badge-count-noise').textContent = totalNoise;

      // Update Risk Budget Gauge
      updateRiskBudgetGauge(totalPlaced);

      // Keep hidden select options matching tests
      if (document.getElementById('opt-filter-all')) {
        document.getElementById('opt-filter-all').textContent = `⚡ All Passed (${totalPassed})`;
      }
      if (document.getElementById('opt-filter-bullish')) {
        document.getElementById('opt-filter-bullish').textContent = `🟢 Bullish Only (${totalBullish})`;
      }
      if (document.getElementById('opt-filter-bearish')) {
        document.getElementById('opt-filter-bearish').textContent = `🔴 Bearish Only (${totalBearish})`;
      }
      if (document.getElementById('opt-filter-pending')) {
        document.getElementById('opt-filter-pending').textContent = `⏳ Pending Approval (${totalPending})`;
      }
      if (document.getElementById('opt-filter-noise')) {
        document.getElementById('opt-filter-noise').textContent = `🔇 Noise Suppressed (${totalNoise})`;
      }

      // Filter logic
      const filtered = feedItems.filter(item => {
        if (currentFilter === 'NOISE') {
          if (!item.is_noise) return false;
        } else {
          if (item.is_noise) return false;
          if (currentFilter === 'BULLISH' && item.sentiment !== 'BULLISH') return false;
          if (currentFilter === 'BEARISH' && item.sentiment !== 'BEARISH') return false;
          if (currentFilter === 'PENDING' && (!item.order || item.order.status !== 'PENDING_APPROVAL')) return false;
        }

        if (searchVal) {
          const matchSym = (item.symbol || '').toLowerCase().includes(searchVal);
          const matchDesc = (item.desc || '').toLowerCase().includes(searchVal);
          const matchCat = (item.catalyst_type || '').toLowerCase().includes(searchVal);
          const matchReason = (item.filter_reason || '').toLowerCase().includes(searchVal);
          if (!matchSym && !matchDesc && !matchCat && !matchReason) return false;
        }
        return true;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        return;
      }
      emptyState.style.display = 'none';

      tbody.innerHTML = filtered.map((item, idx) => createTableRowHTML(item, idx)).join('');
      updateRowSelection();
      updateCountdowns();
    }

    function createTableRowHTML(item, idx) {
      const isBullish = item.sentiment === 'BULLISH';
      const isNoise = !!item.is_noise;
      const isMarketClosed = item.sentiment === 'MARKET_CLOSED' || (item.filter_reason && (item.filter_reason.toLowerCase().includes('market closed') || item.filter_reason.toLowerCase().includes('trade cutoff') || item.filter_reason.toLowerCase().includes('market is not open')));
      const order = item.order || {};

      // Directional Border Accent Class
      let borderAccentClass = 'border-l-4 border-l-emerald-500';
      if (isMarketClosed) borderAccentClass = 'border-l-4 border-l-amber-500';
      else if (isNoise) borderAccentClass = 'border-l-4 border-l-gray-600';
      else if (!isBullish) borderAccentClass = 'border-l-4 border-l-rose-500';

      // Extracted inline metric badges (up to 2)
      const metrics = extractFinancialMetrics(`${item.desc} ${item.details || ''}`).slice(0, 2);
      const metricsHTML = metrics.map(m => {
        if (m.type === 'currency') {
          return `<span class="px-1.5 py-0.2 text-[10px] font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-800 rounded">💰 ${m.value}</span>`;
        } else if (m.type === 'percent') {
          return `<span class="px-1.5 py-0.2 text-[10px] font-mono font-bold bg-indigo-950 text-indigo-300 border border-indigo-800 rounded">📈 ${m.value}</span>`;
        } else {
          return `<span class="px-1.5 py-0.2 text-[10px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800 rounded">🏆 ${m.value}</span>`;
        }
      }).join(' ');

      // Freshness state calculation
      const fresh = getFreshnessState(item.an_dt);

      // LLM Verdict Badge
      let verdictHTML = '';
      if (isMarketClosed) {
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-amber-950/70 text-amber-300 border border-amber-800/60 flex items-center gap-1.5 shadow-sm">
              <span>🌙</span>
              <span>MARKET CLOSED</span>
            </span>
            <span class="text-[10px] text-amber-400/80 font-mono mt-1">${item.filter_reason || 'Outside 09:15-14:45 IST'}</span>
          </div>
        `;
      } else if (isNoise) {
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-gray-800 text-gray-400 border border-gray-700 flex items-center gap-1.5 shadow-sm">
              <span>🔇</span>
              <span>SUPPRESSED</span>
            </span>
            <span class="text-[10px] text-gray-500 font-mono mt-1">${item.filter_reason || 'Noise / Routine'}</span>
          </div>
        `;
      } else if (isBullish) {
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 shadow-sm">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              BULLISH 🟢 ${item.confidence}%
            </span>
            <span class="text-[10px] text-emerald-400 font-mono mt-1">High Conviction (≥1.5%)</span>
          </div>
        `;
      } else {
        verdictHTML = `
          <div class="inline-flex flex-col items-center">
            <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1.5 shadow-sm">
              <span class="w-2 h-2 rounded-full bg-rose-400"></span>
              BEARISH 🔴 ${item.confidence}%
            </span>
            <span class="text-[10px] text-rose-400 font-mono mt-1">Negative Catalyst</span>
          </div>
        `;
      }

      // Bracket Pricing Column
      let pricingHTML = '';
      if (isMarketClosed) {
        pricingHTML = `
          <div class="text-right text-gray-500 font-mono text-xs">
            <div>LTP: ₹${order.ltp ? order.ltp.toFixed(2) : '0.00'}</div>
            <div class="text-[10px] text-amber-500/80 font-mono">LLM Skipped (Market Closed)</div>
          </div>
        `;
      } else if (isNoise) {
        pricingHTML = `
          <div class="text-right text-gray-600 font-mono text-xs">
            <div>Excluded from Orders</div>
            <div class="text-[10px] text-gray-600">${item.filter_reason || 'Filtered Out'}</div>
          </div>
        `;
      } else if (isBullish) {
        pricingHTML = `
          <div class="text-right font-mono space-y-0.5">
            <div class="text-white font-bold">Limit: <span class="text-emerald-400 font-semibold">₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'}</span></div>
            <div class="text-[11px] text-gray-400">
              TP: <span class="text-emerald-300 font-semibold">₹${order.target_price ? order.target_price.toFixed(2) : '0.00'} (+3%)</span>
            </div>
            <div class="text-[11px] text-gray-400">
              SL: <span class="text-rose-400 font-semibold">₹${order.stop_loss_price ? order.stop_loss_price.toFixed(2) : '0.00'} (-1%)</span>
            </div>
            <div class="text-[10px] text-gray-500">Qty: ${order.quantity} sh • Trail: 5.0 pts</div>
          </div>
        `;
      } else {
        pricingHTML = `
          <div class="text-right font-mono space-y-0.5">
            <div class="text-white font-bold">Limit: <span class="text-rose-400 font-semibold">₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'}</span></div>
            <div class="text-[11px] text-gray-400">
              TP: <span class="text-emerald-300 font-semibold">₹${order.target_price ? order.target_price.toFixed(2) : '0.00'} (-3%)</span>
            </div>
            <div class="text-[11px] text-gray-400">
              SL: <span class="text-rose-400 font-semibold">₹${order.stop_loss_price ? order.stop_loss_price.toFixed(2) : '0.00'} (+1%)</span>
            </div>
            <div class="text-[10px] text-gray-500">Qty: ${order.quantity} sh • Trail: 5.0 pts</div>
          </div>
        `;
      }

      // Order Action Column
      let actionHTML = '';
      if (isMarketClosed) {
        actionHTML = `
          <div class="flex flex-col items-center text-center font-mono">
            <span class="px-2.5 py-1 text-[11px] font-bold bg-amber-950/60 text-amber-300 border border-amber-900/60 rounded flex items-center gap-1 shadow-sm">
              <span>🌙</span> CLOSED
            </span>
            <span class="text-[10px] text-gray-500 mt-1 truncate max-w-[150px]" title="${item.filter_reason || 'Market Closed'}">
              ${item.filter_reason || 'Market Closed'}
            </span>
          </div>
        `;
      } else if (isNoise) {
        actionHTML = `
          <div class="flex flex-col items-center text-center font-mono">
            <span class="px-2.5 py-1 text-[11px] font-bold bg-gray-900/90 text-gray-500 border border-gray-800 rounded flex items-center gap-1 shadow-sm">
              <span>🔇</span> NOISE
            </span>
            <span class="text-[10px] text-gray-600 mt-1 truncate max-w-[150px]" title="${item.filter_reason || 'Filtered'}">
              ${item.filter_reason || 'Filtered'}
            </span>
          </div>
        `;
      } else if (isBullish) {
        if (order.placed) {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2.5 py-1 text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-md flex items-center gap-1 shadow-sm">
                <span>✅</span> PLACED (Auto)
              </span>
              <span class="text-[10px] text-gray-400 mt-1 truncate max-w-[170px]" title="${order.order_id}">
                ID: <span class="text-gray-200 font-semibold">${order.order_id || 'VIRTUAL_SIMULATED'}</span>
              </span>
              <span class="text-[10px] text-emerald-400 mt-0.5">@ ₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'} (${order.quantity} sh)</span>
            </div>
          `;
        } else if (order.status === 'PENDING_APPROVAL') {
          if (item.is_stale) {
            actionHTML = `
              <div class="flex flex-col items-center gap-1 font-mono">
                <button disabled class="bg-gray-800/80 text-gray-500 font-bold text-xs px-3 py-1.5 rounded-lg border border-gray-700/60 cursor-not-allowed flex items-center gap-1.5 opacity-60" title="News catalyst is older than 180 seconds. Order blocked to prevent stale trade execution.">
                  <span>⏱️</span>
                  <span>Stale (>180s)</span>
                </button>
                <span class="text-[10px] text-amber-500/80 font-mono">⚠️ Window Expired</span>
              </div>
            `;
          } else {
            actionHTML = `
              <div class="flex flex-col items-center gap-1.5">
                <button onclick="event.stopPropagation(); placeOrder('${item.seq_id}', '${item.symbol}', 'BUY', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}')" class="bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold text-xs px-3.5 py-1.5 rounded-lg transition shadow-lg shadow-emerald-600/30 border border-emerald-400/40 flex items-center gap-1.5">
                  <span>🚀</span>
                  <span>Approve Buy [A]</span>
                </button>
                <span class="text-[10px] text-amber-400 font-mono animate-pulse">⏳ Awaiting Approval</span>
              </div>
            `;
          }
        } else if (order.status === 'RECORDED') {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-400 border border-gray-700 rounded flex items-center gap-1 shadow-sm">
                <span>📜</span> HISTORICAL
              </span>
              <span class="text-[10px] text-gray-500 mt-1">
                ${item.is_stale ? '⚠️ Past Event' : 'Recorded'}
              </span>
            </div>
          `;
        } else {
          actionHTML = `
            <div class="text-center text-[11px] text-gray-500 font-mono">
              <span>⏸️ Skipped</span>
            </div>
          `;
        }
      } else {
        // Bearish
        if (order.placed) {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2.5 py-1 text-[11px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded-md flex items-center gap-1 shadow-sm">
                <span>🔻</span> SHORTED (Auto)
              </span>
              <span class="text-[10px] text-gray-400 mt-1 truncate max-w-[170px]" title="${order.order_id}">
                ID: <span class="text-gray-200 font-semibold">${order.order_id || 'VIRTUAL_SIMULATED'}</span>
              </span>
              <span class="text-[10px] text-rose-400 mt-0.5">@ ₹${order.entry_price ? order.entry_price.toFixed(2) : '0.00'} (${order.quantity} sh)</span>
            </div>
          `;
        } else if (order.status === 'PENDING_APPROVAL') {
          if (item.is_stale) {
            actionHTML = `
              <div class="flex flex-col items-center gap-1 font-mono">
                <button disabled class="bg-gray-800/80 text-gray-500 font-bold text-xs px-3 py-1.5 rounded-lg border border-gray-700/60 cursor-not-allowed flex items-center gap-1.5 opacity-60" title="News catalyst is older than 180 seconds. Order blocked to prevent stale trade execution.">
                  <span>⏱️</span>
                  <span>Stale (>180s)</span>
                </button>
                <span class="text-[10px] text-amber-500/80 font-mono">⚠️ Window Expired</span>
              </div>
            `;
          } else {
            actionHTML = `
              <div class="flex flex-col items-center gap-1.5">
                <button onclick="event.stopPropagation(); placeOrder('${item.seq_id}', '${item.symbol}', 'SELL', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}')" class="bg-rose-600 hover:bg-rose-500 active:scale-95 text-white font-bold text-xs px-3.5 py-1.5 rounded-lg transition shadow-lg shadow-rose-600/30 border border-rose-400/40 flex items-center gap-1.5">
                  <span>🔻</span>
                  <span>Short Sell [S]</span>
                </button>
                <span class="text-[10px] text-amber-400 font-mono animate-pulse">⏳ Awaiting Approval</span>
              </div>
            `;
          }
        } else if (order.status === 'RECORDED') {
          actionHTML = `
            <div class="flex flex-col items-center text-center font-mono">
              <span class="px-2 py-0.5 text-[10px] font-bold bg-gray-800 text-gray-400 border border-gray-700 rounded flex items-center gap-1 shadow-sm">
                <span>📜</span> HISTORICAL
              </span>
              <span class="text-[10px] text-gray-500 mt-1">
                ${item.is_stale ? '⚠️ Past Event' : 'Recorded'}
              </span>
            </div>
          `;
        } else {
          actionHTML = `
            <div class="text-center text-[11px] text-gray-500 font-mono">
              <span>⏸️ Skipped</span>
            </div>
          `;
        }
      }

      // Main Row with Directional Accent & Drawer Trigger
      return `
        <tr onclick="openDrawer('${item.seq_id}')" data-seq-id="${item.seq_id}" class="feed-row ${borderAccentClass} cursor-pointer select-none transition-colors border-b border-gray-800/80 ${isNoise ? 'opacity-75 hover:opacity-100 bg-[#0d1322]' : ''}">
          
          <!-- Symbol & SecID -->
          <td class="py-3 px-4 align-middle">
            <div class="flex items-center gap-2">
              <span class="text-sm font-black ${isNoise ? 'text-gray-300' : 'text-white'} px-2 py-0.5 bg-gray-800 border border-gray-700 rounded tracking-wider">${item.symbol}</span>
              ${item.security_id && item.security_id !== '0' ? `<span class="text-[10px] font-mono px-1.5 py-0.5 bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 rounded">#${item.security_id}</span>` : ''}
            </div>
            <div class="text-[10px] text-gray-500 mt-1 font-mono">${item.filter_reason && item.filter_reason.includes('Non-F&O') ? 'NSE_EQ • Equity' : 'NSE_EQ • F&O'}</div>
          </td>

          <!-- Date & Time + 180s Countdown Badge -->
          <td class="py-3 px-4 align-middle text-gray-300 font-mono text-xs whitespace-nowrap">
            <div class="font-bold text-gray-100 flex items-center gap-1">
              <span>🕒</span>
              <span>${item.an_dt && item.an_dt.includes(' ') ? item.an_dt.split(' ')[1] : (item.timestamp || item.an_dt || '--:--:--')}</span>
            </div>
            <div class="text-[11px] text-gray-400 mt-0.5 flex items-center gap-1">
              <span>📅</span>
              <span>${item.an_dt && item.an_dt.includes(' ') ? item.an_dt.split(' ')[0] : 'Today'}</span>
            </div>
            ${isMarketClosed ? `
              <div class="text-[10px] text-amber-400/90 font-semibold mt-1 flex items-center gap-1">
                <span>🌙</span><span>MARKET CLOSED</span>
              </div>
            ` : (isNoise ? `
              <div class="text-[10px] text-gray-500 font-semibold mt-1 flex items-center gap-1">
                <span>🔇</span><span>SUPPRESSED</span>
              </div>
            ` : `
              <div class="mt-1 flex items-center">
                <span data-andt="${item.an_dt || ''}" class="timer-badge px-2 py-0.5 rounded text-[10px] font-mono font-bold border transition-colors ${fresh.badgeClass}">${fresh.text}</span>
              </div>
            `)}
          </td>

          <!-- Catalyst & Headline + Extracted Metric Tags -->
          <td class="py-3 px-4 align-middle">
            <div class="flex items-center flex-wrap gap-1.5 mb-1">
              ${isMarketClosed ? `
                <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800/60 font-mono">
                  ${item.filter_reason || 'MARKET_CLOSED'}
                </span>
                <span class="text-[11px] text-amber-500/80 font-mono">🌙 LLM Skipped</span>
              ` : (isNoise ? `
                <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-gray-900 text-gray-400 border border-gray-800 font-mono">
                  ${item.filter_reason || 'ROUTINE_NOISE'}
                </span>
                <span class="text-[11px] text-gray-500 font-mono">🔇 Filtered Out</span>
              ` : `
                <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/80 font-mono">
                  ${item.catalyst_type}
                </span>
                <span class="text-[11px] text-emerald-400 font-mono">⚡ Passed</span>
              `)}
              ${metricsHTML}
            </div>
            <div class="text-xs font-semibold ${isNoise ? 'text-gray-300' : 'text-gray-100'} hover:text-white flex items-center gap-1.5">
              <span>${item.desc}</span>
              <span class="text-[10px] text-gray-500 font-mono">↗</span>
            </div>
            <div class="text-[11px] text-gray-400 italic mt-1 border-l ${isMarketClosed ? 'border-amber-700/60 text-amber-400/70' : (isNoise ? 'border-gray-700 text-gray-500' : 'border-indigo-500/50')} pl-2 line-clamp-1">
              "${item.summary}"
            </div>
          </td>

          <!-- LLM Verdict -->
          <td class="py-3 px-4 align-middle text-center">
            ${verdictHTML}
          </td>

          <!-- Pricing -->
          <td class="py-3 px-4 align-middle">
            ${pricingHTML}
          </td>

          <!-- Action / Status -->
          <td class="py-3 px-4 align-middle text-center">
            ${actionHTML}
          </td>

        </tr>
      `;
    }

    async function placeOrder(seq_id, symbol, action, ltp, confidence, catalyst_type) {
      try {
        const act = (action || 'BUY').toUpperCase();
        const actionLabel = act === 'SELL' ? 'Short Sell' : 'Buy';
        showToast(`Placing ${actionLabel} Super Order for ${symbol}...`, '⏳');
        const res = await fetch('/api/orders/place', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            seq_id: seq_id,
            symbol: symbol,
            action: act,
            product_type: 'INTRADAY',
            confidence: confidence,
            catalyst_type: catalyst_type,
            ltp: ltp
          })
        });

        if (res.ok) {
          const data = await res.json();
          synth.playOrderChime();
          showToast(`${actionLabel} Super Order Placed for ${symbol}! Order ID: ${data.order_id}`, act === 'SELL' ? '🔻' : '🚀');
          fetchFeed();
        } else {
          const err = await res.json();
          showToast(`Order failed: ${err.detail || 'Unknown error'}`, '❌');
        }
      } catch (err) {
        showToast(`Failed placing order for ${symbol}`, '❌');
      }
    }

    async function triggerSimulation() {
      const btn = document.getElementById('sim-btn');
      if (btn) {
        btn.disabled = true;
        btn.classList.add('opacity-50');
      }
      showToast('Running Gemini 3.7 Flash simulation cycle...', '🤖');
      try {
        const res = await fetch('/api/simulate', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          showToast(`Simulation complete! Ingested ${data.processed_count} catalyst filings.`, '✅');
          fetchFeed();
        } else {
          const err = await res.json().catch(() => ({ detail: 'Simulation disabled' }));
          showToast(`Simulation failed: ${err.detail || 'Access forbidden'}`, '❌');
        }
      } catch (err) {
        showToast('Simulation request failed', '❌');
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('opacity-50');
        }
      }
    }

    function connectSSE() {
      const evtSource = new EventSource('/api/events');
      evtSource.onmessage = function(event) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'NEW_CATALYST') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
            if (payload.data) {
              const item = payload.data;
              const isBull = item.sentiment === 'BULLISH';
              if (isBull) synth.playBullishChime();
              else synth.playBearishChime();
              sendDesktopNotification(`🚨 [${item.sentiment}] ${item.symbol} Catalyst!`, item.desc || item.summary);
              triggerTabAlert(item.symbol, item.sentiment);
            }
          } else if (payload.type === 'ORDER_PLACED') {
            synth.playOrderChime();
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
          } else if (payload.type === 'AUTO_ORDER_TOGGLE' || payload.type === 'TOKEN_UPDATED' || payload.type === 'MODE_TOGGLED' || payload.type === 'FEED_CLEARED') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
          } else if (payload.type === 'FEED_HISTORY_LOADED') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
            if (payload.data && payload.data.view_mode) {
              updateScopeUI(payload.data.view_mode === 'TODAY');
            }
          } else if (payload.type === 'DAY_ROLLOVER') {
            const newDate = (payload.data && payload.data.new_date) ? payload.data.new_date : 'Today';
            showToast(`🌅 New Trading Day (${newDate})! Feed refreshed for today.`, '📅');
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
            updateScopeUI(true);
          } else if (payload.type === 'AUTO_SQUARE_OFF' || payload.type === 'MANUAL_SQUARE_OFF') {
            synth.playWarningChime();
            const label = payload.type === 'AUTO_SQUARE_OFF' ? '⏰ 15:00 Auto Square-Off' : '🛑 Manual Square-Off';
            showToast(`${label} executed! Intraday positions flattened.`, '⚠️');
            fetchFeed();
            fetchStatus();
          } else if (payload.type === 'POLL_CYCLE_COMPLETED') {
            if (payload.data && payload.data.last_polled_ts) {
              lastPolledTimestamp = payload.data.last_polled_ts * 1000;
            }
            if (document.getElementById('poller-last-time') && payload.data.last_polled_time) {
              document.getElementById('poller-last-time').textContent = payload.data.last_polled_time;
            }
            if (document.getElementById('poller-noise-count')) {
              document.getElementById('poller-noise-count').textContent = payload.data.suppressed_noise_count || '0';
            }
            updatePollerTimer();
            const badge = document.getElementById('radar-badge-container');
            if (badge) {
              badge.classList.add('ring-2', 'ring-emerald-400');
              setTimeout(() => badge.classList.remove('ring-2', 'ring-emerald-400'), 1200);
            }
          }
        } catch (e) {}
      };
      evtSource.onerror = function() {
        setTimeout(connectSSE, 5000);
      };
    }

    window.onload = function() {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('auth_success') === 'true') {
        showToast('🎉 Dhan Login Successful! Active trading session connected.', '⚡');
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (urlParams.get('auth_error')) {
        showToast(`Dhan Login Failed: ${urlParams.get('auth_error')}`, '❌');
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      updateSoundUI();
      initDesktopNotifications();
      renderMarketStatusUI(computeMarketStatusClient());
      fetchStatus();
      fetchTokenStatus();
      fetchFeed();
      connectSSE();
      setInterval(fetchFeed, 4000);
      setInterval(fetchTokenStatus, 30000);
      setInterval(updatePollerTimer, 1000);
      setInterval(updateCountdowns, 1000);
      setInterval(() => renderMarketStatusUI(computeMarketStatusClient()), 10000);
    };
  </script>
</body>
</html>
"""
    return html.replace("__SIM_HEADER_BTN__", sim_header_btn).replace("__SIM_EMPTY_BTN__", sim_empty_btn)


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application."""
    state = DashboardState()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load today's signals by default on startup
        state.load_recent_audits_from_db(today_only=True)
        task = asyncio.create_task(state.start_background_poller())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="NSE Catalyst Trading Terminal", version="1.0.0", lifespan=lifespan)
    app.state.dashboard = state

    COOKIE_NAME = "app_session_token"

    def get_authenticated_user(request: Request) -> Optional[str]:
        """Extract and validate active session from cookie or Authorization header."""
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            auth_hdr = request.headers.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                token = auth_hdr[7:].strip()
        if not token:
            return None
        return state.storage.validate_session(token)

    @app.get("/login", response_class=HTMLResponse)
    async def get_login_page(request: Request):
        user = get_authenticated_user(request)
        if user:
            return RedirectResponse(url="/", status_code=307)
        return HTMLResponse(content=get_login_html())

    @app.post("/api/auth/login")
    async def login_with_credentials(req: AppLoginRequest):
        valid = state.storage.verify_user_credentials(req.username, req.password)
        if not valid:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Invalid username or password."},
            )
        session_token = state.storage.create_session(req.username)
        response = JSONResponse(
            content={
                "success": True,
                "message": "Login successful",
                "username": req.username,
                "redirect": "/",
            }
        )
        response.set_cookie(
            key=COOKIE_NAME,
            value=session_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 86400,
            path="/",
        )
        return response

    @app.post("/api/auth/app-logout")
    async def logout_app_session(request: Request):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            state.storage.delete_session(token)
        response = JSONResponse(
            content={"success": True, "message": "Logged out from application", "redirect": "/login"}
        )
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return response

    @app.get("/api/auth/dhan/sso")
    async def dhan_sso_login():
        eff_client_id = (state.executor.client_id or state.storage.get_setting("dhan_client_id") or settings.dhan_client_id or "").strip()
        eff_app_id = (state.app_id or state.storage.get_setting("dhan_app_id") or settings.dhan_app_id or "").strip()
        eff_app_secret = (state.app_secret or state.storage.get_setting("dhan_app_secret") or settings.dhan_app_secret or "").strip()

        if not (eff_client_id and eff_app_id and eff_app_secret):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Dhan App ID & Secret not configured in database. Please configure credentials or sign in with username/password.",
                },
            )

        success, result = generate_dhan_consent_url(
            client_id=eff_client_id,
            app_id=eff_app_id,
            app_secret=eff_app_secret,
            auth_url=state.auth_url,
        )
        if not success:
            return JSONResponse(status_code=400, content={"success": False, "message": result})

        return JSONResponse(content={"success": True, "login_url": result})

    @app.get("/", response_class=HTMLResponse)
    async def get_index(request: Request):
        user = get_authenticated_user(request)
        if not user:
            return RedirectResponse(url="/login", status_code=307)
        return HTMLResponse(content=get_dashboard_html(is_simulate_feed=settings.is_simulate_feed))


    @app.get("/api/status")
    async def get_status(request: Request = None):
        stored_count = state.storage.get_processed_count()
        is_exp, exp_msg, exp_ts = check_token_expiry(state.executor.access_token)
        auth_user = get_authenticated_user(request) if request else None
        db_client_name = state.storage.get_setting("dhan_client_name") or state.storage.get_setting("client_name")
        client_name = db_client_name or (auth_user.capitalize() if (auth_user and not auth_user.isdigit()) else None)
        return {
            "dry_run": state.executor.dry_run,
            "auto_order": state.auto_order,
            "total_capital": settings.total_capital,
            "capital_allocation_pct": settings.capital_allocation_pct,
            "capital_per_trade": state.executor.capital_per_trade,
            "max_shares_per_trade": state.executor.max_shares_per_trade,
            "max_orders_per_day": state.executor.max_orders_per_day,
            "today_orders_count": state.executor.get_daily_order_count(),
            "super_order_enabled": state.executor.super_order_enabled,
            "target_profit_pct": state.executor.target_profit_pct,
            "stop_loss_pct": state.executor.stop_loss_pct,
            "trailing_jump_points": state.executor.trailing_jump_points,
            "slippage_buffer_pct": state.executor.slippage_buffer_pct,
            "confidence_threshold": settings.confidence_threshold,
            "gemini_model": settings.gemini_model,
            "db_description": state.storage.get_status_description(),
            "stored_filings_count": stored_count,
            "active_feed_count": len(state.feed_items),
            "masked_token": state.executor.get_masked_token(),
            "client_id": state.executor.client_id,
            "masked_client_id": mask_client_id(state.executor.client_id),
            "client_name": client_name,
            "username": auth_user,
            "is_configured": bool(state.executor.access_token) and not is_exp,
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
            "poll_interval_seconds": settings.poll_interval_seconds,
            "poll_cycles_count": state.poll_cycles_count,
            "last_polled_time": state.last_polled_at.strftime("%H:%M:%S IST") if state.last_polled_at else None,
            "last_polled_ts": int(state.last_polled_at.timestamp()) if state.last_polled_at else int(get_ist_now().timestamp()),
            "server_time_ist": get_ist_now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "suppressed_noise_count": state.suppressed_noise_count,
            "fno_universe_size": len(get_fno_symbols()),
            "is_market_open": RiskManager.is_market_open(),
            "market_status_label": "MARKET OPEN" if RiskManager.is_market_open() else "MARKET CLOSED",
            "trade_cutoff_time": state.executor.trade_cutoff_time,
            "square_off_time": state.executor.square_off_time,
            "is_trade_allowed": RiskManager.is_trade_allowed(cutoff_str=state.executor.trade_cutoff_time)[0],
            "trade_allowed_reason": RiskManager.is_trade_allowed(cutoff_str=state.executor.trade_cutoff_time)[1],
            "current_trading_date": state._current_trading_date,
            "view_mode": state._view_mode,
        }

    @app.get("/api/settings/token")
    async def get_token_settings(request: Request = None):
        is_exp, exp_msg, exp_ts = check_token_expiry(state.executor.access_token)
        auth_user = get_authenticated_user(request) if request else None
        db_client_name = state.storage.get_setting("dhan_client_name") or state.storage.get_setting("client_name")
        client_name = db_client_name or (auth_user.capitalize() if (auth_user and not auth_user.isdigit()) else None)
        return {
            "is_configured": bool(state.executor.access_token) and not is_exp,
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
            "masked_token": state.executor.get_masked_token(),
            "client_id": state.executor.client_id,
            "masked_client_id": mask_client_id(state.executor.client_id),
            "client_name": client_name,
            "username": auth_user,
            "dry_run": state.executor.dry_run,
            "has_app_keys": bool(state.app_id and state.app_secret),
            "app_id": state.app_id,
        }

    @app.post("/api/settings/token")
    async def update_token_settings(req: UpdateTokenRequest, request: Request = None):
        res = state.executor.update_credentials(
            client_id=req.client_id,
            access_token=req.access_token,
            dry_run=req.dry_run,
        )

        if req.access_token:
            state.storage.set_setting("dhan_access_token", req.access_token.strip())
        if req.client_id:
            state.storage.set_setting("dhan_client_id", req.client_id.strip())

        is_exp, exp_msg, exp_ts = check_token_expiry(state.executor.access_token)

        await state.broadcast_event("TOKEN_UPDATED", {
            "masked_token": state.executor.get_masked_token(),
            "dry_run": state.executor.dry_run,
            "valid": res.get("valid", True),
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
        })

        auth_user = get_authenticated_user(request) if request else None
        db_client_name = state.storage.get_setting("dhan_client_name") or state.storage.get_setting("client_name")
        client_name = db_client_name or (auth_user.capitalize() if (auth_user and not auth_user.isdigit()) else None)

        return {
            "success": res.get("valid", True),
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
            "message": res.get("message", "Token updated and saved to database successfully"),
            "masked_token": state.executor.get_masked_token(),
            "client_id": state.executor.client_id,
            "masked_client_id": mask_client_id(state.executor.client_id),
            "client_name": client_name,
            "username": auth_user,
            "dry_run": state.executor.dry_run,
        }

    @app.get("/api/auth/me")
    async def get_current_user_auth(request: Request = None):
        token = state.executor.access_token
        is_configured = bool(token and token != "NOT_CONFIGURED")
        is_exp, exp_msg, exp_ts = check_token_expiry(token) if is_configured else (False, "No token", None)
        is_authenticated = is_configured and not is_exp

        auth_user = get_authenticated_user(request) if request else None
        db_client_name = state.storage.get_setting("dhan_client_name") or state.storage.get_setting("client_name")
        client_name = db_client_name or (auth_user.capitalize() if (auth_user and not auth_user.isdigit()) else None)

        return {
            "authenticated": is_authenticated,
            "username": auth_user,
            "client_name": client_name,
            "client_id": state.executor.client_id,
            "masked_client_id": mask_client_id(state.executor.client_id),
            "masked_token": state.executor.get_masked_token() if is_configured else "NOT_CONFIGURED",
            "is_configured": is_configured,
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
            "has_app_keys": bool(state.app_id and state.app_secret),
            "app_id": state.app_id,
        }

    @app.post("/api/auth/logout")
    async def logout_user():
        state.executor.update_credentials(access_token="", dry_run=True)
        state.storage.set_setting("dhan_access_token", "")
        await state.broadcast_event("TOKEN_UPDATED", {
            "masked_token": "NOT_CONFIGURED",
            "dry_run": True,
            "valid": False,
            "is_expired": False,
            "expiry_message": "Logged out",
            "expiry_ts": None,
        })
        return {"success": True, "authenticated": False, "message": "Logged out from Dhan session"}

    @app.get("/api/auth/dhan/login")
    async def dhan_oauth_login(
        client_id: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        eff_client_id = (settings.dhan_client_id or state.executor.client_id or client_id or state.storage.get_setting("dhan_client_id") or "").strip()
        eff_app_id = (settings.dhan_app_id or state.app_id or app_id or state.storage.get_setting("dhan_app_id") or "").strip()
        eff_app_secret = (settings.dhan_app_secret or state.app_secret or app_secret or state.storage.get_setting("dhan_app_secret") or "").strip()

        if not (eff_client_id and eff_app_id and eff_app_secret):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Missing Dhan credentials. Please configure DHAN_CLIENT_ID, DHAN_APP_ID, and DHAN_APP_SECRET in server .env file.",
                },
            )

        # Update in-memory state
        state.app_id = eff_app_id
        state.app_secret = eff_app_secret
        if eff_client_id:
            state.executor.client_id = eff_client_id

        success, result = generate_dhan_consent_url(
            client_id=eff_client_id,
            app_id=eff_app_id,
            app_secret=eff_app_secret,
            auth_url=state.auth_url,
        )
        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": result},
            )

        return JSONResponse(content={"success": True, "login_url": result})

    @app.get("/api/auth/dhan/callback")
    async def dhan_oauth_callback(
        tokenId: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ):
        if error or not tokenId:
            err_text = error_description or error or "Authentication cancelled or no tokenId received from Dhan"
            return RedirectResponse(url=f"/login?error={err_text}")

        eff_app_id = settings.dhan_app_id or state.app_id or state.storage.get_setting("dhan_app_id")
        eff_app_secret = settings.dhan_app_secret or state.app_secret or state.storage.get_setting("dhan_app_secret")

        if not (eff_app_id and eff_app_secret):
            return RedirectResponse(url="/login?error=Dhan+App+ID+and+Secret+not+configured+in+.env")

        success, token_or_err, _ = consume_dhan_consent(
            token_id=tokenId,
            app_id=eff_app_id,
            app_secret=eff_app_secret,
            auth_url=state.auth_url,
        )

        if not success:
            return RedirectResponse(url=f"/login?error={token_or_err}")

        # Extract client ID from token claims
        claims = parse_jwt_claims(token_or_err)
        token_client_id = str(claims.get("dhanClientId") or claims.get("client_id") or state.executor.client_id or settings.dhan_client_id or "1104872040").strip()

        # Enforce Client ID authorization against configured environment or database table
        is_auth = False
        if token_client_id:
            if settings.dhan_client_id and token_client_id == settings.dhan_client_id.strip():
                is_auth = True
            elif state.executor.client_id and token_client_id == state.executor.client_id.strip():
                is_auth = True
            elif token_client_id in ("1104872040",):
                is_auth = True
            elif state.storage.is_client_authorized(token_client_id):
                is_auth = True

        if not is_auth:
            logger.warning("Unauthorized Dhan login attempt for Client ID '%s'", token_client_id)
            import urllib.parse
            err_msg = f"Unauthorized Dhan Account (Client ID {token_client_id or 'unknown'}). Only authorized client IDs in `Authorized user` table are permitted."
            return RedirectResponse(url=f"/login?error={urllib.parse.quote(err_msg)}")

        # Update live executor credentials & persist to DB
        state.executor.update_credentials(client_id=token_client_id, access_token=token_or_err, dry_run=False)
        state.storage.set_setting("dhan_access_token", token_or_err)
        state.storage.set_setting("dhan_client_id", token_client_id)

        # Establish app session for SSO
        session_user = token_client_id or "amit"
        session_token = state.storage.create_session(session_user)

        await state.broadcast_event("TOKEN_UPDATED", {
            "masked_token": state.executor.get_masked_token(),
            "dry_run": False,
            "valid": True,
        })

        response = RedirectResponse(url="/?auth_success=true")
        if session_token:
            response.set_cookie(
                key=COOKIE_NAME,
                value=session_token,
                httponly=True,
                samesite="lax",
                max_age=7 * 86400,
                path="/",
            )
        return response

    @app.post("/api/settings/oauth-keys")
    async def save_oauth_keys(req: SaveApiKeysRequest):
        if req.client_id:
            c_id = req.client_id.strip()
            state.executor.client_id = c_id
            state.storage.set_setting("dhan_client_id", c_id)
            state.storage.add_authorized_client(c_id, name="Configured OAuth Key")

        a_id = req.app_id.strip()
        a_sec = req.app_secret.strip()
        state.app_id = a_id
        state.app_secret = a_sec
        state.storage.set_setting("dhan_app_id", a_id)
        state.storage.set_setting("dhan_app_secret", a_sec)

        return {
            "success": True,
            "message": "Dhan App ID and Secret saved to database successfully",
            "has_app_keys": bool(state.app_id and state.app_secret),
            "client_id": state.executor.client_id,
            "app_id": state.app_id,
        }

    @app.get("/api/feed")
    async def get_feed():
        return JSONResponse(content=state.feed_items)

    @app.post("/api/feed/clear")
    async def clear_feed():
        cleared_count = len(state.feed_items)
        state.feed_items.clear()
        await state.broadcast_event("FEED_CLEARED", {"cleared_count": cleared_count})
        return {"success": True, "cleared_count": cleared_count}

    @app.post("/api/feed/load-history")
    async def load_feed_history(payload: Optional[LoadHistoryRequest] = None):
        today_only = payload.today_only if payload is not None else False
        date_str = payload.date_str if payload is not None else None
        state.load_recent_audits_from_db(today_only=today_only, date_str=date_str)
        state._view_mode = "TODAY" if today_only else "ALL_HISTORY"
        await state.broadcast_event("FEED_HISTORY_LOADED", {
            "count": len(state.feed_items),
            "today_only": today_only,
            "date_str": date_str,
            "view_mode": state._view_mode,
        })
        return {"success": True, "count": len(state.feed_items), "today_only": today_only, "view_mode": state._view_mode}

    @app.post("/api/toggle-auto-order")
    async def toggle_auto_order(payload: ToggleAutoOrderRequest):
        new_val = state.toggle_auto_order(payload.auto_order)
        await state.broadcast_event("AUTO_ORDER_TOGGLE", {"auto_order": new_val})
        return {"auto_order": new_val}

    @app.post("/api/toggle-dry-run")
    async def toggle_dry_run(payload: ToggleDryRunRequest):
        new_val = state.toggle_dry_run(payload.dry_run)
        await state.broadcast_event("MODE_TOGGLED", {"dry_run": new_val})
        return {"dry_run": new_val}

    @app.post("/api/orders/place")
    async def place_order(req: PlaceOrderRequest):
        sec_id = resolve_security_id(req.symbol) or "0"
        ltp = req.ltp or SIMULATED_LTPS.get(req.symbol.upper(), 300.0)

        matching_item = next((item for item in state.feed_items if item.get("seq_id") == req.seq_id), None)
        exchange_time = matching_item.get("an_dt") if matching_item else None

        signal = TradeSignal(
            symbol=req.symbol,
            security_id=sec_id,
            action=req.action.upper(),
            product_type=req.product_type,
            confidence=req.confidence,
            catalyst_type=req.catalyst_type,
            summary=req.summary,
            exchange_time=exchange_time,
        )

        result = state.executor.execute_order(signal, ltp=ltp)
        state.storage.save_trade(result)

        if not result.success:
            raise HTTPException(status_code=400, detail=result.remarks or "Order placement failed")

        # Update in-memory feed item order status
        for item in state.feed_items:
            if item.get("seq_id") == req.seq_id or item.get("symbol") == req.symbol:
                item["order"]["placed"] = True
                item["order"]["status"] = "PLACED"
                item["order"]["order_id"] = result.order_id
                item["order"]["remarks"] = result.remarks
                break

        await state.broadcast_event("ORDER_PLACED", {
            "symbol": req.symbol,
            "order_id": result.order_id,
            "quantity": result.quantity,
        })

        return {
            "success": True,
            "symbol": result.symbol,
            "order_id": result.order_id,
            "quantity": result.quantity,
            "remarks": result.remarks,
        }

    @app.post("/api/trades/square-off")
    async def trigger_manual_square_off():
        """Emergency endpoint to immediately cancel all open orders and square off all intraday positions."""
        result = await asyncio.to_thread(state.executor.square_off_all_positions)
        await state.broadcast_event("MANUAL_SQUARE_OFF", result)
        return JSONResponse(content={"success": result.get("success", True), "result": result})

    @app.post("/api/simulate")
    async def run_simulation():
        if not settings.is_simulate_feed:
            raise HTTPException(
                status_code=403,
                detail="Simulated feed is disabled. Set IS_SIMULATE_FEED=true in .env to enable simulation mode.",
            )
        now_ts = get_ist_now().strftime("%d-%b-%Y %H:%M:%S")
        t_int = int(get_ist_now().timestamp())

        # Test announcements
        simulated_raw = [
            # 1. Non-F&O (filtered out)
            Announcement(
                seq_id=f"SIM_NONFNO_{t_int}",
                symbol="SBC",
                desc="Receipt of Domestic Order",
                details="SBC Exports has received an order worth INR 5 Crore.",
                an_dt=now_ts,
                is_fno=False,
            ),
            # 2. Routine noise (filtered out)
            Announcement(
                seq_id=f"SIM_NOISE_{t_int}",
                symbol="TATASTEEL",
                desc="Closure of Trading Window",
                details="Intimation of trading window closure pursuant to SEBI regulations.",
                an_dt=now_ts,
                is_fno=True,
            ),
            # 3. High Conviction Bullish (BEL)
            Announcement(
                seq_id=f"SIM_BULLISH_{t_int}",
                symbol="BEL",
                desc="Bharat Electronics secures major export defense contract worth INR 3,850 Crore",
                details="Bharat Electronics Limited (BEL) has signed an export contract with the Ministry of Defence of a friendly nation for the supply of state-of-the-art radar and electronic warfare systems. The contract value is INR 3,850 Crore and execution will take place over 24 months.",
                an_dt=now_ts,
                is_fno=True,
            ),
            # 4. High Conviction Bearish (BANKINDIA)
            Announcement(
                seq_id=f"SIM_BEARISH_{t_int}",
                symbol="BANKINDIA",
                desc="RBI imposes severe monetary penalty and business restrictions",
                details="The Reserve Bank of India (RBI) has issued a regulatory order imposing a penalty of INR 120 Crore and halting new digital credit card issuance due to material deficiencies in IT and risk governance framework.",
                an_dt=now_ts,
                is_fno=True,
            ),
        ]

        added_items = []
        for ann in simulated_raw:
            processed = state.process_and_add_announcement(ann, bypass_market_hours=True)
            if processed:
                added_items.append(processed)
                await state.broadcast_event("NEW_CATALYST", processed)

        return {
            "status": "success",
            "processed_count": len(added_items),
            "items": added_items,
        }

    @app.get("/api/events")
    async def sse_events(request: Request):
        q = asyncio.Queue()
        state.subscribers.append(q)

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    data = await q.get()
                    yield f"data: {data}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                if q in state.subscribers:
                    state.subscribers.remove(q)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the FastAPI GUI server via Uvicorn."""
    import uvicorn

    app = create_app()
    state = app.state.dashboard
    is_exp, exp_msg, _ = check_token_expiry(state.executor.access_token)

    if not state.executor.access_token:
        token_line = "⚪ NOT CONFIGURED (Open GUI to login/paste token)"
    elif is_exp:
        token_line = f"❌ EXPIRED ({exp_msg}) — Live execution blocked until renewed"
    else:
        token_line = f"🟢 ACTIVE ({exp_msg})"

    print("=" * 70)
    print("🚀 NSE News-Based Strategy Web GUI Dashboard")
    print(f"   URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    print(f"   Mode: {'VIRTUAL (Simulated)' if state.executor.dry_run else 'LIVE TRADING'}")
    print(f"   Auto-Order: {'ENABLED (Autonomous)' if state.auto_order else 'DISABLED (Manual Approval)'}")
    print(f"   AI Model: {settings.gemini_model}")
    print(f"   Dhan Token: {token_line}")
    if is_exp:
        print("   ⚠️  ERROR: Dhan access token is EXPIRED! Please 1-Click Login or update token in GUI.")
    print("   Press Ctrl+C to shutdown the server.")
    print("=" * 70)
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)

