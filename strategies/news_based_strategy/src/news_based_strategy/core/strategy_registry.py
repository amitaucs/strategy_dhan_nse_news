"""Modular Strategy Registry for Multi-Strategy Trading Terminal."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class StrategyMetadata:
    """Metadata descriptor for an execution strategy."""
    id: str
    code: str
    name: str
    category: str
    category_label: str
    description: str
    timeframe: str
    universe: str
    risk_level: str
    status: str  # ACTIVE, READY, CONFIGURED, PAUSED
    execution_mode: str  # VIRTUAL, LIVE
    auto_order_supported: bool
    auto_order_enabled: bool
    icon: str
    badge_color: str
    metrics: Dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


class StrategyRegistry:
    """Catalog and discovery registry for quantitative trading strategies."""

    _strategies: Dict[str, StrategyMetadata] = {}

    @classmethod
    def initialize_defaults(cls) -> None:
        """Populate standard registered strategies."""
        cls._strategies = {
            "st_news": StrategyMetadata(
                id="st_news",
                code="ST-NEWS",
                name="NSE Catalyst News Engine",
                category="event_news",
                category_label="Event & News",
                description="Real-time NSE corporate filing NLP intelligence with Gemini Flash classification and automated bracket execution.",
                timeframe="Real-time (Tick-to-Trade)",
                universe="NSE Equity / F&O Universe (215+ Stocks)",
                risk_level="Dynamic (1% SL / 3% TP Bracket)",
                status="ACTIVE",
                execution_mode="VIRTUAL",
                auto_order_supported=True,
                auto_order_enabled=True,
                icon="📰",
                badge_color="emerald",
                metrics={
                    "signals_today": 0,
                    "orders_placed": 0,
                    "win_rate_pct": 100.0,
                    "allocated_capital": 20000.0,
                },
            ),
            "st15_largecap": StrategyMetadata(
                id="st15_largecap",
                code="ST-15",
                name="NIFTY 200 LargeCap Momentum",
                category="trend_momentum",
                category_label="Trend & Momentum",
                description="Multi-timeframe Heikin-Ashi EMA momentum strategy with dynamic trailing stop-loss on Nifty 200 leaders.",
                timeframe="15m / Daily Heikin-Ashi",
                universe="NIFTY 200 LargeCap Universe",
                risk_level="Moderate (1.5% SL / 4.5% TP)",
                status="READY",
                execution_mode="VIRTUAL",
                auto_order_supported=True,
                auto_order_enabled=False,
                icon="📈",
                badge_color="blue",
                metrics={
                    "signals_today": 0,
                    "orders_placed": 0,
                    "win_rate_pct": 78.5,
                    "allocated_capital": 50000.0,
                },
            ),
            "st08_ath": StrategyMetadata(
                id="st08_ath",
                code="ST-08",
                name="Monthly ATH Breakout Execution",
                category="breakouts",
                category_label="Breakouts",
                description="Identifies multi-year and All-Time High price breakouts with volume multiplier surge and pullback entry validation.",
                timeframe="Daily / Monthly Candlestick",
                universe="NIFTY 500 High Volume Equities",
                risk_level="Aggressive (2% SL / 6% TP)",
                status="CONFIGURED",
                execution_mode="VIRTUAL",
                auto_order_supported=True,
                auto_order_enabled=False,
                icon="🚀",
                badge_color="violet",
                metrics={
                    "signals_today": 0,
                    "orders_placed": 0,
                    "win_rate_pct": 72.0,
                    "allocated_capital": 30000.0,
                },
            ),
            "st01_ha_reversal": StrategyMetadata(
                id="st01_ha_reversal",
                code="ST-01",
                name="Heikin-Ashi Intraday Reversal",
                category="reversals",
                category_label="Reversals",
                description="Exploits intraday color transitions on smoothed Heikin-Ashi candles near key moving average support/resistance zones.",
                timeframe="5m / 15m Intraday",
                universe="NSE Top 50 Liquid F&O Stocks",
                risk_level="Controlled (0.8% SL / 2.0% TP)",
                status="CONFIGURED",
                execution_mode="VIRTUAL",
                auto_order_supported=True,
                auto_order_enabled=False,
                icon="🔄",
                badge_color="amber",
                metrics={
                    "signals_today": 0,
                    "orders_placed": 0,
                    "win_rate_pct": 69.4,
                    "allocated_capital": 25000.0,
                },
            ),
            "st_order_block": StrategyMetadata(
                id="st_order_block",
                code="ST-OB",
                name="Smart Money Order Block",
                category="smart_money",
                category_label="Smart Money",
                description="Institutional order block mitigation and liquidity sweep strategy with tight stop loss and asymmetric risk-reward.",
                timeframe="15m / 1h Price Action",
                universe="NIFTY 50 & Major Banking Sector",
                risk_level="High Precision (1:3+ R:R)",
                status="CONFIGURED",
                execution_mode="VIRTUAL",
                auto_order_supported=True,
                auto_order_enabled=False,
                icon="🏦",
                badge_color="cyan",
                metrics={
                    "signals_today": 0,
                    "orders_placed": 0,
                    "win_rate_pct": 74.2,
                    "allocated_capital": 40000.0,
                },
            ),
            "st14_bullish_ce": StrategyMetadata(
                id="st14_bullish_ce",
                code="ST-14",
                name="Bullish CE Intraday Setup",
                category="options_intraday",
                category_label="Options & Intraday",
                description="Daily trend alignment (Close > 20 SMA, Close > 5D High, RSI > 60) with 1-Hour momentum breakouts and post-10:15 AM execution.",
                timeframe="Daily + 1H Intraday",
                universe="NSE F&O Underlying Equities (228 Stocks)",
                risk_level="High Conviction (1.2% SL / 3.6% TP)",
                status="CONFIGURED",
                execution_mode="VIRTUAL",
                auto_order_supported=True,
                auto_order_enabled=False,
                icon="⚡",
                badge_color="emerald",
                metrics={
                    "signals_today": 0,
                    "orders_placed": 0,
                    "win_rate_pct": 76.8,
                    "allocated_capital": 35000.0,
                },
            ),
        }

    @classmethod
    def list_all(cls) -> List[dict]:
        """Return list of all registered strategies as dictionaries."""
        if not cls._strategies:
            cls.initialize_defaults()
        return [s.to_dict() for s in cls._strategies.values()]

    @classmethod
    def get(cls, strategy_id: str) -> Optional[StrategyMetadata]:
        """Get strategy metadata by ID."""
        if not cls._strategies:
            cls.initialize_defaults()
        return cls._strategies.get(strategy_id)

    @classmethod
    def update_metrics(cls, strategy_id: str, updates: Dict[str, Any]) -> None:
        """Update live telemetry metrics for a strategy."""
        strat = cls.get(strategy_id)
        if strat:
            strat.metrics.update(updates)

    @classmethod
    def update_status(cls, strategy_id: str, status: str) -> None:
        """Update operational status for a strategy (e.g. ACTIVE, PAUSED, READY)."""
        strat = cls.get(strategy_id)
        if strat:
            strat.status = status


# Auto-initialize on import
StrategyRegistry.initialize_defaults()

__all__ = ["StrategyMetadata", "StrategyRegistry"]

