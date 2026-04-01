import re
from typing import Any, Dict, Optional, Iterable

RE_BAD_PREFIX = re.compile(
    r"(here are the requested sections|requested sections|as an ai|i am an ai)",
    re.IGNORECASE,
)

# Require the new headings to exist
RE_INTERPRETATION = re.compile(r'^\s*\*{0,2}Interpretation\*{0,2}\s*:\s*$', re.M)
RE_SCENARIOS       = re.compile(r'^\s*\*{0,2}Scenarios\*{0,2}\s*:\s*$', re.M)
RE_RISKS           = re.compile(r'^\s*\*{0,2}Risks\s*&\s*invalidation\*{0,2}\s*:\s*$', re.M)
RE_ASSUMPTIONS     = re.compile(r'^\s*\*{0,2}Assumptions\*{0,2}\s*:\s*$', re.M)

# Accept -, *, or • as bullet leaders
RE_BULLETS         = re.compile(r'^\s*[-*•]\s+', re.M)


# Digits (we will sanitize them out first, but keep this as a final safety net)
RE_DIGITS = re.compile(r"\d")


_NUM_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

NUM_RE = re.compile(r"""
(?<![A-Za-z_])
(?:
  \$?\s*\d{1,3}(?:,\d{3})+(?:\.\d+)?%?
 | \$?\s*\d+(?:\.\d+)?%?
)
(?![A-Za-z_])
""", re.VERBOSE)

def _extract_numbers(text: str) -> set[str]:
    # Ignore numbers that are part of indicator tokens like ema20 / sma50 / sma200 / rsi14
    scrubbed = re.sub(r"\b(?:ema|sma|rsi|macd)\s*\d+\b", "", text, flags=re.I)

    # IMPORTANT:
    # Allow the phrase "24-hour" / "24 hours" / "24h" without treating "24" as an invented number.
    # We do this by scrubbing those patterns BEFORE extracting numbers.
    scrubbed = re.sub(r"\b24\s*[- ]?\s*hour(s)?\b", "TWENTYFOURHOUR", scrubbed, flags=re.I)
    scrubbed = re.sub(r"\b24h\b", "TWENTYFOURHOUR", scrubbed, flags=re.I)

    nums = set()
    for m in NUM_RE.finditer(scrubbed):
        s = m.group(0).strip()
        s = re.sub(r"\s+", "", s)  # normalize spaces
        nums.add(s)
    return nums

def _strip_digits_to_words(text: str) -> str:
    """
    Replace digits with words BUT preserve newlines.
    We only normalize horizontal whitespace (spaces/tabs), not line breaks,
    because the heading regex checks rely on multiline anchors (^ and $).
    """
    out = []
    for ch in text:
        if ch in _NUM_WORDS:
            out.append(" " + _NUM_WORDS[ch] + " ")
        else:
            out.append(ch)

    s = "".join(out)

    # Normalize horizontal whitespace only (do NOT collapse newlines)
    s = re.sub(r"[ \t\f\v]+", " ", s)

    # Trim spaces around newlines
    s = re.sub(r" *\n *", "\n", s)

    return s.strip()

def narrative_reject_reason(text: Optional[str]) -> str:
    """
    Lightweight: only used for debug logs.
    We no longer enforce headings/bullets here.
    """
    if not text or not text.strip():
        return "empty"
    t = text.strip()
    if len(t) > 4000:
        return "too_long"
    if RE_BAD_PREFIX.search(t):
        return "bad_prefix"
    return "ok"

def safe_narrative_or_none(
    text: str,
    *,
    allowed_numbers: Iterable[str] | None = None,
) -> Optional[str]:
    """
    Allow free-form narrative, but block invented numbers.
    If allowed_numbers is provided, any number in text must appear in allowed_numbers.
    """
    if not text or not text.strip():
        return None

    t = text.strip()

    if allowed_numbers is None:
        return t

    allowed = set(re.sub(r"\s+", "", str(x)) for x in allowed_numbers if x is not None)

    used = _extract_numbers(t)

    # If model used no numbers, always allow (it can still be useful)
    if not used:
        return t

    # Reject if it uses numbers not in allowed set
    unknown = sorted([x for x in used if x not in allowed])

    if unknown:
        return None

    return t