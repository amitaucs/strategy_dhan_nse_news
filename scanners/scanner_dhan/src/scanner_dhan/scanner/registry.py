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

    @classmethod
    def register(cls, scanner: BaseScanner | type[BaseScanner]) -> None:
        """Register a scanner instance or class."""
        instance = scanner() if isinstance(scanner, type) else scanner
        cls._scanners[instance.id] = instance
        logger.info("Registered scanner: %s (%s)", instance.name, instance.id)

    @classmethod
    def get(cls, scanner_id: str) -> BaseScanner | None:
        """Retrieve a registered scanner by ID."""
        return cls._scanners.get(scanner_id)

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
