"""Central Scanner Registry for dynamic discovery and execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scanner_dhan.data.dhan_provider import DhanDataProvider
    from scanner_dhan.scanner.base import BaseScanner, ScanReport

logger = logging.getLogger(__name__)

__all__ = ["ScannerRegistry", "register_scanner"]


class ScannerRegistry:
    """Registry holding all available trading scanners."""

    _scanners: dict[str, BaseScanner] = {}
    _aliases: dict[str, str] = {
        "vcp_scanner": "vcp_contraction",
        "vcp_breakout": "vcp_contraction",
        "vcp": "vcp_contraction",
        "vcp_pattern": "vcp_contraction",
        "ath_breakout": "monthly_ath_breakout",
        "monthly_ath": "monthly_ath_breakout",
        "st08": "monthly_ath_breakout",
        "fvg_fib": "fvg_fibonacci",
        "fvg_scanner": "fvg_fibonacci",
        "head_shoulders": "head_and_shoulders",
        "hns": "head_and_shoulders",
        "head_and_shoulder": "head_and_shoulders",
        "st01": "ha_st01_reversal",
        "ha_st01": "ha_st01_reversal",
        "st07": "monthly_ha_89ema",
        "ha_89ema": "monthly_ha_89ema",
        "st14": "st14_bullish_ce",
        "bullish_ce": "st14_bullish_ce",
        "st15": "ha_ema_pullback",
        "largecap_ema": "ha_ema_pullback",
    }

    @classmethod
    def register(cls, scanner: BaseScanner | type[BaseScanner]) -> None:
        """Register a scanner instance or class."""
        instance = scanner() if isinstance(scanner, type) else scanner
        cls._scanners[instance.id] = instance
        logger.info("Registered scanner: %s (%s)", instance.name, instance.id)

    @classmethod
    def get(cls, scanner_id: str) -> BaseScanner | None:
        """Retrieve a registered scanner by ID with alias fallback."""
        if not scanner_id:
            return None
        norm_id = scanner_id.strip().lower()
        if norm_id in cls._scanners:
            return cls._scanners[norm_id]
        if norm_id in cls._aliases:
            target_id = cls._aliases[norm_id]
            return cls._scanners.get(target_id)
        # Check if scanner_id starts with or matches after stripping prefix/suffix
        for registered_id, scanner in cls._scanners.items():
            if norm_id == registered_id or norm_id.replace("-", "_") == registered_id:
                return scanner
        return None

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        """List metadata for all registered scanners."""
        return [s.get_metadata() for s in cls._scanners.values()]

    @classmethod
    def run(
        cls,
        scanner_id: str,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        """Run a scanner by ID with parameters."""
        scanner = cls.get(scanner_id)
        if not scanner:
            raise KeyError(f"Scanner '{scanner_id}' not found in registry")
        return scanner.run(params=params, provider=provider)


def register_scanner(cls: type[BaseScanner]) -> type[BaseScanner]:
    """Class decorator to register a scanner with ScannerRegistry."""
    ScannerRegistry.register(cls)
    return cls
