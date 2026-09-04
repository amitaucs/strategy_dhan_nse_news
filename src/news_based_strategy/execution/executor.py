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
        auto_order: Optional[bool] = None,
        capital_per_trade: float = 20000.0,
        max_shares_per_trade: Optional[int] = None,
        max_news_age_seconds: int = 180,
        super_order_enabled: Optional[bool] = None,
        target_profit_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        trailing_jump_points: Optional[float] = None,
        slippage_buffer_pct: Optional[float] = None,
        approval_callback=None,
    ):
        self.client_id = client_id
        self.access_token = access_token
        self.dry_run = dry_run
        self.capital_per_trade = capital_per_trade
        self.max_news_age_seconds = max_news_age_seconds
        self.approval_callback = approval_callback

        from news_based_strategy.config import settings

        self.auto_order = settings.auto_order if auto_order is None else auto_order
        self.max_shares_per_trade = (
            settings.max_shares_per_trade if max_shares_per_trade is None else max_shares_per_trade
        )
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

    def get_masked_token(self) -> str:
        """Return a safely masked version of the access token."""
        if not self.access_token:
            return "NOT_CONFIGURED"
        if len(self.access_token) <= 12:
            return f"{self.access_token[:3]}...{self.access_token[-2:]}"
        return f"{self.access_token[:8]}...{self.access_token[-6:]}"

    def update_credentials(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ) -> dict:
        """Update DhanHQ credentials at runtime and reinitialize client."""
        if client_id is not None:
            self.client_id = client_id.strip()
        if access_token is not None:
            self.access_token = access_token.strip()
        if dry_run is not None:
            self.dry_run = dry_run

        self._init_client()
        return self.validate_token()

    def validate_token(self) -> dict:
        """Validate token format or test connection against Dhan API if available."""
        if not self.access_token:
            return {
                "valid": False,
                "message": "Access token is empty",
                "client_id": self.client_id,
                "dry_run": self.dry_run,
                "masked_token": "NOT_CONFIGURED",
            }

        if self.dry_run:
            return {
                "valid": True,
                "message": "Token updated successfully (Running in DRY-RUN mode)",
                "client_id": self.client_id,
                "dry_run": True,
                "masked_token": self.get_masked_token(),
            }

        if self.dhan:
            try:
                funds = self.dhan.get_fund_limits()
                if isinstance(funds, dict) and funds.get("status") == "success":
                    avail = funds.get("data", {}).get("availabelBalance", "N/A")
                    return {
                        "valid": True,
                        "message": f"DhanHQ connected successfully (Available Margin: ₹{avail})",
                        "client_id": self.client_id,
                        "dry_run": False,
                        "masked_token": self.get_masked_token(),
                        "fund_data": funds.get("data"),
                    }
                else:
                    err_msg = funds.get("remarks") if isinstance(funds, dict) else str(funds)
                    return {
                        "valid": False,
                        "message": f"Dhan API rejected token: {err_msg}",
                        "client_id": self.client_id,
                        "dry_run": False,
                        "masked_token": self.get_masked_token(),
                    }
            except Exception as e:
                logger.warning("Failed validating Dhan token against API: %s", e)
                return {
                    "valid": False,
                    "message": f"Dhan API error: {str(e)}",
                    "client_id": self.client_id,
                    "dry_run": False,
                    "masked_token": self.get_masked_token(),
                }

        return {
            "valid": True,
            "message": "Token format accepted (dhanhq SDK not installed, using simulated execution)",
            "client_id": self.client_id,
            "dry_run": self.dry_run,
            "masked_token": self.get_masked_token(),
        }

    def request_user_approval(
        self,
        signal: TradeSignal,
        quantity: int,
        effective_sec_id: str,
        entry_price: float,
        target_price: float,
        sl_price: float,
        ltp: float,
    ) -> bool:
        """Prompt user for interactive trade approval when AUTO_ORDER=False."""
        if self.approval_callback is not None:
            return bool(
                self.approval_callback(
                    signal=signal,
                    quantity=quantity,
                    effective_sec_id=effective_sec_id,
                    entry_price=entry_price,
                    target_price=target_price,
                    sl_price=sl_price,
                    ltp=ltp,
                )
            )

        mode_str = "DRY-RUN (Simulated)" if self.dry_run else "LIVE (Real Dhan Order)"
        print("\n   ┌─ 🔔 User Trade Approval Required (AUTO_ORDER=False) ────────")
        print(f"   │ • Mode: {mode_str}")
        print(f"   │ • Proposed Order: {signal.action} {quantity} shares of {signal.symbol} (Dhan SecID: {effective_sec_id})")
        print(f"   │ • Order Type: Bracket Super Order (INTRADAY)")
        print(f"   │ • Entry Limit: ₹{entry_price:.2f} (LTP: ₹{ltp:.2f} + {self.slippage_buffer_pct}% buffer)")
        print(f"   │ • Target Profit: ₹{target_price:.2f} (+{self.target_profit_pct}%) | Stop Loss: ₹{sl_price:.2f} (-{self.stop_loss_pct}%)")
        print(f"   │ • Trailing Jump: {self.trailing_jump_points} pts")
        print(f"   │ • Catalyst: {signal.catalyst_type} (Confidence: {signal.confidence}%)")
        print(f"   │ • AI Rationale: \"{signal.summary}\"")
        print("   └─────────────────────────────────────────────────────────────")
        try:
            ans = input(f"   👉 Approve and place this order for {signal.symbol}? [y/N]: ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

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

        quantity = RiskManager.calculate_position_size(
            self.capital_per_trade, ltp, max_quantity=self.max_shares_per_trade
        )

        # Compute Super Order levels
        entry_price, target_price, sl_price = RiskManager.calculate_super_order_levels(
            ltp=ltp,
            action=signal.action,
            target_pct=self.target_profit_pct,
            sl_pct=self.stop_loss_pct,
            slippage_buffer_pct=self.slippage_buffer_pct,
        )

        # 3. User Approval Gate (if AUTO_ORDER=False)
        if not self.auto_order:
            approved = self.request_user_approval(
                signal=signal,
                quantity=quantity,
                effective_sec_id=effective_sec_id,
                entry_price=entry_price,
                target_price=target_price,
                sl_price=sl_price,
                ltp=ltp,
            )
            if not approved:
                remarks = "ORDER SKIPPED: User declined trade approval (AUTO_ORDER=False)"
                logger.info("⏸️ [%s] %s", signal.symbol, remarks)
                return TradeResult(
                    success=False,
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=quantity,
                    product_type="INTRADAY" if self.super_order_enabled else safe_product,
                    order_id=None,
                    remarks=remarks,
                    dry_run=self.dry_run,
                )

        # 4. Simulated Dry-Run Execution
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

