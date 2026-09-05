"""FastAPI Web Server for Real-Time Event-Driven Trading Dashboard."""

import asyncio
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
from news_based_strategy.execution.executor import DhanExecutor, check_token_expiry, parse_jwt_claims
from news_based_strategy.execution.risk import RiskManager
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

        # Load persisted settings from DB with fallback to config / environment
        db_app_id = self.storage.get_setting("dhan_app_id")
        db_app_secret = self.storage.get_setting("dhan_app_secret")
        db_client_id = self.storage.get_setting("dhan_client_id")
        db_access_token = self.storage.get_setting("dhan_access_token")

        self.app_id = db_app_id if db_app_id is not None else settings.dhan_app_id
        self.app_secret = db_app_secret if db_app_secret is not None else settings.dhan_app_secret
        eff_client_id = db_client_id if db_client_id is not None else settings.dhan_client_id
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

    def process_and_add_announcement(self, ann: Announcement) -> Optional[Dict[str, Any]]:
        """Process an announcement: verify filter, run Gemini, evaluate order trigger, and record item."""
        # 1. Reject if noise or not in F&O universe
        if not ann.is_fno:
            return None
        if NoiseFilter.is_noise(ann.desc, ann.details):
            return None

        # 2. Run Gemini AI reasoning
        audit = self.analyzer.audit(
            symbol=ann.symbol,
            headline=ann.desc,
            details=ann.clean_content,
        )
        if not audit:
            return None

        # Filter strictly to Bullish or Bearish
        sentiment_upper = audit.sentiment.upper()
        if sentiment_upper not in ("BULLISH", "BUY", "BEARISH", "SELL"):
            return None

        is_bullish = sentiment_upper in ("BULLISH", "BUY")
        sentiment_label = "BULLISH" if is_bullish else "BEARISH"

        # Save AI audit to DB
        self.storage.save_audit(ann.seq_id, ann.symbol, audit)
        self.storage.mark_processed(ann.seq_id, ann.symbol, ann.an_dt)

        sec_id = resolve_security_id(ann.symbol) or "0"
        ltp = SIMULATED_LTPS.get(ann.symbol.upper(), 300.0)

        entry_price, tp_price, sl_price = RiskManager.calculate_super_order_levels(
            ltp=ltp,
            action="BUY",
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
            and is_bullish
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
                    action="BUY",
                    product_type="INTRADAY",
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
        elif not is_bullish:
            order_data["status"] = "SKIPPED_BEARISH"
            order_data["remarks"] = "Bearish filing — Bullish Super Orders enabled"
        else:
            order_data["status"] = "SKIPPED_LOW_CONFIDENCE"
            order_data["remarks"] = f"Confidence < {settings.confidence_threshold}% or non-material"

        feed_item = {
            "seq_id": ann.seq_id,
            "symbol": ann.symbol,
            "security_id": sec_id,
            "desc": ann.desc,
            "details": ann.clean_content,
            "an_dt": ann.an_dt,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "sentiment": sentiment_label,
            "confidence": audit.confidence,
            "catalyst_type": audit.catalyst_type,
            "material_impact": audit.material_impact,
            "summary": audit.summary,
            "order": order_data,
        }

        # Prepend to feed
        self.feed_items.insert(0, feed_item)
        return feed_item


def get_dashboard_html() -> str:
    """Return a sleek, high-density Trading Terminal Table Grid dashboard."""
    return """<!DOCTYPE html>
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
          <div class="flex items-center gap-2">
            <h1 class="text-sm font-bold text-white tracking-wide uppercase">NSE Catalyst Trading Terminal</h1>
            <span id="live-badge" class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> LIVE
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

          <!-- Simulation Button -->
          <button onclick="triggerSimulation()" id="sim-btn" class="bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white text-xs font-bold px-3 py-2 rounded-lg transition border border-indigo-400/40 shadow-md flex items-center gap-1.5">
            <span>⚡</span>
            <span>Simulate Feed</span>
          </button>

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
                <div class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Trading Account</div>
                <div id="menu-client-id" class="text-xs font-mono font-bold text-white mt-0.5">Client ID: --</div>
                <div id="menu-expiry-info" class="text-[10px] text-emerald-400 font-mono mt-0.5">Active Session</div>
              </div>
              <div class="space-y-1">
                <button onclick="openLoginScreen(); toggleUserMenu();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-gray-800 text-gray-300 hover:text-white flex items-center gap-2 transition">
                  <span>🔄</span> Switch Account / Re-login
                </button>
                <button onclick="logoutDhan(); toggleUserMenu();" class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-rose-950/40 text-rose-400 hover:text-rose-300 flex items-center gap-2 transition font-semibold">
                  <span>🚪</span> Logout from Dhan
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
    <div class="max-w-[1600px] mx-auto grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
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
      <div class="bg-[#131b2e] border border-gray-800/80 px-3 py-2 rounded-lg flex items-center justify-between col-span-2 md:col-span-1">
        <span class="text-[11px] text-amber-400 font-medium">PENDING APPROVAL</span>
        <span id="stat-pending" class="text-base font-bold text-amber-300 font-mono">0</span>
      </div>
    </div>
  </div>

  <!-- TABLE TOOLBAR (TABS & SEARCH) -->
  <div class="max-w-[1600px] mx-auto w-full px-6 pt-5 pb-3 flex flex-wrap items-center justify-between gap-3">
    
    <!-- Filter Tabs -->
    <div class="flex items-center gap-1.5 bg-[#111827] border border-gray-800 p-1 rounded-lg">
      <button onclick="setFilter('ALL')" id="tab-ALL" class="tab-btn px-3 py-1 text-xs font-bold rounded-md bg-gray-800 text-white transition">
        All Passed <span id="tab-count-all" class="text-[10px] text-gray-400 ml-1 font-mono">(0)</span>
      </button>
      <button onclick="setFilter('BULLISH')" id="tab-BULLISH" class="tab-btn px-3 py-1 text-xs font-semibold rounded-md text-gray-400 hover:text-emerald-300 transition">
        🟢 Bullish Only <span id="tab-count-bullish" class="text-[10px] ml-1 font-mono">(0)</span>
      </button>
      <button onclick="setFilter('BEARISH')" id="tab-BEARISH" class="tab-btn px-3 py-1 text-xs font-semibold rounded-md text-gray-400 hover:text-rose-300 transition">
        🔴 Bearish Only <span id="tab-count-bearish" class="text-[10px] ml-1 font-mono">(0)</span>
      </button>
      <button onclick="setFilter('PENDING')" id="tab-PENDING" class="tab-btn px-3 py-1 text-xs font-semibold rounded-md text-gray-400 hover:text-amber-300 transition">
        ⏳ Pending Approval <span id="tab-count-pending" class="text-[10px] ml-1 font-mono">(0)</span>
      </button>
    </div>

    <!-- Search input & Clear Feed -->
    <div class="flex items-center gap-3">
      <div class="relative">
        <input type="text" id="search-input" onkeyup="renderFeed()" placeholder="Search symbol or catalyst..." class="bg-[#111827] border border-gray-800 text-xs text-gray-200 placeholder-gray-500 rounded-lg pl-8 pr-3 py-1.5 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 w-60 transition">
        <span class="absolute left-2.5 top-2 text-xs text-gray-500">🔍</span>
      </div>
      
      <!-- Clear List Button -->
      <button onclick="clearFeedList()" id="btn-clear-feed" class="px-2.5 py-1.5 text-xs font-semibold rounded-lg bg-[#162032] hover:bg-rose-950/40 text-gray-300 hover:text-rose-200 border border-gray-700/80 hover:border-rose-500/50 transition flex items-center gap-1.5 shadow-sm active:scale-95" title="Clear displayed list from screen (All signals & orders remain permanently stored in DB for audit)">
        <span>🗑️</span>
        <span>Clear List</span>
      </button>

      <span class="text-xs text-gray-500 hidden sm:inline">Auto-Refreshes Live</span>
    </div>

  </div>

  <!-- TABLE CONTAINER -->
  <main class="max-w-[1600px] mx-auto w-full px-6 pb-8 flex-1 flex flex-col">
    <div class="bg-[#111827] border border-gray-800 rounded-xl shadow-xl overflow-hidden flex-1 flex flex-col">
      <div class="overflow-x-auto custom-scrollbar flex-1">
        <table class="w-full text-left border-collapse min-w-[1100px]">
          
          <!-- TABLE HEADER -->
          <thead>
            <tr class="bg-[#162032] border-b border-gray-800 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              <th class="py-3.5 px-4 w-32">Symbol / SecID</th>
              <th class="py-3.5 px-4 w-28">Time</th>
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
      <div id="empty-state" class="p-16 text-center bg-[#111827] my-auto">
        <div class="text-3xl mb-2 text-gray-600">🎯</div>
        <h3 class="text-sm font-semibold text-gray-300">No Filtered Catalysts Found</h3>
        <p class="text-xs text-gray-500 max-w-sm mx-auto mt-1 mb-4">
          The system actively filters out routine compliance noise. Click simulate to ingest sample filings.
        </p>
        <button onclick="triggerSimulation()" class="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition shadow">
          <span>⚡ Simulate Live Catalyst Feed</span>
        </button>
      </div>

    </div>
  </main>

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
            <h4 class="text-xs font-bold text-emerald-300 uppercase tracking-wide">1-Click Login with Dhan (Recommended)</h4>
          </div>
          <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full font-mono">OAuth 2.0</span>
        </div>
        <p class="text-[11px] text-gray-300 leading-relaxed">
          Redirects to Dhan to log in securely via Mobile + OTP/TOTP. Token is automatically fetched & activated with zero copy-pasting.
        </p>

        <div class="pt-1 flex items-center gap-2">
          <button onclick="launchDhanOAuth()" id="btn-oauth-login" class="flex-1 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs py-2.5 px-4 rounded-lg shadow-lg shadow-emerald-700/30 border border-emerald-400/40 flex items-center justify-center gap-2 transition active:scale-95">
            <span>🚀 Log In via Dhan Portal</span>
          </button>
          <button onclick="toggleOAuthSettings()" class="px-2.5 py-2.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-xs border border-gray-700 transition" title="Configure App ID & Secret">
            ⚙️ Keys
          </button>
        </div>

        <!-- Collapsible OAuth Keys Config -->
        <div id="oauth-keys-drawer" class="hidden pt-3 space-y-2.5 border-t border-emerald-500/20 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-gray-300 mb-1">Dhan Client ID</label>
            <input type="text" id="input-client-id" placeholder="e.g. 100028912" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-lg px-3 py-1.5 focus:outline-none focus:border-emerald-500 font-mono">
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-semibold text-gray-300 mb-1">Dhan App ID (API Key)</label>
              <input type="text" id="input-app-id" placeholder="App ID" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-lg px-3 py-1.5 focus:outline-none focus:border-emerald-500 font-mono">
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-gray-300 mb-1">Dhan App Secret</label>
              <input type="password" id="input-app-secret" placeholder="App Secret" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-lg px-3 py-1.5 focus:outline-none focus:border-emerald-500 font-mono">
            </div>
          </div>
          <div class="flex justify-end pt-1">
            <button onclick="saveOAuthKeys()" class="text-[11px] bg-emerald-700 hover:bg-emerald-600 text-white font-semibold px-3 py-1.5 rounded-lg transition">Save Credentials to DB</button>
          </div>
        </div>
      </div>

      <!-- DIVIDER -->
      <div class="flex items-center gap-3">
        <div class="flex-1 h-px bg-gray-800"></div>
        <span class="text-[10px] text-gray-500 font-bold uppercase tracking-wider">OR DIRECT TOKEN LOGIN</span>
        <div class="flex-1 h-px bg-gray-800"></div>
      </div>

      <!-- Option 2: Manual Token Paste -->
      <div class="space-y-3">
        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block text-xs font-semibold text-gray-300">Paste DhanHQ Access Token (JWT)</label>
            <span id="current-token-badge" class="text-[10px] font-mono text-gray-400">Current: Loading...</span>
          </div>
          <div class="relative">
            <input type="password" id="input-access-token" placeholder="Paste eyJhbGciOiJIUzI1NiIs... here" class="w-full bg-[#0b0f19] border border-gray-700 text-xs text-white rounded-lg pl-3 pr-10 py-2 focus:outline-none focus:border-amber-500 font-mono">
            <button type="button" onclick="toggleTokenVisibility()" class="absolute right-2.5 top-2 text-gray-400 hover:text-gray-200 text-xs">
              <span id="toggle-vis-icon">👁️</span>
            </button>
          </div>
        </div>

        <!-- Modal Status Feedback -->
        <div id="modal-feedback" class="hidden text-xs p-2.5 rounded-lg"></div>
      </div>

      <!-- Modal Actions -->
      <div class="flex items-center justify-between gap-2.5 pt-2 border-t border-gray-800">
        <button onclick="closeTokenModal()" class="text-xs font-semibold text-gray-400 hover:text-gray-200 px-3 py-2 rounded-lg hover:bg-gray-800 transition">
          <span>👁️ Preview in Virtual Mode</span>
        </button>
        <button onclick="saveTokenModal()" id="btn-save-token" class="bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white text-xs font-bold px-5 py-2 rounded-lg transition shadow-lg shadow-amber-600/20 flex items-center gap-2">
          <span>💾 Login with Token</span>
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

    function toggleOAuthSettings() {
      const drawer = document.getElementById('oauth-keys-drawer');
      drawer.classList.toggle('hidden');
    }

    async function saveOAuthKeys() {
      const clientId = (document.getElementById('input-client-id').value || '').trim();
      const appId = (document.getElementById('input-app-id').value || '').trim();
      const appSecret = (document.getElementById('input-app-secret').value || '').trim();
      const feedback = document.getElementById('modal-feedback');

      if (!appId || !appSecret) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '⚠️ Please enter both Dhan App ID and App Secret.';
        return;
      }

      try {
        const res = await fetch('/api/settings/oauth-keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: clientId, app_id: appId, app_secret: appSecret })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          feedback.className = 'block bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = '✅ App ID & Secret saved. Ready for 1-Click Login.';
          showToast('OAuth App credentials saved!', '🔑');
          document.getElementById('oauth-keys-drawer').classList.add('hidden');
        } else {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = `❌ ${data.message || 'Failed saving keys'}`;
        }
      } catch (err) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '❌ Request failed to connect.';
      }
    }

    async function launchDhanOAuth() {
      const clientId = (document.getElementById('input-client-id').value || '').trim();
      const appId = (document.getElementById('input-app-id').value || '').trim();
      const appSecret = (document.getElementById('input-app-secret').value || '').trim();
      const feedback = document.getElementById('modal-feedback');
      const btn = document.getElementById('btn-oauth-login');

      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<span>⏳ Connecting to Dhan...</span>';

      try {
        let qs = '';
        if (clientId || appId || appSecret) {
          const params = new URLSearchParams();
          if (clientId) params.append('client_id', clientId);
          if (appId) params.append('app_id', appId);
          if (appSecret) params.append('app_secret', appSecret);
          qs = '?' + params.toString();
        }

        const res = await fetch(`/api/auth/dhan/login${qs}`);
        const data = await res.json();

        if (res.ok && data.success && data.login_url) {
          showToast('Redirecting to official Dhan login portal...', '⚡');
          setTimeout(() => {
            window.location.href = data.login_url;
          }, 400);
        } else {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = `❌ ${data.message || 'Failed to initiate login. Please check App ID & Secret.'}`;
          document.getElementById('oauth-keys-drawer').classList.remove('hidden');
        }
      } catch (err) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '❌ Failed connecting to Dhan login service.';
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<span>🚀 Authenticate on Dhan</span>';
      }
    }

    function toggleUserMenu() {
      const dropdown = document.getElementById('user-menu-dropdown');
      if (dropdown) dropdown.classList.toggle('hidden');
    }

    // Close user menu on outside click
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
          const feedback = document.getElementById('modal-feedback');

          if (data.authenticated) {
            // USER IS LOGGED IN
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
            // TOKEN EXPIRED
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
              sessionAlert.innerHTML = `⚠️ <b>Dhan Session Expired:</b> ${expText}. Please 1-Click Login or enter token to reconnect live trading.`;
            }
            if (!window._hasAlertedExpiry) {
              window._hasAlertedExpiry = true;
              showToast(`❌ Dhan Session EXPIRED: ${expText}. Please login.`, '⚠️');
              if (!window._hasDismissedModal) {
                openLoginScreen();
              }
            }
          } else {
            // NOT CONFIGURED / LOGGED OUT
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
              sessionAlert.innerHTML = `ℹ️ <b>Dhan Login Required:</b> Connect your DhanHQ trading account via 1-Click OAuth or Access Token.`;
            }
          }

          if (document.getElementById('input-client-id') && data.client_id) {
            if (!document.getElementById('input-client-id').value) {
              document.getElementById('input-client-id').value = data.client_id;
            }
          }
          if (document.getElementById('input-app-id') && data.app_id) {
            if (!document.getElementById('input-app-id').value) {
              document.getElementById('input-app-id').value = data.app_id;
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

    function toggleTokenVisibility() {
      const input = document.getElementById('input-access-token');
      const icon = document.getElementById('toggle-vis-icon');
      if (input.type === 'password') {
        input.type = 'text';
        icon.textContent = '🙈';
      } else {
        input.type = 'password';
        icon.textContent = '👁️';
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

      // Safety check: Don't allow live mode if token is not configured or expired
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

    async function saveTokenModal() {
      const clientId = (document.getElementById('input-client-id').value || '').trim();
      const accessToken = (document.getElementById('input-access-token').value || '').trim();
      const feedback = document.getElementById('modal-feedback');
      const btn = document.getElementById('btn-save-token');

      if (!accessToken) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '⚠️ Please paste a valid Dhan Access Token.';
        return;
      }

      btn.disabled = true;
      btn.classList.add('opacity-50');
      btn.innerHTML = '<span>⏳ Validating...</span>';

      try {
        const res = await fetch('/api/settings/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: clientId,
            access_token: accessToken,
          })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          feedback.className = 'block bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = `✅ ${data.message}`;
          showToast('Dhan Access Token updated & validated!', '🔑');
          fetchStatus();
          fetchTokenStatus();
          document.getElementById('input-access-token').value = '';
          setTimeout(() => {
            closeTokenModal();
          }, 1200);
        } else {
          feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
          feedback.textContent = `❌ ${data.message || data.detail || 'Validation failed'}`;
        }
      } catch (err) {
        feedback.className = 'block bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs p-2.5 rounded-lg';
        feedback.textContent = '❌ Request failed to connect to strategy server.';
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
        btn.innerHTML = '<span>💾 Save & Apply Token</span>';
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
          const dbStatus = document.getElementById('db-status');
          if (dbStatus && data.db_description) {
            dbStatus.textContent = data.db_description;
          }
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
      currentFilter = filter;
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.className = 'tab-btn px-3 py-1 text-xs font-semibold rounded-md text-gray-400 hover:text-gray-200 transition';
      });
      const activeBtn = document.getElementById(`tab-${filter}`);
      if (activeBtn) {
        activeBtn.className = 'tab-btn px-3 py-1 text-xs font-bold rounded-md bg-gray-800 text-white transition';
      }
      renderFeed();
    }

    function toggleRowDetails(seqId) {
      if (expandedRows.has(seqId)) {
        expandedRows.delete(seqId);
      } else {
        expandedRows.add(seqId);
      }
      renderFeed();
    }

    async function clearFeedList() {
      if (!feedItems || feedItems.length === 0) {
        showToast('Feed list is already empty.', 'ℹ️');
        return;
      }
      try {
        const res = await fetch('/api/feed/clear', { method: 'POST' });
        if (res.ok) {
          feedItems = [];
          expandedRows.clear();
          renderFeed();
          showToast('🧹 List cleared! All signals & orders remain safely stored in DB for audit.', '✅');
        } else {
          showToast('Failed to clear feed list', '❌');
        }
      } catch (err) {
        showToast('Failed to clear feed list', '❌');
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
      let totalBullish = 0, totalBearish = 0, totalPlaced = 0, totalPending = 0;
      feedItems.forEach(item => {
        if (item.sentiment === 'BULLISH') totalBullish++;
        if (item.sentiment === 'BEARISH') totalBearish++;
        if (item.order && item.order.placed) totalPlaced++;
        if (item.order && item.order.status === 'PENDING_APPROVAL') totalPending++;
      });

      document.getElementById('stat-total').textContent = feedItems.length;
      document.getElementById('stat-bullish').textContent = totalBullish;
      document.getElementById('stat-bearish').textContent = totalBearish;
      document.getElementById('stat-placed').textContent = totalPlaced;
      document.getElementById('stat-pending').textContent = totalPending;

      document.getElementById('tab-count-all').textContent = `(${feedItems.length})`;
      document.getElementById('tab-count-bullish').textContent = `(${totalBullish})`;
      document.getElementById('tab-count-bearish').textContent = `(${totalBearish})`;
      document.getElementById('tab-count-pending').textContent = `(${totalPending})`;

      // Filter logic
      const filtered = feedItems.filter(item => {
        if (currentFilter === 'BULLISH' && item.sentiment !== 'BULLISH') return false;
        if (currentFilter === 'BEARISH' && item.sentiment !== 'BEARISH') return false;
        if (currentFilter === 'PENDING' && (!item.order || item.order.status !== 'PENDING_APPROVAL')) return false;

        if (searchVal) {
          const matchSym = (item.symbol || '').toLowerCase().includes(searchVal);
          const matchDesc = (item.desc || '').toLowerCase().includes(searchVal);
          const matchCat = (item.catalyst_type || '').toLowerCase().includes(searchVal);
          if (!matchSym && !matchDesc && !matchCat) return false;
        }
        return true;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        return;
      }
      emptyState.style.display = 'none';

      tbody.innerHTML = filtered.map(item => createTableRowHTML(item)).join('');
    }

    function createTableRowHTML(item) {
      const isBullish = item.sentiment === 'BULLISH';
      const order = item.order || {};
      const isExpanded = expandedRows.has(item.seq_id);

      // LLM Verdict Badge
      const verdictHTML = isBullish ? `
        <div class="inline-flex flex-col items-center">
          <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1.5 shadow-sm">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            BULLISH 🟢 ${item.confidence}%
          </span>
          <span class="text-[10px] text-emerald-400 font-mono mt-1">High Conviction (≥1.5%)</span>
        </div>
      ` : `
        <div class="inline-flex flex-col items-center">
          <span class="px-2.5 py-1 text-xs font-bold rounded-md bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1.5 shadow-sm">
            <span class="w-2 h-2 rounded-full bg-rose-400"></span>
            BEARISH 🔴 ${item.confidence}%
          </span>
          <span class="text-[10px] text-rose-400 font-mono mt-1">Negative Catalyst</span>
        </div>
      `;

      // Bracket Pricing Column
      let pricingHTML = '';
      if (isBullish) {
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
          <div class="text-right text-gray-500 font-mono text-xs">
            <div>LTP: ₹${order.ltp ? order.ltp.toFixed(2) : '0.00'}</div>
            <div class="text-[10px] text-gray-600">No Bracket Levels</div>
          </div>
        `;
      }

      // Order Action Column
      let actionHTML = '';
      if (isBullish) {
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
          actionHTML = `
            <div class="flex flex-col items-center gap-1.5">
              <button onclick="placeOrder('${item.seq_id}', '${item.symbol}', ${order.ltp || 300.0}, ${item.confidence}, '${item.catalyst_type}')" class="bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white font-bold text-xs px-3.5 py-1.5 rounded-lg transition shadow-lg shadow-emerald-600/30 border border-emerald-400/40 flex items-center gap-1.5">
                <span>🚀</span>
                <span>Place Order</span>
              </button>
              <span class="text-[10px] text-amber-400 font-mono animate-pulse">⏳ Awaiting Approval</span>
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
        actionHTML = `
          <div class="text-center text-[11px] text-rose-400/80 font-mono">
            <span>⏸️ Skipped (Bearish)</span>
          </div>
        `;
      }

      // Main Row & Expandable Drawer
      return `
        <tr class="transition-colors border-b border-gray-800/80">
          
          <!-- Symbol & SecID -->
          <td class="py-3 px-4 align-middle">
            <div class="flex items-center gap-2">
              <span class="text-sm font-black text-white px-2 py-0.5 bg-gray-800 border border-gray-700 rounded tracking-wider">${item.symbol}</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 rounded">#${item.security_id}</span>
            </div>
            <div class="text-[10px] text-gray-500 mt-1 font-mono">NSE_EQ • F&O</div>
          </td>

          <!-- Time -->
          <td class="py-3 px-4 align-middle text-gray-400 font-mono text-xs">
            <div>${item.an_dt ? item.an_dt.split(' ')[1] || item.an_dt : item.timestamp}</div>
            <div class="text-[10px] text-gray-500">${item.an_dt ? item.an_dt.split(' ')[0] : 'Today'}</div>
          </td>

          <!-- Catalyst & Headline -->
          <td class="py-3 px-4 align-middle">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/80 font-mono">
                ${item.catalyst_type}
              </span>
              <span class="text-[11px] text-emerald-400 font-mono">⚡ Passed Filter</span>
            </div>
            <div class="text-xs font-semibold text-gray-100 hover:text-white cursor-pointer" onclick="toggleRowDetails('${item.seq_id}')">
              ${item.desc}
            </div>
            <div class="text-[11px] text-gray-400 italic mt-1 border-l border-indigo-500/50 pl-2 line-clamp-1">
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

        ${isExpanded ? `
          <tr class="bg-[#0f172a] border-b border-gray-800">
            <td colspan="6" class="p-4 pl-12 text-xs">
              <div class="bg-[#111827] border border-gray-800 rounded-lg p-4 space-y-2">
                <div class="font-bold text-gray-300 flex items-center justify-between border-b border-gray-800 pb-2">
                  <span>📄 Complete Filed Announcement Content</span>
                  <span class="text-[11px] text-gray-500 font-mono">Sequence ID: ${item.seq_id}</span>
                </div>
                <p class="text-gray-300 whitespace-pre-line font-mono text-[11px] leading-relaxed pt-1">
                  ${item.details || item.desc}
                </p>
                <div class="pt-2 text-[11px] text-indigo-400 font-mono border-t border-gray-800 flex items-center justify-between">
                  <span>🧠 Gemini 3.7 Flash Evaluation: "${item.summary}"</span>
                  <span class="text-gray-500 font-bold">Confidence: ${item.confidence}%</span>
                </div>
              </div>
            </td>
          </tr>
        ` : ''}
      `;
    }

    async function placeOrder(seq_id, symbol, ltp, confidence, catalyst_type) {
      try {
        showToast(`Placing Super Order for ${symbol}...`, '⏳');
        const res = await fetch('/api/orders/place', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            seq_id: seq_id,
            symbol: symbol,
            action: 'BUY',
            product_type: 'INTRADAY',
            confidence: confidence,
            catalyst_type: catalyst_type,
            ltp: ltp
          })
        });

        if (res.ok) {
          const data = await res.json();
          showToast(`Super Order Placed for ${symbol}! Order ID: ${data.order_id}`, '🚀');
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
      btn.disabled = true;
      btn.classList.add('opacity-50');
      showToast('Running Gemini 3.7 Flash simulation cycle...', '🤖');
      try {
        const res = await fetch('/api/simulate', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          showToast(`Simulation complete! Ingested ${data.processed_count} catalyst filings.`, '✅');
          fetchFeed();
        }
      } catch (err) {
        showToast('Simulation request failed', '❌');
      } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50');
      }
    }

    function connectSSE() {
      const evtSource = new EventSource('/api/events');
      evtSource.onmessage = function(event) {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'NEW_CATALYST' || payload.type === 'ORDER_PLACED' || payload.type === 'AUTO_ORDER_TOGGLE' || payload.type === 'TOKEN_UPDATED' || payload.type === 'MODE_TOGGLED' || payload.type === 'FEED_CLEARED') {
            fetchFeed();
            fetchTokenStatus();
            fetchStatus();
          }
        } catch (e) {}
      };
      evtSource.onerror = function() {
        setTimeout(connectSSE, 5000);
      };
    }

    window.onload = function() {
      // Check OAuth redirect return query params
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('auth_success') === 'true') {
        showToast('🎉 Dhan Login Successful! Active trading session connected.', '⚡');
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (urlParams.get('auth_error')) {
        showToast(`Dhan Login Failed: ${urlParams.get('auth_error')}`, '❌');
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      fetchStatus();
      fetchTokenStatus();
      fetchFeed();
      connectSSE();
      setInterval(fetchFeed, 4000);
      setInterval(fetchTokenStatus, 30000);
    };
  </script>
</body>
</html>
"""


def create_app() -> FastAPI:
    """Create and configure the FastAPI web application."""
    app = FastAPI(title="NSE Catalyst Trading Terminal", version="1.0.0")
    state = DashboardState()
    app.state.dashboard = state

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        return HTMLResponse(content=get_dashboard_html())

    @app.get("/api/status")
    async def get_status():
        stored_count = state.storage.get_processed_count()
        is_exp, exp_msg, exp_ts = check_token_expiry(state.executor.access_token)
        return {
            "dry_run": state.executor.dry_run,
            "auto_order": state.auto_order,
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
            "is_configured": bool(state.executor.access_token) and not is_exp,
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
        }

    @app.get("/api/settings/token")
    async def get_token_settings():
        is_exp, exp_msg, exp_ts = check_token_expiry(state.executor.access_token)
        return {
            "is_configured": bool(state.executor.access_token) and not is_exp,
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
            "masked_token": state.executor.get_masked_token(),
            "client_id": state.executor.client_id,
            "dry_run": state.executor.dry_run,
            "has_app_keys": bool(state.app_id and state.app_secret),
            "app_id": state.app_id,
        }

    @app.post("/api/settings/token")
    async def update_token_settings(req: UpdateTokenRequest):
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

        return {
            "success": res.get("valid", True),
            "is_expired": is_exp,
            "expiry_message": exp_msg,
            "expiry_ts": exp_ts,
            "message": res.get("message", "Token updated and saved to database successfully"),
            "masked_token": state.executor.get_masked_token(),
            "client_id": state.executor.client_id,
            "dry_run": state.executor.dry_run,
        }

    @app.get("/api/auth/me")
    async def get_current_user_auth():
        token = state.executor.access_token
        is_configured = bool(token and token != "NOT_CONFIGURED")
        is_exp, exp_msg, exp_ts = check_token_expiry(token) if is_configured else (False, "No token", None)
        is_authenticated = is_configured and not is_exp

        return {
            "authenticated": is_authenticated,
            "client_id": state.executor.client_id,
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
        eff_client_id = (client_id or state.executor.client_id or state.storage.get_setting("dhan_client_id") or settings.dhan_client_id or "").strip()
        eff_app_id = (app_id or state.app_id or state.storage.get_setting("dhan_app_id") or settings.dhan_app_id or "").strip()
        eff_app_secret = (app_secret or state.app_secret or state.storage.get_setting("dhan_app_secret") or settings.dhan_app_secret or "").strip()

        if not (eff_client_id and eff_app_id and eff_app_secret):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Missing Dhan credentials. Please configure Client ID, App ID, and App Secret in the modal or database.",
                },
            )

        # Update in-memory state and persist to DB
        state.app_id = eff_app_id
        state.app_secret = eff_app_secret
        if eff_client_id:
            state.executor.client_id = eff_client_id
        state.storage.set_setting("dhan_app_id", eff_app_id)
        state.storage.set_setting("dhan_app_secret", eff_app_secret)
        state.storage.set_setting("dhan_client_id", eff_client_id)

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
            return RedirectResponse(url=f"/?auth_error={err_text}")

        eff_app_id = state.app_id or state.storage.get_setting("dhan_app_id") or settings.dhan_app_id
        eff_app_secret = state.app_secret or state.storage.get_setting("dhan_app_secret") or settings.dhan_app_secret

        if not (eff_app_id and eff_app_secret):
            return RedirectResponse(url="/?auth_error=Dhan+App+ID+and+Secret+not+configured")

        success, token_or_err, _ = consume_dhan_consent(
            token_id=tokenId,
            app_id=eff_app_id,
            app_secret=eff_app_secret,
            auth_url=state.auth_url,
        )

        if not success:
            return RedirectResponse(url=f"/?auth_error={token_or_err}")

        # Update live executor credentials & persist to DB
        state.executor.update_credentials(access_token=token_or_err, dry_run=False)
        state.storage.set_setting("dhan_access_token", token_or_err)
        if state.executor.client_id:
            state.storage.set_setting("dhan_client_id", state.executor.client_id)

        await state.broadcast_event("TOKEN_UPDATED", {
            "masked_token": state.executor.get_masked_token(),
            "dry_run": False,
            "valid": True,
        })

        return RedirectResponse(url="/?auth_success=true")

    @app.post("/api/settings/oauth-keys")
    async def save_oauth_keys(req: SaveApiKeysRequest):
        if req.client_id:
            c_id = req.client_id.strip()
            state.executor.client_id = c_id
            state.storage.set_setting("dhan_client_id", c_id)

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

        signal = TradeSignal(
            symbol=req.symbol,
            security_id=sec_id,
            action=req.action.upper(),
            product_type=req.product_type,
            confidence=req.confidence,
            catalyst_type=req.catalyst_type,
            summary=req.summary,
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

    @app.post("/api/simulate")
    async def run_simulation():
        now_ts = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        t_int = int(datetime.now().timestamp())

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
            processed = state.process_and_add_announcement(ann)
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
    uvicorn.run(app, host=host, port=port, log_level="info")

