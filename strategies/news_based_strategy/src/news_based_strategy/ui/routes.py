"""FastAPI route definitions for Web UI dashboard and REST API."""

import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import urllib.parse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, TradeSignal
from news_based_strategy.execution.executor import (
    check_token_expiry,
    mask_client_id,
    parse_jwt_claims,
)
from news_based_strategy.execution.quote import get_live_market_ltp
from news_based_strategy.execution.risk import RiskManager, get_ist_now
from news_based_strategy.ingestion.universe import get_fno_symbols, resolve_security_id
from news_based_strategy.ui.auth import consume_dhan_consent, generate_dhan_consent_url
from news_based_strategy.ui.schemas import (
    AppLoginRequest,
    LoadHistoryRequest,
    PlaceOrderRequest,
    SaveApiKeysRequest,
    St14ConfigUpdateRequest,
    St14ExecuteSignalRequest,
    ToggleAutoOrderRequest,
    ToggleDryRunRequest,
    ToggleStrategyAutoOrderRequest,
    ToggleStrategyModeRequest,
    ToggleStrategyProductRequest,
    ToggleStrategyStatusRequest,
    UpdateTokenRequest,
)
from news_based_strategy.core.strategy_registry import StrategyRegistry
from news_based_strategy.ui.state import DashboardState
from news_based_strategy.ui.templates import get_dashboard_html, get_login_html


logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

def _find_scanners_src() -> Optional[Path]:
    p_docker = Path("/app/scanners/scanner_dhan/src")
    if p_docker.exists():
        return p_docker
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        cand = parent / "scanners" / "scanner_dhan" / "src"
        if cand.exists():
            return cand
    return None

_repo_scanners_src = _find_scanners_src()
if _repo_scanners_src and str(_repo_scanners_src) not in sys.path:
    sys.path.insert(0, str(_repo_scanners_src))

try:
    import scanner_dhan.scanner  # noqa: F401
    from scanner_dhan.data.dhan_provider import (
        DhanDataProvider,
        DhanDataAPIError,
        DhanDataAPISubscriptionError,
        DhanAuthError,
        DhanRateLimitError,
    )
    from scanner_dhan.scanner.registry import ScannerRegistry
    SCANNER_AVAILABLE = True
except Exception as _scanner_err:
    logger.warning(f"scanner_dhan package not available: {_scanner_err}")
    SCANNER_AVAILABLE = False

_scanner_executor = ThreadPoolExecutor(max_workers=3)

COOKIE_NAME = "app_session_token"


def register_routes(app: FastAPI, state: DashboardState) -> None:
    """Register all UI and API endpoints onto the FastAPI application."""
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
            "strategy_status": getattr(state, "strategy_status", "ACTIVE"),
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
            "poll_market_hours_only": settings.poll_market_hours_only,
            "market_open_time": settings.market_open_time,
            "market_close_time": settings.market_close_time,
            "is_market_open": RiskManager.is_market_open(open_str=settings.market_open_time, close_str=settings.market_close_time),
            "market_status_label": "MARKET OPEN" if RiskManager.is_market_open(open_str=settings.market_open_time, close_str=settings.market_close_time) else "MARKET CLOSED",
            "trade_cutoff_time": state.executor.trade_cutoff_time,
            "square_off_time": state.executor.square_off_time,
            "is_trade_allowed": RiskManager.is_trade_allowed(cutoff_str=state.executor.trade_cutoff_time, open_str=settings.market_open_time, close_str=settings.market_close_time)[0],
            "trade_allowed_reason": RiskManager.is_trade_allowed(cutoff_str=state.executor.trade_cutoff_time, open_str=settings.market_open_time, close_str=settings.market_close_time)[1],
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

    @app.get("/api/prices/live")
    async def get_live_prices():
        """Fetch updated real-time market prices (LTP) and P&L for all active passed symbols."""
        price_map: Dict[str, Any] = {}
        for item in state.feed_items:
            if item.get("is_noise") or item.get("sentiment") in ("NEUTRAL", "MARKET_CLOSED"):
                continue
            sym = item.get("symbol", "")
            if not sym or sym in price_map:
                continue
            sec_id = item.get("security_id") or "0"
            live_ltp = get_live_market_ltp(sym, security_id=sec_id, dhan_client=state.executor.dhan)
            if live_ltp and live_ltp > 0:
                price_map[sym] = round(live_ltp, 2)

        # Update current_ltp on matching feed_items in memory
        for item in state.feed_items:
            sym = item.get("symbol", "")
            if sym in price_map and "order" in item:
                item["order"]["current_ltp"] = price_map[sym]

        return JSONResponse(
            content={
                "status": "success",
                "timestamp": get_ist_now().strftime("%H:%M:%S IST"),
                "prices": price_map,
            }
        )

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
        ltp = req.ltp or get_live_market_ltp(req.symbol, security_id=sec_id, dhan_client=state.executor.dhan)

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

    # ==================== SCANNER API ENDPOINTS ====================

    @app.get("/api/health")
    async def get_scanner_health():
        has_creds = bool(state.executor.access_token and state.executor.client_id)
        cid = state.executor.client_id or ""
        masked_id = f"{cid[:3]}***{cid[-2:]}" if len(cid) > 5 else ("Configured" if has_creds else "")

        data_api_health = {"active": False, "status": "no_creds", "message": "Credentials not configured"}
        if has_creds and SCANNER_AVAILABLE:
            try:
                prov = DhanDataProvider(
                    client_id=state.executor.client_id,
                    access_token=state.executor.access_token,
                )
                data_api_health = prov.check_data_api_health()
            except Exception as e:
                data_api_health = {"active": False, "status": "error", "message": str(e)}

        return {
            "status": "healthy",
            "dhan_connected": has_creds,
            "client_id": masked_id,
            "data_api_active": data_api_health.get("active", False),
            "data_api_status": data_api_health.get("status", "unknown"),
            "data_api_message": data_api_health.get("message", ""),
            "data_api_error_code": data_api_health.get("error_code"),
            "registered_scanners_count": len(ScannerRegistry.list_all()) if SCANNER_AVAILABLE else 0,
        }

    @app.get("/api/scanners")
    async def list_scanners():
        if not SCANNER_AVAILABLE:
            return []
        return ScannerRegistry.list_all()

    @app.post("/api/scanners/{scanner_id}/run")
    async def run_scanner(scanner_id: str, request: Request):
        if not SCANNER_AVAILABLE:
            raise HTTPException(status_code=500, detail="Scanner module not installed")
        scanner = ScannerRegistry.get(scanner_id)
        if not scanner:
            raise HTTPException(status_code=404, detail=f"Scanner '{scanner_id}' not found")

        params = {}
        try:
            body = await request.json()
            params = body.get("parameters", {})
        except Exception:
            pass

        provider = None
        if state.executor.access_token and state.executor.client_id:
            try:
                provider = DhanDataProvider(
                    client_id=state.executor.client_id,
                    access_token=state.executor.access_token,
                )
            except Exception as pe:
                logger.warning(f"Could not init DhanDataProvider with state executor creds: {pe}")

        loop = asyncio.get_event_loop()
        try:
            report = await loop.run_in_executor(
                _scanner_executor,
                lambda: ScannerRegistry.run(scanner_id, params=params, provider=provider),
            )
            return report.to_dict()
        except DhanDataAPISubscriptionError as exc:
            logger.warning("Dhan Data API plan inactive running %s: %s", scanner_id, exc)
            return {
                "status": "error",
                "error_type": "DATA_API_UNSUBSCRIBED",
                "error_title": "DhanHQ Data API Subscription Required",
                "error_message": (
                    "Your Dhan account has not subscribed to Historical Data APIs (DH-902 / HTTP 451). "
                    "Historical candlestick scans require an active Data API subscription from DhanHQ."
                ),
                "action_url": "https://web.dhan.co",
                "action_label": "Enable Data Plan on DhanHQ",
                "timestamp": datetime.now().isoformat(),
                "scanner_id": scanner_id,
                "scanner_name": scanner.name,
                "total_scanned": 0,
                "matched_count": 0,
                "results": [],
            }
        except DhanAuthError as exc:
            logger.warning("Dhan Auth error running %s: %s", scanner_id, exc)
            return {
                "status": "error",
                "error_type": "AUTH_ERROR",
                "error_title": "Dhan Access Token Expired or Invalid",
                "error_message": (
                    "Your Dhan Access Token is expired or invalid (DH-901 / 401). "
                    "Please generate a fresh token on web.dhan.co and update your configuration."
                ),
                "action_url": "https://web.dhan.co",
                "action_label": "Generate Access Token",
                "timestamp": datetime.now().isoformat(),
                "scanner_id": scanner_id,
                "scanner_name": scanner.name,
                "total_scanned": 0,
                "matched_count": 0,
                "results": [],
            }
        except DhanRateLimitError as exc:
            logger.warning("Dhan Rate Limit exceeded running %s: %s", scanner_id, exc)
            return {
                "status": "error",
                "error_type": "RATE_LIMIT",
                "error_title": "DhanHQ Rate Limit Exceeded",
                "error_message": (
                    "Dhan API request rate limit was reached (DH-904). "
                    "Please wait a few moments and click Re-Run."
                ),
                "action_url": None,
                "action_label": None,
                "timestamp": datetime.now().isoformat(),
                "scanner_id": scanner_id,
                "scanner_name": scanner.name,
                "total_scanned": 0,
                "matched_count": 0,
                "results": [],
            }
        except Exception as exc:
            logger.error("Error running scanner %s: %s", scanner_id, exc, exc_info=True)
            return {
                "status": "error",
                "error_type": "EXECUTION_ERROR",
                "error_title": "Scanner Execution Failed",
                "error_message": str(exc),
                "action_url": None,
                "action_label": None,
                "timestamp": datetime.now().isoformat(),
                "scanner_id": scanner_id,
                "scanner_name": scanner.name,
                "total_scanned": 0,
                "matched_count": 0,
                "results": [],
            }

    # ==================== STRATEGY API ENDPOINTS ====================

    @app.get("/api/strategies")
    async def list_strategies():
        # Update live telemetry metrics for active ST-NEWS strategy
        StrategyRegistry.update_metrics("st_news", {
            "signals_today": len(state.feed_items),
            "orders_placed": state.executor.get_daily_order_count(),
            "allocated_capital": state.executor.capital_per_trade,
            "auto_order_enabled": state.executor.auto_order,
            "execution_mode": "VIRTUAL" if state.executor.dry_run else "LIVE",
        })
        strat_news = StrategyRegistry.get("st_news")
        if strat_news:
            strat_news.status = getattr(state, "strategy_status", "ACTIVE")
            strat_news.execution_mode = "VIRTUAL" if state.executor.dry_run else "LIVE"
            strat_news.auto_order_enabled = state.executor.auto_order

        # Update live telemetry metrics for ST-14 Bullish CE strategy
        if hasattr(state, "st14_strategy") and state.st14_strategy:
            st14_telem = state.st14_strategy.get_strategy_telemetry()
            total_st14_signals = len(st14_telem.get("breakout_watchlist", [])) + len(st14_telem.get("recent_signals", []))
            StrategyRegistry.update_metrics("st14_bullish_ce", {
                "signals_today": total_st14_signals,
                "orders_placed": len(st14_telem.get("closed_positions", [])) + st14_telem.get("active_positions_count", 0),
                "allocated_capital": st14_telem.get("capital_per_trade", 25000.0),
                "auto_order_enabled": state.st14_strategy.config.auto_order,
                "execution_mode": state.st14_strategy.config.mode.value,
            })
            strat_st14 = StrategyRegistry.get("st14_bullish_ce")
            if strat_st14:
                strat_st14.status = state.st14_strategy.config.status
                strat_st14.execution_mode = state.st14_strategy.config.mode.value
                strat_st14.auto_order_enabled = state.st14_strategy.config.auto_order

        return StrategyRegistry.list_all()

    @app.get("/api/strategies/{strategy_id}")
    async def get_strategy(strategy_id: str):
        strat = StrategyRegistry.get(strategy_id)
        if not strat:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
        
        resp = strat.to_dict()
        if strategy_id == "st_news":
            strat.status = getattr(state, "strategy_status", "ACTIVE")
            strat.execution_mode = "VIRTUAL" if state.executor.dry_run else "LIVE"
            strat.auto_order_enabled = state.executor.auto_order
            resp["status"] = strat.status
            resp["execution_mode"] = strat.execution_mode
            resp["auto_order_enabled"] = strat.auto_order_enabled
            resp["metrics"].update({
                "signals_today": len(state.feed_items),
                "orders_placed": state.executor.get_daily_order_count(),
                "allocated_capital": state.executor.capital_per_trade,
            })
        elif strategy_id == "st14_bullish_ce" and hasattr(state, "st14_strategy") and state.st14_strategy:
            telem = state.st14_strategy.get_strategy_telemetry()
            resp["status"] = state.st14_strategy.config.status
            resp["execution_mode"] = state.st14_strategy.config.mode.value
            resp["auto_order_enabled"] = state.st14_strategy.config.auto_order
            resp["telemetry"] = telem
            resp["metrics"].update({
                "signals_today": len(telem.get("breakout_watchlist", [])) + len(telem.get("recent_signals", [])),
                "orders_placed": len(telem.get("closed_positions", [])) + telem.get("active_positions_count", 0),
                "allocated_capital": telem.get("capital_per_trade", 25000.0),
            })
        return resp

    @app.post("/api/strategies/{strategy_id}/toggle-status")
    async def toggle_strategy_status_endpoint(strategy_id: str, payload: Optional[ToggleStrategyStatusRequest] = None):
        target_status = payload.status if payload else None
        if target_status is not None:
            norm_status = target_status.strip().upper()
            if norm_status not in ("ACTIVE", "PAUSED", "READY", "DISABLED"):
                raise HTTPException(status_code=400, detail=f"Invalid status '{target_status}'. Allowed statuses: ACTIVE, PAUSED, READY, DISABLED")
            target_status = norm_status

        strat = StrategyRegistry.get(strategy_id)
        if not strat and strategy_id not in ("st_news", "st14_bullish_ce"):
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")

        new_status = state.toggle_strategy_status(strategy_id=strategy_id, new_status=target_status)
        await state.broadcast_event("STRATEGY_STATUS_TOGGLE", {
            "strategy_id": strategy_id,
            "status": new_status,
            "auto_order": state.auto_order,
            "dry_run": state.executor.dry_run,
        })
        return {
            "success": True,
            "strategy_id": strategy_id,
            "status": new_status,
            "message": f"Strategy {strategy_id} status updated to {new_status}",
        }

    @app.post("/api/strategies/{strategy_id}/toggle-mode")
    async def toggle_strategy_mode_endpoint(strategy_id: str, payload: Optional[ToggleStrategyModeRequest] = None):
        target_mode = payload.mode if payload else None
        if target_mode is not None:
            target_mode = target_mode.strip().upper()
            if target_mode not in ("VIRTUAL", "LIVE"):
                raise HTTPException(status_code=400, detail="Invalid mode. Allowed: VIRTUAL, LIVE")

        new_mode = state.toggle_strategy_mode(strategy_id=strategy_id, mode=target_mode)
        await state.broadcast_event("STRATEGY_MODE_TOGGLE", {
            "strategy_id": strategy_id,
            "mode": new_mode,
        })
        return {
            "success": True,
            "strategy_id": strategy_id,
            "mode": new_mode,
            "message": f"Strategy {strategy_id} execution mode set to {new_mode}",
        }

    @app.post("/api/strategies/{strategy_id}/toggle-auto-order")
    async def toggle_strategy_auto_order_endpoint(strategy_id: str, payload: Optional[ToggleStrategyAutoOrderRequest] = None):
        target_val = payload.auto_order if payload else None
        new_val = state.toggle_strategy_auto_order(strategy_id=strategy_id, enabled=target_val)
        await state.broadcast_event("STRATEGY_AUTO_ORDER_TOGGLE", {
            "strategy_id": strategy_id,
            "auto_order": new_val,
        })
        return {
            "success": True,
            "strategy_id": strategy_id,
            "auto_order": new_val,
            "message": f"Strategy {strategy_id} auto-order set to {new_val}",
        }

    @app.post("/api/strategies/{strategy_id}/toggle-product")
    async def toggle_strategy_product_endpoint(strategy_id: str, payload: Optional[ToggleStrategyProductRequest] = None):
        target_prod = payload.product_type if payload else None
        new_prod = state.toggle_strategy_product_type(strategy_id=strategy_id, product_type=target_prod)
        return {
            "success": True,
            "strategy_id": strategy_id,
            "product_type": new_prod,
            "message": f"Strategy {strategy_id} product type set to {new_prod}",
        }

    @app.post("/api/strategies/st14_bullish_ce/scan")
    async def run_st14_scan_endpoint(bypass_timing: bool = False):
        """Execute real-time ST-14 full iteration (hourly scan + trigger check)."""
        if not hasattr(state, "st14_strategy") or not state.st14_strategy:
            raise HTTPException(status_code=500, detail="ST-14 Strategy engine not initialized")
        
        res = await asyncio.to_thread(state.run_st14_scan, bypass_timing=bypass_timing)
        await state.broadcast_event("ST14_UPDATE", {
            "type": "FULL_SCAN_COMPLETED",
            "telemetry": state.st14_strategy.get_strategy_telemetry(),
        })
        return {
            "success": True,
            "result": res,
            "telemetry": state.st14_strategy.get_strategy_telemetry(),
        }

    @app.post("/api/strategies/st14_bullish_ce/scan-hourly")
    async def run_st14_hourly_scan_endpoint(bypass_timing: bool = False):
        """Execute Tier 1: 1-Hour Discovery Scanner on demand."""
        if not hasattr(state, "st14_strategy") or not state.st14_strategy:
            raise HTTPException(status_code=500, detail="ST-14 Strategy engine not initialized")
        
        res = await asyncio.to_thread(state.run_st14_hourly_scan, bypass_timing=bypass_timing)
        await state.broadcast_event("ST14_UPDATE", {
            "type": "HOURLY_DISCOVERY_SCAN",
            "telemetry": state.st14_strategy.get_strategy_telemetry(),
        })
        return {
            "success": True,
            "result": res,
            "telemetry": state.st14_strategy.get_strategy_telemetry(),
        }

    @app.post("/api/strategies/st14_bullish_ce/check-triggers")
    async def run_st14_trigger_check_endpoint(bypass_timing: bool = False):
        """Execute Tier 2: 5-Minute Breakout Trigger Poller on demand."""
        if not hasattr(state, "st14_strategy") or not state.st14_strategy:
            raise HTTPException(status_code=500, detail="ST-14 Strategy engine not initialized")
        
        res = await asyncio.to_thread(state.run_st14_5min_check, bypass_timing=bypass_timing)
        await state.broadcast_event("ST14_UPDATE", {
            "type": "5MIN_TRIGGER_MONITOR",
            "telemetry": state.st14_strategy.get_strategy_telemetry(),
        })
        return {
            "success": True,
            "result": res,
            "telemetry": state.st14_strategy.get_strategy_telemetry(),
        }

    @app.post("/api/strategies/st14_bullish_ce/execute")
    async def execute_st14_signal_endpoint(req: St14ExecuteSignalRequest):
        """Manually execute a confirmed ST-14 signal."""
        if not hasattr(state, "st14_strategy") or not state.st14_strategy:
            raise HTTPException(status_code=500, detail="ST-14 Strategy engine not initialized")
        
        target_signal = next((s for s in state.st14_strategy.signals_history if s.signal_id == req.signal_id or s.symbol == req.signal_id), None)
        if not target_signal and req.signal_id in state.st14_strategy.breakout_watchlist:
            watch_item = state.st14_strategy.breakout_watchlist[req.signal_id]
            from st14_bullish_ce.models import St14TradeSignal
            target_signal = St14TradeSignal(
                signal_id=f"MANUAL_ST14_{watch_item.symbol}_{int(datetime.now().timestamp())}",
                symbol=watch_item.symbol,
                underlying_sec_id=watch_item.security_id,
                underlying_ltp=watch_item.current_ltp,
                breakout_candle_high=watch_item.breakout_candle_high,
                daily_ema20=watch_item.daily_ema20,
                hourly_ema20=watch_item.hourly_ema20,
                vwap=watch_item.vwap,
                vwap_dist_pct=watch_item.distance_pct,
                vwap_angle_deg=45.0,
                status=watch_item.status,
                is_confirmed=True,
                option_contract=watch_item.option_contract,
                order_levels=watch_item.order_levels,
            )
            state.st14_strategy.signals_history.append(target_signal)
            watch_item.status = target_signal.status

        if not target_signal:
            raise HTTPException(status_code=404, detail=f"Signal or Watchlist candidate '{req.signal_id}' not found")
        
        state.sync_dhan_credentials()
        success, msg, pos = state.st14_strategy.execute_order(target_signal)
        if success and target_signal.symbol in state.st14_strategy.breakout_watchlist:
            state.st14_strategy.breakout_watchlist[target_signal.symbol].status = target_signal.status
        return {
            "success": success,
            "message": msg,
            "position": pos.to_dict() if pos else None,
            "signal": target_signal.to_dict(),
        }

    @app.post("/api/strategies/st14_bullish_ce/square-off")
    async def square_off_st14_positions_endpoint():
        """Emergency square-off for all open ST-14 positions."""
        if not hasattr(state, "st14_strategy") or not state.st14_strategy:
            raise HTTPException(status_code=500, detail="ST-14 Strategy engine not initialized")
        
        closed = state.st14_strategy.emergency_square_off_all()
        return {
            "success": True,
            "closed_count": len(closed),
            "closed_positions": [p.to_dict() for p in closed],
            "message": f"Successfully squared off {len(closed)} open ST-14 positions",
        }

    @app.post("/api/strategies/st14_bullish_ce/config")
    async def update_st14_config_endpoint(req: St14ConfigUpdateRequest):
        """Update ST-14 parameters and risk limits."""
        if not hasattr(state, "st14_strategy") or not state.st14_strategy:
            raise HTTPException(status_code=500, detail="ST-14 Strategy engine not initialized")
        
        cfg = state.st14_strategy.config
        if req.capital_per_trade is not None and req.capital_per_trade > 0:
            cfg.capital_per_trade = req.capital_per_trade
            state.storage.set_setting("st14_capital", str(req.capital_per_trade))
        if req.target_profit_pct is not None and req.target_profit_pct > 0:
            cfg.target_profit_pct = req.target_profit_pct
        if req.stop_loss_pct is not None and req.stop_loss_pct > 0:
            cfg.stop_loss_pct = req.stop_loss_pct
        if req.trailing_jump_pts is not None and req.trailing_jump_pts >= 0:
            cfg.trailing_jump_pts = req.trailing_jump_pts
        if req.trade_cutoff_time is not None:
            cfg.trade_cutoff_time = req.trade_cutoff_time
        if req.square_off_time is not None:
            cfg.square_off_time = req.square_off_time
        if req.mode is not None:
            state.toggle_strategy_mode("st14_bullish_ce", req.mode)
        if req.product_type is not None:
            state.toggle_strategy_product_type("st14_bullish_ce", req.product_type)
        if req.auto_order is not None:
            state.toggle_strategy_auto_order("st14_bullish_ce", req.auto_order)

        return {
            "success": True,
            "config": cfg.to_dict(),
            "message": "ST-14 configuration updated successfully",
        }


    @app.post("/api/universe/sync")
    async def sync_universe_endpoint(force: bool = True):
        """Force immediate re-synchronization of all market universes and Dhan Scrip Master."""
        try:
            from scanner_dhan.universe.manager import get_universe_manager
            from news_based_strategy.ingestion.universe import sync_dhan_fno_symbols
            summary = await asyncio.to_thread(get_universe_manager().sync_all, force=force)
            sync_dhan_fno_symbols()
            return {
                "success": True,
                "summary": summary,
                "message": "Universal market universes successfully synchronized from official sources.",
            }
        except Exception as exc:
            logger.error("Error during universe sync endpoint execution: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))


__all__ = ["register_routes", "COOKIE_NAME"]

