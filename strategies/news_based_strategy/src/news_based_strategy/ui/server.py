"""Web GUI Server and FastAPI application entrypoint for NSE Catalyst Strategy."""

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Optional
import requests
import uvicorn
from fastapi import FastAPI

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
from news_based_strategy.storage.repository import StrategyStorage
from news_based_strategy.ui.auth import consume_dhan_consent, generate_dhan_consent_url
from news_based_strategy.ui.routes import COOKIE_NAME, register_routes
from news_based_strategy.ui.schemas import (
    AppLoginRequest,
    LoadHistoryRequest,
    PlaceOrderRequest,
    SaveApiKeysRequest,
    ToggleAutoOrderRequest,
    ToggleDryRunRequest,
    UpdateTokenRequest,
)
from news_based_strategy.ui.state import DashboardState
from news_based_strategy.ui.templates import get_dashboard_html, get_login_html

logger = logging.getLogger(__name__)


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

    # Register all modular endpoint routes
    register_routes(app, state)

    return app


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the FastAPI GUI server via Uvicorn."""
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


__all__ = [
    "create_app",
    "run_server",
    "DashboardState",
    "COOKIE_NAME",
    "register_routes",
    "generate_dhan_consent_url",
    "consume_dhan_consent",
    "get_login_html",
    "get_dashboard_html",
    "AppLoginRequest",
    "PlaceOrderRequest",
    "ToggleAutoOrderRequest",
    "ToggleDryRunRequest",
    "UpdateTokenRequest",
    "SaveApiKeysRequest",
    "LoadHistoryRequest",
]
