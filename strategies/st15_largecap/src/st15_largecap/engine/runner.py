"""ST15 Strategy Universe Scanner and Periodic Runner."""

import asyncio
import concurrent.futures
from datetime import datetime
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from st15_largecap.config import settings
from st15_largecap.core.models import ScanResult, SetupSignal, SignalStatus, TradeOrder
from st15_largecap.engine.screener import ST15Screener
from st15_largecap.execution.executor import OrderExecutor
from st15_largecap.ingestion.candles import CandleFetcher
from st15_largecap.ingestion.universe import UniverseManager, universe_manager
from st15_largecap.storage.repository import repository as default_repo, Repository

logger = logging.getLogger(__name__)


class StrategyRunner:
    """Orchestrates universe scanning, signal generation, and execution."""

    def __init__(
        self,
        screener: Optional[ST15Screener] = None,
        universe: Optional[UniverseManager] = None,
        candle_fetcher: Optional[CandleFetcher] = None,
        executor: Optional[OrderExecutor] = None,
        on_signal_callback: Optional[Callable[[SetupSignal], None]] = None,
        repo: Optional[Repository] = None,
        auto_order: bool = settings.AUTO_ORDER,
    ):
        self.screener = screener or ST15Screener()
        self.universe = universe or universe_manager
        self.fetcher = candle_fetcher or CandleFetcher()
        self.executor = executor or OrderExecutor(dry_run=settings.DRY_RUN)
        self.repository = repo or default_repo
        self.on_signal_callback = on_signal_callback or (lambda sig: self.repository.save_signal(sig))
        self.auto_order = auto_order

        self._last_scan_time: Optional[datetime] = None
        self._latest_results: List[ScanResult] = []
        self._latest_signals: List[SetupSignal] = []
        self._is_running: bool = False
        self._thread: Optional[threading.Thread] = None

        self._is_scanning: bool = False
        self._scan_progress: int = 0
        self._scan_total: int = 0

    @property
    def latest_results(self) -> List[ScanResult]:
        return list(self._latest_results)

    @property
    def latest_signals(self) -> List[SetupSignal]:
        return list(self._latest_signals)

    @property
    def last_scan_time(self) -> Optional[datetime]:
        return self._last_scan_time

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_scanning(self) -> bool:
        return self._is_scanning

    @property
    def scan_progress(self) -> int:
        return self._scan_progress

    @property
    def scan_total(self) -> int:
        return self._scan_total

    def set_auto_order(self, enabled: bool) -> None:
        """Enable or disable autonomous order placement upon setup trigger."""
        self.auto_order = enabled
        logger.info("Auto-Order Placement set to: %s", "ENABLED (Bot Executes)" if self.auto_order else "DISABLED (Manual Execution)")

    def set_execution_mode(self, dry_run: bool) -> None:
        """Switch between VIRTUAL (Paper Trading) and LIVE (Real Money) execution."""
        if self.executor:
            self.executor.set_mode(dry_run)

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """Clear candle cache and reset in-memory scan results if requested."""
        if self.fetcher:
            self.fetcher.clear_cache(symbol)
        if not symbol:
            self._latest_results = []
            self._latest_signals = []
            logger.info("Runner caches and in-memory results cleared.")

    def scan_symbol(self, symbol: str, force_refresh: bool = False) -> ScanResult:
        """Scan a single stock symbol."""
        sec_id = self.universe.get_security_id(symbol)
        candles = self.fetcher.fetch_2h_candles(
            security_id=sec_id,
            symbol=symbol,
            days=settings.HISTORY_DAYS,
            force_refresh=force_refresh,
        )
        return self.screener.evaluate(symbol=symbol, sec_id=sec_id, candles=candles)

    def scan_universe(self, symbols: Optional[List[str]] = None, force_refresh: bool = False) -> List[ScanResult]:
        """Run a fast parallel scan across the provided or default universe."""
        target_symbols = symbols or self.universe.get_universe()
        if force_refresh:
            self.clear_cache()
        logger.info("Starting ST15 scan across %d symbols (Auto-Order: %s, Mode: %s, Force: %s)...",
                    len(target_symbols), "ON" if self.auto_order else "OFF",
                    "VIRTUAL" if (self.executor and self.executor.dry_run) else "LIVE",
                    force_refresh)

        self._is_scanning = True
        self._scan_progress = 0
        self._scan_total = len(target_symbols)
        lock = threading.Lock()

        def _worker(sym: str) -> Optional[ScanResult]:
            try:
                return self.scan_symbol(sym, force_refresh=force_refresh)
            except Exception as e:
                logger.error("Error scanning symbol %s: %s", sym, e)
                return None
            finally:
                with lock:
                    self._scan_progress += 1

        results: List[ScanResult] = []
        signals: List[SetupSignal] = []

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="ST15Scanner") as pool:
                futures = [pool.submit(_worker, sym) for sym in target_symbols]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res:
                        results.append(res)
                        if res.is_setup_ready and res.signal:
                            signals.append(res.signal)
                            logger.info(
                                "🎯 Setup Triggered: %s | Trigger: %.2f | SL: %.2f | Target: %.2f (R:R %.1f)",
                                res.symbol, res.signal.trigger_price, res.signal.stop_loss_price,
                                res.signal.target_profit_price, res.signal.risk_reward_ratio,
                            )
                            if self.on_signal_callback:
                                self.on_signal_callback(res.signal)

                            # Auto Order Execution if enabled
                            if self.auto_order and self.executor:
                                today_orders = self.repository.get_today_orders() if self.repository else []
                                active_today = [
                                    o for o in today_orders
                                    if o.get("status") in ("PLACED", "SIMULATED", "FILLED", "OPEN")
                                ]
                                if len(active_today) >= settings.MAX_POSITIONS_PER_DAY:
                                    logger.warning(
                                        "⚠️ Daily position limit reached (%d/%d). Auto-order skipped for %s.",
                                        len(active_today), settings.MAX_POSITIONS_PER_DAY, res.symbol
                                    )
                                    continue

                                already_placed = any(
                                    o.get("symbol") == res.symbol and o.get("status") in ("PLACED", "SIMULATED", "FILLED", "OPEN")
                                    for o in today_orders
                                )
                                if not already_placed:
                                    mode_str = "VIRTUAL" if self.executor.dry_run else "LIVE"
                                    logger.info("🤖 [AUTO BOT] Auto-dispatching %s order for %s (Position %d/%d)...",
                                                mode_str, res.symbol, len(active_today) + 1, settings.MAX_POSITIONS_PER_DAY)
                                    order = self.executor.execute_signal(res.signal)
                                    if self.repository:
                                        self.repository.save_order(order)
        finally:
            self._is_scanning = False

        # Sort results: Setups ready first, then nearest to EMA
        results.sort(key=lambda r: (not r.is_setup_ready, r.nearest_ema_dist_pct))

        self._latest_results = results
        self._latest_signals = signals
        self._last_scan_time = datetime.now()

        if self.repository:
            try:
                self.repository.save_scan_results(results)
            except Exception as e:
                logger.error("Error saving scan results to repository: %s", e)

        logger.info(
            "ST15 Scan complete. Total: %d, Qualified Setups: %d",
            len(results), len(signals)
        )
        return results

    def validate_and_execute(self, symbol: str) -> tuple[bool, Optional[TradeOrder], str]:
        """Verify that the setup for symbol is still currently qualified and active before executing order.
        
        If user delayed and the setup has fallen (e.g., price dropped below SL, HA turned Red, SuperTrend flipped,
        or EMAs unstacked), this method rejects execution and returns a descriptive reason.
        Also enforces the daily maximum position limit (3 per day).
        """
        sym = symbol.upper().strip()
        sec_id = self.universe.get_security_id(sym)
        candles = self.fetcher.fetch_2h_candles(security_id=sec_id, symbol=sym, days=settings.HISTORY_DAYS)

        if not candles or len(candles) < 20:
            return False, None, "Insufficient candle data to validate setup"

        # 1. Check if an existing signal exists for this symbol and validate live conditions
        matching_signal = next((s for s in self._latest_signals if s.symbol == sym), None)
        if not matching_signal and self.repository:
            db_signals = self.repository.get_signals(limit=20)
            matching_signal = next((
                SetupSignal(
                    symbol=s["symbol"],
                    sec_id=s["sec_id"],
                    setup_time=datetime.fromisoformat(s["setup_time"]) if isinstance(s["setup_time"], str) else s["setup_time"],
                    trigger_price=s["trigger_price"],
                    stop_loss_price=s["stop_loss_price"],
                    target_profit_price=s["target_profit_price"],
                    risk_per_share=s["risk_per_share"],
                    risk_reward_ratio=s["risk_reward_ratio"],
                    ema_20=s["ema_20"],
                    ema_50=s["ema_50"],
                    ema_200=s["ema_200"],
                    supertrend=s.get("supertrend", 0.0),
                    nearest_ema_name=s.get("nearest_ema_name", ""),
                    nearest_ema_dist_pct=s.get("nearest_ema_dist_pct", 0.0),
                    status=SignalStatus(s.get("status", "TRIGGERED")),
                )
                for s in db_signals if s.get("symbol") == sym
            ), None)

        if matching_signal:
            is_valid, msg = self.screener.validate_setup_signal(matching_signal, candles)
            if not is_valid:
                logger.warning("Order execution rejected for %s: Setup has fallen (%s)", sym, msg)
                return False, None, f"Setup has fallen: {msg}"
            signal = matching_signal
        else:
            scan_res = self.screener.evaluate(symbol=sym, sec_id=sec_id, candles=candles)
            if not scan_res.is_setup_ready:
                reason = scan_res.invalidation_reason or "Setup conditions are no longer met."
                logger.warning("Order execution rejected for %s: Setup has fallen (%s)", sym, reason)
                return False, None, f"Setup has fallen: {reason}"
            signal = scan_res.signal

        # 2. Check daily position limit and duplicate order prevention
        if self.repository:
            today_orders = self.repository.get_today_orders()
            active_today = [
                o for o in today_orders
                if o.get("status") in ("PLACED", "SIMULATED", "FILLED", "OPEN")
            ]
            if len(active_today) >= settings.MAX_POSITIONS_PER_DAY:
                msg = f"Daily position limit reached: Maximum {settings.MAX_POSITIONS_PER_DAY} positions per day reached ({len(active_today)}/{settings.MAX_POSITIONS_PER_DAY} filled/placed today)"
                logger.warning("Order execution rejected for %s: %s", sym, msg)
                return False, None, msg

            already_placed = any(
                o.get("symbol") == sym and o.get("status") in ("PLACED", "SIMULATED", "FILLED", "OPEN")
                for o in today_orders
            )
            if already_placed:
                msg = f"Order already placed for {sym} today"
                logger.warning("Order execution rejected for %s: %s", sym, msg)
                return False, None, msg

        if not signal:
            trigger_price = round(candles[-1].close * 1.002, 2)
            stop_loss = round(candles[-1].close * 0.98, 2)
            risk = round(trigger_price - stop_loss, 2)
            target = round(trigger_price + (risk * self.screener.risk_reward_ratio), 2)
            signal = SetupSignal(
                symbol=sym,
                sec_id=sec_id,
                setup_time=datetime.now(),
                trigger_price=trigger_price,
                stop_loss_price=stop_loss,
                target_profit_price=target,
                risk_per_share=risk,
                risk_reward_ratio=self.screener.risk_reward_ratio,
                ema_20=0.0,
                ema_50=0.0,
                ema_200=0.0,
                supertrend=0.0,
                status=SignalStatus.TRIGGERED,
            )

        if not self.executor:
            return False, None, "No executor configured"

        order = self.executor.execute_signal(signal)
        if self.repository:
            self.repository.save_order(order)
        return True, order, f"Order executed successfully in {'VIRTUAL' if self.executor.dry_run else 'LIVE'} mode"

    def re_evaluate_with_tolerance(self, new_tolerance_pct: float) -> List[ScanResult]:
        """Re-evaluate the existing universe results in-memory instantly with a new dip tolerance."""
        self.screener.ema_proximity_pct = new_tolerance_pct
        if not self._latest_results:
            return []

        updated_results: List[ScanResult] = []
        updated_signals: List[SetupSignal] = []

        for r in self._latest_results:
            is_in_dip = r.nearest_ema_dist_pct <= new_tolerance_pct
            was_trigger_qualified = r.is_setup_ready or (r.invalidation_reason and r.invalidation_reason.startswith("Dip:"))
            is_setup_ready = bool(
                r.is_ema_stacked
                and is_in_dip
                and r.is_ha_green
                and r.is_supertrend_green
                and was_trigger_qualified
            )

            invalidation_reason = ""
            if not r.is_ema_stacked:
                invalidation_reason = "EMA: 20/50/200 EMAs Not Stacked"
            elif not is_in_dip:
                invalidation_reason = f"Dip: Distance ({r.nearest_ema_dist_pct:+.2f}%) exceeds tolerance"
            elif not r.is_ha_green:
                invalidation_reason = "HA: Candle is Red (In Pullback)"
            elif not r.is_supertrend_green:
                invalidation_reason = "SuperTrend: Bearish (Red - waiting for flip)"
            elif not was_trigger_qualified:
                invalidation_reason = r.invalidation_reason or "Trigger: Move in-progress"

            signal = r.signal
            if is_setup_ready and not signal:
                trigger_price = round(r.ltp * 1.002, 2)
                stop_loss = round(r.swing_low or (r.ltp * 0.98), 2)
                risk = round(trigger_price - stop_loss, 2)
                target = round(trigger_price + (risk * self.screener.risk_reward_ratio), 2)
                signal = SetupSignal(
                    symbol=r.symbol,
                    sec_id=r.sec_id,
                    setup_time=datetime.now(),
                    trigger_price=trigger_price,
                    stop_loss_price=stop_loss,
                    target_profit_price=target,
                    risk_per_share=risk,
                    risk_reward_ratio=self.screener.risk_reward_ratio,
                    ema_20=r.ema_20,
                    ema_50=r.ema_50,
                    ema_200=r.ema_200,
                    supertrend=0.0,
                    nearest_ema_name=r.nearest_ema,
                    nearest_ema_dist_pct=r.nearest_ema_dist_pct,
                    status=SignalStatus.TRIGGERED,
                )

            new_res = ScanResult(
                symbol=r.symbol,
                sec_id=r.sec_id,
                ltp=r.ltp,
                ema_20=r.ema_20,
                ema_50=r.ema_50,
                ema_200=r.ema_200,
                is_ema_stacked=r.is_ema_stacked,
                is_in_dip=is_in_dip,
                nearest_ema=r.nearest_ema,
                nearest_ema_dist_pct=r.nearest_ema_dist_pct,
                is_ha_green=r.is_ha_green,
                is_supertrend_green=r.is_supertrend_green,
                is_setup_ready=is_setup_ready,
                swing_low=r.swing_low,
                signal=signal if is_setup_ready else None,
                candles_count=r.candles_count,
                invalidation_reason=invalidation_reason,
                scanned_at=datetime.now(),
            )
            updated_results.append(new_res)
            if is_setup_ready and signal:
                updated_signals.append(signal)

        updated_results.sort(key=lambda r: (not r.is_setup_ready, r.nearest_ema_dist_pct))
        self._latest_results = updated_results
        self._latest_signals = updated_signals

        if self.repository:
            try:
                self.repository.save_scan_results(updated_results)
            except Exception as e:
                logger.error("Error saving updated scan results: %s", e)

        logger.info(
            "Re-evaluated %d symbols with tolerance %.2f%%: %d Qualified Setups",
            len(updated_results), new_tolerance_pct, len(updated_signals)
        )
        return updated_results

    def _loop(self, interval_seconds: int):
        logger.info("Background scanner loop started (Interval: %ds)", interval_seconds)
        while self._is_running:
            try:
                self.scan_universe()
            except Exception as e:
                logger.error("Error in background scan loop: %s", e)
            
            # Sleep in small increments to allow responsive stopping
            for _ in range(interval_seconds):
                if not self._is_running:
                    break
                time.sleep(1)

    def start_background_loop(self, interval_seconds: int = 300) -> None:
        """Start periodic background scanning in a dedicated thread."""
        if self._is_running:
            logger.warning("Background scanner is already running.")
            return

        self._is_running = True
        self._thread = threading.Thread(
            target=self._loop,
            args=(interval_seconds,),
            daemon=True,
            name="ST15ScannerThread",
        )
        self._thread.start()

    def stop_background_loop(self) -> None:
        """Stop background scanning thread."""
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Background scanner loop stopped.")
