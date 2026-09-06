"""ST15 Strategy Universe Scanner and Periodic Runner."""

import asyncio
from datetime import datetime
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from st15_largecap.config import settings
from st15_largecap.core.models import ScanResult, SetupSignal
from st15_largecap.engine.screener import ST15Screener
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
        on_signal_callback: Optional[Callable[[SetupSignal], None]] = None,
        repo: Optional[Repository] = None,
    ):
        self.screener = screener or ST15Screener()
        self.universe = universe or universe_manager
        self.fetcher = candle_fetcher or CandleFetcher()
        self.repository = repo or default_repo
        self.on_signal_callback = on_signal_callback or (lambda sig: self.repository.save_signal(sig))

        self._last_scan_time: Optional[datetime] = None
        self._latest_results: List[ScanResult] = []
        self._latest_signals: List[SetupSignal] = []
        self._is_running: bool = False
        self._thread: Optional[threading.Thread] = None

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

    def scan_symbol(self, symbol: str) -> ScanResult:
        """Scan a single stock symbol."""
        sec_id = self.universe.get_security_id(symbol)
        candles = self.fetcher.fetch_2h_candles(
            security_id=sec_id,
            symbol=symbol,
            days=settings.HISTORY_DAYS,
        )
        return self.screener.evaluate(symbol=symbol, sec_id=sec_id, candles=candles)

    def scan_universe(self, symbols: Optional[List[str]] = None) -> List[ScanResult]:
        """Run a full scan across the provided or default universe."""
        target_symbols = symbols or self.universe.get_universe()
        logger.info("Starting ST15 scan across %d symbols...", len(target_symbols))

        results: List[ScanResult] = []
        signals: List[SetupSignal] = []

        for symbol in target_symbols:
            try:
                res = self.scan_symbol(symbol)
                results.append(res)
                if res.is_setup_ready and res.signal:
                    signals.append(res.signal)
                    logger.info(
                        "🎯 Setup Triggered: %s | Trigger: %.2f | SL: %.2f | Target: %.2f (R:R %.1f)",
                        symbol, res.signal.trigger_price, res.signal.stop_loss_price,
                        res.signal.target_profit_price, res.signal.risk_reward_ratio,
                    )
                    if self.on_signal_callback:
                        self.on_signal_callback(res.signal)
            except Exception as e:
                logger.error("Error scanning symbol %s: %s", symbol, e)

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
