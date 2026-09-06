"""News-Based Trading Strategy Package."""

from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, FilingAudit, TradeResult, TradeSignal
from news_based_strategy.engine import StrategyEngine
from news_based_strategy.execution.executor import DhanExecutor
from news_based_strategy.execution.risk import RiskManager
from news_based_strategy.ingestion.extractor import PDFExtractor
from news_based_strategy.ingestion.filter import NoiseFilter
from news_based_strategy.ingestion.monitor import NSEFilingMonitor
from news_based_strategy.ingestion.universe import FNO_SYMBOLS, is_fno_stock
from news_based_strategy.intelligence.analyzer import FilingAnalyzer
from news_based_strategy.storage.repository import StrategyStorage

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "settings",
    # Core
    "Announcement",
    "FilingAudit",
    "TradeSignal",
    "TradeResult",
    # Ingestion
    "NSEFilingMonitor",
    "NoiseFilter",
    "PDFExtractor",
    "FNO_SYMBOLS",
    "is_fno_stock",
    # Intelligence
    "FilingAnalyzer",
    # Storage
    "StrategyStorage",
    # Execution
    "DhanExecutor",
    "RiskManager",
    # Orchestrator
    "StrategyEngine",
]
