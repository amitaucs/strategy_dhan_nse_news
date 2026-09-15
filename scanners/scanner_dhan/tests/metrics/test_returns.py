import pytest

from scanner_dhan.metrics import maximum_drawdown, total_return


def test_total_return() -> None:
    assert total_return(100.0, 125.0) == pytest.approx(0.25)


def test_maximum_drawdown() -> None:
    assert maximum_drawdown([100.0, 120.0, 90.0, 110.0]) == pytest.approx(0.25)
