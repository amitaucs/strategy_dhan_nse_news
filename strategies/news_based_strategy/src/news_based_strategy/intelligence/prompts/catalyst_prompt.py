"""System and user prompt templates for corporate disclosure evaluation."""

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


def build_announcement_prompt(symbol: str, headline: str, details: str = "") -> str:
    """Build the full prompt payload for an announcement.

    Args:
        symbol: Stock ticker (e.g. BEL, TATAMOTORS).
        headline: Main announcement description.
        details: Clean filed details or extracted PDF text.

    Returns:
        Formatted prompt string.
    """
    return f"""
{SYSTEM_PROMPT}

TICKER: {symbol}
ANNOUNCEMENT TITLE: {headline}
FILING TEXT / DETAILS: {details}
"""


__all__ = ["SYSTEM_PROMPT", "build_announcement_prompt"]

