"""FastAPI Backend Application for Trading Scanners Dashboard."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from datetime import datetime

# Import all registered scanners so they register on startup
import scanner_dhan.scanner  # noqa: F401
from scanner_dhan.data.dhan_provider import (
    DhanDataProvider,
    DhanDataAPIError,
    DhanDataAPISubscriptionError,
    DhanAuthError,
    DhanRateLimitError,
    load_dhan_credentials,
)
from scanner_dhan.scanner.registry import ScannerRegistry

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
executor = ThreadPoolExecutor(max_workers=3)


class RunScannerRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


def create_app() -> FastAPI:
    """Create and configure FastAPI dashboard application."""
    app = FastAPI(
        title="DhanHQ Trading Scanners Dashboard",
        version="1.0.0",
        description="Interactive Multi-Scanner Dashboard for Indian Markets using DhanHQ API.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def get_health() -> dict[str, Any]:
        """Check system and Dhan credentials status."""
        has_creds = False
        client_id_masked = ""
        data_api_health = {"active": False, "status": "no_creds", "message": "Credentials not configured"}
        try:
            cid, token = load_dhan_credentials()
            if cid and token:
                has_creds = True
                client_id_masked = f"{cid[:3]}***{cid[-2:]}" if len(cid) > 5 else "Configured"
                prov = DhanDataProvider(client_id=cid, access_token=token)
                data_api_health = prov.check_data_api_health()
        except Exception:
            has_creds = False

        return {
            "status": "healthy",
            "dhan_connected": has_creds,
            "client_id": client_id_masked,
            "data_api_active": data_api_health.get("active", False),
            "data_api_status": data_api_health.get("status", "unknown"),
            "data_api_message": data_api_health.get("message", ""),
            "data_api_error_code": data_api_health.get("error_code"),
            "registered_scanners_count": len(ScannerRegistry.list_all()),
        }

    @app.get("/api/scanners")
    async def list_scanners() -> list[dict[str, Any]]:
        """Return all available registered scanners."""
        return ScannerRegistry.list_all()

    @app.post("/api/scanners/{scanner_id}/run")
    async def run_scanner(
        scanner_id: str, request: RunScannerRequest | None = None
    ) -> dict[str, Any]:
        """Execute a scanner asynchronously in a background thread."""
        scanner = ScannerRegistry.get(scanner_id)
        if not scanner:
            raise HTTPException(status_code=404, detail=f"Scanner '{scanner_id}' not found")

        params = request.parameters if request else {}

        loop = asyncio.get_event_loop()
        try:
            # Run in worker thread so we do not block event loop
            report = await loop.run_in_executor(
                executor,
                lambda: ScannerRegistry.run(scanner_id, params=params),
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
            logger.error("Error executing scanner %s: %s", scanner_id, exc, exc_info=True)
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

    # Mount static assets
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def serve_spa() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

    return app
