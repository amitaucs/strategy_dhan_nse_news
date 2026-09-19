"""Unit tests for the shared Wick Filter utility."""

from scanner_dhan.scanner.wick_filter import (
    calculate_wick_percentages,
    check_candle_wick,
    get_wick_parameter,
)


def test_get_wick_parameter():
    param = get_wick_parameter(default="NA")
    assert param.name == "max_wick_pct"
    assert param.param_type == "select"
    assert param.default == "NA"
    assert len(param.options) == 5
    option_values = [opt["value"] for opt in param.options]
    assert "NA" in option_values
    assert "20" in option_values
    assert "30" in option_values
    assert "40" in option_values
    assert "50" in option_values


def test_calculate_wick_percentages():
    # Bullish candle: O=100, H=120, L=90, C=110 (Range=30)
    # Upper wick: 120 - 110 = 10 (10/30 = 33.33%)
    # Lower wick: 100 - 90 = 10 (10/30 = 33.33%)
    # Body: 110 - 100 = 10 (10/30 = 33.33%)
    upper, lower, body = calculate_wick_percentages(100.0, 120.0, 90.0, 110.0)
    assert round(upper, 1) == 33.3
    assert round(lower, 1) == 33.3
    assert round(body, 1) == 33.3

    # Strong bullish expansion: O=100, H=105, L=99, C=105 (Range=6)
    # Upper wick: 0
    # Lower wick: 1 (16.67%)
    # Body: 5 (83.33%)
    upper, lower, body = calculate_wick_percentages(100.0, 105.0, 99.0, 105.0)
    assert upper == 0.0
    assert round(lower, 1) == 16.7
    assert round(body, 1) == 83.3


def test_check_candle_wick_na():
    # If NA or disabled, always passes
    passed, pct = check_candle_wick(100, 150, 90, 105, is_bullish_setup=True, max_wick_pct_param="NA")
    assert passed is True
    assert pct == 0.0

    passed, pct = check_candle_wick(100, 150, 90, 105, is_bullish_setup=True, max_wick_pct_param=None)
    assert passed is True


def test_check_candle_wick_bullish_rejection():
    # Range = 100 (L=100, H=200). Open=110, Close=120.
    # Upper wick = 200 - 120 = 80 (80%) -> Severe rejection
    # Should FAIL 30% check
    passed, pct = check_candle_wick(110.0, 200.0, 100.0, 120.0, is_bullish_setup=True, max_wick_pct_param="30")
    assert passed is False
    assert pct == 80.0

    # Range = 100 (L=100, H=200). Open=110, Close=185.
    # Upper wick = 200 - 185 = 15 (15%) -> Clean close near high
    # Should PASS 30% and 20% check
    passed, pct = check_candle_wick(110.0, 200.0, 100.0, 185.0, is_bullish_setup=True, max_wick_pct_param="30")
    assert passed is True
    assert pct == 15.0


def test_check_candle_wick_bearish_rejection():
    # Range = 100 (L=100, H=200). Open=190, Close=180.
    # Lower wick = 180 - 100 = 80 (80%) -> Severe lower rejection
    # For a bearish setup (short), long lower wick is an opposing wick and should fail
    passed, pct = check_candle_wick(190.0, 200.0, 100.0, 180.0, is_bullish_setup=False, max_wick_pct_param="30")
    assert passed is False
    assert pct == 80.0

    # Bearish clean close near low: Open=190, Close=115, Low=100, High=200.
    # Lower wick = 115 - 100 = 15 (15%)
    passed, pct = check_candle_wick(190.0, 200.0, 100.0, 115.0, is_bullish_setup=False, max_wick_pct_param="30")
    assert passed is True
    assert pct == 15.0


def test_all_scanners_have_wick_parameter():
    """Verify that every single registered scanner in the system includes the max_wick_pct parameter."""
    from scanner_dhan.scanner import ScannerRegistry

    scanners = ScannerRegistry.list_all()
    assert len(scanners) >= 10, f"Expected at least 10 registered scanners, found {len(scanners)}"

    for sc in scanners:
        if sc["id"].startswith("mock_") or sc["id"].startswith("test_"):
            continue
        param_names = [p["name"] for p in sc["parameters"]]
        assert "max_wick_pct" in param_names, (
            f"Scanner '{sc['id']}' ({sc['name']}) is missing the 'max_wick_pct' parameter!"
        )
