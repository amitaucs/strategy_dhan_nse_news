"""FastAPI Web Server for Real-Time Event-Driven Trading Dashboard."""

import asyncio
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, TradeSignal
from news_based_strategy.execution.executor import DhanExecutor
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


class DashboardState:
    """In-memory state manager for live feed and SSE broadcast."""

    def __init__(self):
        self.storage = StrategyStorage()
        self.analyzer = FilingAnalyzer(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
        )
        self.executor = DhanExecutor(
            client_id=settings.dhan_client_id,
            access_token=settings.dhan_access_token,
            dry_run=settings.dry_run,
            auto_order=settings.auto_order,
            capital_per_trade=settings.capital_per_trade,
            max_shares_per_trade=settings.max_shares_per_trade,
            super_order_enabled=settings.super_order_enabled,
            target_profit_pct=settings.target_profit_pct,
            stop_loss_pct=settings.stop_loss_pct,
            trailing_jump_points=settings.trailing_jump_points,
            slippage_buffer_pct=settings.slippage_buffer_pct,
        )
        self.feed_items: List[Dict[str, Any]] = []
        self.subscribers: List[asyncio.Queue] = []
        self.auto_order = settings.auto_order

    def toggle_auto_order(self, enabled: bool) -> bool:
        self.auto_order = enabled
        self.executor.auto_order = enabled
        return self.auto_order

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
            <span>Broker: <span id="mode-text" class="text-amber-400 font-mono font-semibold">DRY-RUN</span></span>
            <span>•</span>
            <span id="db-status" class="text-emerald-400 font-mono">MySQL Primary</span>
          </div>
        </div>
      </div>

      <!-- Controls & Actions -->
      <div class="flex items-center gap-3">
        
        <!-- AUTO_ORDER Toggle Switch -->
        <div class="flex items-center gap-2.5 bg-[#1e293b]/70 border border-gray-700/80 px-3 py-1.5 rounded-lg shadow-sm">
          <span class="text-xs font-semibold text-gray-300">AUTO ORDER:</span>
          <button id="toggle-auto-btn" onclick="toggleAutoOrder()" class="px-2.5 py-1 text-xs font-bold rounded transition flex items-center gap-1.5 shadow">
            <span id="auto-status-indicator" class="w-2 h-2 rounded-full"></span>
            <span id="auto-status-label">LOADING...</span>
          </button>
        </div>

        <!-- Simulation Button -->
        <button onclick="triggerSimulation()" id="sim-btn" class="bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white text-xs font-bold px-3.5 py-2 rounded-lg transition border border-indigo-400/40 shadow-md flex items-center gap-1.5">
          <span>⚡</span>
          <span>Simulate Feed</span>
        </button>

        <!-- Refresh Button -->
        <button onclick="fetchFeed()" class="bg-gray-800 hover:bg-gray-700 text-gray-200 text-xs font-semibold p-2 rounded-lg transition border border-gray-700" title="Refresh Table">
          🔄
        </button>

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

    <!-- Search input -->
    <div class="flex items-center gap-3">
      <div class="relative">
        <input type="text" id="search-input" onkeyup="renderFeed()" placeholder="Search symbol or catalyst..." class="bg-[#111827] border border-gray-800 text-xs text-gray-200 placeholder-gray-500 rounded-lg pl-8 pr-3 py-1.5 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 w-64 transition">
        <span class="absolute left-2.5 top-2 text-xs text-gray-500">🔍</span>
      </div>
      <span class="text-xs text-gray-500">Auto-Refreshes Live</span>
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

  <!-- TOAST NOTIFICATION -->
  <div id="toast" class="fixed bottom-5 right-5 bg-gray-900 border border-gray-700 text-white text-xs px-4 py-3 rounded-lg shadow-2xl transition-all duration-300 opacity-0 translate-y-4 pointer-events-none z-50 flex items-center gap-2">
    <span id="toast-icon">ℹ️</span>
    <span id="toast-msg">Notification</span>
  </div>

  <!-- JAVASCRIPT LOGIC -->
  <script>
    let isAutoOrder = true;
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

    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const data = await res.json();
          isAutoOrder = data.auto_order;
          updateAutoOrderUI();
          document.getElementById('mode-text').textContent = data.dry_run ? 'DRY-RUN (Simulated)' : 'LIVE TRADING';
          document.getElementById('db-status').textContent = data.db_description;
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
                ID: <span class="text-gray-200 font-semibold">${order.order_id || 'DRY_SIMULATED'}</span>
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
          if (payload.type === 'NEW_CATALYST' || payload.type === 'ORDER_PLACED' || payload.type === 'AUTO_ORDER_TOGGLE') {
            fetchFeed();
          }
        } catch (e) {}
      };
      evtSource.onerror = function() {
        setTimeout(connectSSE, 5000);
      };
    }

    window.onload = function() {
      fetchStatus();
      fetchFeed();
      connectSSE();
      setInterval(fetchFeed, 4000);
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
        return {
            "dry_run": settings.dry_run,
            "auto_order": state.auto_order,
            "super_order_enabled": settings.super_order_enabled,
            "max_shares_per_trade": settings.max_shares_per_trade,
            "confidence_threshold": settings.confidence_threshold,
            "gemini_model": settings.gemini_model,
            "db_description": state.storage.get_status_description(),
            "stored_filings_count": stored_count,
            "active_feed_count": len(state.feed_items),
        }

    @app.get("/api/feed")
    async def get_feed():
        return JSONResponse(content=state.feed_items)

    @app.post("/api/toggle-auto-order")
    async def toggle_auto_order(payload: ToggleAutoOrderRequest):
        new_val = state.toggle_auto_order(payload.auto_order)
        await state.broadcast_event("AUTO_ORDER_TOGGLE", {"auto_order": new_val})
        return {"auto_order": new_val}

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
    print("=" * 70)
    print("🚀 NSE News-Based Strategy Web GUI Dashboard")
    print(f"   URL: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    print(f"   Mode: {'DRY-RUN (Simulated)' if settings.dry_run else 'LIVE TRADING'}")
    print(f"   Auto-Order: {'ENABLED (Autonomous)' if settings.auto_order else 'DISABLED (Manual Approval)'}")
    print(f"   AI Model: {settings.gemini_model}")
    print("   Press Ctrl+C to shutdown the server.")
    print("=" * 70)
    uvicorn.run(app, host=host, port=port, log_level="info")

