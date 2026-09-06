"""Risk management, position sizing, and profit target calculations."""

import math
from typing import Dict, Any, Optional

from st15_largecap.config import settings
from st15_largecap.core.models import SetupSignal


def calculate_position_size(
    entry_price: float,
    capital_per_trade: Optional[float] = None,
    total_capital: Optional[float] = None,
    capital_allocation_pct: Optional[float] = None,
) -> int:
    """Calculate integer share quantity based on 33% of allocated total capital per single order."""
    if entry_price <= 0:
        return 0

    if capital_per_trade is not None and capital_per_trade > 0:
        cap = capital_per_trade
    elif total_capital is not None and capital_allocation_pct is not None:
        cap = total_capital * (capital_allocation_pct / 100.0)
    else:
        cap = settings.CAPITAL_PER_POSITION

    if cap <= 0:
        return 0

    qty = int(math.floor(cap / entry_price))
    return max(1, qty) if cap >= entry_price else 0


def calculate_trade_parameters(
    signal: SetupSignal,
    capital_per_trade: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate complete execution parameters including quantities and risk amounts."""
    cap = capital_per_trade if (capital_per_trade is not None and capital_per_trade > 0) else settings.CAPITAL_PER_POSITION
    quantity = calculate_position_size(signal.trigger_price, capital_per_trade=cap)
    total_investment = round(quantity * signal.trigger_price, 2)
    max_risk_amount = round(quantity * signal.risk_per_share, 2)
    potential_profit_amount = round(
        quantity * (signal.target_profit_price - signal.trigger_price), 2
    )

    return {
        "symbol": signal.symbol,
        "sec_id": signal.sec_id,
        "quantity": quantity,
        "capital_allocated": cap,
        "entry_price": signal.trigger_price,
        "stop_loss_price": signal.stop_loss_price,
        "target_profit_price": signal.target_profit_price,
        "risk_per_share": signal.risk_per_share,
        "risk_reward_ratio": signal.risk_reward_ratio,
        "total_investment": total_investment,
        "max_risk_amount": max_risk_amount,
        "potential_profit_amount": potential_profit_amount,
    }
