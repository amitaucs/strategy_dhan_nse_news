#!/usr/bin/env python3
"""Run the DhanHQ Trading Scanners Dashboard Web Application.

Usage:
    python run_dashboard.py
    python run_dashboard.py --port 8080 --no-browser
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Add src to Python path
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root / "src"))

import uvicorn
from scanner_dhan.ui.app import create_app


def open_browser(url: str, delay: float = 1.0) -> None:
    """Open web browser after a short delay for server startup."""
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the DhanHQ Multi-Scanner Web Dashboard."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host interface to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Disable automatic opening of browser on launch",
    )

    args = parser.parse_args()
    url = f"http://{args.host}:{args.port}"

    print(f"\n" + "=" * 70)
    print(f"  🚀 Launching DhanHQ Multi-Scanner Dashboard")
    print(f"  🌐 URL: {url}")
    print(f"  📊 Press Ctrl+C to stop the dashboard server")
    print(f"=" * 70 + "\n")

    if not args.no_browser:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
