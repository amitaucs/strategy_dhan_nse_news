"""Strategy orchestrator connecting ingestion, storage, intelligence, and execution."""

from datetime import datetime
import logging
import time
from typing import Optional
from news_based_strategy.config import settings
from news_based_strategy.core.models import Announcement, TradeSignal
from news_based_strategy.execution.executor import DhanExecutor
from news_based_strategy.execution.risk import RiskManager
from news_based_strategy.ingestion.monitor import NSEFilingMonitor
from news_based_strategy.ingestion.universe import resolve_security_id
from news_based_strategy.intelligence.analyzer import FilingAnalyzer
from news_based_strategy.storage.repository import StrategyStorage

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Coordinates the end-to-end event-driven trading workflow."""

    def __init__(
        self,
        monitor: Optional[NSEFilingMonitor] = None,
        storage: Optional[StrategyStorage] = None,
        analyzer: Optional[FilingAnalyzer] = None,
        executor: Optional[DhanExecutor] = None,
        dry_run: bool = True,
        fno_only: bool = True,
        filter_noise: bool = True,
        extract_pdf: bool = True,
    ):
        self.monitor = monitor or NSEFilingMonitor(
            base_url=settings.nse_base_url,
            api_url=settings.nse_api_url,
            headers=settings.headers,
        )
        self.storage = storage or StrategyStorage(settings.database_path)
        self.analyzer = analyzer or FilingAnalyzer(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model,
        )
        self.executor = executor or DhanExecutor(
            client_id=settings.dhan_client_id,
            access_token=settings.dhan_access_token,
            dry_run=dry_run,
            capital_per_trade=settings.capital_per_trade,
            max_shares_per_trade=settings.max_shares_per_trade,
        )
        self.fno_only = fno_only
        self.filter_noise = filter_noise
        self.extract_pdf = extract_pdf

    def process_announcement(self, item: Announcement) -> Optional[TradeSignal]:
        """Process a single announcement through deduplication, AI analysis, and execution."""
        # 1. Deduplication check via persistent storage
        if self.storage.is_processed(item.seq_id):
            return None

        # Mark as processed in database immediately
        self.storage.mark_processed(item.seq_id, item.symbol, item.an_dt)

        # 2. AI Reasoning via Gemini
        audit = self.analyzer.audit(
            symbol=item.symbol,
            headline=item.desc,
            details=item.clean_content,
        )

        if audit:
            self.storage.save_audit(item.seq_id, item.symbol, audit)
            logger.info(
                "🤖 [%s] AI Verdict: %s (Confidence: %d%%) | Catalyst: %s | Material: %s",
                item.symbol,
                audit.sentiment,
                audit.confidence,
                audit.catalyst_type,
                audit.material_impact,
            )

            # 3. Phase 3 High-Conviction Bullish Filter (>=70% confidence, material impact)
            if (
                audit.material_impact
                and audit.confidence >= settings.confidence_threshold
                and audit.sentiment.upper() in ("BULLISH", "BUY")
            ):
                action = "BUY"
                product = RiskManager.get_safe_product_type(action)

                sec_id = resolve_security_id(item.symbol) or "0"
                signal = TradeSignal(
                    symbol=item.symbol,
                    security_id=sec_id,
                    action=action,
                    product_type=product,
                    confidence=audit.confidence,
                    catalyst_type=audit.catalyst_type,
                    summary=audit.summary,
                    exchange_time=item.an_dt,
                )

                # 4. Super Order Execution (Max 10 shares cap)
                result = self.executor.execute_order(signal)
                self.storage.save_trade(result)
                return signal

        return None

    def run_cycle(self, symbol_filter: Optional[str] = None) -> list[Announcement]:
        """Execute a single polling and evaluation cycle."""
        new_items = self.monitor.get_new_announcements(
            symbol_filter=symbol_filter,
            fno_only=self.fno_only,
            filter_noise=self.filter_noise,
            extract_pdf=self.extract_pdf,
        )

        for item in new_items:
            self.process_announcement(item)

        return new_items


__all__ = ["StrategyEngine"]

