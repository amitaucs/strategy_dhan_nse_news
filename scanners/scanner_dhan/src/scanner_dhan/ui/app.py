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

# Import all registered scanners so they register on startup
import scanner_dhan.scanner  # noqa: F401
from scanner_dhan.data.dhan_provider import load_dhan_credentials
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
        try:
            cid, token = load_dhan_credentials()
            if cid and token:
                has_creds = True
                client_id_masked = f"{cid[:3]}***{cid[-2:]}" if len(cid) > 5 else "Configured"
        except Exception:
            has_creds = False

        return {
            "status": "healthy",
            "dhan_connected": has_creds,
            "client_id": client_id_masked,
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
        except Exception as exc:
            logger.error("Error executing scanner %s: %s", scanner_id, exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Mount static assets
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def serve_spa() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

    return app
