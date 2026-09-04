"""Core domain models for news filings, AI audits, and trade signals."""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

try:
    from pydantic import BaseModel, Field

    class FilingAudit(BaseModel):
        """Pydantic schema for deterministic LLM output."""

        sentiment: str = Field(description="'BULLISH', 'BEARISH', or 'NEUTRAL'")
        confidence: int = Field(description="Score between 0 and 100")
        catalyst_type: str = Field(
            description="e.g. ORDER_WIN, EARNINGS_BEAT, RESIGNATION, PENALTY, BOARD_OUTCOME, ACQUISITION, REGULATORY_APPROVAL"
        )
        material_impact: bool = Field(description="True if this is likely to move the price by >= 1.5% rapidly")
        summary: str = Field(description="1-sentence plain english reason")

except ImportError:
    @dataclass
    class FilingAudit:  # type: ignore[no-redef]
        """Fallback dataclass for FilingAudit when pydantic is unavailable."""

        sentiment: str
        confidence: int
        catalyst_type: str
        material_impact: bool
        summary: str

        def model_dump(self) -> dict:
            return asdict(self)


@dataclass
class Announcement:
    """Represents a corporate announcement disclosure from NSE."""

    seq_id: str
    symbol: str
    desc: str
    details: str
    an_dt: str
    attmnt_file: Optional[str] = None
    extracted_text: Optional[str] = None
    extraction_error: Optional[str] = None
    is_fno: bool = False
    raw_data: Optional[dict] = None
    created_at: str = datetime.now().isoformat()

    @property
    def attachment_url(self) -> Optional[str]:
        """Full URL to the attachment on NSE archives if present."""
        if not self.attmnt_file:
            return None
        clean = self.attmnt_file.strip()
        if clean in ("-", "--", "NA", "N/A", "null", "none", ""):
            return None
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        return f"https://nsearchives.nseindia.com/corporate/{clean}"


    @property
    def clean_content(self) -> str:
        """The most informative text available for this announcement."""
        if self.extracted_text and len(self.extracted_text.strip()) > 30:
            return self.extracted_text.strip()
        if self.details and len(self.details.strip()) > 10:
            return self.details.strip()
        return self.desc.strip()

    @property
    def llm_payload(self) -> str:
        """The exact prompt payload prepared for the LLM evaluation."""
        lines = [
            f"TICKER: {self.symbol}",
            f"EXCHANGE TIMESTAMP: {self.an_dt or 'N/A'}",
            f"HEADLINE: {self.desc or 'N/A'}",
        ]
        if self.details:
            lines.append(f"FILED DETAILS: {self.details}")
        if self.attachment_url:
            lines.append(f"ATTACHMENT URL: {self.attachment_url}")

        if self.extracted_text:
            lines.append("\nEXTRACTED LETTER CONTENT:")
            lines.append(self.extracted_text.strip())
        elif self.extraction_error:
            lines.append(f"\nATTACHMENT STATUS: [{self.extraction_error}]")

        return "\n".join(lines)

    def get_age_seconds(self, reference_time: Optional[datetime] = None) -> Optional[float]:
        """Compute the elapsed latency in seconds since exchange broadcast."""
        if not self.an_dt:
            return None
        from news_based_strategy.execution.risk import RiskManager
        _, age = RiskManager.is_news_fresh(self.an_dt, max_age_seconds=999999, reference_time=reference_time)
        return age

    def freshness_badge(self, max_age_seconds: int = 180, reference_time: Optional[datetime] = None) -> str:
        """Format latency status indicator for console display."""
        age = self.get_age_seconds(reference_time=reference_time)
        if age is None:
            return ""
        age_int = int(round(age))
        if max_age_seconds <= 0 or age <= max_age_seconds:
            return f"(⏱️ Latency: {age_int}s | ⚡ Fresh)"
        return f"(⏱️ Latency: {age_int}s | ⚠️ STALE > {max_age_seconds}s)"

    @property
    def formatted_summary(self) -> str:
        """Single-line summary for logging or console display."""
        content_preview = self.clean_content.replace("\n", " ")[:120]
        fno_tag = " [F&O]" if self.is_fno else ""
        return f"[{self.an_dt}] [{self.symbol}{fno_tag}] {self.desc} | {content_preview}"

    def to_dict(self) -> dict:
        """Convert dataclass to dictionary."""
        return asdict(self)


@dataclass
class TradeSignal:
    """Actionable trading signal produced by evaluating an announcement."""

    symbol: str
    security_id: str
    action: str  # "BUY" or "SELL"
    product_type: str  # "INTRADAY" or "CNC"
    confidence: int
    catalyst_type: str
    summary: str
    exchange_time: Optional[str] = None
    created_at: str = datetime.now().isoformat()



@dataclass
class TradeResult:
    """Result of an order execution attempt."""

    success: bool
    symbol: str
    action: str
    quantity: int
    product_type: str
    order_id: Optional[str] = None
    remarks: Optional[str] = None
    dry_run: bool = False
    timestamp: str = datetime.now().isoformat()


__all__ = ["FilingAudit", "Announcement", "TradeSignal", "TradeResult"]
