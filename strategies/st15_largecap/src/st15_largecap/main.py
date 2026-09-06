"""ST15 Large-Cap Positional Momentum Strategy CLI & Application Entry Point."""

import argparse
import logging
import sys

from st15_largecap.config import settings
from st15_largecap.engine.runner import StrategyRunner
from st15_largecap.ingestion.universe import universe_manager
from st15_largecap.ui.server import start_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("st15_largecap")


def main():
    parser = argparse.ArgumentParser(
        description="ST15 Large-Cap 2H Heikin Ashi Momentum Strategy (DhanHQ)"
    )
    parser.add_argument(
        "--server", "--gui", action="store_true", help="Launch the Web UI Dashboard on Port 8015"
    )
    parser.add_argument(
        "--port", type=int, default=settings.PORT, help=f"Web server port (default: {settings.PORT})"
    )
    parser.add_argument(
        "--scan", action="store_true", help="Perform immediate universe scan in console"
    )
    parser.add_argument(
        "--sync-scrip", action="store_true", help="Sync latest scrip master from DhanHQ"
    )

    args = parser.parse_args()

    if args.sync_scrip:
        logger.info("Syncing scrip master security IDs from DhanHQ...")
        count = universe_manager.sync_from_dhan()
        logger.info("Scrip sync complete. Updated %d security IDs.", count)
        if not args.scan and not args.server:
            sys.exit(0)

    if args.scan:
        logger.info("Running ST15 Console Scan across Nifty 200 universe...")
        runner = StrategyRunner()
        results = runner.scan_universe()
        
        print("\n" + "=" * 80)
        print(f"{'SYMBOL':<12} | {'LTP':<8} | {'EMA STACK':<12} | {'DIP PROX':<14} | {'HA':<8} | {'ST':<8} | {'SETUP':<10}")
        print("=" * 80)
        for r in results[:30]:  # Top 30
            stack_str = "20>50>200" if r.is_ema_stacked else "NO"
            dip_str = f"{r.nearest_ema} ({r.nearest_ema_dist_pct}%)"
            ha_str = "GREEN" if r.is_ha_green else "RED"
            st_str = "GREEN" if r.is_supertrend_green else "RED"
            setup_str = "✅ BUY" if r.is_setup_ready else "WATCH"
            print(f"{r.symbol:<12} | {r.ltp:<8.2f} | {stack_str:<12} | {dip_str:<14} | {ha_str:<8} | {st_str:<8} | {setup_str:<10}")
        print("=" * 80 + "\n")

    if args.server or len(sys.argv) == 1:
        # Default behavior: Launch Web Dashboard
        start_server(host=settings.HOST, port=args.port)


if __name__ == "__main__":
    main()
