from datetime import date, datetime

import pytest

from scanner_dhan import (
    BacktestConfig,
    BacktestEngine,
    Bar,
    Signal,
    SignalType,
    Strategy,
)


class BuyOnce(Strategy):
    def __init__(self) -> None:
        self._has_bought = False

    def on_bar(self, bar: Bar) -> Signal | None:
        if self._has_bought:
            return None
        self._has_bought = True
        return Signal(bar.timestamp, bar.symbol, SignalType.BUY, quantity=1)


def test_engine_marks_open_position_to_final_price() -> None:
    bars = [
        Bar(datetime(2025, 1, 1), "TEST", 100, 101, 99, 100, 1_000),
        Bar(datetime(2025, 1, 2), "TEST", 110, 111, 109, 110, 1_000),
    ]
    config = BacktestConfig(date(2025, 1, 1), date(2025, 1, 2), initial_cash=1_000)

    result = BacktestEngine(config).run(bars, BuyOnce())

    assert result.final_equity == pytest.approx(1_010)
    assert result.total_return == pytest.approx(0.01)
    assert result.trade_count == 1
