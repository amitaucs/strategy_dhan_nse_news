"""CLI and Entry Point for ST15_LargeCap Positional Momentum Strategy."""

import argparse
import sys
from st15_largecap.config import settings


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="ST15_LargeCap Positional Momentum Strategy")
    parser.add_argument("--gui", action="store_true", help="Launch Web GUI Terminal")
    parser.add_argument("--port", type=int, default=settings.ui_port, help="Port for Web GUI (default: 8015)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    args = parser.parse_args()

    print("======================================================================")
    print("🚀 ST15_LargeCap Positional Momentum Strategy")
    print(f"   Environment: {settings.app_env}")
    print(f"   Universe: {settings.universe_type}")
    print(f"   Max Positions: {settings.max_positions}")
    print(f"   Dry Run: {settings.dry_run}")
    print("======================================================================")


if __name__ == "__main__":
    main()

