"""Broker order executor with DhanHQ integration and dry-run simulation."""

import logging
from typing import Optional
from news_based_strategy.core.models import TradeResult, TradeSignal
from news_based_strategy.execution.risk import RiskManager
from news_based_strategy.ingestion.universe import resolve_security_id

logger = logging.getLogger(__name__)


class DhanExecutor:
    """Executes trade orders on DhanHQ or in simulated dry-run mode."""

    def __init__(
        self,
        client_id: str = "",
        access_token: str = "",
        dry_run: bool = True,
        capital_per_trade: float = 20000.0,
        max_news_age_seconds: int = 180,
        super_order_enabled: Optional[bool] = None,
        target_profit_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        trailing_jump_points: Optional[float] = None,
        slippage_buffer_pct: Optional[float] = None,
    ):
        self.client_id = client_id
        self.access_token = access_token
        self.dry_run = dry_run
        self.capital_per_trade = capital_per_trade
        self.max_news_age_seconds = max_news_age_seconds

        from news_based_strategy.config import settings

        self.super_order_enabled = (
            settings.super_order_enabled if super_order_enabled is None else super_order_enabled
        )
        self.target_profit_pct = (
            settings.target_profit_pct if target_profit_pct is None else target_profit_pct
        )
        self.stop_loss_pct = (
            settings.stop_loss_pct if stop_loss_pct is None else stop_loss_pct
        )
        self.trailing_jump_points = (
            settings.trailing_jump_points if trailing_jump_points is None else trailing_jump_points
        )
        self.slippage_buffer_pct = (
            settings.slippage_buffer_pct if slippage_buffer_pct is None else slippage_buffer_pct
        )

        self.dhan = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Dhan client if credentials are provided and dry_run is False."""
        if self.dry_run:
            logger.info("DhanExecutor initialized in DRY-RUN mode. No real orders will be placed.")
            return

        if not (self.client_id and self.access_token):
            logger.warning("Dhan credentials missing. Reverting to DRY-RUN mode.")
            self.dry_run = True
            return

        try:
            from dhanhq import dhanhq

            self.dhan = dhanhq(self.client_id, self.access_token)
            logger.info("DhanHQ client successfully initialized for live execution.")
        except ImportError:
            logger.warning("dhanhq package not installed. Running in DRY-RUN mode.")
            self.dry_run = True

    def execute_order(self, signal: TradeSignal, ltp: float = 100.0) -> TradeResult:
        """Place an order or simulate execution with staleness circuit breaker, SecID, and Super Orders."""
        safe_product = RiskManager.get_safe_product_type(signal.action, signal.product_type)

        # 0. Dynamic Security ID Resolution (Ticker -> Dhan Numeric ID)
        effective_sec_id = signal.security_id
        if not effective_sec_id or effective_sec_id == "0":
            effective_sec_id = resolve_security_id(signal.symbol) or "0"

        # 1. Staleness Circuit Breaker (Disarm if news broadcast is too old)
        if signal.exchange_time:
            is_fresh, age = RiskManager.is_news_fresh(signal.exchange_time, self.max_news_age_seconds)
            if not is_fresh:
                age_int = int(round(age))
                remarks = f"ORDER REJECTED: Catalyst too stale (Age: {age_int}s > {self.max_news_age_seconds}s)"
                logger.warning("⚠️ [%s] %s", signal.symbol, remarks)
                return TradeResult(
                    success=False,
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=0,
                    product_type=safe_product,
                    order_id=None,
                    remarks=remarks,
                    dry_run=self.dry_run,
                )

        # 2. Defensive check for live execution: must have a valid non-zero numeric Security ID
        if not self.dry_run and self.dhan:
            if not effective_sec_id or effective_sec_id == "0":
                remarks = f"ORDER REJECTED: Could not resolve Dhan security ID for {signal.symbol}"
                logger.error("❌ [%s] %s", signal.symbol, remarks)
                return TradeResult(
                    success=False,
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=0,
                    product_type=safe_product,
                    order_id=None,
                    remarks=remarks,
                    dry_run=False,
                )

        quantity = RiskManager.calculate_position_size(self.capital_per_trade, ltp)

        # Compute Super Order levels
        entry_price, target_price, sl_price = RiskManager.calculate_super_order_levels(
            ltp=ltp,
            action=signal.action,
            target_pct=self.target_profit_pct,
            sl_pct=self.stop_loss_pct,
            slippage_buffer_pct=self.slippage_buffer_pct,
        )

        # 3. Simulated Dry-Run Execution
        if self.dry_run or not self.dhan:
            simulated_order_id = f"DRY_{signal.symbol}_{effective_sec_id}_{int(signal.confidence)}"
            if self.super_order_enabled:
                logger.info(
                    "🚀 [DRY-RUN SUPER ORDER] %s %d shares of %s (Dhan SecID: %s) @ Entry Limit ₹%.2f | Target: ₹%.2f (+%.1f%%) | SL: ₹%.2f (-%.1f%%) | Trail: %.1f pts (Catalyst: %s)",
                    signal.action,
                    quantity,
                    signal.symbol,
                    effective_sec_id,
                    entry_price,
                    target_price,
                    self.target_profit_pct,
                    sl_price,
                    self.stop_loss_pct,
                    self.trailing_jump_points,
                    signal.catalyst_type,
                )
                remarks = (
                    f"Simulated Super Order: Entry Limit ₹{entry_price:.2f}, "
                    f"TP ₹{target_price:.2f} (+{self.target_profit_pct}%), "
                    f"SL ₹{sl_price:.2f} (-{self.stop_loss_pct}%), "
                    f"Trail {self.trailing_jump_points} pts"
                )
            else:
                logger.info(
                    "🚀 [DRY-RUN] Simulated %s %d shares of %s (Dhan SecID: %s | %s) @ ₹%.2f (Catalyst: %s)",
                    signal.action,
                    quantity,
                    signal.symbol,
                    effective_sec_id,
                    safe_product,
                    ltp,
                    signal.catalyst_type,
                )
                remarks = "Simulated dry-run order execution"

            return TradeResult(
                success=True,
                symbol=signal.symbol,
                action=signal.action,
                quantity=quantity,
                product_type="INTRADAY" if self.super_order_enabled else safe_product,
                order_id=simulated_order_id,
                remarks=remarks,
                dry_run=True,
            )

        # 4. Live DhanHQ Execution
        try:
            txn_type = self.dhan.BUY if signal.action.upper() == "BUY" else self.dhan.SELL

            if self.super_order_enabled:
                # Dhan Super Orders are strictly Intraday bracket orders with Limit entry
                order = self.dhan.place_super_order(
                    security_id=effective_sec_id,
                    exchange_segment=self.dhan.NSE,
                    transaction_type=txn_type,
                    quantity=quantity,
                    order_type=self.dhan.LIMIT,
                    product_type=self.dhan.INTRA,
                    price=entry_price,
                    targetPrice=target_price,
                    stopLossPrice=sl_price,
                    trailingJump=self.trailing_jump_points,
                    tag="news_super",
                )
                placed_product = "INTRADAY"
            else:
                prod_type = self.dhan.INTRA if safe_product == "INTRADAY" else self.dhan.CNC
                order = self.dhan.place_order(
                    security_id=effective_sec_id,
                    exchange_segment=self.dhan.NSE,
                    transaction_type=txn_type,
                    quantity=quantity,
                    order_type=self.dhan.MARKET,
                    product_type=prod_type,
                    price=0,
                )
                placed_product = safe_product

            order_id = str(order.get("orderId", "")) if isinstance(order, dict) else str(order)
            logger.info("✅ Live Dhan order placed for %s: %s", signal.symbol, order)
            return TradeResult(
                success=True,
                symbol=signal.symbol,
                action=signal.action,
                quantity=quantity,
                product_type=placed_product,
                order_id=order_id,
                remarks=str(order),
                dry_run=False,
            )
        except Exception as e:
            logger.error("❌ Dhan order placement failed for %s: %s", signal.symbol, e)
            return TradeResult(
                success=False,
                symbol=signal.symbol,
                action=signal.action,
                quantity=quantity,
                product_type="INTRADAY" if self.super_order_enabled else safe_product,
                remarks=str(e),
                dry_run=False,
            )


__all__ = ["DhanExecutor"]

