"""End-of-Day Multi-Scanner Daily Digest Package.

Provides automated 6:30 PM IST batch execution, multi-strategy confluence
detection, historical daily snapshot archiving, and TradingView watchlist generation.
"""

from scanner_dhan.eod.models import (
    EODConfluenceStock,
    EODDigestReport,
    EODMatchedStrategy,
    EODStrategySummary,
)
from scanner_dhan.eod.runner import EODScanRunner
from scanner_dhan.eod.scheduler import EODScheduler
from scanner_dhan.eod.store import EODReportStore

__all__ = [
    "EODConfluenceStock",
    "EODDigestReport",
    "EODMatchedStrategy",
    "EODStrategySummary",
    "EODScanRunner",
    "EODScheduler",
    "EODReportStore",
]

