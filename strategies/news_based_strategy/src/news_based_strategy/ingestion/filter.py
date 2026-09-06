"""Pre-LLM noise filtering engine to discard routine compliance disclosures."""

import re
from typing import List, Optional, Pattern, Tuple

# Categorized regular expressions matching non-material administrative filings
CATEGORIZED_NOISE_PATTERNS: List[tuple[str, List[Pattern]]] = [
    (
        "Trading Window",
        [
            re.compile(r"trading\s+window\s+(closure|closed|open|re-open)", re.IGNORECASE),
            re.compile(r"intimation\s+of\s+trading\s+window", re.IGNORECASE),
            re.compile(r"closure\s+of\s+trading\s+window", re.IGNORECASE),
        ],
    ),
    (
        "Share Certificate / Demat",
        [
            re.compile(r"loss\s+of\s+(share\s+)?certificate", re.IGNORECASE),
            re.compile(r"duplicate\s+(share\s+)?certificate", re.IGNORECASE),
            re.compile(r"issue\s+of\s+duplicate", re.IGNORECASE),
            re.compile(r"regulation\s+39\s*\(\s*3\s*\)", re.IGNORECASE),
            re.compile(r"regulation\s+74\s*\(\s*5\s*\)", re.IGNORECASE),
            re.compile(r"demat(erialisation)?\s+of\s+shares", re.IGNORECASE),
        ],
    ),
    (
        "Newspaper Publication",
        [
            re.compile(r"newspaper\s+(publication|advertisement|clipping)", re.IGNORECASE),
            re.compile(r"published\s+in\s+newspaper", re.IGNORECASE),
            re.compile(r"extract\s+of\s+(un-?audited|audited)\s+financial\s+results\s+in\s+newspaper", re.IGNORECASE),
        ],
    ),
    (
        "Analyst Meet / Earnings Call Schedule",
        [
            re.compile(r"schedule\s+of\s+(analyst|institutional\s+investor|investor\s+meet|meet)", re.IGNORECASE),
            re.compile(r"intimation\s+of\s+(analyst|investor\s+meet|schedule\s+of\s+meet)", re.IGNORECASE),
            re.compile(r"analysts?(\s*/\s*institutional\s+investor)?\s+meet", re.IGNORECASE),
            re.compile(r"investor\s+meet(\s*/\s*con\.\s*call)?\s+updates", re.IGNORECASE),
            re.compile(r"con(\.|\s+)?call\s+updates", re.IGNORECASE),
            re.compile(r"audio\s+recording\s+of\s+investor", re.IGNORECASE),
            re.compile(r"transcript\s+of\s+(earnings|conference|analyst)", re.IGNORECASE),
            re.compile(r"investor\s+(presentation|meet)", re.IGNORECASE),
        ],
    ),
    (
        "AGM / Administrative Update",
        [
            re.compile(r"change\s+in\s+(registered\s+office|email|website|contact\s+details)", re.IGNORECASE),
            re.compile(r"closure\s+of\s+register\s+of\s+members", re.IGNORECASE),
            re.compile(r"book\s+closure", re.IGNORECASE),
            re.compile(r"notice\s+of\s+annual\s+general\s+meeting", re.IGNORECASE),
            re.compile(r"shareholders\s+meeting", re.IGNORECASE),
            re.compile(r"intimation\s+of\s+agm", re.IGNORECASE),
            re.compile(r"notice\s+of\s+(the\s+)?agm", re.IGNORECASE),
            re.compile(r"postal\s+ballot\s+notice", re.IGNORECASE),
            re.compile(r"e-?voting\s+results", re.IGNORECASE),
            re.compile(r"scrutinizer('?s)?\s+report", re.IGNORECASE),
            re.compile(r"regulation\s+44", re.IGNORECASE),
        ],
    ),
    (
        "Routine Periodic Compliance / Secretarial",
        [
            re.compile(r"corporate\s+governance\s+report", re.IGNORECASE),
            re.compile(r"regulation\s+27\s*\(\s*2\s*\)", re.IGNORECASE),
            re.compile(r"shareholding\s+pattern", re.IGNORECASE),
            re.compile(r"regulation\s+31", re.IGNORECASE),
            re.compile(r"secretarial\s+compliance\s+report", re.IGNORECASE),
            re.compile(r"regulation\s+24a", re.IGNORECASE),
            re.compile(r"reconciliation\s+of\s+share\s+capital\s+audit", re.IGNORECASE),
            re.compile(r"regulation\s+76", re.IGNORECASE),
            re.compile(r"statement\s+of\s+deviation", re.IGNORECASE),
            re.compile(r"regulation\s+32", re.IGNORECASE),
        ],
    ),
    (
        "Board Meeting Schedule (Without Outcome)",
        [
            re.compile(r"(prior\s+)?intimation\s+of\s+board\s+meeting", re.IGNORECASE),
            re.compile(r"reschedul(e|ing)\s+of\s+board\s+meeting", re.IGNORECASE),
            re.compile(r"postponement\s+of\s+board\s+meeting", re.IGNORECASE),
            re.compile(r"regulation\s+29", re.IGNORECASE),
        ],
    ),
    (
        "ESOP / Option Allotment",
        [
            re.compile(r"allotment\s+of\s+(equity\s+)?shares\s+under\s+esop", re.IGNORECASE),
            re.compile(r"grant\s+of\s+(stock\s+)?options\s+under\s+esop", re.IGNORECASE),
            re.compile(r"esos\s+allotment", re.IGNORECASE),
        ],
    ),
]

# Flattened list for backwards compatibility
NOISE_PATTERNS: List[Pattern] = [
    pat for _, patterns in CATEGORIZED_NOISE_PATTERNS for pat in patterns
]

# Keywords that override noise filter (if these appear, NEVER drop the filing)
HIGH_VALUE_OVERRIDES: List[Pattern] = [
    re.compile(r"\b(order|contract)\s+win\b", re.IGNORECASE),
    re.compile(r"\b(awarded|bagged|secured)\s+(order|contract|project)\b", re.IGNORECASE),
    re.compile(r"\b(dividend|bonus|split|buyback)\b", re.IGNORECASE),
    re.compile(r"\b(financial\s+results|q[1-4]\s+results|net\s+profit)\b", re.IGNORECASE),
    re.compile(r"\b(outcome\s+of\s+board\s+meeting|board\s+meeting\s+outcome)\b", re.IGNORECASE),
    re.compile(r"\b(resignation|removed|suspended|appointment\s+of\s+(ceo|cfo|director|md))\b", re.IGNORECASE),
    re.compile(r"\b(acquisition|merger|demerger|takeover|amalgamation|joint\s+venture)\b", re.IGNORECASE),
    re.compile(r"\b(fda|approval|sanction|penalty|fine|probe|raid|search)\b", re.IGNORECASE),
    re.compile(r"\b(credit\s+rating\s+(downgrade|upgrade))\b", re.IGNORECASE),
]


class NoiseFilter:
    """Detects and suppresses routine compliance disclosures."""

    @classmethod
    def explain_noise(cls, desc: str, details: str = "") -> Optional[str]:
        """Return the category name if routine compliance noise, or None if material."""
        combined = f"{desc} {details}".strip()
        if not combined:
            return None

        # Check for definitive administrative noise patterns
        for category, patterns in CATEGORIZED_NOISE_PATTERNS:
            for pattern in patterns:
                if pattern.search(combined):
                    return category

        return None


    @classmethod
    def is_noise(cls, desc: str, details: str = "") -> bool:
        """Evaluate if an announcement is routine compliance noise."""
        return cls.explain_noise(desc, details) is not None


__all__ = ["NoiseFilter", "NOISE_PATTERNS", "CATEGORIZED_NOISE_PATTERNS", "HIGH_VALUE_OVERRIDES"]


