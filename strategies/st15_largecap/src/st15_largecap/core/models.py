"""Core data models for ST15_LargeCap Positional Momentum Strategy."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class SignalStatus(str, Enum):
    PENDING = "PENDING"
    TRIGGERED = "TRIGGERED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FALLEN = "FALLEN"
    INVALIDATED = "INVALIDATED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class Candle:
    """Standard OHLCV price candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_green(self) -> bool:
        return self.close >= self.open


@dataclass
class HeikinAshiCandle:
    """Heikin Ashi transformed candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    raw_candle: Optional[Candle] = None

    @property
    def is_green(self) -> bool:
        return self.close > self.open

    @property
    def is_red(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class IndicatorSnapshot:
    """Snapshot of technical indicator values for a specific candle."""
    timestamp: datetime
    ema_20: float
    ema_50: float
    ema_200: float
    supertrend: float
    is_supertrend_green: bool
    swing_low: float

    @property
    def is_ema_stacked_bullish(self) -> bool:
        """Confirms 20 EMA > 50 EMA > 200 EMA."""
        return self.ema_20 > self.ema_50 > self.ema_200


@dataclass
class SetupSignal:
    """A qualified ST15 trading setup signal."""
    symbol: str
    sec_id: str
    setup_time: datetime
    trigger_price: float      # High of Green HA confirmation candle
    stop_loss_price: float    # Swing low
    target_profit_price: float # 1:3 or 1:4 R:R target
    risk_per_share: float
    risk_reward_ratio: float
    ema_20: float
    ema_50: float
    ema_200: float
    supertrend: float
    ha_close: float = 0.0
    ha_open: float = 0.0
    nearest_ema_name: str = ""
    nearest_ema_dist_pct: float = 0.0
    status: SignalStatus = SignalStatus.PENDING
    invalidation_reason: str = ""

    @property
    def potential_profit_pct(self) -> float:
        if self.trigger_price <= 0:
            return 0.0
        return ((self.target_profit_price - self.trigger_price) / self.trigger_price) * 100

    @property
    def risk_pct(self) -> float:
        if self.trigger_price <= 0:
            return 0.0
        return ((self.trigger_price - self.stop_loss_price) / self.trigger_price) * 100


@dataclass
class Position:
    """Active or closed positional trading holding."""
    id: Optional[int]
    symbol: str
    sec_id: str
    quantity: int
    entry_price: float
    entry_time: datetime
    stop_loss: float
    target_price: float
    current_price: float
    product_type: str = "CNC"
    status: PositionStatus = PositionStatus.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    order_id: Optional[str] = None
    exit_order_id: Optional[str] = None
    remarks: str = ""

    @property
    def pnl(self) -> float:
        price = self.exit_price if self.status == PositionStatus.CLOSED and self.exit_price else self.current_price
        return (price - self.entry_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        price = self.exit_price if self.status == PositionStatus.CLOSED and self.exit_price else self.current_price
        return ((price - self.entry_price) / self.entry_price) * 100


@dataclass
class TradeOrder:
    """Record of an order dispatched to broker or simulated."""
    order_id: str
    symbol: str
    sec_id: str
    action: str               # BUY / SELL
    quantity: int
    entry_price: float
    stop_loss: float
    target_price: float
    product_type: str
    order_type: str           # BRACKET / FOREVER_OCO / LIMIT / MARKET
    status: str               # PLACED, REJECTED, SIMULATED, FILLED
    dry_run: bool
    placed_at: datetime
    remarks: str = ""


@dataclass
class ScanResult:
    """Result of scanning a single stock from the universe."""
    symbol: str
    sec_id: str
    ltp: float
    ema_20: float
    ema_50: float
    ema_200: float
    is_ema_stacked: bool
    is_in_dip: bool
    nearest_ema: str
    nearest_ema_dist_pct: float
    is_ha_green: bool
    is_supertrend_green: bool
    is_setup_ready: bool
    swing_low: float = 0.0
    signal: Optional[SetupSignal] = None
    candles_count: int = 0
    invalidation_reason: str = ""
    scanned_at: datetime = field(default_factory=datetime.now)

