"""Data models and schemas for ST-14 Bullish CE Options Trading Strategy."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

__all__ = [
    "ExecutionMode",
    "ProductType",
    "OrderStatus",
    "St14OptionContract",
    "St14TradeSignal",
    "St14SuperOrderLevels",
    "St14StrategyConfig",
    "St14Position",
    "BreakoutWatchlistItem",
]


class ExecutionMode(str, Enum):
    """Trading execution environment mode."""

    VIRTUAL = "VIRTUAL"  # Simulated paper trading with live market ticks
    LIVE = "LIVE"        # Real capital execution on DhanHQ API


class ProductType(str, Enum):
    """Product type classification for F&O orders."""

    INTRADAY = "INTRADAY"  # MIS - Auto square-off at 15:00 IST
    DELIVERY = "DELIVERY"  # MARGIN / NORMAL - Positional carry-forward


class OrderStatus(str, Enum):
    """Lifecycle status for strategy signals and orders."""

    SCAN_QUALIFIED = "SCAN_QUALIFIED"      # Passed ST-14 5-rule filter
    WAITING_BREADTH = "WAITING_BREADTH"    # Waiting for Nifty + Bank Nifty Green
    WAITING_TRIGGER = "WAITING_TRIGGER"    # Waiting for LTP > H_breakout
    TRIGGERED = "TRIGGERED"                # Trigger condition met
    ORDER_PLACED = "ORDER_PLACED"          # Super order placed (Live or Virtual)
    ORDER_REJECTED = "ORDER_REJECTED"      # Order rejected by broker / risk manager
    POSITION_OPEN = "POSITION_OPEN"        # Position currently active
    POSITION_CLOSED = "POSITION_CLOSED"    # Position closed by TP, SL, or 3 PM square-off


@dataclass
class St14OptionContract:
    """Resolved 1-OTM Call Option Contract Metadata."""

    symbol: str
    underlying_symbol: str
    strike_price: float
    option_type: str = "CE"
    expiry_date: str = ""
    security_id: str = ""
    lot_size: int = 1
    ltp: float = 0.0
    is_next_month: bool = False
    is_synthetic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class St14SuperOrderLevels:
    """Calculated Super Order / Bracket Order price points for options."""

    entry_price: float
    target_price: float
    stop_loss_price: float
    target_pct: float = 40.0
    stop_loss_pct: float = 20.0
    trailing_jump: float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class St14TradeSignal:
    """Complete ST-14 trade candidate lifecycle container."""

    signal_id: str
    symbol: str
    underlying_sec_id: str
    underlying_ltp: float
    breakout_candle_high: float
    daily_ema20: float
    hourly_ema20: float
    vwap: float
    vwap_dist_pct: float
    vwap_angle_deg: float
    status: OrderStatus = OrderStatus.SCAN_QUALIFIED
    nifty_green: bool = False
    banknifty_green: bool = False
    is_confirmed: bool = False
    option_contract: Optional[St14OptionContract] = None
    order_levels: Optional[St14SuperOrderLevels] = None
    order_id: Optional[str] = None
    remarks: str = ""
    created_at_ist: str = field(
        default_factory=lambda: datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class St14Position:
    """Active option position tracked by the strategy engine."""

    position_id: str
    symbol: str
    option_symbol: str
    security_id: str
    quantity: int
    entry_price: float
    current_ltp: float
    target_price: float
    stop_loss_price: float
    product_type: ProductType
    mode: ExecutionMode
    entry_time_ist: str
    unrealized_pnl: float = 0.0
    pnl_pct: float = 0.0
    status: str = "OPEN"
    close_reason: Optional[str] = None
    exit_price: Optional[float] = None
    exit_time_ist: Optional[str] = None

    def update_pnl(self, live_ltp: float) -> None:
        self.current_ltp = live_ltp
        self.unrealized_pnl = round((self.current_ltp - self.entry_price) * self.quantity, 2)
        if self.entry_price > 0:
            self.pnl_pct = round(((self.current_ltp - self.entry_price) / self.entry_price) * 100.0, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["product_type"] = self.product_type.value
        d["mode"] = self.mode.value
        return d


@dataclass
class St14StrategyConfig:
    """Configuration and risk control settings for ST-14 Strategy."""

    enabled: bool = True
    status: str = "ACTIVE"
    mode: ExecutionMode = ExecutionMode.VIRTUAL
    auto_order: bool = True
    product_type: ProductType = ProductType.INTRADAY
    capital_per_trade: float = 25000.0
    target_profit_pct: float = 40.0       # 40% gain on Option Premium
    stop_loss_pct: float = 20.0           # 20% SL on Option Premium
    trailing_jump_pts: float = 2.0        # Trailing jump points
    trade_cutoff_time: str = "14:00"      # No new triggers after 14:00 IST
    square_off_time: str = "15:00"        # Auto square-off at 15:00 IST for Intraday
    max_open_positions: int = 5
    universe: str = "ALL_F_AND_O"
    vwap_min_dist_pct: float = -1.0
    vwap_max_dist_pct: float = 5.0
    require_rising_vwap: bool = True
    slippage_buffer_pct: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["product_type"] = self.product_type.value
        d["status"] = self.status
        d["auto_order"] = self.auto_order
        return d


@dataclass
class BreakoutWatchlistItem:
    """Watchlist candidate discovered by the 1-hour scanner, monitored every 5 minutes."""

    symbol: str
    security_id: str
    breakout_candle_high: float
    current_ltp: float
    distance_pct: float
    daily_ema20: float = 0.0
    hourly_ema20: float = 0.0
    vwap: float = 0.0
    status: OrderStatus = OrderStatus.WAITING_TRIGGER
    option_contract: Optional[St14OptionContract] = None
    order_levels: Optional[St14SuperOrderLevels] = None
    discovered_at_ist: str = ""
    last_checked_at_ist: str = ""
    order_id: Optional[str] = None
    remarks: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


