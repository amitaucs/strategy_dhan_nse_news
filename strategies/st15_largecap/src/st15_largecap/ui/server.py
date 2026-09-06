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
from st15_largecap.core.models import SetupSignal, SignalStatus
from st15_largecap.engine.runner import StrategyRunner
from st15_largecap.execution.executor import OrderExecutor
from st15_largecap.indicators.ema import calculate_triple_ema
from st15_largecap.indicators.supertrend import calculate_supertrend
from st15_largecap.ingestion.heikin_ashi import calculate_heikin_ashi
from st15_largecap.ingestion.universe import universe_manager
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


@app.get("/api/chart/{symbol}")
def get_chart_data(symbol: str) -> Dict[str, Any]:
    """Get 2H candles, Heikin Ashi, 20/50/200 EMAs, SuperTrend, and signal levels for charting."""
    sym = symbol.upper().strip()
    sec_id = universe_manager.get_security_id(sym)
    candles = runner.fetcher.fetch_2h_candles(
        security_id=sec_id,
        symbol=sym,
        days=settings.HISTORY_DAYS,
    )

    if not candles:
        return {"status": "error", "message": f"No candle data available for {sym}"}

    # 1. Raw & Heikin Ashi Candles
    ha_candles = calculate_heikin_ashi(candles)
    
    # 2. Triple EMA (20, 50, 200)
    closes = [c.close for c in candles]
    ema_dict = calculate_triple_ema(closes, fast_span=settings.EMA_FAST, mid_span=settings.EMA_MID, slow_span=settings.EMA_SLOW)
    
    # 3. SuperTrend
    st_vals, st_green = calculate_supertrend(candles, period=settings.SUPERTREND_PERIOD, multiplier=settings.SUPERTREND_MULTIPLIER)

    # 4. Format series for Lightweight Charts (UNIX timestamp in seconds)
    raw_series = []
    ha_series = []
    ema_20_series = []
    ema_50_series = []
    ema_200_series = []
    supertrend_series = []

    for i, c in enumerate(candles):
        ts = int(c.timestamp.timestamp())
        raw_series.append({
            "time": ts,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        })

        ha = ha_candles[i]
        ha_series.append({
            "time": ts,
            "open": ha.open,
            "high": ha.high,
            "low": ha.low,
            "close": ha.close,
        })

        if ema_dict["ema_20"][i] > 0:
            ema_20_series.append({"time": ts, "value": ema_dict["ema_20"][i]})
        if ema_dict["ema_50"][i] > 0:
            ema_50_series.append({"time": ts, "value": ema_dict["ema_50"][i]})
        if ema_dict["ema_200"][i] > 0:
            ema_200_series.append({"time": ts, "value": ema_dict["ema_200"][i]})

        if st_vals[i] > 0:
            supertrend_series.append({
                "time": ts,
                "value": st_vals[i],
                "color": "#10b981" if st_green[i] else "#ef4444",
                "is_green": st_green[i],
            })

    # Find latest scan / signal info
    scan_res = next((r for r in runner.latest_results if r.symbol == sym), None)
    if not scan_res:
        scan_res = runner.screener.evaluate(symbol=sym, sec_id=sec_id, candles=candles)

    signal_info = None
    if scan_res and scan_res.signal:
        signal_info = {
            "trigger_price": scan_res.signal.trigger_price,
            "stop_loss": scan_res.signal.stop_loss_price,
            "target_price": scan_res.signal.target_profit_price,
            "risk_per_share": scan_res.signal.risk_per_share,
            "rr_ratio": scan_res.signal.risk_reward_ratio,
        }
    elif scan_res and scan_res.is_setup_ready:
        trig = round(scan_res.ltp * 1.002, 2)
        sl = round(scan_res.swing_low or (scan_res.ltp * 0.98), 2)
        risk = round(trig - sl, 2)
        tgt = round(trig + (risk * settings.RISK_REWARD_RATIO), 2)
        signal_info = {
            "trigger_price": trig,
            "stop_loss": sl,
            "target_price": tgt,
            "risk_per_share": risk,
            "rr_ratio": settings.RISK_REWARD_RATIO,
        }

    return {
        "status": "success",
        "symbol": sym,
        "sec_id": sec_id,
        "ltp": candles[-1].close,
        "timeframe": "2-Hour (120-min)",
        "candles_count": len(candles),
        "raw_candles": raw_series,
        "ha_candles": ha_series,
        "ema_20": ema_20_series,
        "ema_50": ema_50_series,
        "ema_200": ema_200_series,
        "supertrend": supertrend_series,
        "scan": {
            "is_ema_stacked": scan_res.is_ema_stacked if scan_res else False,
            "is_in_dip": scan_res.is_in_dip if scan_res else False,
            "nearest_ema": scan_res.nearest_ema if scan_res else "",
            "nearest_ema_dist_pct": scan_res.nearest_ema_dist_pct if scan_res else 0.0,
            "is_ha_green": scan_res.is_ha_green if scan_res else False,
            "is_supertrend_green": scan_res.is_supertrend_green if scan_res else False,
            "is_setup_ready": scan_res.is_setup_ready if scan_res else False,
        },
        "signal": signal_info,
    }


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
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
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

    <!-- Embedded TradingView Lightweight Chart Modal -->
    <div id="chartModal" class="fixed inset-0 bg-slate-950/85 backdrop-blur-sm z-50 hidden flex items-center justify-center p-2 md:p-6 transition-all duration-200">
        <div class="card-bg w-full max-w-6xl h-[92vh] rounded-2xl border border-slate-700/80 shadow-2xl flex flex-col overflow-hidden bg-slate-900">
            <!-- Modal Header -->
            <div class="px-5 py-3.5 border-b border-slate-700/80 bg-slate-800/80 flex flex-wrap items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                    <div class="p-2 bg-blue-500/20 text-blue-400 rounded-xl border border-blue-500/30">
                        <i class="fa-solid fa-chart-candlestick text-lg"></i>
                    </div>
                    <div>
                        <div class="flex items-center gap-2.5">
                            <h3 id="chartModalSymbol" class="text-lg font-bold text-white tracking-wide">--</h3>
                            <span id="chartModalSecId" class="text-xs text-slate-400 font-mono">(--)</span>
                            <span id="chartModalPrice" class="text-base font-mono font-bold text-emerald-400">₹--.--</span>
                            <span id="chartModalTriggerBadge" class="text-[11px] font-bold px-2 py-0.5 rounded-full badge-green">--</span>
                        </div>
                        <p class="text-[11px] text-slate-400">2-Hour (120-min) Positional Chart • Triple EMA (20/50/200) • SuperTrend • Unlimited Indicators (TV Engine)</p>
                    </div>
                </div>

                <!-- Interactive Toggles & Action -->
                <div class="flex flex-wrap items-center gap-2">
                    <!-- Candle Type Toggle -->
                    <button id="chartTypeBtn" onclick="toggleChartCandleType()" class="px-2.5 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition">
                        <i class="fa-solid fa-layer-group text-amber-400"></i> <span id="chartTypeLabel">Heikin Ashi</span>
                    </button>

                    <!-- Indicators Toggles -->
                    <button id="toggleEmaBtn" onclick="toggleEmas()" class="px-2.5 py-1.5 bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition">
                        <i class="fa-solid fa-wave-square"></i> EMAs (20/50/200)
                    </button>
                    <button id="toggleStBtn" onclick="toggleSuperTrend()" class="px-2.5 py-1.5 bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition">
                        <i class="fa-solid fa-shield-halved"></i> SuperTrend
                    </button>

                    <!-- Order Action inside chart -->
                    <button id="chartBuyBtn" onclick="executeOrderFromChart()" class="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition shadow flex items-center gap-1.5">
                        <i class="fa-solid fa-crosshairs"></i> Buy Setup
                    </button>

                    <!-- Close Modal -->
                    <button onclick="closeChartModal()" class="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700/60 transition">
                        <i class="fa-solid fa-xmark text-lg"></i>
                    </button>
                </div>
            </div>

            <!-- Strategy Signal & Metrics Bar -->
            <div id="chartMetricsBar" class="px-5 py-2 bg-slate-950/70 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                <!-- Multi-Gate Badges -->
                <div class="flex flex-wrap items-center gap-3">
                    <span id="cGateEma" class="px-2 py-0.5 rounded font-mono text-[11px] badge-green">EMA: Stacked</span>
                    <span id="cGateDip" class="px-2 py-0.5 rounded font-mono text-[11px] badge-green">Dip: In Zone</span>
                    <span id="cGateHa" class="px-2 py-0.5 rounded font-mono text-[11px] text-emerald-400 font-semibold">HA: 1st Green</span>
                    <span id="cGateSt" class="px-2 py-0.5 rounded font-mono text-[11px] badge-green">SuperTrend: Bullish</span>
                </div>

                <!-- Signal Levels -->
                <div id="chartSignalLevels" class="flex flex-wrap items-center gap-3 font-mono text-[11px]">
                    <span class="text-sky-400 font-semibold">Trigger: <span id="cSignalTrig">₹--</span></span>
                    <span class="text-rose-400 font-semibold">Stop Loss: <span id="cSignalSL">₹--</span></span>
                    <span class="text-emerald-400 font-semibold">Target (1:3): <span id="cSignalTgt">₹--</span></span>
                </div>
            </div>

            <!-- Dynamic Live Tooltip Legend -->
            <div class="px-5 py-2 bg-slate-900/90 border-b border-slate-800/80 flex flex-wrap items-center gap-4 text-xs font-mono select-none">
                <span id="chartLegendOhlc" class="text-slate-300">O: -- H: -- L: -- C: --</span>
                <span class="text-sky-400 font-semibold flex items-center gap-1"><span class="w-2.5 h-0.5 bg-sky-400 inline-block"></span> 20 EMA: <span id="legEma20">--</span></span>
                <span class="text-amber-400 font-semibold flex items-center gap-1"><span class="w-2.5 h-0.5 bg-amber-400 inline-block"></span> 50 EMA: <span id="legEma50">--</span></span>
                <span class="text-purple-400 font-semibold flex items-center gap-1"><span class="w-2.5 h-0.5 bg-purple-400 inline-block"></span> 200 EMA: <span id="legEma200">--</span></span>
                <span class="text-emerald-400 font-semibold flex items-center gap-1"><span class="w-2.5 h-0.5 bg-emerald-400 inline-block"></span> SuperTrend: <span id="legSt">--</span></span>
            </div>

            <!-- Chart Canvas Container -->
            <div class="flex-1 w-full h-full relative bg-slate-950" id="chartWrapper">
                <div id="tvChartContainer" class="w-full h-full"></div>
                <div id="chartLoadingOverlay" class="absolute inset-0 bg-slate-950/80 flex items-center justify-center gap-3 text-sm text-slate-400 z-10">
                    <i class="fa-solid fa-circle-notch animate-spin text-blue-400 text-lg"></i> Loading 2H candles and indicators...
                </div>
            </div>
        </div>
    </div>

    <script>
        let allScans = [];
        let qualifiedOnly = false;
        let currentTolerance = 0.5;

        // Chart Global State
        let chartInstance = null;
        let candleSeries = null;
        let ema20Series = null;
        let ema50Series = null;
        let ema200Series = null;
        let superTrendSeries = null;
        let trigPriceLine = null;
        let slPriceLine = null;
        let tgtPriceLine = null;
        let currentChartSymbol = null;
        let currentChartData = null;
        let isHeikinAshi = true;
        let showEmas = true;
        let showSuperTrend = true;

        async function openChartModal(symbol) {{
            currentChartSymbol = symbol;
            const modal = document.getElementById('chartModal');
            const overlay = document.getElementById('chartLoadingOverlay');
            modal.classList.remove('hidden');
            if (overlay) overlay.classList.remove('hidden');

            document.getElementById('chartModalSymbol').innerText = symbol;
            document.getElementById('chartModalSecId').innerText = 'Loading...';
            document.getElementById('chartModalPrice').innerText = '₹--.--';

            try {{
                const res = await fetch(`/api/chart/${{symbol}}`);
                const data = await res.json();
                if (data.status !== 'success') {{
                    alert(data.message || 'Failed to load chart data');
                    closeChartModal();
                    return;
                }}
                currentChartData = data;
                renderTvChart(data);
            }} catch (e) {{
                console.error('Failed to fetch chart:', e);
                alert('Error loading chart: ' + e);
                closeChartModal();
            }} finally {{
                if (overlay) overlay.classList.add('hidden');
            }}
        }}

        function closeChartModal() {{
            const modal = document.getElementById('chartModal');
            modal.classList.add('hidden');
            if (chartInstance) {{
                chartInstance.remove();
                chartInstance = null;
                candleSeries = null;
                ema20Series = null;
                ema50Series = null;
                ema200Series = null;
                superTrendSeries = null;
            }}
            currentChartSymbol = null;
            currentChartData = null;
        }}

        function renderTvChart(data) {{
            const container = document.getElementById('tvChartContainer');
            container.innerHTML = '';

            // Update Header & Badge Stats
            document.getElementById('chartModalSymbol').innerText = data.symbol;
            document.getElementById('chartModalSecId').innerText = `(SecID: ${{data.sec_id || 'N/A'}})`;
            document.getElementById('chartModalPrice').innerText = `₹${{Number(data.ltp || 0).toFixed(2)}}`;

            const trigBadge = document.getElementById('chartModalTriggerBadge');
            if (data.scan && data.scan.is_setup_ready) {{
                trigBadge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full badge-green animate-pulse';
                trigBadge.innerHTML = '<i class="fa-solid fa-crosshairs mr-1"></i> BUY SETUP READY';
            }} else {{
                trigBadge.className = 'text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700';
                trigBadge.innerText = 'WATCHING';
            }}

            // Update Multi-Gate Badges
            if (data.scan) {{
                const gEma = document.getElementById('cGateEma');
                if (data.scan.is_ema_stacked) {{
                    gEma.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-green';
                    gEma.innerHTML = '<i class="fa-solid fa-check mr-1"></i> EMA: 20 &gt; 50 &gt; 200';
                }} else {{
                    gEma.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-red';
                    gEma.innerHTML = '<i class="fa-solid fa-xmark mr-1"></i> EMA: Not Stacked';
                }}

                const gDip = document.getElementById('cGateDip');
                const dist = Number(data.scan.nearest_ema_dist_pct || 0);
                const prefix = dist > 0 ? '+' : '';
                if (data.scan.is_in_dip) {{
                    gDip.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-green';
                    gDip.innerHTML = `<i class="fa-solid fa-check mr-1"></i> Dip: ${{data.scan.nearest_ema}} (${{prefix}}${{dist.toFixed(2)}}%)`;
                }} else {{
                    gDip.className = 'px-2 py-0.5 rounded font-mono text-[11px] text-slate-400 bg-slate-800/80 border border-slate-700';
                    gDip.innerHTML = `Dip: ${{data.scan.nearest_ema}} (${{prefix}}${{dist.toFixed(2)}}%)`;
                }}

                const gHa = document.getElementById('cGateHa');
                if (data.scan.is_ha_green) {{
                    gHa.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-green';
                    gHa.innerHTML = '<i class="fa-solid fa-circle text-[8px] mr-1"></i> HA: Green';
                }} else {{
                    gHa.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-red';
                    gHa.innerHTML = '<i class="fa-solid fa-circle text-[8px] mr-1"></i> HA: Red';
                }}

                const gSt = document.getElementById('cGateSt');
                if (data.scan.is_supertrend_green) {{
                    gSt.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-green';
                    gSt.innerHTML = '<i class="fa-solid fa-check mr-1"></i> SuperTrend: Bullish';
                }} else {{
                    gSt.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-red';
                    gSt.innerHTML = '<i class="fa-solid fa-xmark mr-1"></i> SuperTrend: Bearish';
                }}
            }}

            // Update Signal Levels
            if (data.signal) {{
                document.getElementById('cSignalTrig').innerText = `₹${{Number(data.signal.trigger_price).toFixed(2)}}`;
                document.getElementById('cSignalSL').innerText = `₹${{Number(data.signal.stop_loss).toFixed(2)}}`;
                document.getElementById('cSignalTgt').innerText = `₹${{Number(data.signal.target_price).toFixed(2)}}`;
                document.getElementById('chartSignalLevels').classList.remove('hidden');
            }} else {{
                document.getElementById('chartSignalLevels').classList.add('hidden');
            }}

            // Create Lightweight Chart
            chartInstance = LightweightCharts.createChart(container, {{
                layout: {{
                    background: {{ type: 'solid', color: '#0b0f19' }},
                    textColor: '#94a3b8',
                    fontFamily: 'ui-sans-serif, system-ui, -apple-system, sans-serif',
                }},
                grid: {{
                    vertLines: {{ color: 'rgba(51, 65, 85, 0.3)' }},
                    horzLines: {{ color: 'rgba(51, 65, 85, 0.3)' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {{
                        color: '#38bdf8',
                        width: 1,
                        style: LightweightCharts.LineStyle.Dashed,
                        labelBackgroundColor: '#1e293b',
                    }},
                    horzLine: {{
                        color: '#38bdf8',
                        width: 1,
                        style: LightweightCharts.LineStyle.Dashed,
                        labelBackgroundColor: '#1e293b',
                    }},
                }},
                rightPriceScale: {{
                    borderColor: '#334155',
                    scaleMargins: {{
                        top: 0.1,
                        bottom: 0.15,
                    }},
                }},
                timeScale: {{
                    borderColor: '#334155',
                    timeVisible: true,
                    secondsVisible: false,
                }},
            }});

            // 1. Candlestick Series (Heikin Ashi or Raw)
            candleSeries = chartInstance.addCandlestickSeries({{
                upColor: '#10b981',
                downColor: '#ef4444',
                borderUpColor: '#10b981',
                borderDownColor: '#ef4444',
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            }});

            const candleData = isHeikinAshi ? data.ha_candles : data.raw_candles;
            candleSeries.setData(candleData);

            // 2. Triple EMAs Series
            ema20Series = chartInstance.addLineSeries({{
                color: '#38bdf8',
                lineWidth: 2,
                title: '20 EMA',
                priceLineVisible: false,
                lastValueVisible: true,
            }});
            ema20Series.setData(data.ema_20 || []);

            ema50Series = chartInstance.addLineSeries({{
                color: '#fbbf24',
                lineWidth: 2,
                title: '50 EMA',
                priceLineVisible: false,
                lastValueVisible: true,
            }});
            ema50Series.setData(data.ema_50 || []);

            ema200Series = chartInstance.addLineSeries({{
                color: '#a855f7',
                lineWidth: 2,
                title: '200 EMA',
                priceLineVisible: false,
                lastValueVisible: true,
            }});
            ema200Series.setData(data.ema_200 || []);

            // 3. SuperTrend Series
            superTrendSeries = chartInstance.addLineSeries({{
                color: '#10b981',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                title: 'SuperTrend',
                priceLineVisible: false,
                lastValueVisible: true,
            }});
            if (data.supertrend && data.supertrend.length > 0) {{
                const stData = data.supertrend.map(st => ({{
                    time: st.time,
                    value: st.value,
                    color: st.color,
                }}));
                superTrendSeries.setData(stData);
            }}

            // 4. Signal Price Lines (Trigger, Stop Loss, Target)
            if (data.signal) {{
                trigPriceLine = candleSeries.createPriceLine({{
                    price: data.signal.trigger_price,
                    color: '#38bdf8',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `TRIGGER ₹${{data.signal.trigger_price}}`,
                }});

                slPriceLine = candleSeries.createPriceLine({{
                    price: data.signal.stop_loss,
                    color: '#f43f5e',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `SL ₹${{data.signal.stop_loss}}`,
                }});

                tgtPriceLine = candleSeries.createPriceLine({{
                    price: data.signal.target_price,
                    color: '#10b981',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `TGT (1:3) ₹${{data.signal.target_price}}`,
                }});
            }}

            // 5. Crosshair Legend Tracking
            chartInstance.subscribeCrosshairMove((param) => {{
                if (!param.time || !param.seriesPrices) {{
                    if (candleData.length > 0) {{
                        const last = candleData[candleData.length - 1];
                        document.getElementById('chartLegendOhlc').innerText = `O: ${{last.open.toFixed(2)}} H: ${{last.high.toFixed(2)}} L: ${{last.low.toFixed(2)}} C: ${{last.close.toFixed(2)}}`;
                    }}
                    return;
                }}

                const cPrice = param.seriesPrices.get(candleSeries);
                if (cPrice) {{
                    document.getElementById('chartLegendOhlc').innerText = `O: ${{cPrice.open?.toFixed(2)}} H: ${{cPrice.high?.toFixed(2)}} L: ${{cPrice.low?.toFixed(2)}} C: ${{cPrice.close?.toFixed(2)}}`;
                }}

                const e20 = param.seriesPrices.get(ema20Series);
                document.getElementById('legEma20').innerText = e20 ? `₹${{e20.toFixed(2)}}` : '--';

                const e50 = param.seriesPrices.get(ema50Series);
                document.getElementById('legEma50').innerText = e50 ? `₹${{e50.toFixed(2)}}` : '--';

                const e200 = param.seriesPrices.get(ema200Series);
                document.getElementById('legEma200').innerText = e200 ? `₹${{e200.toFixed(2)}}` : '--';

                const st = param.seriesPrices.get(superTrendSeries);
                document.getElementById('legSt').innerText = st ? `₹${{st.toFixed(2)}}` : '--';
            }});

            // Set default legend to last candle
            if (candleData.length > 0) {{
                const last = candleData[candleData.length - 1];
                document.getElementById('chartLegendOhlc').innerText = `O: ${{last.open.toFixed(2)}} H: ${{last.high.toFixed(2)}} L: ${{last.low.toFixed(2)}} C: ${{last.close.toFixed(2)}}`;
                if (data.ema_20 && data.ema_20.length) document.getElementById('legEma20').innerText = `₹${{data.ema_20[data.ema_20.length - 1].value.toFixed(2)}}`;
                if (data.ema_50 && data.ema_50.length) document.getElementById('legEma50').innerText = `₹${{data.ema_50[data.ema_50.length - 1].value.toFixed(2)}}`;
                if (data.ema_200 && data.ema_200.length) document.getElementById('legEma200').innerText = `₹${{data.ema_200[data.ema_200.length - 1].value.toFixed(2)}}`;
                if (data.supertrend && data.supertrend.length) document.getElementById('legSt').innerText = `₹${{data.supertrend[data.supertrend.length - 1].value.toFixed(2)}}`;
            }}

            chartInstance.timeScale().fitContent();
        }}

        function toggleChartCandleType() {{
            if (!currentChartData || !candleSeries) return;
            isHeikinAshi = !isHeikinAshi;
            const label = document.getElementById('chartTypeLabel');
            if (isHeikinAshi) {{
                label.innerText = 'Heikin Ashi';
                candleSeries.setData(currentChartData.ha_candles);
            }} else {{
                label.innerText = 'Standard Candles';
                candleSeries.setData(currentChartData.raw_candles);
            }}
        }}

        function toggleEmas() {{
            if (!chartInstance) return;
            showEmas = !showEmas;
            const btn = document.getElementById('toggleEmaBtn');
            if (showEmas) {{
                btn.className = 'px-2.5 py-1.5 bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition';
                if (ema20Series) ema20Series.applyOptions({{ visible: true }});
                if (ema50Series) ema50Series.applyOptions({{ visible: true }});
                if (ema200Series) ema200Series.applyOptions({{ visible: true }});
            }} else {{
                btn.className = 'px-2.5 py-1.5 bg-slate-800 text-slate-400 border border-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition';
                if (ema20Series) ema20Series.applyOptions({{ visible: false }});
                if (ema50Series) ema50Series.applyOptions({{ visible: false }});
                if (ema200Series) ema200Series.applyOptions({{ visible: false }});
            }}
        }}

        function toggleSuperTrend() {{
            if (!chartInstance || !superTrendSeries) return;
            showSuperTrend = !showSuperTrend;
            const btn = document.getElementById('toggleStBtn');
            if (showSuperTrend) {{
                btn.className = 'px-2.5 py-1.5 bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition';
                superTrendSeries.applyOptions({{ visible: true }});
            }} else {{
                btn.className = 'px-2.5 py-1.5 bg-slate-800 text-slate-400 border border-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition';
                superTrendSeries.applyOptions({{ visible: false }});
            }}
        }}

        async function executeOrderFromChart() {{
            if (!currentChartSymbol) return;
            await executeOrder(currentChartSymbol);
        }}

        // Window resize and Escape key support
        window.addEventListener('resize', () => {{
            if (chartInstance) {{
                const container = document.getElementById('tvChartContainer');
                if (container) {{
                    chartInstance.applyOptions({{
                        width: container.clientWidth,
                        height: container.clientHeight,
                    }});
                }}
            }}
        }});

        window.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') {{
                closeChartModal();
            }}
        }});

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

                const actionBtn = `
                    <div class="flex items-center justify-end gap-1.5">
                        <button onclick="openChartModal('${{item.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-[11px] transition shadow">
                            <i class="fa-solid fa-chart-candlestick"></i>
                        </button>
                        ${{item.is_setup_ready
                            ? `<button onclick="executeOrder('${{item.symbol}}')" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-[11px] transition shadow">BUY</button>`
                            : `<button disabled class="px-2.5 py-1 bg-slate-800 text-slate-600 rounded text-[11px] cursor-not-allowed">--</button>`
                        }}
                    </div>
                `;

                return `
                    <tr class="hover:bg-slate-800/50 transition">
                        <td class="p-3 font-bold text-white">
                            <div class="flex items-center gap-2">
                                <button onclick="openChartModal('${{item.symbol}}')" class="text-white hover:text-sky-400 font-bold flex items-center gap-1.5 transition text-left group">
                                    <i class="fa-solid fa-chart-candlestick text-slate-500 group-hover:text-sky-400 text-xs"></i>
                                    <span>${{item.symbol}}</span>
                                </button>
                                <span class="text-[10px] text-slate-500 font-mono">(${{item.sec_id || ''}})</span>
                            </div>
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
                        <td class="p-3 font-bold text-white">
                            <button onclick="openChartModal('${{s.symbol}}')" class="text-white hover:text-sky-400 font-bold flex items-center gap-1.5 transition text-left group">
                                <i class="fa-solid fa-chart-candlestick text-slate-500 group-hover:text-sky-400 text-xs"></i>
                                <span>${{s.symbol}}</span>
                            </button>
                        </td>
                        <td class="p-3 font-mono text-emerald-400">₹${{s.trigger_price}}</td>
                        <td class="p-3 font-mono text-rose-400">₹${{s.stop_loss_price}}</td>
                        <td class="p-3 font-mono text-sky-400">₹${{s.target_profit_price}}</td>
                        <td class="p-3 font-mono text-slate-300">₹${{s.risk_per_share}}</td>
                        <td class="p-3 text-slate-300">${{s.nearest_ema_name}}</td>
                        <td class="p-3"><span class="badge-green px-2 py-0.5 rounded text-[11px] font-semibold">${{s.status}}</span></td>
                        <td class="p-3 text-right">
                            <div class="flex items-center justify-end gap-1.5">
                                <button onclick="openChartModal('${{s.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-xs shadow transition">
                                    <i class="fa-solid fa-chart-candlestick"></i>
                                </button>
                                <button onclick="executeOrder('${{s.symbol}}')" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow transition">BUY</button>
                            </div>
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
