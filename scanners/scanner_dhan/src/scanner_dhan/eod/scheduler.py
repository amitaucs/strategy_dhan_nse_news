"""Background Scheduler for Automated 6:30 PM IST EOD Multi-Scanner Runs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from scanner_dhan.eod.models import EODDigestReport
from scanner_dhan.eod.runner import EODScanRunner
from scanner_dhan.eod.store import EODReportStore

logger = logging.getLogger(__name__)
IST_TZ = ZoneInfo("Asia/Kolkata")


class EODScheduler:
    """Schedules and manages automated 6:30 PM IST End-of-Day Multi-Scanner executions."""

    def __init__(
        self,
        runner: Optional[EODScanRunner] = None,
        store: Optional[EODReportStore] = None,
        target_hour: int = 18,
        target_minute: int = 30,
        universe: str = "NIFTY_500",
    ) -> None:
        self.store = store or EODReportStore()
        self.runner = runner or EODScanRunner(store=self.store)
        self.target_hour = target_hour
        self.target_minute = target_minute
        self.universe = universe

        self._is_running = False
        self._is_executing = False
        self._last_run_date: Optional[str] = None
        self._last_run_timestamp: Optional[str] = None
        self._last_error: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    def get_next_run_ist(self) -> datetime:
        """Calculate the next scheduled weekday 18:30 IST execution time."""
        now_ist = datetime.now(IST_TZ)
        target_today = now_ist.replace(
            hour=self.target_hour, minute=self.target_minute, second=0, microsecond=0
        )

        if now_ist < target_today and now_ist.weekday() < 5:
            # Later today (Mon-Fri)
            return target_today

        # Find next weekday
        candidate = target_today + timedelta(days=1)
        while candidate.weekday() >= 5:  # 5=Sat, 6=Sun
            candidate += timedelta(days=1)
        return candidate

    def get_status(self) -> Dict[str, Any]:
        """Return live scheduler health, state, and next execution time."""
        next_run = self.get_next_run_ist()
        return {
            "scheduler_active": self._is_running,
            "is_executing": self._is_executing,
            "current_scanner": getattr(self.runner, "current_scanner_name", ""),
            "completed_scanners": getattr(self.runner, "completed_scanners_count", 0),
            "total_scanners": getattr(self.runner, "total_scanners_count", 12),
            "progress_pct": getattr(self.runner, "progress_pct", 0),
            "target_time_ist": f"{self.target_hour:02d}:{self.target_minute:02d} IST",
            "universe": self.universe,
            "last_run_date": self._last_run_date,
            "last_run_timestamp": self._last_run_timestamp,
            "next_run_ist": next_run.isoformat(),
            "next_run_display": next_run.strftime("%A, %d %b %Y at %I:%M %p IST"),
            "available_dates_count": len(self.store.list_available_dates()),
            "last_error": self._last_error,
        }

    async def trigger_now(
        self,
        universe: Optional[str] = None,
        provider: Optional[Any] = None,
    ) -> EODDigestReport:
        """Manually trigger an immediate EOD scan asynchronously."""
        if self._is_executing:
            raise RuntimeError("An EOD scan is already in progress.")

        self._is_executing = True
        self._last_error = None
        univ = universe or self.universe
        loop = asyncio.get_running_loop()

        try:
            logger.info(f"Triggering immediate on-demand EOD Multi-Scanner run on universe '{univ}'...")
            report = await loop.run_in_executor(
                None,
                lambda: self.runner.run_all(universe=univ, provider=provider),
            )
            self._last_run_date = report.date
            self._last_run_timestamp = report.timestamp
            return report
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Manual EOD scan execution failed: {e}", exc_info=True)
            raise
        finally:
            self._is_executing = False

    async def start(self) -> None:
        """Start the background scheduler loop."""
        if self._is_running:
            return
        self._is_running = True
        logger.info(
            f"EOD Multi-Scanner Scheduler started. Scheduled for {self.target_hour:02d}:{self.target_minute:02d} IST (Mon-Fri)."
        )

        while self._is_running:
            try:
                now_ist = datetime.now(IST_TZ)
                is_weekday = now_ist.weekday() < 5
                is_target_time = (
                    now_ist.hour == self.target_hour and now_ist.minute == self.target_minute
                )
                today_str = now_ist.strftime("%Y-%m-%d")

                if is_weekday and is_target_time and self._last_run_date != today_str:
                    logger.info(f"⏰ Reached 18:30 IST on weekday {today_str}. Launching automated EOD scan...")
                    try:
                        await self.trigger_now()
                    except Exception as err:
                        logger.error(f"Automated EOD scheduled run failed: {err}")

                # Sleep 30 seconds before next check
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.info("EOD Scheduler loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in EOD scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(60)

        self._is_running = False

    def stop(self) -> None:
        """Stop the background scheduler."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

