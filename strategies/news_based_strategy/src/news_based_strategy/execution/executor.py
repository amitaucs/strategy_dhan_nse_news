import base64
from datetime import datetime
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from news_based_strategy.core.models import TradeResult, TradeSignal
from news_based_strategy.execution.risk import RiskManager
from news_based_strategy.ingestion.universe import resolve_security_id

logger = logging.getLogger(__name__)


def parse_jwt_claims(token: str) -> dict:
    """Safely decode JWT payload without verification."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return {}


def check_token_expiry(token: str) -> Tuple[bool, str, Optional[int]]:
    """
    Check if a Dhan JWT token is expired.
    Returns (is_expired, status_message, expiry_timestamp).
    """
    if not token or not token.strip():
        return False, "No token configured", None
    claims = parse_jwt_claims(token)
    exp = claims.get("exp")
    if exp is None:
        return False, "Valid format (no expiry claim)", None

    current_ts = int(time.time())
    if current_ts >= exp:
        exp_str = time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(exp))
        return True, f"Token expired on {exp_str}", exp
    else:
        diff_seconds = exp - current_ts
        hours_left = diff_seconds / 3600
        days_left = diff_seconds / 86400
        if days_left >= 1:
            time_left_str = f"{days_left:.1f}d remaining"
        else:
            time_left_str = f"{hours_left:.1f}h remaining"
        exp_str = time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(exp))
        return False, f"Valid until {exp_str} ({time_left_str})", exp


def mask_client_id(client_id: Optional[str]) -> Optional[str]:
    """
    Mask a client ID showing only the last 4 digits (e.g. ••••2040).
    """
    if not client_id:
        return None
    cid = str(client_id).strip()
    if len(cid) <= 4:
        return cid
    return f"••••{cid[-4:]}"


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
        max_orders_per_day: Optional[int] = None,
        max_news_age_seconds: int = 180,
        super_order_enabled: Optional[bool] = None,
        target_profit_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        trailing_jump_points: Optional[float] = None,
        slippage_buffer_pct: Optional[float] = None,
        trade_cutoff_time: Optional[str] = None,
        square_off_time: Optional[str] = None,
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
        self.max_orders_per_day = (
            settings.max_orders_per_day if max_orders_per_day is None else max_orders_per_day
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
        self.trade_cutoff_time = (
            settings.trade_cutoff_time if trade_cutoff_time is None else trade_cutoff_time
        )
        self.square_off_time = (
            settings.square_off_time if square_off_time is None else square_off_time
        )

        self._daily_order_timestamps: List[datetime] = []
        self.dhan = None
        self._init_client()

    def get_daily_order_count(self, ref_dt: Optional[datetime] = None) -> int:
        """Return count of orders successfully placed on reference date in IST (defaults to today)."""
        target_date = (ref_dt or RiskManager.get_ist_now()).date()
        return sum(1 for dt in self._daily_order_timestamps if dt.date() == target_date)

    def record_placed_order(self, dt: Optional[datetime] = None) -> None:
        """Record an executed order timestamp for daily limit tracking in IST."""
        self._daily_order_timestamps.append(dt or RiskManager.get_ist_now())

    def reset_daily_order_count(self) -> None:
        """Clear recorded daily order history."""
        self._daily_order_timestamps.clear()

    def _init_client(self) -> None:
        """Initialize Dhan client if credentials are provided and dry_run is False."""
        if self.dry_run:
            logger.info("DhanExecutor initialized in VIRTUAL mode. No real orders will be placed.")
            self.dhan = None
            return

        if not (self.client_id and self.access_token):
            logger.warning("Dhan credentials not configured for live execution.")
            self.dhan = None
            return

        try:
            try:
                from dhanhq import DhanContext, dhanhq
                ctx = DhanContext(self.client_id, self.access_token)
                self.dhan = dhanhq(ctx)
            except (TypeError, ImportError, AttributeError):
                from dhanhq import dhanhq
                self.dhan = dhanhq(self.client_id, self.access_token)
            logger.info("DhanHQ client successfully initialized for live execution.")
        except ImportError:
            logger.warning("dhanhq package not installed. Live orders will fail until installed.")
            self.dhan = None
        except Exception as e:
            logger.warning("Could not initialize DhanHQ client: %s", e)
            self.dhan = None

    def get_masked_token(self) -> str:
        """Return a safely masked version of the access token."""
        if not self.access_token:
            return "NOT_CONFIGURED"
        if len(self.access_token) <= 12:
            return f"{self.access_token[:3]}...{self.access_token[-2:]}"
        return f"{self.access_token[:8]}...{self.access_token[-6:]}"

    def get_masked_client_id(self) -> str:
        """Return masked client ID showing last 4 digits (e.g. ••••2040)."""
        if not self.client_id:
            return ""
        return mask_client_id(self.client_id) or ""

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

    def get_token_expiry_info(self) -> dict:
        """Return structured expiry information for the current token."""
        is_exp, msg, exp_ts = check_token_expiry(self.access_token)
        return {
            "is_expired": is_exp,
            "expiry_message": msg,
            "expiry_ts": exp_ts,
            "formatted_expiry": time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(exp_ts)) if exp_ts else None,
        }

    def validate_token(self) -> dict:
        """Validate token format, check expiry, or test connection against Dhan API if available."""
        if not self.access_token:
            return {
                "valid": False,
                "is_expired": False,
                "message": "Access token is empty",
                "client_id": self.client_id,
                "masked_client_id": self.get_masked_client_id(),
                "dry_run": self.dry_run,
                "masked_token": "NOT_CONFIGURED",
                "expiry_info": self.get_token_expiry_info(),
            }

        is_exp, exp_msg, exp_ts = check_token_expiry(self.access_token)
        if is_exp:
            return {
                "valid": False,
                "is_expired": True,
                "message": f"Dhan Access Token is EXPIRED ({exp_msg})",
                "client_id": self.client_id,
                "masked_client_id": self.get_masked_client_id(),
                "dry_run": self.dry_run,
                "masked_token": self.get_masked_token(),
                "expiry_ts": exp_ts,
                "expiry_info": self.get_token_expiry_info(),
            }

        if self.dry_run:
            return {
                "valid": True,
                "is_expired": False,
                "message": f"Token updated successfully ({exp_msg} | Running in VIRTUAL mode)",
                "client_id": self.client_id,
                "masked_client_id": self.get_masked_client_id(),
                "dry_run": True,
                "masked_token": self.get_masked_token(),
                "expiry_ts": exp_ts,
                "expiry_info": self.get_token_expiry_info(),
            }

        if self.dhan:
            try:
                funds = self.dhan.get_fund_limits()
                if isinstance(funds, dict) and funds.get("status") == "success":
                    avail = funds.get("data", {}).get("availabelBalance", "N/A")
                    return {
                        "valid": True,
                        "is_expired": False,
                        "message": f"DhanHQ connected successfully (Available Margin: ₹{avail} | {exp_msg})",
                        "client_id": self.client_id,
                        "masked_client_id": self.get_masked_client_id(),
                        "dry_run": False,
                        "masked_token": self.get_masked_token(),
                        "fund_data": funds.get("data"),
                        "expiry_info": self.get_token_expiry_info(),
                    }
                else:
                    err_msg = funds.get("remarks") if isinstance(funds, dict) else str(funds)
                    return {
                        "valid": False,
                        "is_expired": False,
                        "message": f"Dhan API rejected token: {err_msg}",
                        "client_id": self.client_id,
                        "masked_client_id": self.get_masked_client_id(),
                        "dry_run": False,
                        "masked_token": self.get_masked_token(),
                        "expiry_info": self.get_token_expiry_info(),
                    }
            except Exception as e:
                logger.warning("Failed validating Dhan token against API: %s", e)
                return {
                    "valid": False,
                    "is_expired": False,
                    "message": f"Dhan API error: {str(e)}",
                    "client_id": self.client_id,
                    "masked_client_id": self.get_masked_client_id(),
                    "dry_run": False,
                    "masked_token": self.get_masked_token(),
                    "expiry_info": self.get_token_expiry_info(),
                }

        return {
            "valid": True,
            "is_expired": False,
            "message": f"Token format accepted ({exp_msg})",
            "client_id": self.client_id,
            "masked_client_id": self.get_masked_client_id(),
            "dry_run": self.dry_run,
            "masked_token": self.get_masked_token(),
            "expiry_info": self.get_token_expiry_info(),
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

        mode_str = "VIRTUAL (Simulated)" if self.dry_run else "LIVE (Real Dhan Order)"
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

        if not self.dry_run and (not effective_sec_id or effective_sec_id == "0"):
            remarks = f"ORDER REJECTED: Could not resolve Dhan security ID for {signal.symbol}"
            logger.warning("⚠️ [%s] %s", signal.symbol, remarks)
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

        # 2. Intraday Trade Cutoff Window (No new trades permitted after 02:45 PM IST)
        if not self.dry_run:
            ref_dt = RiskManager.parse_exchange_timestamp(signal.exchange_time) if signal.exchange_time else RiskManager.get_ist_now()
            is_allowed, cutoff_reason = RiskManager.is_trade_allowed(ref_dt, cutoff_str=self.trade_cutoff_time)
            if not is_allowed:
                remarks = f"ORDER REJECTED: {cutoff_reason}"
                logger.warning("⚠️ [%s] %s", signal.symbol, remarks)
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

        # 3. Daily Max Orders Circuit Breaker (Configurable per day limit)
        today_order_count = self.get_daily_order_count()
        if RiskManager.is_daily_order_limit_reached(today_order_count, self.max_orders_per_day):
            remarks = (
                f"ORDER REJECTED: Daily order limit reached "
                f"({today_order_count}/{self.max_orders_per_day} orders placed today)"
            )
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

        # 4. Position Sizing
        quantity = RiskManager.calculate_position_size(
            capital=self.capital_per_trade,
            ltp=ltp,
            max_quantity=self.max_shares_per_trade,
        )
        if quantity <= 0:
            remarks = (
                f"ORDER REJECTED: Insufficient trade capital (₹{self.capital_per_trade:,.2f}) "
                f"to purchase 1 share of {signal.symbol} at LTP ₹{ltp:,.2f}"
            )
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

        # 5. Bracket Orders (Super Order) Level Calculations
        if self.super_order_enabled:
            entry_price, target_price, sl_price = RiskManager.calculate_super_order_levels(
                ltp=ltp,
                action=signal.action,
                target_pct=self.target_profit_pct,
                sl_pct=self.stop_loss_pct,
                slippage_buffer_pct=self.slippage_buffer_pct,
            )
        else:
            entry_price = round(ltp * (1.0 + self.slippage_buffer_pct / 100.0), 2)
            target_price, sl_price = 0.0, 0.0

        # 6. Manual Approval Check
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
                remarks = f"ORDER SKIPPED: User declined trade approval for {signal.symbol}"
                logger.info("⏸️ [%s] %s", signal.symbol, remarks)
                return TradeResult(
                    success=False,
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=quantity,
                    product_type=safe_product,
                    order_id=None,
                    remarks=remarks,
                    dry_run=self.dry_run,
                )

        # 7. Execution: Dry-Run Mode
        if self.dry_run or not self.dhan:
            mode_tag = "VIRTUAL_SIMULATED" if self.dry_run else "MOCK_DISCONNECTED"
            sim_id = f"{mode_tag}_{signal.symbol}_{effective_sec_id}"
            if self.super_order_enabled:
                remarks = (
                    f"Simulated Super Order: Entry Limit ₹{entry_price:.2f} "
                    f"(TP ₹{target_price:.2f} (+{self.target_profit_pct}%), "
                    f"SL ₹{sl_price:.2f} (-{self.stop_loss_pct}%), Trail {self.trailing_jump_points} pts)"
                )
            else:
                remarks = f"Simulated execution for {signal.symbol} (Dry-run mode active)"
            logger.info("🛡️ [%s] %s (SecID: %s, Qty: %d)", signal.symbol, remarks, effective_sec_id, quantity)
            self.record_placed_order()
            return TradeResult(
                success=True,
                symbol=signal.symbol,
                action=signal.action,
                quantity=quantity,
                product_type="INTRADAY" if self.super_order_enabled else safe_product,
                order_id=sim_id,
                remarks=remarks,
                dry_run=True,
            )

        # 8. Execution: Live Dhan Mode
        try:
            if self.super_order_enabled:
                order_resp = self.dhan.place_super_order(
                    security_id=effective_sec_id,
                    exchange_segment=self.dhan.NSE,
                    transaction_type=self.dhan.BUY if signal.action == "BUY" else self.dhan.SELL,
                    quantity=quantity,
                    order_type=self.dhan.LIMIT,
                    product_type=self.dhan.INTRA,
                    price=entry_price,
                    targetPrice=target_price,
                    stopLossPrice=sl_price,
                    trailingJump=self.trailing_jump_points,
                    tag="news_super",
                )
                order_id = str(order_resp.get("orderId", "UNKNOWN_SUPER_ID")) if isinstance(order_resp, dict) else str(order_resp)
                remarks = (
                    f"Dhan Super Order placed successfully! ID: {order_id} "
                    f"(Entry ₹{entry_price:.2f}, TP ₹{target_price:.2f}, SL ₹{sl_price:.2f})"
                )
                logger.info("🚀 [%s] %s", signal.symbol, remarks)
                self.record_placed_order()
                return TradeResult(
                    success=True,
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=quantity,
                    product_type="INTRADAY",
                    order_id=order_id,
                    remarks=remarks,
                    dry_run=False,
                )
            else:
                order_resp = self.dhan.place_order(
                    security_id=effective_sec_id,
                    exchange_segment=self.dhan.NSE,
                    transaction_type=self.dhan.BUY if signal.action == "BUY" else self.dhan.SELL,
                    quantity=quantity,
                    order_type=self.dhan.MARKET,
                    product_type=self.dhan.CNC if safe_product == "CNC" else self.dhan.INTRA,
                    price=0,
                )
                order_id = str(order_resp.get("orderId", "UNKNOWN_DHAN_ID")) if isinstance(order_resp, dict) else str(order_resp)
                remarks = f"Dhan order placed successfully! Order ID: {order_id}"
                logger.info("🚀 [%s] %s", signal.symbol, remarks)
                self.record_placed_order()
                return TradeResult(
                    success=True,
                    symbol=signal.symbol,
                    action=signal.action,
                    quantity=quantity,
                    product_type=safe_product,
                    order_id=order_id,
                    remarks=remarks,
                    dry_run=False,
                )
        except Exception as e:
            logger.error("❌ [%s] Live order placement failed: %s", signal.symbol, e)
            return TradeResult(
                success=False,
                symbol=signal.symbol,
                action=signal.action,
                quantity=quantity,
                product_type="INTRADAY" if self.super_order_enabled else safe_product,
                remarks=str(e),
                dry_run=False,
            )

    def square_off_all_positions(self) -> dict:
        """Cancel all pending/open orders and square off all open intraday positions (Long & Short)."""
        mode_str = "VIRTUAL" if self.dry_run else "LIVE"
        logger.info("⏰ Triggering Intraday Square-Off routine (Mode: %s)...", mode_str)
        now_ist = RiskManager.get_ist_now()
        results = {
            "success": True,
            "dry_run": self.dry_run,
            "timestamp": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
            "orders_cancelled": 0,
            "positions_squared_off": 0,
            "cancelled_orders": [],
            "closed_positions": [],
            "details": [],
        }

        if self.dry_run or not self.dhan:
            msg = "Virtual square-off completed: All virtual intraday positions and orders cleared."
            logger.info("✅ [VIRTUAL] %s", msg)
            results["details"].append({"type": "VIRTUAL", "status": "CLEARED", "remarks": msg})
            return results

        try:
            # 1. Cancel all open / pending regular orders
            try:
                orders_resp = self.dhan.get_order_list()
                order_list = orders_resp if isinstance(orders_resp, list) else orders_resp.get("data", []) if isinstance(orders_resp, dict) else []
                for o in order_list:
                    if isinstance(o, dict):
                        o_id = str(o.get("orderId", ""))
                        o_status = str(o.get("orderStatus", "")).upper()
                        if o_status in ("PENDING", "TRANSIT", "TRIGGER_PENDING", "OPEN"):
                            try:
                                cancel_res = self.dhan.cancel_order(order_id=o_id)
                                results["orders_cancelled"] += 1
                                results["cancelled_orders"].append(o_id)
                                results["details"].append({
                                    "type": "CANCEL_ORDER",
                                    "order_id": o_id,
                                    "status": "CANCELLED",
                                    "response": cancel_res,
                                })
                                logger.info("🚫 Cancelled open order %s (%s)", o_id, o_status)
                            except Exception as ce:
                                logger.warning("Failed to cancel order %s: %s", o_id, ce)
            except Exception as oe:
                logger.warning("Error fetching order list during square off: %s", oe)

            # 2. Cancel open Super Orders
            try:
                if hasattr(self.dhan, "get_super_order_list") and hasattr(self.dhan, "cancel_super_order"):
                    so_resp = self.dhan.get_super_order_list()
                    so_list = so_resp if isinstance(so_resp, list) else so_resp.get("data", []) if isinstance(so_resp, dict) else []
                    for so in so_list:
                        if isinstance(so, dict):
                            so_id = str(so.get("orderId", "") or so.get("superOrderId", ""))
                            so_status = str(so.get("orderStatus", "")).upper()
                            if so_status in ("PENDING", "TRANSIT", "TRIGGER_PENDING", "OPEN"):
                                try:
                                    cancel_so = self.dhan.cancel_super_order(order_id=so_id)
                                    results["orders_cancelled"] += 1
                                    results["cancelled_orders"].append(so_id)
                                    results["details"].append({
                                        "type": "CANCEL_SUPER_ORDER",
                                        "order_id": so_id,
                                        "status": "CANCELLED",
                                        "response": cancel_so,
                                    })
                                    logger.info("🚫 Cancelled open super order %s (%s)", so_id, so_status)
                                except Exception as cse:
                                    logger.warning("Failed to cancel super order %s: %s", so_id, cse)
            except Exception as soe:
                logger.debug("Super order list check skipped/unsupported: %s", soe)

            # 3. Query open positions and square off intraday positions
            pos_resp = self.dhan.get_positions()
            pos_list = pos_resp if isinstance(pos_resp, list) else pos_resp.get("data", []) if isinstance(pos_resp, dict) else []

            for p in pos_list:
                if not isinstance(p, dict):
                    continue
                prod_type = str(p.get("productType", "") or p.get("positionType", "")).upper()
                sec_id = str(p.get("securityId", ""))
                symbol = str(p.get("tradingSymbol", "") or sec_id)
                net_qty = int(p.get("netQty", 0) or 0)

                # Square off open intraday positions
                if net_qty != 0 and prod_type in ("INTRADAY", "INTRA", ""):
                    sq_action = self.dhan.SELL if net_qty > 0 else self.dhan.BUY
                    sq_qty = abs(net_qty)
                    try:
                        sq_order = self.dhan.place_order(
                            security_id=sec_id,
                            exchange_segment=self.dhan.NSE,
                            transaction_type=sq_action,
                            quantity=sq_qty,
                            order_type=self.dhan.MARKET,
                            product_type=self.dhan.INTRA,
                            price=0,
                        )
                        results["positions_squared_off"] += 1
                        results["closed_positions"].append(symbol)
                        results["details"].append({
                            "type": "SQUARE_OFF_POSITION",
                            "symbol": symbol,
                            "security_id": sec_id,
                            "action": "SELL" if net_qty > 0 else "BUY",
                            "quantity": sq_qty,
                            "order": sq_order,
                        })
                        logger.info(
                            "✅ Squared off intraday position for %s: %s %d shares",
                            symbol,
                            "SELL" if net_qty > 0 else "BUY",
                            sq_qty,
                        )
                    except Exception as sq_err:
                        logger.error("❌ Failed to square off position for %s: %s", symbol, sq_err)
                        results["details"].append({
                            "type": "SQUARE_OFF_ERROR",
                            "symbol": symbol,
                            "error": str(sq_err),
                        })

            return results
        except Exception as e:
            logger.error("❌ Unexpected error in square_off_all_positions: %s", e)
            results["success"] = False
            results["error"] = str(e)
            return results


__all__ = ["DhanExecutor", "check_token_expiry", "parse_jwt_claims"]

