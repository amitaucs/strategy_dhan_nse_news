"""DhanHQ order execution engine with support for Bracket and Forever OCO orders."""

from datetime import datetime
import logging
import uuid
from typing import Any, Dict, Optional

from st15_largecap.config import settings
from st15_largecap.core.models import SetupSignal, TradeOrder
from st15_largecap.execution.risk import calculate_position_size

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Dispatches trade orders to DhanHQ broker or handles simulated DRY_RUN execution."""

    def __init__(self, dhan_client: Optional[Any] = None, dry_run: bool = settings.DRY_RUN):
        self.dhan = dhan_client
        self.dry_run = dry_run

    def execute_signal(
        self,
        signal: SetupSignal,
        quantity: Optional[int] = None,
        product_type: str = settings.PRODUCT_TYPE,
        order_type_preference: str = settings.ORDER_TYPE,
    ) -> TradeOrder:
        """Execute a qualified ST15 Setup Signal."""
        qty = quantity if quantity is not None else calculate_position_size(signal.trigger_price)

        if qty <= 0:
            logger.warning("Calculated quantity for %s is 0 (Insufficient capital)", signal.symbol)
            return TradeOrder(
                order_id=f"REJ-{uuid.uuid4().hex[:8]}",
                symbol=signal.symbol,
                sec_id=signal.sec_id,
                action="BUY",
                quantity=0,
                entry_price=signal.trigger_price,
                stop_loss=signal.stop_loss_price,
                target_price=signal.target_profit_price,
                product_type=product_type,
                order_type=order_type_preference,
                status="REJECTED_ZERO_QTY",
                dry_run=self.dry_run,
                placed_at=datetime.now(),
                remarks="Insufficient capital for 1 unit allocation",
            )

        if self.dry_run or not self.dhan:
            simulated_id = f"SIM-ST15-{uuid.uuid4().hex[:10].upper()}"
            logger.info(
                "🧪 [DRY RUN] Simulating %s Order: %s x %d @ %.2f (SL: %.2f, Target: %.2f)",
                order_type_preference, signal.symbol, qty, signal.trigger_price,
                signal.stop_loss_price, signal.target_profit_price,
            )
            return TradeOrder(
                order_id=simulated_id,
                symbol=signal.symbol,
                sec_id=signal.sec_id,
                action="BUY",
                quantity=qty,
                entry_price=signal.trigger_price,
                stop_loss=signal.stop_loss_price,
                target_price=signal.target_profit_price,
                product_type=product_type,
                order_type=order_type_preference,
                status="SIMULATED",
                dry_run=True,
                placed_at=datetime.now(),
                remarks="Dry run simulation execution",
            )

        # Live DhanHQ Order Placement
        try:
            logger.info(
                "🚀 [LIVE] Placing Dhan Order for %s (%s) x %d @ %.2f (SL: %.2f, TGT: %.2f)",
                signal.symbol, signal.sec_id, qty, signal.trigger_price,
                signal.stop_loss_price, signal.target_profit_price,
            )

            # Strategy specifies positional holding (CNC/MTF) with server-side exit:
            # We place a Forever OCO or Super Order
            if order_type_preference.upper() in ("SUPER_ORDER", "BRACKET"):
                response = self.dhan.place_super_order(
                    security_id=str(signal.sec_id),
                    exchange_segment="NSE_EQ",
                    transaction_type="BUY",
                    quantity=qty,
                    order_type="LIMIT",
                    product_type=product_type,
                    price=float(signal.trigger_price),
                    targetPrice=float(signal.target_profit_price),
                    stopLossPrice=float(signal.stop_loss_price),
                    tag="ST15_LargeCap",
                )
            elif order_type_preference.upper() in ("FOREVER_OCO", "GTT"):
                response = self.dhan.place_forever(
                    security_id=str(signal.sec_id),
                    exchange_segment="NSE_EQ",
                    transaction_type="BUY",
                    product_type=product_type,
                    order_type="LIMIT",
                    quantity=qty,
                    price=float(signal.trigger_price),
                    trigger_Price=float(signal.trigger_price),
                    order_flag="SINGLE",
                    tag="ST15_LargeCap",
                    symbol=signal.symbol,
                )
            else:
                # Regular Limit Order
                response = self.dhan.place_order(
                    security_id=str(signal.sec_id),
                    exchange_segment="NSE_EQ",
                    transaction_type="BUY",
                    quantity=qty,
                    order_type="LIMIT",
                    product_type=product_type,
                    price=float(signal.trigger_price),
                    validity="DAY",
                    tag="ST15_LargeCap",
                )

            if isinstance(response, dict) and response.get("status") == "success":
                order_id = str(response.get("data", {}).get("orderId", uuid.uuid4().hex[:8]))
                order_status = response.get("data", {}).get("orderStatus", "PLACED")
                return TradeOrder(
                    order_id=order_id,
                    symbol=signal.symbol,
                    sec_id=signal.sec_id,
                    action="BUY",
                    quantity=qty,
                    entry_price=signal.trigger_price,
                    stop_loss=signal.stop_loss_price,
                    target_price=signal.target_profit_price,
                    product_type=product_type,
                    order_type=order_type_preference,
                    status=order_status,
                    dry_run=False,
                    placed_at=datetime.now(),
                    remarks="Live DhanHQ order placed successfully",
                )
            else:
                err_msg = str(response.get("remarks") if isinstance(response, dict) else response)
                logger.error("DhanHQ Order placement failed for %s: %s", signal.symbol, err_msg)
                return TradeOrder(
                    order_id=f"ERR-{uuid.uuid4().hex[:8]}",
                    symbol=signal.symbol,
                    sec_id=signal.sec_id,
                    action="BUY",
                    quantity=qty,
                    entry_price=signal.trigger_price,
                    stop_loss=signal.stop_loss_price,
                    target_price=signal.target_profit_price,
                    product_type=product_type,
                    order_type=order_type_preference,
                    status="FAILED",
                    dry_run=False,
                    placed_at=datetime.now(),
                    remarks=err_msg,
                )
        except Exception as e:
            logger.error("Exception placing order for %s: %s", signal.symbol, e)
            return TradeOrder(
                order_id=f"EXC-{uuid.uuid4().hex[:8]}",
                symbol=signal.symbol,
                sec_id=signal.sec_id,
                action="BUY",
                quantity=qty,
                entry_price=signal.trigger_price,
                stop_loss=signal.stop_loss_price,
                target_price=signal.target_profit_price,
                product_type=product_type,
                order_type=order_type_preference,
                status="ERROR",
                dry_run=False,
                placed_at=datetime.now(),
                remarks=str(e),
            )
