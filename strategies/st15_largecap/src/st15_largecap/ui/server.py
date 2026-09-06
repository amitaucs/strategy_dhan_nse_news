"""FastAPI Web Dashboard for ST15 Large-Cap Positional Momentum Strategy."""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from st15_largecap.config import settings
from st15_largecap.core.models import SignalStatus
from st15_largecap.engine.runner import StrategyRunner
from st15_largecap.execution.executor import OrderExecutor
from st15_largecap.storage.repository import repository

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ST15 LargeCap Positional Momentum Strategy",
    description="2H Heikin Ashi + Triple EMA + SuperTrend Positional Momentum Strategy for Nifty 200",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

runner = StrategyRunner(on_signal_callback=repository.save_signal)
executor = OrderExecutor(dry_run=settings.DRY_RUN)


@app.on_event("startup")
def on_startup():
    logger.info("ST15 Strategy Dashboard ready on Port %d", settings.PORT)


@app.on_event("shutdown")
def on_shutdown():
    logger.info("Stopping ST15 Strategy background services...")
    runner.stop_background_loop()


@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Strategy operational status."""
    tol = runner.screener.ema_proximity_pct
    prefix = "+" if tol > 0 else ""
    
    if runner.latest_results:
        triggered_count = len([r for r in runner.latest_results if r.is_setup_ready])
        scanned_count = len(runner.latest_results)
    else:
        db_scans = repository.get_latest_scans()
        scanned_count = len(db_scans) if db_scans else 0
        triggered_count = sum(1 for s in db_scans if s.get("is_setup_ready")) if db_scans else 0

    return {
        "strategy": "ST15_LargeCap",
        "universe": "Nifty 200",
        "timeframe": "2-Hour (120-min) Heikin Ashi",
        "is_scanner_running": runner.is_running,
        "dry_run": settings.DRY_RUN,
        "dhan_client_id": settings.DHAN_CLIENT_ID or "NOT_CONFIGURED",
        "dhan_connected": bool(settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN),
        "ema_stack": f"{settings.EMA_FAST} > {settings.EMA_MID} > {settings.EMA_SLOW}",
        "dip_tolerance_pct": f"≤ {prefix}{tol:.2f}%",
        "proximity_tolerance_pct": f"≤ {prefix}{tol:.2f}%",
        "tolerance_value": tol,
        "supertrend": f"ATR({settings.SUPERTREND_PERIOD}), Mult({settings.SUPERTREND_MULTIPLIER})",
        "risk_reward_ratio": f"1:{settings.RISK_REWARD_RATIO}",
        "capital_per_trade": f"₹{settings.CAPITAL_PER_TRADE:,.2f}",
        "order_type": settings.ORDER_TYPE,
        "last_scan_time": runner.last_scan_time.isoformat() if runner.last_scan_time else None,
        "scanned_count": scanned_count,
        "triggered_count": triggered_count,
    }


@app.post("/api/tolerance")
async def update_tolerance(request: Request) -> Dict[str, Any]:
    """Dynamically adjust the EMA Dip Tolerance (%). Supports positive, 0%, and negative values."""
    payload = await request.json()
    try:
        new_tol = float(payload.get("tolerance_pct", 0.5))
        if new_tol < -10.0 or new_tol > 20.0:
            return {"status": "error", "message": "Tolerance must be between -10.0% and +20.0%"}

        logger.info("Adjusted EMA Dip Tolerance to %.2f%% and re-evaluating universe...", new_tol)
        updated_scans = runner.re_evaluate_with_tolerance(new_tol)
        triggered_count = len(runner.latest_signals)
        
        return {
            "status": "success",
            "tolerance_pct": new_tol,
            "triggered_count": triggered_count,
            "scanned_count": len(updated_scans),
            "message": f"Dip tolerance updated to {new_tol:.2f}%. {triggered_count} setups qualified.",
        }
    except Exception as e:
        logger.error("Error updating tolerance: %s", e)
        return {"status": "error", "message": str(e)}


@app.get("/api/scans")
def get_scans() -> List[Dict[str, Any]]:
    """Get latest universe scan results."""
    if runner.latest_results:
        return [
            {
                "symbol": r.symbol,
                "sec_id": r.sec_id,
                "ltp": r.ltp,
                "ema_20": r.ema_20,
                "ema_50": r.ema_50,
                "ema_200": r.ema_200,
                "is_ema_stacked": r.is_ema_stacked,
                "is_in_dip": r.is_in_dip,
                "nearest_ema": r.nearest_ema,
                "nearest_ema_dist_pct": r.nearest_ema_dist_pct,
                "is_ha_green": r.is_ha_green,
                "is_supertrend_green": r.is_supertrend_green,
                "is_setup_ready": r.is_setup_ready,
                "swing_low": r.swing_low,
                "scanned_at": r.scanned_at.isoformat(),
            }
            for r in runner.latest_results
        ]
    db_results = repository.get_latest_scans()
    if db_results:
        return db_results
    return []


@app.get("/api/signals")
def get_signals() -> List[Dict[str, Any]]:
    """Get recent setup signals."""
    signals_list = []
    if runner.latest_signals:
        signals_list = runner.latest_signals
    elif runner.latest_results:
        signals_list = [r.signal for r in runner.latest_results if r.is_setup_ready and r.signal]

    if signals_list:
        return [
            {
                "id": i + 1,
                "symbol": s.symbol,
                "sec_id": s.sec_id,
                "setup_time": s.setup_time.isoformat() if isinstance(s.setup_time, datetime) else str(s.setup_time),
                "trigger_price": s.trigger_price,
                "stop_loss_price": s.stop_loss_price,
                "target_profit_price": s.target_profit_price,
                "risk_per_share": s.risk_per_share,
                "risk_reward_ratio": s.risk_reward_ratio,
                "ema_20": s.ema_20,
                "ema_50": s.ema_50,
                "ema_200": s.ema_200,
                "supertrend": s.supertrend,
                "nearest_ema_name": s.nearest_ema_name,
                "nearest_ema_dist_pct": s.nearest_ema_dist_pct,
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "created_at": datetime.now().isoformat(),
            }
            for i, s in enumerate(signals_list)
        ]

    db_signals = repository.get_signals(limit=50)
    if db_signals:
        return db_signals

    return []


@app.get("/api/positions")
def get_positions() -> List[Dict[str, Any]]:
    """Get positions."""
    return repository.get_positions()


@app.get("/api/orders")
def get_orders() -> List[Dict[str, Any]]:
    """Get orders."""
    return repository.get_orders(limit=50)


@app.post("/api/scan")
def trigger_scan(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Trigger an immediate scan across the Nifty 200 universe."""
    background_tasks.add_task(runner.scan_universe)
    return {"status": "success", "message": "Universe scan scheduled in background"}


@app.post("/api/toggle-scanner")
def toggle_scanner() -> Dict[str, Any]:
    """Start or stop the background periodic scanner."""
    if runner.is_running:
        runner.stop_background_loop()
        return {"status": "success", "is_running": False, "message": "Scanner stopped"}
    else:
        runner.start_background_loop(interval_seconds=settings.SCAN_INTERVAL_MINUTES * 60)
        return {"status": "success", "is_running": True, "message": "Scanner started"}


@app.post("/api/execute/{symbol}")
def execute_setup(symbol: str) -> Dict[str, Any]:
    """Manually dispatch an entry order for a qualified setup."""
    sym = symbol.upper().strip()
    match_signal = next((s for s in runner.latest_signals if s.symbol == sym), None)
    if not match_signal:
        scan_match = next((r for r in runner.latest_results if r.symbol == sym and r.is_setup_ready), None)
        if scan_match and scan_match.signal:
            match_signal = scan_match.signal
        elif scan_match:
            trigger_price = round(scan_match.ltp * 1.002, 2)
            stop_loss = round(scan_match.swing_low or scan_match.ltp * 0.98, 2)
            risk = round(trigger_price - stop_loss, 2)
            target = round(trigger_price + (risk * settings.RISK_REWARD_RATIO), 2)
            match_signal = SetupSignal(
                symbol=sym,
                sec_id=scan_match.sec_id,
                setup_time=datetime.now(),
                trigger_price=trigger_price,
                stop_loss_price=stop_loss,
                target_profit_price=target,
                risk_per_share=risk,
                risk_reward_ratio=settings.RISK_REWARD_RATIO,
                ema_20=scan_match.ema_20,
                ema_50=scan_match.ema_50,
                ema_200=scan_match.ema_200,
                supertrend=0.0,
                nearest_ema_name=scan_match.nearest_ema,
                nearest_ema_dist_pct=scan_match.nearest_ema_dist_pct,
                status=SignalStatus.TRIGGERED,
            )

    if not match_signal:
        return {"status": "error", "message": f"No active qualified setup found for {sym}"}

    trade_order = executor.execute_signal(match_signal)
    repository.save_order(trade_order)
    return {"status": "success", "order": trade_order.__dict__}


@app.get("/", response_class=HTMLResponse)
def index_page() -> str:
    """Render the full ST15 Large-Cap dashboard."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ST15 LargeCap Positional Momentum Strategy</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {{ background-color: #0f172a; color: #f8fafc; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; }}
        .badge-green {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
        .badge-red {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }}
        .badge-yellow {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #d97706; }}
        .badge-blue {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #2563eb; }}
        .badge-purple {{ background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #9333ea; }}
        .card-bg {{ background: #1e293b; border: 1px solid #334155; }}
        .tab-btn.active {{ border-bottom: 2px solid #38bdf8; color: #38bdf8; font-weight: 600; }}
        input[type=number]::-webkit-inner-spin-button, 
        input[type=number]::-webkit-outer-spin-button {{ 
            -webkit-appearance: none; 
            margin: 0; 
        }}
    </style>
</head>
<body class="min-h-screen p-4 md:p-8">
    <!-- Top Header -->
    <header class="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-700 gap-4">
        <div>
            <div class="flex items-center gap-3">
                <span class="p-2.5 bg-blue-600/20 text-blue-400 rounded-xl border border-blue-500/30 text-xl">
                    <i class="fa-solid fa-chart-line"></i>
                </span>
                <div>
                    <h1 class="text-2xl font-bold text-white tracking-tight">ST15 Large-Cap Positional Momentum</h1>
                    <p class="text-xs text-slate-400">2H Heikin Ashi • Triple EMA (20/50/200) • SuperTrend • DhanHQ Positional (Port 8015)</p>
                </div>
            </div>
        </div>
        <div class="flex flex-wrap items-center gap-3">
            <span id="dryRunBadge" class="px-3 py-1 text-xs rounded-full badge-yellow font-semibold">
                <i class="fa-solid fa-flask mr-1"></i> DRY RUN
            </span>
            <span id="scannerStatusBadge" class="px-3 py-1 text-xs rounded-full badge-green font-semibold">
                <i class="fa-solid fa-circle-dot mr-1 animate-pulse"></i> SCANNER READY
            </span>
            <button onclick="triggerScanNow()" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-lg transition">
                <i class="fa-solid fa-arrows-rotate" id="scanIcon"></i> Scan Universe
            </button>
            <button onclick="toggleScanner()" id="toggleBtn" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-2 transition">
                <i class="fa-solid fa-play"></i> Start Scanner
            </button>
        </div>
    </header>

    <!-- Interactive Dip Tolerance Control Bar -->
    <div class="card-bg px-4 py-3 rounded-xl my-6 border border-slate-700/80 bg-slate-900/60 shadow flex flex-wrap items-center justify-between gap-4">
        <!-- Unified Dip Tolerance Input Cluster -->
        <div class="flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2 text-xs font-semibold text-slate-300">
                <i class="fa-solid fa-sliders text-amber-400"></i>
                <span>Dip Tolerance:</span>
            </div>

            <!-- Dropdown Selection -->
            <select id="tolerancePresetSelect" onchange="onPresetDropdownChange()" 
                    class="bg-slate-800 text-amber-300 font-mono text-xs font-semibold rounded-lg px-2.5 py-1.5 border border-slate-600 focus:outline-none focus:border-amber-400 cursor-pointer shadow-inner">
                <option value="-0.50">-0.50% (Deep Penetration)</option>
                <option value="-0.20">-0.20% (Dip Below EMA)</option>
                <option value="0.00">0.00% (Exact Touch / Kiss)</option>
                <option value="0.20">+0.20% (Tight Pullback)</option>
                <option value="0.50" selected>+0.50% (Standard Dip - Default)</option>
                <option value="0.80">+0.80% (Moderate Dip)</option>
                <option value="1.00">+1.00% (Wide Dip)</option>
                <option value="1.50">+1.50% (Loose Pullback)</option>
                <option value="2.00">+2.00% (Broad Zone)</option>
                <option value="custom" disabled hidden>Custom</option>
            </select>

            <!-- Stepper Adjuster [-] [0.50 %] [+] -->
            <div class="flex items-center bg-slate-950 rounded-lg border border-slate-700 overflow-hidden shadow-inner">
                <button onclick="stepTolerance(-0.1)" title="Decrease tolerance" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-bold transition">
                    <i class="fa-solid fa-minus"></i>
                </button>
                <input type="number" id="customTolInput" value="0.50" min="-5.0" max="10.0" step="0.05" onchange="onCustomInputChange()"
                       class="w-16 bg-transparent text-center text-xs font-mono font-bold text-amber-400 focus:outline-none py-1">
                <span class="text-xs text-slate-500 pr-2 font-mono">%</span>
                <button onclick="stepTolerance(0.1)" title="Increase tolerance" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-bold transition">
                    <i class="fa-solid fa-plus"></i>
                </button>
            </div>

            <!-- Apply Button -->
            <button onclick="applyCustomTolerance()" class="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs rounded-lg transition shadow flex items-center gap-1.5 whitespace-nowrap">
                <i class="fa-solid fa-check"></i> Apply &amp; Re-Scan
            </button>
        </div>

        <!-- Strategy Info Pill on Right -->
        <div class="text-xs text-slate-400 items-center gap-1.5 hidden lg:flex">
            <i class="fa-solid fa-circle-info text-sky-400 text-xs"></i>
            <span>Pullback threshold across 20, 50, and 200 EMAs</span>
        </div>
    </div>

    <!-- Metrics Strip -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="card-bg p-4 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Universe Size</span>
            <div class="text-2xl font-bold text-white mt-1" id="metricUniverse">200</div>
            <span class="text-xs text-slate-500">Nifty 200 Large Caps</span>
        </div>
        <div class="card-bg p-4 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Qualified Setups</span>
            <div class="text-2xl font-bold text-emerald-400 mt-1" id="metricQualified">0</div>
            <span class="text-xs text-slate-500">All 4 Gates Passed</span>
        </div>
        <div class="card-bg p-4 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Risk : Reward</span>
            <div class="text-2xl font-bold text-sky-400 mt-1">1 : 3.0</div>
            <span class="text-xs text-slate-500">Swing Low Protected SL</span>
        </div>
        <div class="card-bg p-4 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Dip Tolerance</span>
            <div class="text-2xl font-bold text-amber-400 mt-1" id="metricDipTol">≤ +0.50%</div>
            <span class="text-xs text-slate-500">Adjustable on screen</span>
        </div>
        <div class="card-bg p-4 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Order Execution</span>
            <div class="text-2xl font-bold text-purple-400 mt-1">Forever OCO</div>
            <span class="text-xs text-slate-500">Server-Side Positional Exit</span>
        </div>
    </div>

    <!-- Strategy Rule Banner -->
    <div class="card-bg p-4 rounded-xl mb-6 border border-slate-700/80 flex flex-col md:flex-row justify-between items-center gap-4 text-xs">
        <div class="flex items-center gap-4 flex-wrap">
            <span class="font-semibold text-slate-300"><i class="fa-solid fa-list-check text-blue-400 mr-1.5"></i> Entry Gates:</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-slate-700">1. Bullish Stack (20 &gt; 50 &gt; 200 EMA)</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-amber-500/40 text-amber-300 font-semibold" id="ruleBannerDip">2. Pullback Dip (≤ +0.50% or Touch EMA)</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-slate-700">3. 1st Green Heikin Ashi Candle</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-slate-700">4. SuperTrend Bullish (Green)</span>
        </div>
        <div class="text-slate-400 text-right">
            Last scan: <span id="lastScanTime" class="text-slate-200 font-mono">--:--:--</span>
        </div>
    </div>

    <!-- Tabs Navigation -->
    <div class="flex border-b border-slate-700 mb-6 gap-6 text-sm">
        <button onclick="switchTab('scannerTab')" id="tab-scannerTab" class="tab-btn active pb-3 flex items-center gap-2">
            <i class="fa-solid fa-radar"></i> Live Universe Scanner (<span id="scanCountBadge">0</span>)
        </button>
        <button onclick="switchTab('signalsTab')" id="tab-signalsTab" class="tab-btn pb-3 flex items-center gap-2 text-slate-400">
            <i class="fa-solid fa-bullseye"></i> Qualified Signals (<span id="signalCountBadge">0</span>)
        </button>
        <button onclick="switchTab('positionsTab')" id="tab-positionsTab" class="tab-btn pb-3 flex items-center gap-2 text-slate-400">
            <i class="fa-solid fa-briefcase"></i> Positions (<span id="posCountBadge">0</span>)
        </button>
        <button onclick="switchTab('ordersTab')" id="tab-ordersTab" class="tab-btn pb-3 flex items-center gap-2 text-slate-400">
            <i class="fa-solid fa-receipt"></i> Orders Log
        </button>
    </div>

    <!-- Scanner View -->
    <div id="scannerTab" class="tab-content">
        <!-- Interactive Multi-Gate Filter Toolbar -->
        <div class="card-bg p-3.5 rounded-xl mb-4 border border-slate-700/80 bg-slate-900/70 flex flex-wrap items-center justify-between gap-3 shadow">
            <div class="flex flex-wrap items-center gap-2.5 flex-1">
                <!-- Symbol Search Input -->
                <div class="relative min-w-[150px] max-w-xs flex-1">
                    <i class="fa-solid fa-search absolute left-3 top-2.5 text-slate-500 text-xs"></i>
                    <input type="text" id="symbolSearch" onkeyup="filterTable()" placeholder="Search ticker / sec ID..." 
                           class="w-full bg-slate-950 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500 shadow-inner">
                </div>

                <!-- Gate 1: EMA Alignment Filter -->
                <select id="filterEma" onchange="filterTable()" 
                        class="bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-medium rounded-lg px-2.5 py-1.5 border border-slate-600 focus:outline-none focus:border-blue-400 cursor-pointer shadow">
                    <option value="all">All EMA Alignments</option>
                    <option value="stacked">🟢 20 &gt; 50 &gt; 200 Stacked</option>
                    <option value="not_stacked">🔴 Not Stacked</option>
                </select>

                <!-- Gate 2: Nearest EMA & Dip % Filter -->
                <select id="filterDip" onchange="filterTable()" 
                        class="bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-medium rounded-lg px-2.5 py-1.5 border border-slate-600 focus:outline-none focus:border-amber-400 cursor-pointer shadow">
                    <option value="all">All Dip States</option>
                    <option value="in_dip">🟢 In Dip (≤ Tolerance)</option>
                    <option value="out_dip">⚪ Out of Dip (&gt; Tolerance)</option>
                    <option value="EMA_20">Near 20 EMA</option>
                    <option value="EMA_50">Near 50 EMA</option>
                    <option value="EMA_200">Near 200 EMA</option>
                </select>

                <!-- Gate 3: Heikin Ashi Filter -->
                <select id="filterHa" onchange="filterTable()" 
                        class="bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-medium rounded-lg px-2.5 py-1.5 border border-slate-600 focus:outline-none focus:border-emerald-400 cursor-pointer shadow">
                    <option value="all">All Heikin Ashi</option>
                    <option value="green">🟢 Green HA (Bullish)</option>
                    <option value="red">🔴 Red HA (Pullback)</option>
                </select>

                <!-- Gate 4: SuperTrend Filter -->
                <select id="filterSt" onchange="filterTable()" 
                        class="bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-medium rounded-lg px-2.5 py-1.5 border border-slate-600 focus:outline-none focus:border-sky-400 cursor-pointer shadow">
                    <option value="all">All SuperTrend</option>
                    <option value="bullish">🟢 Bullish (Green)</option>
                    <option value="bearish">🔴 Bearish (Red)</option>
                </select>

                <!-- Setup Trigger Filter -->
                <select id="filterTrigger" onchange="filterTable()" 
                        class="bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-medium rounded-lg px-2.5 py-1.5 border border-slate-600 focus:outline-none focus:border-emerald-400 cursor-pointer shadow">
                    <option value="all">All Setups</option>
                    <option value="qualified">🎯 BUY TRIGGER Only</option>
                    <option value="watching">⏳ Watching Only</option>
                </select>
            </div>

            <!-- Quick Action & Match Count Badge -->
            <div class="flex items-center gap-2.5">
                <span id="showingCountBadge" class="text-xs font-mono font-semibold px-2.5 py-1 bg-slate-800/90 text-slate-300 rounded-lg border border-slate-700 whitespace-nowrap">
                    Showing: 200 / 200
                </span>
                <button onclick="resetAllFilters()" title="Clear all filters back to default" 
                        class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-semibold border border-slate-600 transition flex items-center gap-1.5 shadow">
                    <i class="fa-solid fa-rotate-left text-xs"></i> Reset
                </button>
            </div>
        </div>

        <div class="overflow-x-auto rounded-xl border border-slate-700 card-bg">
            <table class="w-full text-left text-xs text-slate-300">
                <thead class="bg-slate-800/80 text-slate-400 uppercase font-semibold border-b border-slate-700 select-none">
                    <tr>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('symbol')" title="Sort by Symbol">
                            Symbol <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('ltp')" title="Sort by LTP">
                            LTP (₹) <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('ema_alignment')" title="Sort by EMA Alignment">
                            EMA Alignment <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('nearest_ema')" title="Sort by Dip Distance">
                            Nearest EMA &amp; Dip % <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('ha')" title="Sort by Heikin Ashi">
                            Heikin Ashi <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('supertrend')" title="Sort by SuperTrend">
                            SuperTrend <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 cursor-pointer hover:text-white transition" onclick="sortTable('trigger')" title="Sort by Setup Trigger">
                            Setup Trigger <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                        </th>
                        <th class="p-3 text-right">Action</th>
                    </tr>
                </thead>
                <tbody id="scannerTableBody" class="divide-y divide-slate-800">
                    <tr><td colspan="8" class="p-6 text-center text-slate-500">Loading scanner results...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Signals View -->
    <div id="signalsTab" class="tab-content hidden">
        <div class="overflow-x-auto rounded-xl border border-slate-700 card-bg">
            <table class="w-full text-left text-xs text-slate-300">
                <thead class="bg-slate-800/80 text-slate-400 uppercase font-semibold border-b border-slate-700">
                    <tr>
                        <th class="p-3">Symbol</th>
                        <th class="p-3">Trigger Price</th>
                        <th class="p-3">Stop Loss (Swing Low)</th>
                        <th class="p-3">Target (1:3 R:R)</th>
                        <th class="p-3">Risk/Share</th>
                        <th class="p-3">Nearest EMA</th>
                        <th class="p-3">Status</th>
                        <th class="p-3 text-right">Execute</th>
                    </tr>
                </thead>
                <tbody id="signalsTableBody" class="divide-y divide-slate-800">
                    <tr><td colspan="8" class="p-6 text-center text-slate-500">No signals triggered yet.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Positions View -->
    <div id="positionsTab" class="tab-content hidden">
        <div class="overflow-x-auto rounded-xl border border-slate-700 card-bg">
            <table class="w-full text-left text-xs text-slate-300">
                <thead class="bg-slate-800/80 text-slate-400 uppercase font-semibold border-b border-slate-700">
                    <tr>
                        <th class="p-3">Symbol</th>
                        <th class="p-3">Qty</th>
                        <th class="p-3">Entry Price</th>
                        <th class="p-3">Stop Loss</th>
                        <th class="p-3">Target Price</th>
                        <th class="p-3">Current LTP</th>
                        <th class="p-3">PnL (₹)</th>
                        <th class="p-3">Status</th>
                    </tr>
                </thead>
                <tbody id="positionsTableBody" class="divide-y divide-slate-800">
                    <tr><td colspan="8" class="p-6 text-center text-slate-500">No open positional holdings.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- Orders View -->
    <div id="ordersTab" class="tab-content hidden">
        <div class="overflow-x-auto rounded-xl border border-slate-700 card-bg">
            <table class="w-full text-left text-xs text-slate-300">
                <thead class="bg-slate-800/80 text-slate-400 uppercase font-semibold border-b border-slate-700">
                    <tr>
                        <th class="p-3">Order ID</th>
                        <th class="p-3">Symbol</th>
                        <th class="p-3">Action</th>
                        <th class="p-3">Qty</th>
                        <th class="p-3">Price</th>
                        <th class="p-3">Stop Loss</th>
                        <th class="p-3">Target</th>
                        <th class="p-3">Type</th>
                        <th class="p-3">Status</th>
                        <th class="p-3">Placed At</th>
                    </tr>
                </thead>
                <tbody id="ordersTableBody" class="divide-y divide-slate-800">
                    <tr><td colspan="10" class="p-6 text-center text-slate-500">No orders executed yet.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let allScans = [];
        let qualifiedOnly = false;
        let currentTolerance = 0.5;

        function switchTab(tabId) {{
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-btn').forEach(el => {{
                el.classList.remove('active');
                el.classList.add('text-slate-400');
            }});
            document.getElementById(tabId).classList.remove('hidden');
            const activeBtn = document.getElementById('tab-' + tabId);
            activeBtn.classList.add('active');
            activeBtn.classList.remove('text-slate-400');
        }}

        async function fetchStatus() {{
            try {{
                const res = await fetch('/api/status');
                const data = await res.json();
                if (data.last_scan_time) {{
                    const d = new Date(data.last_scan_time);
                    document.getElementById('lastScanTime').innerText = d.toLocaleTimeString();
                }}
                document.getElementById('metricUniverse').innerText = data.scanned_count || '200';
                document.getElementById('metricQualified').innerText = data.triggered_count || '0';
                
                if (data.tolerance_value !== undefined) {{
                    currentTolerance = data.tolerance_value;
                    updateToleranceDisplay(currentTolerance);
                }}

                const toggleBtn = document.getElementById('toggleBtn');
                const badge = document.getElementById('scannerStatusBadge');
                if (data.is_scanner_running) {{
                    toggleBtn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause Scanner';
                    badge.className = 'px-3 py-1 text-xs rounded-full badge-green font-semibold';
                    badge.innerHTML = '<i class="fa-solid fa-circle-dot mr-1 animate-pulse"></i> SCANNER LIVE';
                }} else {{
                    toggleBtn.innerHTML = '<i class="fa-solid fa-play"></i> Start Scanner';
                    badge.className = 'px-3 py-1 text-xs rounded-full badge-blue font-semibold';
                    badge.innerHTML = '<i class="fa-solid fa-check mr-1"></i> READY';
                }}
            }} catch(e) {{
                console.error(e);
            }}
        }}

        function onPresetDropdownChange() {{
            const select = document.getElementById('tolerancePresetSelect');
            const val = parseFloat(select.value);
            if (!isNaN(val)) {{
                document.getElementById('customTolInput').value = val.toFixed(2);
                sendToleranceUpdate(val);
            }}
        }}

        function onCustomInputChange() {{
            const val = parseFloat(document.getElementById('customTolInput').value);
            if (!isNaN(val)) {{
                syncDropdownWithVal(val);
            }}
        }}

        function stepTolerance(delta) {{
            let val = parseFloat(document.getElementById('customTolInput').value) || 0.0;
            val = Math.max(-5.0, Math.min(10.0, val + delta));
            document.getElementById('customTolInput').value = val.toFixed(2);
            syncDropdownWithVal(val);
        }}

        function syncDropdownWithVal(val) {{
            const select = document.getElementById('tolerancePresetSelect');
            const valStr = parseFloat(val).toFixed(2);
            let matched = false;
            for (let opt of select.options) {{
                if (parseFloat(opt.value).toFixed(2) === valStr) {{
                    select.value = opt.value;
                    matched = true;
                    break;
                }}
            }}
            if (!matched) {{
                select.value = 'custom';
            }}
        }}

        function updateToleranceDisplay(val) {{
            const num = parseFloat(val);
            const prefix = num > 0 ? '+' : '';
            const formatted = '≤ ' + prefix + num.toFixed(2) + '%';
            const metric = document.getElementById('metricDipTol');
            if (metric) metric.innerText = formatted;
            const ruleBanner = document.getElementById('ruleBannerDip');
            if (ruleBanner) ruleBanner.innerText = '2. Pullback Dip (' + formatted + ' or Touch EMA)';
            const input = document.getElementById('customTolInput');
            if (input) input.value = num.toFixed(2);
            syncDropdownWithVal(num);
        }}

        async function applyCustomTolerance() {{
            const val = parseFloat(document.getElementById('customTolInput').value);
            if (isNaN(val)) {{
                alert('Please enter a valid tolerance percentage (e.g. 0.5, 0.0, -0.2)');
                return;
            }}
            await sendToleranceUpdate(val);
        }}

        async function sendToleranceUpdate(val) {{
            const icon = document.getElementById('scanIcon');
            if (icon) icon.classList.add('animate-spin');
            currentTolerance = parseFloat(val);
            updateToleranceDisplay(currentTolerance);
            renderScannerTable();

            try {{
                const res = await fetch('/api/tolerance', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ tolerance_pct: currentTolerance }})
                }});
                const data = await res.json();
                if (data.status === 'success') {{
                    await refreshData();
                }} else {{
                    alert('Failed to update tolerance: ' + data.message);
                }}
            }} catch(e) {{
                console.error('Tolerance update error:', e);
            }} finally {{
                if (icon) icon.classList.remove('animate-spin');
            }}
        }}

        let sortColumn = 'trigger';
        let sortAsc = false;

        function sortTable(col) {{
            if (sortColumn === col) {{
                sortAsc = !sortAsc;
            }} else {{
                sortColumn = col;
                sortAsc = (col === 'symbol' || col === 'nearest_ema');
            }}
            renderScannerTable();
        }}

        function resetAllFilters() {{
            const search = document.getElementById('symbolSearch');
            if (search) search.value = '';
            const fEma = document.getElementById('filterEma');
            if (fEma) fEma.value = 'all';
            const fDip = document.getElementById('filterDip');
            if (fDip) fDip.value = 'all';
            const fHa = document.getElementById('filterHa');
            if (fHa) fHa.value = 'all';
            const fSt = document.getElementById('filterSt');
            if (fSt) fSt.value = 'all';
            const fTrig = document.getElementById('filterTrigger');
            if (fTrig) fTrig.value = 'all';
            qualifiedOnly = false;
            sortColumn = 'trigger';
            sortAsc = false;
            renderScannerTable();
        }}

        async function fetchScans() {{
            try {{
                const res = await fetch('/api/scans');
                allScans = await res.json();
                renderScannerTable();
            }} catch(e) {{
                console.error(e);
            }}
        }}

        function renderScannerTable() {{
            const tbody = document.getElementById('scannerTableBody');
            const searchInput = document.getElementById('symbolSearch');
            const query = searchInput ? searchInput.value.toUpperCase().trim() : '';
            
            const filterEma = document.getElementById('filterEma') ? document.getElementById('filterEma').value : 'all';
            const filterDip = document.getElementById('filterDip') ? document.getElementById('filterDip').value : 'all';
            const filterHa = document.getElementById('filterHa') ? document.getElementById('filterHa').value : 'all';
            const filterSt = document.getElementById('filterSt') ? document.getElementById('filterSt').value : 'all';
            const filterTrigger = document.getElementById('filterTrigger') ? document.getElementById('filterTrigger').value : 'all';

            // Dynamically evaluate dip and setup readiness against active tolerance
            allScans.forEach(item => {{
                const distNum = Number(item.nearest_ema_dist_pct || 0);
                item.is_in_dip = distNum <= currentTolerance;
                item.is_setup_ready = Boolean(item.is_ema_stacked && item.is_in_dip && item.is_ha_green && item.is_supertrend_green);
            }});

            let filtered = [...allScans];

            // 1. Symbol / Sec ID Search Filter
            if (query) {{
                filtered = filtered.filter(s => s.symbol.toUpperCase().includes(query) || String(s.sec_id || '').includes(query));
            }}

            // 2. EMA Alignment Filter
            if (filterEma === 'stacked') {{
                filtered = filtered.filter(s => s.is_ema_stacked);
            }} else if (filterEma === 'not_stacked') {{
                filtered = filtered.filter(s => !s.is_ema_stacked);
            }}

            // 3. Nearest EMA & Dip % Filter
            if (filterDip === 'in_dip') {{
                filtered = filtered.filter(s => s.is_in_dip);
            }} else if (filterDip === 'out_dip') {{
                filtered = filtered.filter(s => !s.is_in_dip);
            }} else if (filterDip === 'EMA_20' || filterDip === 'EMA_50' || filterDip === 'EMA_200') {{
                filtered = filtered.filter(s => s.nearest_ema === filterDip);
            }}

            // 4. Heikin Ashi Filter
            if (filterHa === 'green') {{
                filtered = filtered.filter(s => s.is_ha_green);
            }} else if (filterHa === 'red') {{
                filtered = filtered.filter(s => !s.is_ha_green);
            }}

            // 5. SuperTrend Filter
            if (filterSt === 'bullish') {{
                filtered = filtered.filter(s => s.is_supertrend_green);
            }} else if (filterSt === 'bearish') {{
                filtered = filtered.filter(s => !s.is_supertrend_green);
            }}

            // 6. Setup Trigger Filter
            if (filterTrigger === 'qualified' || qualifiedOnly) {{
                filtered = filtered.filter(s => s.is_setup_ready);
            }} else if (filterTrigger === 'watching') {{
                filtered = filtered.filter(s => !s.is_setup_ready);
            }}

            // Sort filtered results
            filtered.sort((a, b) => {{
                let valA, valB;
                if (sortColumn === 'symbol') {{
                    valA = a.symbol; valB = b.symbol;
                    return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                }} else if (sortColumn === 'ltp') {{
                    valA = Number(a.ltp || 0); valB = Number(b.ltp || 0);
                }} else if (sortColumn === 'ema_alignment') {{
                    valA = a.is_ema_stacked ? 1 : 0; valB = b.is_ema_stacked ? 1 : 0;
                }} else if (sortColumn === 'nearest_ema') {{
                    valA = Number(a.nearest_ema_dist_pct || 0); valB = Number(b.nearest_ema_dist_pct || 0);
                }} else if (sortColumn === 'ha') {{
                    valA = a.is_ha_green ? 1 : 0; valB = b.is_ha_green ? 1 : 0;
                }} else if (sortColumn === 'supertrend') {{
                    valA = a.is_supertrend_green ? 1 : 0; valB = b.is_supertrend_green ? 1 : 0;
                }} else {{
                    // Default trigger sorting: Qualified first, then nearest dip distance
                    valA = (a.is_setup_ready ? 1000 : 0) - Number(a.nearest_ema_dist_pct || 0);
                    valB = (b.is_setup_ready ? 1000 : 0) - Number(b.nearest_ema_dist_pct || 0);
                }}
                if (valA === valB) return 0;
                return sortAsc ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
            }});

            const qualifiedCount = allScans.filter(s => s.is_setup_ready).length;
            document.getElementById('scanCountBadge').innerText = allScans.length;
            document.getElementById('metricUniverse').innerText = allScans.length || '200';
            document.getElementById('metricQualified').innerText = qualifiedCount;
            document.getElementById('signalCountBadge').innerText = qualifiedCount;

            const showingBadge = document.getElementById('showingCountBadge');
            if (showingBadge) {{
                showingBadge.innerText = `Showing: ${{filtered.length}} / ${{allScans.length}}`;
            }}

            if (filtered.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="8" class="p-6 text-center text-slate-500">No matching stocks found for selected filters. <button onclick="resetAllFilters()" class="text-sky-400 underline ml-1">Reset Filters</button></td></tr>';
                return;
            }}

            tbody.innerHTML = filtered.map(item => {{
                const emaBadge = item.is_ema_stacked 
                    ? `<span class="badge-green px-2 py-0.5 rounded font-mono text-[11px]"><i class="fa-solid fa-arrow-trend-up mr-1"></i> 20 &gt; 50 &gt; 200</span>`
                    : `<span class="badge-red px-2 py-0.5 rounded font-mono text-[11px]"><i class="fa-solid fa-xmark mr-1"></i> Not Stacked</span>`;

                const distNum = Number(item.nearest_ema_dist_pct || 0);
                const distPrefix = distNum > 0 ? '+' : '';
                const dipBadge = item.is_in_dip
                    ? `<span class="badge-green px-2 py-0.5 rounded font-mono text-[11px]">${{item.nearest_ema}} (${{distPrefix}}${{distNum.toFixed(2)}}%)</span>`
                    : `<span class="text-slate-400 font-mono text-[11px]">${{item.nearest_ema}} (${{distPrefix}}${{distNum.toFixed(2)}}%)</span>`;

                const haBadge = item.is_ha_green
                    ? `<span class="text-emerald-400 font-semibold"><i class="fa-solid fa-circle text-[9px] mr-1"></i> Green</span>`
                    : `<span class="text-rose-400 font-semibold"><i class="fa-solid fa-circle text-[9px] mr-1"></i> Red</span>`;

                const stBadge = item.is_supertrend_green
                    ? `<span class="badge-green px-2 py-0.5 rounded text-[11px] font-semibold"><i class="fa-solid fa-check mr-1"></i> Bullish</span>`
                    : `<span class="badge-red px-2 py-0.5 rounded text-[11px] font-semibold"><i class="fa-solid fa-ban mr-1"></i> Bearish</span>`;

                const triggerBadge = item.is_setup_ready
                    ? `<span class="badge-green px-2.5 py-1 rounded-full font-bold text-[11px] animate-pulse"><i class="fa-solid fa-crosshairs mr-1"></i> BUY TRIGGER</span>`
                    : `<span class="text-slate-500 text-[11px]">Watching</span>`;

                const actionBtn = item.is_setup_ready
                    ? `<button onclick="executeOrder('${{item.symbol}}')" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-[11px] transition shadow">BUY</button>`
                    : `<button disabled class="px-2.5 py-1 bg-slate-800 text-slate-600 rounded text-[11px] cursor-not-allowed">--</button>`;

                return `
                    <tr class="hover:bg-slate-800/50 transition">
                        <td class="p-3 font-bold text-white flex items-center gap-2">
                            <span>${{item.symbol}}</span>
                            <span class="text-[10px] text-slate-500 font-mono">(${{item.sec_id || ''}})</span>
                        </td>
                        <td class="p-3 font-mono text-slate-200">₹${{Number(item.ltp || 0).toFixed(2)}}</td>
                        <td class="p-3">${{emaBadge}}</td>
                        <td class="p-3">${{dipBadge}}</td>
                        <td class="p-3">${{haBadge}}</td>
                        <td class="p-3">${{stBadge}}</td>
                        <td class="p-3">${{triggerBadge}}</td>
                        <td class="p-3 text-right">${{actionBtn}}</td>
                    </tr>
                `;
            }}).join('');
        }}

        async function fetchSignals() {{
            try {{
                const res = await fetch('/api/signals');
                let signals = await res.json();

                if ((!signals || signals.length === 0) && allScans && allScans.length > 0) {{
                    const qualifiedScans = allScans.filter(s => s.is_setup_ready);
                    if (qualifiedScans.length > 0) {{
                        signals = qualifiedScans.map((s, idx) => {{
                            const trig = Number((s.ltp * 1.002).toFixed(2));
                            const sl = Number((s.swing_low || s.ltp * 0.98).toFixed(2));
                            const risk = Number((trig - sl).toFixed(2));
                            const tgt = Number((trig + (risk * 3.0)).toFixed(2));
                            return {{
                                id: idx + 1,
                                symbol: s.symbol,
                                trigger_price: trig,
                                stop_loss_price: sl,
                                target_profit_price: tgt,
                                risk_per_share: risk,
                                nearest_ema_name: s.nearest_ema || 'EMA_20',
                                status: 'TRIGGERED'
                            }};
                        }});
                    }}
                }}

                document.getElementById('signalCountBadge').innerText = signals ? signals.length : 0;
                const tbody = document.getElementById('signalsTableBody');

                if (!signals || signals.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="8" class="p-6 text-center text-slate-500">No active signals recorded yet.</td></tr>';
                    return;
                }}

                tbody.innerHTML = signals.map(s => `
                    <tr class="hover:bg-slate-800/50">
                        <td class="p-3 font-bold text-white">${{s.symbol}}</td>
                        <td class="p-3 font-mono text-emerald-400">₹${{s.trigger_price}}</td>
                        <td class="p-3 font-mono text-rose-400">₹${{s.stop_loss_price}}</td>
                        <td class="p-3 font-mono text-sky-400">₹${{s.target_profit_price}}</td>
                        <td class="p-3 font-mono text-slate-300">₹${{s.risk_per_share}}</td>
                        <td class="p-3 text-slate-300">${{s.nearest_ema_name}}</td>
                        <td class="p-3"><span class="badge-green px-2 py-0.5 rounded text-[11px] font-semibold">${{s.status}}</span></td>
                        <td class="p-3 text-right">
                            <button onclick="executeOrder('${{s.symbol}}')" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow transition">BUY</button>
                        </td>
                    </tr>
                `).join('');
            }} catch(e) {{
                console.error(e);
            }}
        }}

        async function fetchPositions() {{
            try {{
                const res = await fetch('/api/positions');
                const positions = await res.json();
                document.getElementById('posCountBadge').innerText = positions.length;
                const tbody = document.getElementById('positionsTableBody');

                if (positions.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="8" class="p-6 text-center text-slate-500">No open positional holdings.</td></tr>';
                    return;
                }}

                tbody.innerHTML = positions.map(p => `
                    <tr class="hover:bg-slate-800/50">
                        <td class="p-3 font-bold text-white">${{p.symbol}}</td>
                        <td class="p-3 font-mono">${{p.quantity}}</td>
                        <td class="p-3 font-mono">₹${{p.entry_price}}</td>
                        <td class="p-3 font-mono text-rose-400">₹${{p.stop_loss}}</td>
                        <td class="p-3 font-mono text-sky-400">₹${{p.target_price}}</td>
                        <td class="p-3 font-mono">₹${{p.current_price}}</td>
                        <td class="p-3 font-mono font-bold ${{p.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}}">
                            ${{p.pnl >= 0 ? '+' : ''}}₹${{Number(p.pnl || 0).toFixed(2)}}
                        </td>
                        <td class="p-3"><span class="badge-blue px-2 py-0.5 rounded text-[11px]">${{p.status}}</span></td>
                    </tr>
                `).join('');
            }} catch(e) {{
                console.error(e);
            }}
        }}

        async function fetchOrders() {{
            try {{
                const res = await fetch('/api/orders');
                const orders = await res.json();
                const tbody = document.getElementById('ordersTableBody');

                if (orders.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="10" class="p-6 text-center text-slate-500">No orders placed yet.</td></tr>';
                    return;
                }}

                tbody.innerHTML = orders.map(o => `
                    <tr class="hover:bg-slate-800/50">
                        <td class="p-3 font-mono text-slate-400 text-[10px]">${{o.order_id}}</td>
                        <td class="p-3 font-bold text-white">${{o.symbol}}</td>
                        <td class="p-3 text-emerald-400 font-semibold">${{o.action}}</td>
                        <td class="p-3 font-mono">${{o.quantity}}</td>
                        <td class="p-3 font-mono">₹${{o.entry_price}}</td>
                        <td class="p-3 font-mono text-rose-400">₹${{o.stop_loss}}</td>
                        <td class="p-3 font-mono text-sky-400">₹${{o.target_price}}</td>
                        <td class="p-3 text-slate-400">${{o.order_type}}</td>
                        <td class="p-3"><span class="badge-green px-2 py-0.5 rounded text-[11px]">${{o.status}}</span></td>
                        <td class="p-3 text-slate-500 text-[10px] font-mono">${{o.placed_at}}</td>
                    </tr>
                `).join('');
            }} catch(e) {{
                console.error(e);
            }}
        }}

        async function triggerScanNow() {{
            const icon = document.getElementById('scanIcon');
            icon.classList.add('animate-spin');
            try {{
                await fetch('/api/scan', {{ method: 'POST' }});
                setTimeout(() => {{
                    refreshData();
                    icon.classList.remove('animate-spin');
                }}, 2000);
            }} catch(e) {{
                icon.classList.remove('animate-spin');
                alert('Scan trigger failed: ' + e);
            }}
        }}

        async function toggleScanner() {{
            try {{
                await fetch('/api/toggle-scanner', {{ method: 'POST' }});
                fetchStatus();
            }} catch(e) {{
                alert('Toggle failed: ' + e);
            }}
        }}

        async function executeOrder(symbol) {{
            if (!confirm(`Confirm execution of ST15 order for ${{symbol}}?`)) return;
            try {{
                const res = await fetch(`/api/execute/${{symbol}}`, {{ method: 'POST' }});
                const data = await res.json();
                if (data.status === 'success') {{
                    alert(`Order Dispatched: ${{data.order.order_id}} (${{data.order.status}})`);
                    refreshData();
                }} else {{
                    alert('Order Execution Failed: ' + data.message);
                }}
            }} catch(e) {{
                alert('Execution Error: ' + e);
            }}
        }}

        function filterTable() {{
            renderScannerTable();
        }}

        function filterQualifiedOnly() {{
            qualifiedOnly = !qualifiedOnly;
            const btn = document.getElementById('filterQualBtn');
            if (qualifiedOnly) {{
                btn.className = 'px-3 py-1.5 bg-emerald-600 text-white rounded text-xs font-semibold';
            }} else {{
                btn.className = 'px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs border border-slate-700';
            }}
            renderScannerTable();
        }}

        function refreshData() {{
            fetchStatus();
            fetchScans();
            fetchSignals();
            fetchPositions();
            fetchOrders();
        }}

        // Initial Load and 10s auto-refresh
        refreshData();
        setInterval(refreshData, 10000);
    </script>
</body>
</html>
"""


def start_server(host: str = "0.0.0.0", port: int = settings.PORT):
    """Start the FastAPI uvicorn server."""
    logger.info("Starting ST15 Large-Cap Server at http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
