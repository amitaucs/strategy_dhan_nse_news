#!/usr/bin/env python3
"""Standalone Runner for ST-14 Bullish CE Options Trading Strategy.

Usage:
    python scripts/run_st14_live.py --mode VIRTUAL --product INTRADAY
    python scripts/run_st14_live.py --mode LIVE --product DELIVERY --bypass-timing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add strategies/st14_bullish_ce/src and scanners/scanner_dhan/src to path
repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "strategies" / "st14_bullish_ce" / "src"))
sys.path.insert(0, str(repo_root / "scanners" / "scanner_dhan" / "src"))

from dotenv import load_dotenv

load_dotenv()

from scanner_dhan.data.dhan_provider import DhanDataProvider
from st14_bullish_ce.models import ExecutionMode, ProductType, St14StrategyConfig
from st14_bullish_ce.strategy import St14BullishCeStrategy


def main() -> None:
    parser = argparse.ArgumentParser(description="ST-14 Bullish CE Options Strategy Runner")
    parser.add_argument("--mode", choices=["VIRTUAL", "LIVE"], default="VIRTUAL", help="Execution mode (default: VIRTUAL)")
    parser.add_argument("--product", choices=["INTRADAY", "DELIVERY"], default="INTRADAY", help="Product type (default: INTRADAY)")
    parser.add_argument("--capital", type=float, default=25000.0, help="Capital per trade (default: ₹25,000)")
    parser.add_argument("--tp", type=float, default=40.0, help="Target Profit % (default: 40%)")
    parser.add_argument("--sl", type=float, default=20.0, help="Stop Loss % (default: 20%)")
    parser.add_argument("--universe", default="ALL_F_AND_O", choices=["ALL_F_AND_O", "NIFTY_100", "NIFTY_50", "NIFTY_500"])
    parser.add_argument("--bypass-timing", action="store_true", help="Bypass 10:15 AM - 2:00 PM timing filter")
    parser.add_argument("--loop", action="store_true", help="Run in continuous polling loop")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 80)
    print("🚀 ST-14: BULLISH CE OPTIONS TRADING STRATEGY (DhanHQ SDK v2)")
    print("=" * 80)
    print(f"⚙️ Execution Mode:    {args.mode}")
    print(f"📦 Product Type:       {args.product} ({'3:00 PM Square-off' if args.product == 'INTRADAY' else 'Carry-Forward'})")
    print(f"💰 Capital Per Trade:  ₹{args.capital:,.2f}")
    print(f"🎯 Target Profit:      +{args.tp}% on Option Premium")
    print(f"🛑 Stop Loss:          -{args.sl}% on Option Premium")
    print(f"⏰ Session Timing:     10:15 AM Entry Start | 14:00 (2:00 PM) Cutoff | 15:00 (3:00 PM) Square-Off")
    print("=" * 80)

    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    provider = DhanDataProvider(client_id=client_id, access_token=access_token) if client_id and access_token else None

    config = St14StrategyConfig(
        mode=ExecutionMode(args.mode),
        product_type=ProductType(args.product),
        capital_per_trade=args.capital,
        target_profit_pct=args.tp,
        stop_loss_pct=args.sl,
        universe=args.universe,
    )

    strategy = St14BullishCeStrategy(config=config, provider=provider)

    try:
        while True:
            ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))
            print(f"\n⏱️ [{ist_now.strftime('%H:%M:%S IST')}] Scanning universe & evaluating triggers...")

            # Check 3 PM square off
            if strategy.is_square_off_time(ist_now):
                closed = strategy.square_off_intraday_positions(ist_now)
                if closed:
                    print(f"⏰ Auto Squared Off {len(closed)} Intraday Positions at 3:00 PM IST.")

            # Scan and evaluate signals
            signals = strategy.evaluate_market_and_scan(target_dt=ist_now, bypass_timing=args.bypass_timing)

            if not signals:
                print("ℹ️ No actionable confirmed signals at this time.")
            else:
                for sig in signals:
                    print(f"\n🎯 [SIGNAL] {sig.symbol} (Underlying: ₹{sig.underlying_ltp:,.2f} | 5H Breakout: ₹{sig.breakout_candle_high:,.2f})")
                    if sig.option_contract:
                        opt = sig.option_contract
                        print(f"   ↳ Option: {opt.symbol} (Strike: ₹{opt.strike_price}, Expiry: {opt.expiry_date} {'[NEXT MONTH]' if opt.is_next_month else '[CURRENT MONTH]'})")
                    if sig.order_levels:
                        lv = sig.order_levels
                        print(f"   ↳ Super Order: Entry ₹{lv.entry_price:.2f} | Target ₹{lv.target_price:.2f} (+{lv.target_pct}%) | SL ₹{lv.stop_loss_price:.2f} (-{lv.stop_loss_pct}%)")

                    if sig.is_confirmed:
                        success, remarks, pos = strategy.execute_order(sig)
                        print(f"   ↳ Result: {remarks}")

            telemetry = strategy.get_strategy_telemetry()
            print(f"\n📊 Active Positions: {telemetry['active_positions_count']} | Total P&L: ₹{telemetry['total_pnl']:,.2f}")

            if not args.loop:
                break

            print("\n⏳ Sleeping 60s until next cycle... (Ctrl+C to stop)")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Strategy execution stopped by user.")


if __name__ == "__main__":
    main()

