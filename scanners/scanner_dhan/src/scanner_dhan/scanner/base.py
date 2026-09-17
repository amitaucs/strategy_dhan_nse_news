"""Base Scanner Contract, Parameter Definitions, and Report Models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from scanner_dhan.data.dhan_provider import DhanDataProvider

__all__ = ["ScannerParameter", "BaseScanner", "ScanReport"]


@dataclass(frozen=True, slots=True)
class ScannerParameter:
    """Definition of a tunable parameter for a scanner."""

    name: str
    label: str
    param_type: str  # "float", "int", "select", "bool"
    default: Any
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    options: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.param_type,
            "default": self.default,
            "description": self.description,
            "min": self.min_value,
            "max": self.max_value,
            "step": self.step,
            "options": self.options,
        }


@dataclass(frozen=True)
class ScanReport:
    """Consolidated report of a trading scan."""

    timestamp: datetime
    scanner_id: str
    scanner_name: str
    total_scanned: int
    matched_count: int
    results: list[Any]
    status: str = "success"  # "success" or "error"
    error_message: str | None = None
    error_type: str | None = None
    error_title: str | None = None
    action_url: str | None = None
    action_label: str | None = None

    @property
    def at_support_count(self) -> int:
        return self.matched_count

    def to_dataframe(self, only_matched: bool = False) -> pd.DataFrame:
        """Convert results to a pandas DataFrame."""
        rows = []
        for r in self.results:
            is_matched = getattr(r, "is_at_support", False)
            if only_matched and not is_matched:
                continue

            nearest_support = getattr(r, "nearest_support", None)
            supp_desc = nearest_support.description if nearest_support else "N/A"
            supp_price = nearest_support.price if nearest_support else None
            supp_type = (
                nearest_support.level_type.value
                if nearest_support and hasattr(nearest_support.level_type, "value")
                else ("N/A" if not nearest_support else str(nearest_support.level_type))
            )

            rows.append(
                {
                    "Symbol": r.symbol,
                    "LTP": r.ltp,
                    "Key Level Price": supp_price,
                    "Level Type": supp_type,
                    "Description": supp_desc,
                    "Distance (%)": getattr(r, "distance_pct", 0.0),
                    "Matched": "YES" if is_matched else "NO",
                    "RSI (14)": getattr(r, "rsi", None),
                    "Candle Signal": getattr(r, "candle_signal", ""),
                }
            )
        return pd.DataFrame(rows)

    def to_dict(self) -> dict[str, Any]:
        """Convert full report to JSON-serializable dictionary."""
        return {
            "status": self.status,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "error_title": self.error_title,
            "action_url": self.action_url,
            "action_label": self.action_label,
            "timestamp": self.timestamp.isoformat(),
            "scanner_id": self.scanner_id,
            "scanner_name": self.scanner_name,
            "total_scanned": self.total_scanned,
            "matched_count": self.matched_count,
            "results": [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in self.results],
        }

    def to_cli_table(self, only_at_support: bool = False) -> str:
        """Format scan results as a clean ASCII table."""
        items = [
            r for r in self.results if not only_at_support or getattr(r, "is_at_support", False)
        ]

        if not items:
            return "No stocks currently matching scanner criteria."

        time_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        header = (
            f"\n{'=' * 96}\n"
            f"  {self.scanner_name.upper()} REPORT — {time_str}\n"
            f"  Total Scanned: {self.total_scanned} | Matched Criteria: {self.matched_count}\n"
            f"{'=' * 96}\n"
            f"{'Symbol':<12} {'LTP (₹)':<10} {'Key Level (₹)':<14} "
            f"{'Distance (%)':<14} {'Level Type / Desc':<26} {'RSI':<6} {'Signal':<16}\n"
            f"{'-' * 96}"
        )

        lines = [header]
        for r in items:
            nearest_support = getattr(r, "nearest_support", None)
            supp_price_str = f"{nearest_support.price:,.2f}" if nearest_support else "N/A"
            supp_desc = nearest_support.description if nearest_support else "None"
            rsi_val = getattr(r, "rsi", None)
            rsi_str = f"{rsi_val:.1f}" if rsi_val is not None else "-"
            dist_pct = getattr(r, "distance_pct", 0.0)
            dist_str = f"{dist_pct:+.2f}%"
            is_matched = getattr(r, "is_at_support", False)
            marker = "🟢" if is_matched else "  "
            candle_sig = getattr(r, "candle_signal", "")

            lines.append(
                f"{marker}{r.symbol:<10} {r.ltp:<10,.2f} {supp_price_str:<14} "
                f"{dist_str:<14} {supp_desc:<26} {rsi_str:<6} {candle_sig:<16}"
            )

        lines.append("=" * 96)
        return "\n".join(lines)


class BaseScanner(ABC):
    """Abstract base class that all trading scanners must implement."""

    id: str
    name: str
    description: str
    category: str
    icon: str = "activity"  # Lucide icon name
    parameters: list[ScannerParameter] = []

    @abstractmethod
    def run(
        self,
        params: dict[str, Any] | None = None,
        provider: DhanDataProvider | None = None,
    ) -> ScanReport:
        """Execute the scanner with the specified parameters."""
        ...

    def get_metadata(self) -> dict[str, Any]:
        """Return scanner metadata for UI display."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "parameters": [p.to_dict() for p in self.parameters],
        }
