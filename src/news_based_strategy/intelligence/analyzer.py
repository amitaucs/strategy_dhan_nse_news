"""Filing analysis engine powered by Google Gemini structured outputs."""

import logging
from typing import Optional
from news_based_strategy.core.models import FilingAudit

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior quantitative equity trader analyzing real-time Indian stock exchange (NSE/BSE) corporate disclosures.
Evaluate the immediate price impact of the disclosure.

Guidelines:
1. Ignore routine administrative filings (e.g. standard trading window closures, routine share transfers, investor meet intimations, secretarial compliance). Mark these NEUTRAL with confidence 90-100 and material_impact=False.
2. Identify high-impact catalysts:
   - BULLISH: Large unexpected order/contract wins (>= 10% annual revenue), massive dividend hikes, stellar earnings surprises, promoter stake hikes, key drug approvals.
   - BEARISH: Severe regulatory bans or penalties, auditor resignations, forensic accounting probes, huge earnings miss, promoter pledge invocation, management fraud.
   - NEUTRAL: Expected outcomes, minor fines, non-binding MoUs.
3. material_impact MUST be True ONLY if this filing is likely to move the stock price by >= 1.5% rapidly within the trading session.
4. Keep the summary concise (exactly 1 sentence).
"""


class FilingAnalyzer:
    """Classifies corporate announcements using Gemini 3.6 Flash."""

    def __init__(self, api_key: str = "", model_name: str = "gemini-3.6-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Google GenAI client if package is available and API key is present."""
        if not self.api_key:
            logger.debug("Gemini API key is not set. Analyzer operates in fallback mode.")
            return

        try:
            from google import genai

            self.client = genai.Client(api_key=self.api_key)
        except ImportError:
            logger.warning("google-genai package is not installed.")
            self.client = None

    def audit(self, symbol: str, headline: str, details: str = "") -> Optional[FilingAudit]:
        """Send filing text to Gemini for structured classification."""
        if not self.client:
            return FilingAudit(
                sentiment="NEUTRAL",
                confidence=50,
                catalyst_type="UNCLASSIFIED",
                material_impact=False,
                summary=f"Analysis placeholder for {symbol}: {headline[:80]}",
            )

        prompt = f"""
{SYSTEM_PROMPT}

TICKER: {symbol}
ANNOUNCEMENT TITLE: {headline}
FILING TEXT / DETAILS: {details}
"""
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FilingAudit,
                    temperature=0.0,
                ),
            )
            if hasattr(response, "parsed") and response.parsed:
                return response.parsed
            return FilingAudit.model_validate_json(response.text)
        except Exception as e:
            logger.error("Gemini classification failed for %s: %s", symbol, e)
            return None


__all__ = ["FilingAnalyzer", "SYSTEM_PROMPT"]

