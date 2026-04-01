from __future__ import annotations
from typing import Any, Dict, List, Optional

from .ollama_client import ollama_generate


def _safe(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def build_market_brief_prompt(
    user_message: str,
    symbol: str,
    snapshot: Dict[str, Any],
    news_items: List[Dict[str, Any]],
) -> str:
    """
    LLM must be:
    - qualitative
    - no invented facts
    - use only provided snapshot + headlines
    - no 'guarantees' / no hard prediction language
    """
    price = _safe(snapshot.get("price_usd"))
    chg_raw = snapshot.get("change_24h_pct")
    chg = f"{float(chg_raw):.2f}%" if chg_raw is not None else ""

    headlines = []
    for it in (news_items or [])[:5]:
        title = _safe(it.get("title"))
        source = _safe(it.get("source"))
        published = _safe(it.get("published_at"))
        if title:
            headlines.append(f"- {title} ({source}, {published})")

    headlines_block = "\n".join(headlines) if headlines else "- (no headlines available)"

    return f"""
You are WSAI -- a crypto strategist and risk manager. You write like an operator desk, not a chatbot.
Tone: concise, professional, high-signal, trader-native. No hype. No filler. Every sentence helps the user decide.

User asked: {user_message}
Token: {symbol}

DATA YOU MAY USE (do not invent anything else):
- Snapshot: price_usd={price}, change_24h_pct={chg}
- Headlines (most recent first):
{headlines_block}

Write ONLY the summary text body (no title, no numbering, no header).

Rules:
- Start with the bottom line -- what is actually happening and why it matters.
- Reference at least one headline by paraphrasing (not copying).
- Explain what the snapshot suggests for positioning, not just information.
- If no clear catalyst exists, say "no direct catalyst" and explain what the tape itself is telling you.
- Never use filler like "sentiment is mixed" without immediately saying what that means for action.
- Every paragraph should help the reader decide, not just understand.
- No predictions. No "will" or guaranteed outcomes. Frame as scenarios.
- Keep it compact but strong.

Now output ONLY the summary paragraph(s).
""".strip()


def generate_market_brief(
    user_message: str,
    symbol: str,
    snapshot: Dict[str, Any],
    news_items: List[Dict[str, Any]],
) -> Optional[str]:
    prompt = build_market_brief_prompt(
        user_message=user_message,
        symbol=symbol,
        snapshot=snapshot,
        news_items=news_items,
    )
    out = ollama_generate(prompt)
    return out
