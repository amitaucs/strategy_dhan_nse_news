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

executor = OrderExecutor(dry_run=settings.DRY_RUN)
runner = StrategyRunner(
    on_signal_callback=repository.save_signal,
    executor=executor,
    auto_order=settings.AUTO_ORDER,
)


@app.on_event("startup")
def on_startup():
    logger.info("ST15 Strategy Dashboard ready on Port %d", settings.PORT)


@app.on_event("shutdown")
def on_shutdown():
    logger.info("Stopping ST15 Strategy background services...")
    runner.stop_background_loop()


@app.get("/api/chart/{symbol}")
def get_chart_data(symbol: str, refresh: bool = False) -> Dict[str, Any]:
    """Get 2H candles, Heikin Ashi, 20/50/200 EMAs, SuperTrend, and signal levels for charting."""
    sym = symbol.upper().strip()
    sec_id = universe_manager.get_security_id(sym)
    candles = runner.fetcher.fetch_2h_candles(
        security_id=sec_id,
        symbol=sym,
        days=settings.HISTORY_DAYS,
        force_refresh=refresh,
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

    # Freshly evaluate multi-gate screener on the exact candles returned
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
            "invalidation_reason": scan_res.invalidation_reason if scan_res else "",
        },
        "signal": signal_info,
    }


@app.post("/api/cache/clear")
def clear_caches() -> Dict[str, Any]:
    """Clear candle and scanner caches."""
    runner.clear_cache()
    return {"status": "success", "message": "All caches successfully cleared"}


@app.get("/api/status")
def get_status() -> Dict[str, Any]:
    """Strategy operational status."""
    tol = runner.screener.ema_proximity_pct
    prefix = "+" if tol > 0 else ""
    
    if runner.latest_results:
        triggered_count = len([r for r in runner.latest_results if r.is_setup_ready])
        scanned_count = len(runner.latest_results)
    else:
        scanned_count = 0
        triggered_count = 0
    today_orders = repository.get_today_orders()
    today_active_count = sum(
        1 for o in today_orders
        if o.get("status") in ("PLACED", "SIMULATED", "FILLED", "OPEN")
    )
    remaining_positions = max(0, settings.MAX_POSITIONS_PER_DAY - today_active_count)

    return {
        "strategy": "ST15_LargeCap",
        "universe": "Nifty 200",
        "timeframe": "2-Hour (120-min) Heikin Ashi",
        "is_scanner_running": runner.is_running,
        "is_scanning": runner.is_scanning,
        "scan_progress": runner.scan_progress,
        "scan_total": runner.scan_total,
        "mode": "VIRTUAL" if executor.dry_run else "LIVE",
        "dry_run": executor.dry_run,
        "order_mode": "AUTO" if runner.auto_order else "MANUAL",
        "auto_order": runner.auto_order,
        "dhan_client_id": settings.DHAN_CLIENT_ID or "NOT_CONFIGURED",
        "dhan_connected": bool(settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN),
        "ema_stack": f"{settings.EMA_FAST} > {settings.EMA_MID} > {settings.EMA_SLOW}",
        "dip_tolerance_pct": f"≤ {prefix}{tol:.2f}%",
        "proximity_tolerance_pct": f"≤ {prefix}{tol:.2f}%",
        "tolerance_value": tol,
        "supertrend": f"ATR({settings.SUPERTREND_PERIOD}), Mult({settings.SUPERTREND_MULTIPLIER})",
        "risk_reward_ratio": f"1:{settings.RISK_REWARD_RATIO}",
        "total_capital": settings.TOTAL_CAPITAL,
        "capital_allocation_pct": settings.CAPITAL_ALLOCATION_PCT,
        "capital_per_position": settings.CAPITAL_PER_POSITION,
        "capital_per_trade": f"₹{settings.CAPITAL_PER_POSITION:,.2f}",
        "max_positions_per_day": settings.MAX_POSITIONS_PER_DAY,
        "today_orders_count": today_active_count,
        "remaining_positions_today": remaining_positions,
        "order_type": settings.ORDER_TYPE,
        "last_scan_time": runner.last_scan_time.isoformat() if runner.last_scan_time else None,
        "scanned_count": scanned_count,
        "triggered_count": triggered_count,
        "scan_interval_minutes": settings.SCAN_INTERVAL_MINUTES,
    }


@app.post("/api/toggle-mode")
def toggle_execution_mode() -> Dict[str, Any]:
    """Toggle between VIRTUAL (simulated) and LIVE (real money DhanHQ) mode."""
    new_dry_run = not executor.dry_run
    executor.set_mode(new_dry_run)
    runner.set_execution_mode(new_dry_run)
    mode_name = "VIRTUAL" if new_dry_run else "LIVE"
    logger.info("Switched execution mode to %s", mode_name)
    return {
        "status": "success",
        "mode": mode_name,
        "dry_run": new_dry_run,
        "message": f"Execution mode switched to {mode_name}",
    }


@app.post("/api/mode")
async def set_execution_mode(request: Request) -> Dict[str, Any]:
    """Explicitly set execution mode: LIVE or VIRTUAL."""
    payload = await request.json()
    mode = str(payload.get("mode", "")).upper()
    if mode in ("LIVE", "REAL"):
        dry_run = False
    elif mode in ("VIRTUAL", "PAPER", "DRY_RUN", "DRYRUN"):
        dry_run = True
    elif "dry_run" in payload:
        dry_run = bool(payload.get("dry_run"))
    else:
        return {"status": "error", "message": "Invalid mode specified. Use 'LIVE' or 'VIRTUAL'."}

    executor.set_mode(dry_run)
    runner.set_execution_mode(dry_run)
    mode_name = "VIRTUAL" if dry_run else "LIVE"
    return {
        "status": "success",
        "mode": mode_name,
        "dry_run": dry_run,
        "message": f"Execution mode set to {mode_name}",
    }


@app.post("/api/toggle-auto-order")
def toggle_auto_order() -> Dict[str, Any]:
    """Toggle between AUTO (bot places order automatically) and MANUAL (user must click BUY)."""
    new_auto = not runner.auto_order
    runner.set_auto_order(new_auto)
    order_mode = "AUTO" if new_auto else "MANUAL"
    logger.info("Switched order placement mode to %s", order_mode)
    return {
        "status": "success",
        "order_mode": order_mode,
        "auto_order": new_auto,
        "message": f"Order placement mode switched to {order_mode}",
    }


@app.post("/api/auto-order")
async def set_auto_order(request: Request) -> Dict[str, Any]:
    """Explicitly set auto order placement mode: true or false, AUTO or MANUAL."""
    payload = await request.json()
    mode_str = str(payload.get("order_mode", payload.get("mode", ""))).upper()
    if mode_str in ("AUTO", "BOT", "AUTOMATIC"):
        auto_val = True
    elif mode_str in ("MANUAL", "USER"):
        auto_val = False
    elif "auto_order" in payload:
        auto_val = bool(payload.get("auto_order"))
    elif "auto" in payload:
        auto_val = bool(payload.get("auto"))
    else:
        auto_val = False

    runner.set_auto_order(auto_val)
    order_mode = "AUTO" if auto_val else "MANUAL"
    return {
        "status": "success",
        "order_mode": order_mode,
        "auto_order": auto_val,
        "message": f"Order placement mode set to {order_mode}",
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
    """Get latest universe scan results from the current active session.
    
    Returns empty list on server startup until the user runs a scan.
    """
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
                "invalidation_reason": r.invalidation_reason,
                "swing_low": r.swing_low,
                "scanned_at": r.scanned_at.isoformat(),
            }
            for r in runner.latest_results
        ]
    return []


@app.get("/api/signals")
def get_signals() -> List[Dict[str, Any]]:
    """Get active setup signals from current scan session.
    
    Returns empty list on server startup until a scan is performed.
    """
    signals_list = []
    if runner.latest_signals:
        signals_list = runner.latest_signals
    elif runner.latest_results:
        signals_list = [r.signal for r in runner.latest_results if r.is_setup_ready and r.signal]

    if signals_list:
        results = []
        for i, s in enumerate(signals_list):
            matching_scan = next((r for r in runner.latest_results if r.symbol == s.symbol), None)
            is_active = matching_scan.is_setup_ready if matching_scan else True
            inval_reason = matching_scan.invalidation_reason if (matching_scan and not is_active) else s.invalidation_reason
            status_val = "FALLEN" if not is_active else (s.status.value if hasattr(s.status, "value") else str(s.status))

            results.append({
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
                "is_active": is_active,
                "invalidation_reason": inval_reason,
                "status": status_val,
                "created_at": datetime.now().isoformat(),
            })
        return results

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
    if runner.is_scanning:
        return {"status": "in_progress", "message": "Universe scan is already in progress"}
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
    """Manually dispatch an entry order for a qualified setup with real-time validation."""
    sym = symbol.upper().strip()
    success, trade_order, message = runner.validate_and_execute(sym)
    if not success:
        return {
            "status": "error",
            "reason": "SETUP_FALLEN",
            "message": message,
        }

    return {
        "status": "success",
        "mode": "VIRTUAL" if trade_order.dry_run else "LIVE",
        "order": trade_order.__dict__,
        "message": message,
    }


@app.get("/", response_class=HTMLResponse)
def index_page() -> str:
    """Render the full ST15 Large-Cap dashboard."""
    is_live = not executor.dry_run
    mode_cls = "badge-green" if is_live else "badge-yellow"
    mode_icon = '<i class="fa-solid fa-bolt text-emerald-300"></i>' if is_live else '<i class="fa-solid fa-flask text-amber-400"></i>'
    mode_label = "LIVE (Real)" if is_live else "VIRTUAL (Paper)"
    mode_title = "LIVE trading is ACTIVE. Real orders dispatched to DhanHQ broker. Click to switch to VIRTUAL." if is_live else "VIRTUAL (Paper trading) is ACTIVE. No real broker orders. Click to switch to LIVE."

    is_auto = runner.auto_order
    order_cls = "border-purple-500/50 bg-purple-600/30 text-purple-300 hover:bg-purple-600/40" if is_auto else "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-750"
    order_icon = '<i class="fa-solid fa-robot text-purple-400 animate-pulse"></i>' if is_auto else '<i class="fa-solid fa-hand-pointer text-sky-400"></i>'
    order_label = "AUTO BOT" if is_auto else "MANUAL"
    order_title = "AUTO-BOT is ACTIVE. Scans will auto-dispatch qualified setups. Click to switch to MANUAL." if is_auto else "MANUAL mode is ACTIVE. User must click BUY to place orders. Click to switch to AUTO BOT."

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
                    <p class="text-xs text-slate-400">2H Heikin Ashi • Triple EMA (20/50/200) • SuperTrend • 15m Interval • DhanHQ Positional (Port 8015)</p>
                </div>
            </div>
        </div>
        <div class="flex flex-wrap items-center gap-3">
            <!-- Mode Toggle Button (LIVE vs VIRTUAL) -->
            <button id="modeToggleBtn" onclick="toggleExecutionMode()" 
                    class="px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition border shadow-sm {mode_cls} hover:brightness-110 cursor-pointer"
                    title="{mode_title}">
                {mode_icon}
                <span>{mode_label}</span>
            </button>

            <!-- Order Placement Mode Toggle Button (MANUAL vs AUTO BOT) -->
            <button id="orderModeToggleBtn" onclick="toggleOrderMode()" 
                    class="px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition border {order_cls} shadow-sm cursor-pointer"
                    title="{order_title}">
                {order_icon}
                <span>{order_label}</span>
            </button>

            <!-- Scanner Status Badge -->
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
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5 mb-6">
        <div onclick="resetAllFilters()" class="card-bg p-3.5 rounded-xl shadow cursor-pointer hover:border-blue-500/50 transition" title="Click to view all 200 universe stocks">
            <span class="text-xs font-medium text-slate-400">Universe Size</span>
            <div class="text-xl font-bold text-white mt-1" id="metricUniverse">200</div>
            <span class="text-[11px] text-slate-500">Nifty 200 Large Caps</span>
        </div>
        <div onclick="filterToQualifiedOnly()" class="card-bg p-3.5 rounded-xl shadow cursor-pointer hover:border-emerald-500/50 transition" title="Click to filter table to ONLY BUY Trigger qualified setups">
            <span class="text-xs font-medium text-slate-400 flex items-center justify-between">
                <span>Qualified Setups</span>
                <i class="fa-solid fa-filter text-[10px] text-emerald-400"></i>
            </span>
            <div class="text-xl font-bold text-emerald-400 mt-1" id="metricQualified">0</div>
            <span class="text-[11px] text-slate-500">All 4 Gates Passed (Click to filter)</span>
        </div>
        <div class="card-bg p-3.5 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Risk : Reward</span>
            <div class="text-xl font-bold text-sky-400 mt-1">1 : 3.0</div>
            <span class="text-[11px] text-slate-500">Swing Low SL</span>
        </div>
        <div class="card-bg p-3.5 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Dip Tolerance</span>
            <div class="text-xl font-bold text-amber-400 mt-1" id="metricDipTol">≤ +0.50%</div>
            <span class="text-[11px] text-slate-500">Adjustable on screen</span>
        </div>
        <div class="card-bg p-3.5 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Capital / Order</span>
            <div class="text-xl font-bold text-emerald-400 mt-1" id="metricCapitalOrder">33%</div>
            <span class="text-[11px] text-slate-500" id="metricCapitalSub">₹33,000 / trade</span>
        </div>
        <div class="card-bg p-3.5 rounded-xl shadow">
            <span class="text-xs font-medium text-slate-400">Daily Positions</span>
            <div class="text-xl font-bold text-purple-400 mt-1" id="metricDailyPos">0 / 3</div>
            <span class="text-[11px] text-slate-500" id="metricDailyPosSub">Max 3 / day</span>
        </div>
    </div>

    <!-- Strategy Rule Banner -->
    <div class="card-bg p-4 rounded-xl mb-6 border border-slate-700/80 flex flex-col md:flex-row justify-between items-center gap-4 text-xs">
        <div class="flex items-center gap-4 flex-wrap">
            <span class="font-semibold text-slate-300"><i class="fa-solid fa-list-check text-blue-400 mr-1.5"></i> Entry Gates:</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-slate-700">1. Bullish Stack (20 &gt; 50 &gt; 200 EMA)</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-amber-500/40 text-amber-300 font-semibold" id="ruleBannerDip">2. Pullback Dip (≤ +0.50% or Touch EMA)</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-slate-700">3. 1st Green HA Candle (Bounce)</span>
            <span class="px-2 py-1 bg-slate-800 rounded border border-slate-700">4. SuperTrend Green (Already Green or Flips Green)</span>
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
                <button onclick="copyTvWatchlist()" id="copyWatchlistBtn" title="Copy all visible filtered symbols in TradingView format (e.g. NSE:RELIANCE, NSE:TCS...)" 
                        class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-white rounded-lg text-xs font-semibold border border-slate-600 transition flex items-center gap-1.5 shadow cursor-pointer">
                    <i class="fa-regular fa-copy text-xs"></i> Copy TV Watchlist
                </button>
                <button onclick="clearAndRescan()" id="freshRescanBtn" title="Clear candle cache and force fresh live scan across all 200 universe stocks" 
                        class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg text-xs font-semibold border border-slate-600 transition flex items-center gap-1.5 shadow cursor-pointer">
                    <i class="fa-solid fa-arrows-rotate text-xs"></i> Fresh Rescan
                </button>
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
                        <th class="p-3">
                            <div class="flex items-center justify-between gap-2">
                                <span class="cursor-pointer hover:text-white transition flex items-center" onclick="sortTable('symbol')" title="Sort by Symbol">
                                    Symbol <i class="fa-solid fa-sort text-[10px] ml-1 text-slate-500"></i>
                                </span>
                                <button onclick="copyTvWatchlist(event)" id="copyAllTvHeaderBtn" title="Copy all displayed symbols in TradingView Watchlist format (NSE:SYM1, NSE:SYM2...)" 
                                        class="px-2 py-0.5 bg-slate-800 hover:bg-sky-600/30 text-sky-400 hover:text-white rounded border border-slate-600 font-semibold text-[11px] normal-case transition flex items-center gap-1 cursor-pointer">
                                    <i class="fa-regular fa-copy text-xs"></i> Copy Watchlist
                                </button>
                            </div>
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
                        <th class="p-3">
                            <div class="flex items-center justify-between gap-2">
                                <span>Symbol</span>
                                <button onclick="copySignalsWatchlist(event)" id="copySignalsWatchlistBtn" title="Copy all qualified signal symbols in TradingView Watchlist format (NSE:SYM1, NSE:SYM2...)" 
                                        class="px-2 py-0.5 bg-slate-800 hover:bg-sky-600/30 text-sky-400 hover:text-white rounded border border-slate-600 font-semibold text-[11px] normal-case transition flex items-center gap-1 cursor-pointer">
                                    <i class="fa-regular fa-copy text-xs"></i> Copy Watchlist
                                </button>
                            </div>
                        </th>
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
                            <button onclick="copyTvSymbol(event, currentChartSymbol)" id="chartModalCopyTvBtn" title="Copy TradingView symbol (NSE:...)" class="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-sky-400 rounded-md text-[11px] font-semibold border border-slate-700 transition flex items-center gap-1 cursor-pointer">
                                <i class="fa-regular fa-copy text-xs"></i> Copy TV
                            </button>
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

                    <!-- Force Refresh Chart Data -->
                    <button onclick="openChartModal(currentChartSymbol, true)" class="p-2 text-slate-400 hover:text-sky-400 rounded-lg hover:bg-slate-700/60 transition" title="Force Refresh Live Data &amp; Indicators">
                        <i class="fa-solid fa-arrows-rotate text-base"></i>
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

    <!-- Toast Notification Container -->
    <div id="toastContainer" class="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none"></div>

    <script>
        let allScans = [];
        let currentlyDisplayedSymbols = [];
        let lastFetchedSignals = [];
        let qualifiedOnly = false;
        let currentTolerance = 0.5;
        let currentMode = 'VIRTUAL';
        let currentOrderMode = 'MANUAL';
        let isAutoOrder = false;
        let isDryRun = true;
        let isScanningActive = false;
        let scanPollInterval = null;
        let lastKnownScanTime = null;

        // Toast & Clipboard Helpers
        function showToast(message, type = 'info') {{
            const container = document.getElementById('toastContainer');
            if (!container) return;
            const toast = document.createElement('div');
            const bgClass = type === 'success' ? 'bg-slate-900/95 border-emerald-500/50 text-emerald-300' : 'bg-slate-900/95 border-sky-500/50 text-sky-200';
            const iconClass = type === 'success' ? 'fa-solid fa-circle-check text-emerald-400' : 'fa-solid fa-clipboard-check text-sky-400';
            toast.className = `px-4 py-2.5 rounded-xl shadow-2xl text-xs font-semibold flex items-center gap-2.5 border backdrop-blur-md transform transition-all duration-300 translate-y-3 opacity-0 ${{bgClass}} pointer-events-auto`;
            toast.innerHTML = `<i class="${{iconClass}} text-sm"></i> <span>${{message}}</span>`;
            container.appendChild(toast);

            setTimeout(() => {{
                toast.classList.remove('translate-y-3', 'opacity-0');
            }}, 10);

            setTimeout(() => {{
                toast.classList.add('opacity-0', 'translate-y-3');
                setTimeout(() => toast.remove(), 350);
            }}, 2200);
        }}

        function copyTextToClipboard(text, successMsg = 'Copied to clipboard!') {{
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(text).then(() => {{
                    showToast(successMsg, 'success');
                }}).catch(() => {{
                    fallbackCopyText(text, successMsg);
                }});
            }} else {{
                fallbackCopyText(text, successMsg);
            }}
        }}

        function fallbackCopyText(text, successMsg) {{
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {{
                document.execCommand('copy');
                showToast(successMsg, 'success');
            }} catch (err) {{
                alert('Could not copy text: ' + err);
            }}
            textArea.remove();
        }}

        function copyTvSymbol(event, symbol) {{
            if (event) {{
                event.stopPropagation();
                event.preventDefault();
            }}
            if (!symbol) return;
            const tvSymbol = 'NSE:' + String(symbol).trim().toUpperCase();
            copyTextToClipboard(tvSymbol, `Copied ${{tvSymbol}} for TradingView`);

            const btn = event ? (event.currentTarget || (event.target && event.target.closest('button'))) : null;
            if (btn) {{
                const icon = btn.querySelector('i');
                if (icon) {{
                    const prevClass = icon.className;
                    icon.className = 'fa-solid fa-check text-emerald-400';
                    setTimeout(() => {{
                        icon.className = prevClass;
                    }}, 1500);
                }}
            }}
        }}

        function copyTvWatchlist(event) {{
            if (event) {{
                event.stopPropagation();
                event.preventDefault();
            }}
            const symbolsToCopy = (currentlyDisplayedSymbols && currentlyDisplayedSymbols.length > 0)
                ? currentlyDisplayedSymbols
                : allScans.map(s => s.symbol);

            if (!symbolsToCopy || symbolsToCopy.length === 0) {{
                showToast('No symbols found to copy', 'info');
                return;
            }}

            const tvList = symbolsToCopy.map(s => 'NSE:' + String(s).trim().toUpperCase()).join(', ');
            copyTextToClipboard(tvList, `Copied ${{symbolsToCopy.length}} symbols in TradingView Watchlist format`);

            const btn = event ? (event.currentTarget || (event.target && event.target.closest('button'))) : null;
            if (btn) {{
                const icon = btn.querySelector('i');
                if (icon) {{
                    const prevClass = icon.className;
                    icon.className = 'fa-solid fa-check text-emerald-400';
                    setTimeout(() => {{
                        icon.className = prevClass;
                    }}, 1500);
                }}
            }}
        }}

        function copySignalsWatchlist(event) {{
            if (event) {{
                event.stopPropagation();
                event.preventDefault();
            }}
            const symbolsToCopy = (lastFetchedSignals && lastFetchedSignals.length > 0)
                ? lastFetchedSignals.map(s => s.symbol)
                : allScans.filter(s => s.is_setup_ready).map(s => s.symbol);

            if (!symbolsToCopy || symbolsToCopy.length === 0) {{
                showToast('No qualified signals to copy', 'info');
                return;
            }}

            const tvList = symbolsToCopy.map(s => 'NSE:' + String(s).trim().toUpperCase()).join(', ');
            copyTextToClipboard(tvList, `Copied ${{symbolsToCopy.length}} signals in TradingView Watchlist format`);

            const btn = event ? (event.currentTarget || (event.target && event.target.closest('button'))) : null;
            if (btn) {{
                const icon = btn.querySelector('i');
                if (icon) {{
                    const prevClass = icon.className;
                    icon.className = 'fa-solid fa-check text-emerald-400';
                    setTimeout(() => {{
                        icon.className = prevClass;
                    }}, 1500);
                }}
            }}
        }}

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

        async function openChartModal(symbol, forceRefresh = false) {{
            currentChartSymbol = symbol;
            const modal = document.getElementById('chartModal');
            const overlay = document.getElementById('chartLoadingOverlay');
            modal.classList.remove('hidden');
            if (overlay) overlay.classList.remove('hidden');

            document.getElementById('chartModalSymbol').innerText = symbol;
            document.getElementById('chartModalSecId').innerText = 'Loading...';
            document.getElementById('chartModalPrice').innerText = '₹--.--';

            try {{
                const url = forceRefresh ? `/api/chart/${{symbol}}?refresh=true` : `/api/chart/${{symbol}}`;
                const res = await fetch(url);
                const data = await res.json();
                if (data.status !== 'success') {{
                    alert(data.message || 'Failed to load chart data');
                    closeChartModal();
                    return;
                }}
                currentChartData = data;
                renderTvChart(data);
                if (forceRefresh) {{
                    showToast(`Fresh 2H data reloaded for ${{symbol}}`, 'info');
                }}
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
            const buyBtn = document.getElementById('chartBuyBtn');
            const isReady = data.scan && data.scan.is_setup_ready;

            if (isReady) {{
                trigBadge.className = 'text-[11px] font-bold px-2.5 py-0.5 rounded-full badge-green animate-pulse';
                trigBadge.innerHTML = '<i class="fa-solid fa-crosshairs mr-1"></i> BUY SETUP READY';
                if (buyBtn) {{
                    buyBtn.className = 'px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold transition shadow flex items-center gap-1.5 cursor-pointer';
                    buyBtn.disabled = false;
                    buyBtn.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Buy Setup';
                    buyBtn.title = 'Dispatch ST15 order for ' + data.symbol;
                }}
            }} else {{
                trigBadge.className = 'text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700';
                trigBadge.innerText = 'WATCHING';
                if (buyBtn) {{
                    buyBtn.className = 'px-3.5 py-1.5 bg-slate-800 text-slate-500 rounded-lg text-xs font-bold border border-slate-700 cursor-not-allowed flex items-center gap-1.5';
                    buyBtn.disabled = true;
                    buyBtn.innerHTML = '<i class="fa-solid fa-ban"></i> Setup Disabled';
                    buyBtn.title = 'Setup Not Ready / Fallen';
                }}
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
                if (!data.scan.is_ema_stacked) {{
                    gDip.className = 'px-2 py-0.5 rounded font-mono text-[11px] text-slate-400 bg-slate-900/90 border border-slate-700';
                    gDip.innerHTML = '<i class="fa-solid fa-ban mr-1 text-slate-500"></i> Dip: N/A (EMAs Inverted)';
                }} else if (data.scan.is_in_dip) {{
                    gDip.className = 'px-2 py-0.5 rounded font-mono text-[11px] badge-green';
                    gDip.innerHTML = `<i class="fa-solid fa-check mr-1"></i> Dip: ${{data.scan.nearest_ema}} (${{prefix}}${{dist.toFixed(2)}}%)`;
                }} else {{
                    gDip.className = 'px-2 py-0.5 rounded font-mono text-[11px] text-slate-400 bg-slate-800/80 border border-slate-700';
                    gDip.innerHTML = `Dip: ${{data.scan.nearest_ema || 'None'}} (${{prefix}}${{dist.toFixed(2)}}%)`;
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

        function startScanProgressWatcher() {{
            if (!scanPollInterval) {{
                scanPollInterval = setInterval(fetchStatus, 600);
            }}
        }}

        function stopScanProgressWatcher() {{
            if (scanPollInterval) {{
                clearInterval(scanPollInterval);
                scanPollInterval = null;
            }}
        }}

        async function fetchStatus() {{
            try {{
                const res = await fetch('/api/status');
                const data = await res.json();
                let scanTimeChanged = false;
                if (data.last_scan_time) {{
                    if (lastKnownScanTime && lastKnownScanTime !== data.last_scan_time) {{
                        scanTimeChanged = true;
                    }}
                    lastKnownScanTime = data.last_scan_time;
                    const d = new Date(data.last_scan_time);
                    document.getElementById('lastScanTime').innerText = d.toLocaleTimeString();
                }}
                document.getElementById('metricUniverse').innerText = data.scanned_count || '200';
                document.getElementById('metricQualified').innerText = data.triggered_count || '0';
                
                if (scanTimeChanged && !data.is_scanning) {{
                    await fetchScans();
                    await fetchSignals();
                }}
                
                if (data.tolerance_value !== undefined) {{
                    currentTolerance = data.tolerance_value;
                    updateToleranceDisplay(currentTolerance);
                }}

                currentMode = data.mode || 'VIRTUAL';
                isDryRun = data.dry_run !== undefined ? data.dry_run : true;
                currentOrderMode = data.order_mode || 'MANUAL';
                isAutoOrder = Boolean(data.auto_order);

                // Update Mode Toggle Button
                const modeBtn = document.getElementById('modeToggleBtn');
                if (modeBtn) {{
                    if (currentMode === 'LIVE') {{
                        modeBtn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition border shadow-sm badge-green hover:brightness-110 cursor-pointer';
                        modeBtn.innerHTML = '<i class="fa-solid fa-bolt text-emerald-300"></i> <span>LIVE (Real)</span>';
                        modeBtn.title = 'LIVE trading is ACTIVE. Real orders dispatched to DhanHQ broker. Click to switch to VIRTUAL.';
                    }} else {{
                        modeBtn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition border shadow-sm badge-yellow hover:brightness-110 cursor-pointer';
                        modeBtn.innerHTML = '<i class="fa-solid fa-flask text-amber-400"></i> <span>VIRTUAL (Paper)</span>';
                        modeBtn.title = 'VIRTUAL (Paper trading) is ACTIVE. No real broker orders. Click to switch to LIVE.';
                    }}
                }}

                // Update Order Placement Mode Toggle Button
                const orderBtn = document.getElementById('orderModeToggleBtn');
                if (orderBtn) {{
                    if (isAutoOrder) {{
                        orderBtn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition border border-purple-500/50 bg-purple-600/30 text-purple-300 hover:bg-purple-600/40 shadow-sm cursor-pointer';
                        orderBtn.innerHTML = '<i class="fa-solid fa-robot text-purple-400 animate-pulse"></i> <span>AUTO BOT</span>';
                        orderBtn.title = 'AUTO-BOT is ACTIVE. Scans will auto-dispatch qualified setups. Click to switch to MANUAL.';
                    }} else {{
                        orderBtn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-750 shadow-sm cursor-pointer';
                        orderBtn.innerHTML = '<i class="fa-solid fa-hand-pointer text-sky-400"></i> <span>MANUAL</span>';
                        orderBtn.title = 'MANUAL mode is ACTIVE. User must click BUY to place orders. Click to switch to AUTO BOT.';
                    }}
                }}

                // Update Metric Strip
                const metricCapOrder = document.getElementById('metricCapitalOrder');
                if (metricCapOrder && data.capital_allocation_pct !== undefined) {{
                    metricCapOrder.innerText = `${{data.capital_allocation_pct}}%`;
                }}
                const metricCapSub = document.getElementById('metricCapitalSub');
                if (metricCapSub && data.capital_per_position !== undefined) {{
                    metricCapSub.innerText = `₹${{Number(data.capital_per_position).toLocaleString()}} / trade`;
                }}
                const metricDaily = document.getElementById('metricDailyPos');
                if (metricDaily && data.max_positions_per_day !== undefined) {{
                    const todayCount = data.today_orders_count || 0;
                    metricDaily.innerText = `${{todayCount}} / ${{data.max_positions_per_day}}`;
                    if (todayCount >= data.max_positions_per_day) {{
                        metricDaily.className = 'text-xl font-bold text-rose-400 mt-1';
                    }} else {{
                        metricDaily.className = 'text-xl font-bold text-purple-400 mt-1';
                    }}
                }}
                const metricDailySub = document.getElementById('metricDailyPosSub');
                if (metricDailySub && data.remaining_positions_today !== undefined) {{
                    metricDailySub.innerText = `${{data.remaining_positions_today}} remaining today`;
                }}

                const toggleBtn = document.getElementById('toggleBtn');
                const badge = document.getElementById('scannerStatusBadge');
                const scanIcon = document.getElementById('scanIcon');

                // Handle is_scanning live status
                if (data.is_scanning) {{
                    isScanningActive = true;
                    if (scanIcon) scanIcon.classList.add('animate-spin');
                    badge.className = 'px-3 py-1 text-xs rounded-full badge-yellow font-semibold';
                    const prog = data.scan_progress || 0;
                    const tot = data.scan_total || 200;
                    badge.innerHTML = `<i class="fa-solid fa-arrows-rotate animate-spin mr-1"></i> SCANNING (${{prog}}/${{tot}})`;
                    
                    // If no scans loaded yet, show live scanning in table placeholder
                    if (allScans.length === 0) {{
                        const tbody = document.getElementById('scannerTableBody');
                        if (tbody) {{
                            tbody.innerHTML = `
                                <tr>
                                    <td colspan="8" class="p-12 text-center text-slate-400">
                                        <div class="flex flex-col items-center justify-center gap-3">
                                            <i class="fa-solid fa-arrows-rotate animate-spin text-3xl text-sky-400 mb-1"></i>
                                            <span class="text-sm font-semibold text-white">Scanning Nifty 200 Universe...</span>
                                            <div class="w-64 bg-slate-800 rounded-full h-2.5 overflow-hidden border border-slate-700 mt-1">
                                                <div class="bg-blue-500 h-2.5 rounded-full transition-all duration-300" style="width: ${{tot > 0 ? Math.min(100, Math.round(prog / tot * 100)) : 0}}%"></div>
                                            </div>
                                            <p class="text-xs text-slate-400 font-mono">${{prog}} of ${{tot}} stocks evaluated</p>
                                        </div>
                                    </td>
                                </tr>
                            `;
                        }}
                    }}

                    // Start rapid polling
                    startScanProgressWatcher();
                }} else {{
                    // Check if scan just transitioned from running to finished
                    if (isScanningActive) {{
                        isScanningActive = false;
                        stopScanProgressWatcher();
                        if (scanIcon) scanIcon.classList.remove('animate-spin');
                        const rescanBtn = document.getElementById('freshRescanBtn');
                        if (rescanBtn) rescanBtn.classList.remove('opacity-50', 'pointer-events-none');
                        await fetchScans();
                        await fetchSignals();
                        showToast(`Universe scan complete! ${{data.scanned_count || 200}} stocks evaluated.`, 'success');
                    }}

                    if (data.is_scanner_running) {{
                        const intervalMin = data.scan_interval_minutes || 15;
                        toggleBtn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause Scanner';
                        badge.className = 'px-3 py-1 text-xs rounded-full badge-green font-semibold';
                        badge.innerHTML = `<i class="fa-solid fa-circle-dot mr-1 animate-pulse"></i> SCANNER LIVE (${{intervalMin}}m)`;
                    }} else {{
                        toggleBtn.innerHTML = '<i class="fa-solid fa-play"></i> Start Scanner';
                        badge.className = 'px-3 py-1 text-xs rounded-full badge-blue font-semibold';
                        badge.innerHTML = '<i class="fa-solid fa-check mr-1"></i> READY';
                    }}
                }}
            }} catch(e) {{
                console.error(e);
            }}
        }}

        async function toggleExecutionMode() {{
            const targetMode = currentMode === 'VIRTUAL' ? 'LIVE' : 'VIRTUAL';
            if (targetMode === 'LIVE') {{
                const confirmed = confirm(
                    "⚠️ ATTENTION: SWITCH TO LIVE TRADING MODE?\\n\\n" +
                    "• In LIVE mode, real orders will be placed on your DhanHQ trading account using REAL MONEY.\\n" +
                    "• Ensure your Dhan credentials and margin are verified.\\n\\n" +
                    "Are you sure you want to switch to LIVE mode?"
                );
                if (!confirmed) return;
            }}
            
            try {{
                const res = await fetch('/api/toggle-mode', {{ method: 'POST' }});
                const data = await res.json();
                if (data.status === 'success') {{
                    currentMode = data.mode;
                    isDryRun = data.dry_run;
                    await fetchStatus();
                }} else {{
                    alert('Failed to switch execution mode: ' + (data.message || 'Unknown error'));
                }}
            }} catch(e) {{
                alert('Mode switch error: ' + e);
            }}
        }}

        async function toggleOrderMode() {{
            const willEnableAuto = !isAutoOrder;
            if (willEnableAuto) {{
                const confirmed = confirm(
                    `🤖 ENABLE AUTO-BOT ORDER EXECUTION?\\n\\n` +
                    `• The bot will automatically place BUY orders whenever a Nifty 200 stock qualifies all ST15 criteria.\\n` +
                    `• Current Execution Mode: ${{currentMode}}\\n` +
                    `• Max 1 trade per symbol per trading day.\\n\\n` +
                    `Enable AUTO BOT now?`
                );
                if (!confirmed) return;
            }}
            
            try {{
                const res = await fetch('/api/toggle-auto-order', {{ method: 'POST' }});
                const data = await res.json();
                if (data.status === 'success') {{
                    isAutoOrder = data.auto_order;
                    currentOrderMode = data.order_mode;
                    await fetchStatus();
                }} else {{
                    alert('Failed to toggle auto order: ' + (data.message || 'Unknown error'));
                }}
            }} catch(e) {{
                alert('Order mode error: ' + e);
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

        function filterToQualifiedOnly() {{
            switchTab('scannerTab');
            const fTrig = document.getElementById('filterTrigger');
            if (fTrig) fTrig.value = 'qualified';
            qualifiedOnly = true;
            renderScannerTable();
            showToast('Showing only BUY Trigger qualified setups', 'success');
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
                const wasTriggerQualified = item.is_setup_ready || (item.invalidation_reason && item.invalidation_reason.startsWith('Dip:'));
                item.is_setup_ready = Boolean(item.is_ema_stacked && item.is_in_dip && item.is_ha_green && item.is_supertrend_green && wasTriggerQualified);
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
            currentlyDisplayedSymbols = filtered.map(s => s.symbol);

            if (allScans.length === 0) {{
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="p-12 text-center text-slate-400">
                            <div class="flex flex-col items-center justify-center gap-2">
                                <i class="fa-solid fa-radar text-3xl text-slate-600 mb-1"></i>
                                <span class="text-sm font-semibold text-slate-300">Scanner Ready (0 Scanned)</span>
                                <p class="text-xs text-slate-500 max-w-md">No universe scan results loaded yet. Click <button onclick="triggerScanNow()" class="text-sky-400 font-bold hover:underline cursor-pointer">Scan Universe</button> or start the background scanner to fetch live market candles across Nifty 200.</p>
                            </div>
                        </td>
                    </tr>
                `;
                return;
            }}

            if (filtered.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="8" class="p-6 text-center text-slate-500">No matching stocks found for selected filters. <button onclick="resetAllFilters()" class="text-sky-400 underline ml-1 cursor-pointer">Reset Filters</button></td></tr>';
                return;
            }}

            tbody.innerHTML = filtered.map(item => {{
                const ema20 = Number(item.ema_20 || 0);
                const ema50 = Number(item.ema_50 || 0);
                const ema200 = Number(item.ema_200 || 0);

                let emaBadge = '';
                if (item.is_ema_stacked) {{
                    emaBadge = `<span class="badge-green px-2 py-0.5 rounded font-mono text-[11px]" title="20 EMA: ₹${{ema20.toFixed(2)}} > 50 EMA: ₹${{ema50.toFixed(2)}} > 200 EMA: ₹${{ema200.toFixed(2)}}"><i class="fa-solid fa-arrow-trend-up mr-1"></i> 20 &gt; 50 &gt; 200</span>`;
                }} else if (ema200 > ema50 && ema50 > ema20) {{
                    emaBadge = `<span class="badge-red px-2 py-0.5 rounded font-mono text-[11px]" title="Inverted: 200 EMA (₹${{ema200.toFixed(2)}}) > 50 EMA (₹${{ema50.toFixed(2)}}) > 20 EMA (₹${{ema20.toFixed(2)}})"><i class="fa-solid fa-arrow-trend-down mr-1"></i> 200 &gt; 50 &gt; 20 (Bearish)</span>`;
                }} else if (ema200 > ema50) {{
                    emaBadge = `<span class="badge-red px-2 py-0.5 rounded font-mono text-[11px]" title="200 EMA (₹${{ema200.toFixed(2)}}) > 50 EMA (₹${{ema50.toFixed(2)}})"><i class="fa-solid fa-xmark mr-1"></i> 200 &gt; 50 EMA</span>`;
                }} else {{
                    emaBadge = `<span class="badge-red px-2 py-0.5 rounded font-mono text-[11px]" title="20/50/200 EMAs not aligned"><i class="fa-solid fa-xmark mr-1"></i> Not Stacked</span>`;
                }}

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

                let triggerBadge = '';
                let actionBtn = '';

                if (item.is_setup_ready) {{
                    triggerBadge = `<span class="badge-green px-2.5 py-1 rounded-full font-bold text-[11px] animate-pulse"><i class="fa-solid fa-crosshairs mr-1"></i> BUY TRIGGER</span>`;
                    actionBtn = `
                        <div class="flex items-center justify-end gap-1.5">
                            <button onclick="openChartModal('${{item.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-[11px] transition shadow cursor-pointer">
                                <i class="fa-solid fa-chart-candlestick"></i>
                            </button>
                            <button onclick="executeOrder('${{item.symbol}}')" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-[11px] transition shadow cursor-pointer">BUY</button>
                        </div>
                    `;
                }} else if (!item.is_ema_stacked) {{
                    const reason = item.invalidation_reason || (ema200 > ema50 ? '200 EMA > 50 EMA (Not Stacked)' : 'EMAs Not Stacked');
                    triggerBadge = `<span class="badge-red px-2 py-0.5 rounded font-mono text-[10px]" title="${{reason}}"><i class="fa-solid fa-ban mr-1"></i> Not Stacked</span>`;
                    actionBtn = `
                        <div class="flex items-center justify-end gap-1.5">
                            <button onclick="openChartModal('${{item.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-[11px] transition shadow cursor-pointer">
                                <i class="fa-solid fa-chart-candlestick"></i>
                            </button>
                            <button disabled title="Setup Unqualified: ${{reason}}" class="px-2.5 py-1 bg-slate-800 text-slate-600 rounded text-[11px] cursor-not-allowed border border-slate-700/50">DISABLED</button>
                        </div>
                    `;
                }} else if (item.invalidation_reason) {{
                    triggerBadge = `<span class="badge-red px-2 py-0.5 rounded font-mono text-[10px]" title="Setup Fallen: ${{item.invalidation_reason}}"><i class="fa-solid fa-triangle-exclamation mr-1"></i> ${{item.invalidation_reason}}</span>`;
                    actionBtn = `
                        <div class="flex items-center justify-end gap-1.5">
                            <button onclick="openChartModal('${{item.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-[11px] transition shadow cursor-pointer">
                                <i class="fa-solid fa-chart-candlestick"></i>
                            </button>
                            <button disabled title="Setup Fallen / Not Qualified: ${{item.invalidation_reason}}" class="px-2.5 py-1 bg-slate-800 text-slate-600 rounded text-[11px] cursor-not-allowed border border-slate-700/50">DISABLED</button>
                        </div>
                    `;
                }} else {{
                    triggerBadge = `<span class="text-slate-500 text-[11px]">Watching</span>`;
                    actionBtn = `
                        <div class="flex items-center justify-end gap-1.5">
                            <button onclick="openChartModal('${{item.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-[11px] transition shadow cursor-pointer">
                                <i class="fa-solid fa-chart-candlestick"></i>
                            </button>
                            <button disabled class="px-2.5 py-1 bg-slate-800 text-slate-600 rounded text-[11px] cursor-not-allowed">--</button>
                        </div>
                    `;
                }}

                return `
                    <tr class="hover:bg-slate-800/50 transition">
                        <td class="p-3 font-bold text-white">
                            <div class="flex items-center gap-2">
                                <button onclick="openChartModal('${{item.symbol}}')" class="text-white hover:text-sky-400 font-bold flex items-center gap-1.5 transition text-left group cursor-pointer" title="Open 2H Chart">
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
                                is_active: true,
                                status: 'TRIGGERED'
                            }};
                        }});
                    }}
                }}

                lastFetchedSignals = signals || [];
                const activeSignals = (signals || []).filter(s => s.is_active !== false && s.status !== 'FALLEN');
                document.getElementById('signalCountBadge').innerText = activeSignals.length;
                const tbody = document.getElementById('signalsTableBody');

                if (!signals || signals.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="8" class="p-8 text-center text-slate-500"><i class="fa-solid fa-bullseye text-2xl text-slate-600 mb-2 block"></i>No qualified signals found yet. Run a universe scan to identify triggered setups.</td></tr>';
                    return;
                }}

                tbody.innerHTML = signals.map(s => {{
                    const isFallen = (s.is_active === false) || (s.status === 'FALLEN');
                    const statusBadge = isFallen
                        ? `<span class="badge-red px-2 py-0.5 rounded text-[11px] font-semibold" title="${{s.invalidation_reason || 'Setup Fallen'}}"><i class="fa-solid fa-triangle-exclamation mr-1"></i> FALLEN (${{s.invalidation_reason || 'Breached'}})</span>`
                        : `<span class="badge-green px-2 py-0.5 rounded text-[11px] font-semibold"><i class="fa-solid fa-check mr-1"></i> ${{s.status}}</span>`;

                    const actionBtn = isFallen
                        ? `
                            <div class="flex items-center justify-end gap-1.5">
                                <button onclick="openChartModal('${{s.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-xs shadow transition cursor-pointer">
                                    <i class="fa-solid fa-chart-candlestick"></i>
                                </button>
                                <button disabled title="Setup Fallen: ${{s.invalidation_reason || 'Criteria Breached'}}" class="px-2.5 py-1 bg-slate-800 text-slate-600 rounded font-bold text-xs cursor-not-allowed border border-slate-700/50">DISABLED</button>
                            </div>
                        `
                        : `
                            <div class="flex items-center justify-end gap-1.5">
                                <button onclick="openChartModal('${{s.symbol}}')" title="Open 2H TradingView Chart" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 rounded border border-slate-700 font-bold text-xs shadow transition cursor-pointer">
                                    <i class="fa-solid fa-chart-candlestick"></i>
                                </button>
                                <button onclick="executeOrder('${{s.symbol}}')" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-bold text-xs shadow transition cursor-pointer">BUY</button>
                            </div>
                        `;

                    return `
                        <tr class="hover:bg-slate-800/50">
                            <td class="p-3 font-bold text-white">
                                <button onclick="openChartModal('${{s.symbol}}')" class="text-white hover:text-sky-400 font-bold flex items-center gap-1.5 transition text-left group cursor-pointer" title="Open 2H Chart">
                                    <i class="fa-solid fa-chart-candlestick text-slate-500 group-hover:text-sky-400 text-xs"></i>
                                    <span>${{s.symbol}}</span>
                                </button>
                            </td>
                            <td class="p-3 font-mono text-emerald-400">₹${{s.trigger_price}}</td>
                            <td class="p-3 font-mono text-rose-400">₹${{s.stop_loss_price}}</td>
                            <td class="p-3 font-mono text-sky-400">₹${{s.target_profit_price}}</td>
                            <td class="p-3 font-mono text-slate-300">₹${{s.risk_per_share}}</td>
                            <td class="p-3 text-slate-300">${{s.nearest_ema_name}}</td>
                            <td class="p-3">${{statusBadge}}</td>
                            <td class="p-3 text-right">${{actionBtn}}</td>
                        </tr>
                    `;
                }}).join('');
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
                        <td class="p-3 font-bold text-white">
                            <button onclick="openChartModal('${{p.symbol}}')" class="text-white hover:text-sky-400 font-bold flex items-center gap-1.5 transition text-left group cursor-pointer" title="Open 2H Chart">
                                <i class="fa-solid fa-chart-candlestick text-slate-500 group-hover:text-sky-400 text-xs"></i>
                                <span>${{p.symbol}}</span>
                            </button>
                        </td>
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
            if (icon) icon.classList.add('animate-spin');
            showToast('Starting universe scan across Nifty 200...', 'info');
            try {{
                await fetch('/api/scan', {{ method: 'POST' }});
                isScanningActive = true;
                startScanProgressWatcher();
                fetchStatus();
            }} catch(e) {{
                if (icon) icon.classList.remove('animate-spin');
                showToast('Scan trigger failed: ' + e, 'error');
            }}
        }}

        async function clearAndRescan() {{
            const icon = document.getElementById('scanIcon');
            const rescanBtn = document.getElementById('freshRescanBtn');
            if (icon) icon.classList.add('animate-spin');
            if (rescanBtn) rescanBtn.classList.add('opacity-50', 'pointer-events-none');
            showToast('Clearing candle & scan caches and re-fetching live data...', 'info');

            try {{
                await fetch('/api/cache/clear', {{ method: 'POST' }});
                await fetch('/api/scan', {{ method: 'POST' }});
                isScanningActive = true;
                startScanProgressWatcher();
                fetchStatus();
            }} catch(e) {{
                if (icon) icon.classList.remove('animate-spin');
                if (rescanBtn) rescanBtn.classList.remove('opacity-50', 'pointer-events-none');
                showToast('Fresh Rescan failed: ' + e, 'error');
            }}
        }}

        async function toggleScanner() {{
            try {{
                const res = await fetch('/api/toggle-scanner', {{ method: 'POST' }});
                const data = await res.json();
                if (data.is_running) {{
                    showToast('Background scanner started! Running universe scan...', 'info');
                    isScanningActive = true;
                    startScanProgressWatcher();
                }} else {{
                    showToast('Background scanner paused.', 'info');
                }}
                fetchStatus();
            }} catch(e) {{
                alert('Toggle failed: ' + e);
            }}
        }}

        async function executeOrder(symbol) {{
            const sym = symbol.toUpperCase().trim();
            const modeDesc = currentMode === 'LIVE' ? '🔴 LIVE (REAL MONEY)' : '🟡 VIRTUAL (PAPER)';
            if (!confirm(`Confirm execution of ST15 order for ${{sym}} in [${{modeDesc}}] mode?`)) return;

            try {{
                const res = await fetch(`/api/execute/${{sym}}`, {{ method: 'POST' }});
                const data = await res.json();
                if (data.status === 'success') {{
                    alert(`✅ Order Dispatched [${{data.mode}}]:\n\nSymbol: ${{sym}}\nOrder ID: ${{data.order.order_id}}\nStatus: ${{data.order.status}}\nMessage: ${{data.message}}`);
                    refreshData();
                }} else if (data.reason === 'SETUP_FALLEN') {{
                    alert(`❌ Order Blocked: SETUP HAS FALLEN!\n\n${{data.message}}\n\nThe order was not placed because market conditions or indicators violated the ST15 setup.`);
                    refreshData();
                }} else {{
                    alert('Order Execution Failed: ' + (data.message || 'Unknown error'));
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
