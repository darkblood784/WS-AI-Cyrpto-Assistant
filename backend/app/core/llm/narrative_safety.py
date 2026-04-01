import re
from typing import Any, Dict, Optional, Set


_NUM_RE = re.compile(r"\d[\d,\.]*")  # captures 90,000 / 0.91 / 1234.56 etc

# Keep this list short. We don't need perfect NLP; just block obvious forecasting language.
_BANNED_FUTURE_PHRASES = [
    "will ", "soon", "next", "tomorrow", "target", "in the next", "likely to",
    "guarantee", "certain", "definitely",
]


def _extract_numbers(text: str) -> Set[str]:
    if not text:
        return set()
    return set(_NUM_RE.findall(text))


def _tool_number_whitelist(snapshot: Optional[Dict[str, Any]], indicators: Optional[Dict[str, Any]]) -> Set[str]:
    allowed: Set[str] = set()

    # snapshot numbers
    if snapshot:
        for k in ["price_usd", "change_24h_pct", "volume_24h_usd", "market_cap_usd"]:
            v = snapshot.get(k)
            if v is not None:
                allowed |= _extract_numbers(str(v))

    # indicators numbers
    if indicators:
        for k in ["rsi_14", "ema_20", "sma_20", "sma_50", "sma_200"]:
            v = indicators.get(k)
            if v is not None:
                allowed |= _extract_numbers(str(v))

        macd = indicators.get("macd_12_26_9") or {}
        if isinstance(macd, dict):
            for k in ["macd", "signal", "hist"]:
                v = macd.get(k)
                if v is not None:
                    allowed |= _extract_numbers(str(v))

    return allowed


def safe_narrative_or_none(
    narrative_text: Optional[str],
    *,
    snapshot: Optional[Dict[str, Any]],
    indicators: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Returns narrative_text if it looks safe; otherwise returns None.

    Safety rules:
    - If narrative contains ANY numbers not present in tool data -> reject.
    - If narrative contains obvious future/prediction phrasing -> reject.
    """
    if not narrative_text:
        return None

    txt = narrative_text.strip()
    if not txt:
        return None

    lower = txt.lower()
    if any(p in lower for p in _BANNED_FUTURE_PHRASES):
        return None

    allowed_numbers = _tool_number_whitelist(snapshot, indicators)
    used_numbers = _extract_numbers(txt)

    # If model invents any number not in tools -> reject narrative
    invented = [n for n in used_numbers if n not in allowed_numbers]
    if invented:
        return None

    return txt
