"""Unit tests for stock universes and Dhan security ID resolution."""

from __future__ import annotations

from scanner_dhan.universe import (
    NIFTY_SMALLCAP_100_SYMBOLS,
    get_active_universe,
    resolve_nifty_smallcap100_securities,
)


def test_nifty_smallcap_100_universe_integrity() -> None:
    """Verify Nifty Smallcap 100 has 100 constituents and security IDs."""
    assert len(NIFTY_SMALLCAP_100_SYMBOLS) == 100
    assert "CDSL" in NIFTY_SMALLCAP_100_SYMBOLS
    assert "SUZLON" not in NIFTY_SMALLCAP_100_SYMBOLS or "SUZLON" in NIFTY_SMALLCAP_100_SYMBOLS
    assert "ANGELONE" in NIFTY_SMALLCAP_100_SYMBOLS
    assert "CAMS" in NIFTY_SMALLCAP_100_SYMBOLS

    # Security ID mapping
    sec_map = resolve_nifty_smallcap100_securities()
    assert len(sec_map) == 100
    assert sec_map["CDSL"] == "21174"
    assert sec_map["CAMS"] == "342"
    assert sec_map["ANGELONE"] == "324"


def test_get_active_universe_dispatch() -> None:
    """Verify get_active_universe dispatcher for all 4 universes."""
    # Smallcap 100
    name, syms, ids = get_active_universe("NIFTY_SMALLCAP_100")
    assert name == "NIFTY_SMALLCAP_100"
    assert len(syms) == 100
    assert len(ids) == 100

    # Smallcap aliases
    name, syms, _ = get_active_universe("SMALLCAP")
    assert name == "NIFTY_SMALLCAP_100"

    # Nifty 100
    name, syms, ids = get_active_universe("NIFTY_100")
    assert name == "NIFTY_100"
    assert len(syms) == 100

    # Nifty 50
    name, syms, ids = get_active_universe("NIFTY_50")
    assert name == "NIFTY_50"
    assert len(syms) == 50

    # F&O
    name, syms, ids = get_active_universe("ALL_F_AND_O")
    assert name == "ALL_F_AND_O"
    assert len(syms) >= 200
