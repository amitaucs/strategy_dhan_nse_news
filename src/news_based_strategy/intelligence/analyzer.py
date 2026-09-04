"""Filing analysis engine powered by Google Gemini structured outputs."""

import logging
from typing import Optional
from news_based_strategy.core.models import FilingAudit
from news_based_strategy.intelligence.prompts import SYSTEM_PROMPT, build_announcement_prompt

logger = logging.getLogger(__name__)


class FilingAnalyzer:
    """Classifies corporate announcements using Gemini 3.7 Flash."""

    def __init__(self, api_key: str = "", model_name: str = "gemini-3.7-flash"):
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

        prompt = build_announcement_prompt(symbol=symbol, headline=headline, details=details)
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
            err_str = str(e)
            if "404" in err_str and "is no longer available" in err_str and self.model_name != "gemini-flash-latest":
                logger.warning("Model %s unavailable on this API key. Retrying with gemini-flash-latest...", self.model_name)
                try:
                    response = self.client.models.generate_content(
                        model="gemini-flash-latest",
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
                except Exception as inner_e:
                    logger.error("Fallback Gemini classification failed for %s: %s", symbol, inner_e)
                    return None

            logger.error("Gemini classification failed for %s: %s", symbol, e)
            return None


__all__ = ["FilingAnalyzer", "SYSTEM_PROMPT"]

