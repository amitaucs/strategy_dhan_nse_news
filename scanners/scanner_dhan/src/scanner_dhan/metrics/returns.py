"""Portfolio return calculations."""

from collections.abc import Sequence

__all__ = ["maximum_drawdown", "total_return"]


def total_return(initial_equity: float, final_equity: float) -> float:
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    return (final_equity / initial_equity) - 1


def maximum_drawdown(equity_curve: Sequence[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, (equity / peak) - 1)
    return abs(drawdown)
