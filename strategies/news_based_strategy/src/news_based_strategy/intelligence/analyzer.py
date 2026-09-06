"""Filing analysis engine powered by Google Gemini structured outputs."""

import logging
from typing import Optional
from news_based_strategy.core.models import FilingAudit
from news_based_strategy.intelligence.prompts import SYSTEM_PROMPT, build_announcement_prompt

logger = logging.getLogger(__name__)


class FilingAnalyzer:
    """Classifies corporate announcements using Gemini 3.1 Flash Lite."""

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "gemini-3.1-flash-lite",
        thinking_budget: int = 0,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.thinking_budget = thinking_budget
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
                    thinking_config=types.ThinkingConfig(thinking_budget=self.thinking_budget),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            if hasattr(response, "parsed") and response.parsed:
                return response.parsed
            return FilingAudit.model_validate_json(response.text)
        except Exception as e:
            err_str = str(e)
            if ("404" in err_str or "no longer available" in err_str or "NOT_FOUND" in err_str) and self.model_name != "gemini-3.1-flash-lite":
                logger.warning("Model %s unavailable on this API key. Retrying with gemini-3.1-flash-lite...", self.model_name)
                try:
                    response = self.client.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=[prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=FilingAudit,
                            temperature=0.0,
                            thinking_config=types.ThinkingConfig(thinking_budget=self.thinking_budget),
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
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

