"""Minimal event-driven portfolio simulator."""

from dataclasses import dataclass

from scanner_dhan.config import BacktestConfig
from scanner_dhan.models import Bar, SignalType
from scanner_dhan.strategies import Strategy

__all__ = ["BacktestEngine", "BacktestResult"]


@dataclass(frozen=True, slots=True)
class BacktestResult:
    initial_cash: float
    final_equity: float
    total_return: float
    trade_count: int


class BacktestEngine:
    """Execute all-in-cash signals against bar closing prices."""

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config

    def run(self, bars: list[Bar], strategy: Strategy) -> BacktestResult:
        cash = self._config.initial_cash
        positions: dict[str, int] = {}
        last_prices: dict[str, float] = {}
        trade_count = 0

        for bar in sorted(bars, key=lambda item: item.timestamp):
            if not self._config.start_date <= bar.timestamp.date() <= self._config.end_date:
                continue
            last_prices[bar.symbol] = bar.close
            signal = strategy.on_bar(bar)
            if signal is None or signal.action is SignalType.HOLD:
                continue

            signed_quantity = (
                signal.quantity if signal.action is SignalType.BUY else -signal.quantity
            )
            current_quantity = positions.get(signal.symbol, 0)
            if current_quantity + signed_quantity < 0:
                continue

            slippage_direction = 1 if signed_quantity > 0 else -1
            price = bar.close * (1 + self._config.slippage_rate * slippage_direction)
            notional = price * abs(signed_quantity)
            commission = notional * self._config.commission_rate
            cash_change = -(price * signed_quantity) - commission
            if cash + cash_change < 0:
                continue

            cash += cash_change
            positions[signal.symbol] = current_quantity + signed_quantity
            trade_count += 1

        final_equity = cash + sum(
            quantity * last_prices.get(symbol, 0.0) for symbol, quantity in positions.items()
        )
        return BacktestResult(
            initial_cash=self._config.initial_cash,
            final_equity=final_equity,
            total_return=(final_equity / self._config.initial_cash) - 1,
            trade_count=trade_count,
        )
