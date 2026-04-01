import logging
import re
from typing import Any, Dict, Optional

from app.core.llm.ollama_client import ollama_generate
from app.core.llm.narrative_guard import safe_narrative_or_none, narrative_reject_reason

logger = logging.getLogger("uvicorn")

_TIMEFRAME_TOKEN_RE = re.compile(
    r"\b\d+\s*(h|hr|hrs|hour|hours|d|day|days|w|week|weeks|m|month|months)\b",
    re.I,
)
_24H_RE = re.compile(r"\b24\s*[-]?\s*hour\b|\b24h\b", re.I)
_DIGIT_RE = re.compile(r"\d+")

def _timeframe_to_words(tf: Optional[str]) -> str:
    """
    Convert timeframe tokens into user-friendly words WITHOUT digits.
    Used for Facts so the model doesn't output "1h" etc.
    """
    tf = (tf or "").strip().lower()

    mapping = {
        "1h": "hourly",
        "1hr": "hourly",
        "60m": "hourly",
        "4h": "four-hour",
        "12h": "twelve-hour",
        "1d": "daily",
        "7d": "weekly",
        "1w": "weekly",
    }

    return mapping.get(tf, "unknown")


def _compute_levels_below_none(snapshot: dict, indicators: dict | None) -> bool:
    snap = snapshot or {}
    ind = indicators or {}
    price = snap.get("price_usd")
    ema20 = ind.get("ema_20")
    sma50 = ind.get("sma_50")
    sma200 = ind.get("sma_200")

    try:
        p = float(price)
    except Exception:
        return False

    below = []
    for v in (ema20, sma50, sma200):
        try:
            fv = float(v)
        except Exception:
            continue
        if fv < p:
            below.append(fv)

    return len(below) == 0

def _sanitize_user_for_narrative(text: str) -> str:
    """
    Strip stuff that causes the model to echo digits/timeframes.
    We still show timeframe elsewhere in your deterministic contract output.
    """
    t = (text or "").strip()
    t = _24H_RE.sub("", t)
    t = _TIMEFRAME_TOKEN_RE.sub("", t)
    # if user typed "1 h" etc, remove remaining digits
    t = _DIGIT_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _allowed_numbers_from_facts(snapshot: dict, indicators: dict | None) -> set[str]:
    """
    Only allow the exact numeric STRINGS we intentionally expose in Facts.
    This prevents rejections caused by formatting mismatches.
    """
    snap = snapshot or {}
    ind = indicators or {}

    def _fmt_usd(x):
        try:
            return f"${float(x):,.2f}"
        except Exception:
            return ""

    def _fmt_pct(x):
        try:
            return f"{float(x):.2f}%"
        except Exception:
            return ""

    def _fmt_num(x, nd=2):
        try:
            return f"{float(x):.{nd}f}"
        except Exception:
            return ""

    allowed: set[str] = set()

    # Allow common zero variants because LLM sometimes says "0" in text.
    allowed.update({"0", "0.0", "0.00", "0%"})

    price_fmt = _fmt_usd(snap.get("price_usd"))
    chg_fmt = _fmt_pct(snap.get("change_24h_pct"))

    ema20_fmt = _fmt_usd(ind.get("ema_20"))
    sma50_fmt = _fmt_usd(ind.get("sma_50"))
    sma200_fmt = _fmt_usd(ind.get("sma_200"))

    rsi_fmt = _fmt_num(ind.get("rsi_14"), 2)

    # Add exact strings (normalized: no spaces)
    for s in (price_fmt, chg_fmt, ema20_fmt, sma50_fmt, sma200_fmt, rsi_fmt):
        s = (s or "").strip()
        if s:
            allowed.add(s.replace(" ", ""))

    # Also allow unsigned % (LLM sometimes drops the minus)
    if chg_fmt.startswith("-"):
        allowed.add(chg_fmt.lstrip("-").replace(" ", ""))

    return allowed

def _apply_level_direction_sanity(text: str, *, levels_below_none: bool) -> str:
    """
    If there are no key levels below price, we must not talk like
    EMA/SMA are 'support' or 'holding above'. They are resistance.
    Also prevent upside/break-above lines from being described as bearish continuation.
    """
    if not text:
        return text

    t = text

    if levels_below_none:
        # Convert wrong "support" language to resistance language
        t = re.sub(r"\bmay provide support\b", "may act as resistance", t, flags=re.I)
        t = re.sub(r"\bprovide support\b", "act as resistance", t, flags=re.I)
        t = re.sub(r"\bsupport\b", "resistance", t, flags=re.I)

        # Convert "hold above" phrases (wrong when price is below levels)
        t = re.sub(r"\bfailure to hold above\b", "failure to reclaim", t, flags=re.I)
        t = re.sub(r"\bfails to hold above\b", "fails to reclaim", t, flags=re.I)
        t = re.sub(r"\bholding above\b", "trading below", t, flags=re.I)
        t = re.sub(r"\bhold above\b", "reclaim", t, flags=re.I)

        # Kill "support below / lower levels" implications (when none exists)
        bad_line_patterns = [
            r"\bbreak below\b",
            r"\bbelow\b.*\bnone\b",
            r"\bsupport\b.*\bbelow\b",
            r"\bbelow\b.*\bcurrent\b.*\bprice\b",
            r"\blower levels?\b",
            r"\blow(er)? end\b",
            r"\bdownside\b",
            r"\btest\b.*\bresistance\b.*\bbelow\b",  # just in case model says weird stuff
        ]

        lines = []
        for ln in t.splitlines():
            if any(re.search(p, ln, flags=re.I) for p in bad_line_patterns):
                continue
            lines.append(ln)
        t = "\n".join(lines).strip()

        # Fix the specific nonsense you’re seeing:
        # "fall/decline ... if it breaks above <level>" is contradictory.
        # Replace with a neutral / correct framing.
        t = re.sub(
            r"(may|could|might)?\s*continue to\s*(fall|decline|drop|sell off)\s*if\s*it\s*breaks\s*above\b",
            "would weaken further downside if it breaks above",
            t,
            flags=re.I,
        )
        t = re.sub(
            r"\b(bearish|downtrend)\b.*\bif\b.*\bbreaks above\b",
            "the bearish read weakens if it breaks above",
            t,
            flags=re.I,
        )

    return t

def build_crypto_narrative_prompt(
    user_message: str,
    symbol: str,
    timeframe: str | None,
    snapshot: dict,
    indicators: dict | None,
) -> str:
    clean_user = _sanitize_user_for_narrative(user_message)

    snap = snapshot or {}
    ind = indicators or {}

    # Pull facts safely
    price = snap.get("price_usd")
    chg24 = snap.get("change_24h_pct")
    try:
        if chg24 is not None:
            chg24 = round(float(chg24), 2)
    except Exception:
        pass

    rsi = ind.get("rsi_14")
    rsi_label = ind.get("rsi_label") or ind.get("rsiLabel") or ""
    bias = ind.get("bias") or ""
    momentum = ind.get("momentum") or ""
    ema20 = ind.get("ema_20")
    sma50 = ind.get("sma_50")
    sma200 = ind.get("sma_200")
    
    def _above_below(price, levels: dict):
        try:
            p = float(price)
        except Exception:
            return "none", "none"
    
        above = []
        below = []
        for name, v in levels.items():
            try:
                fv = float(v)
            except Exception:
                continue
            if fv > p:
                above.append(name)
            elif fv < p:
                below.append(name)
    
        return ", ".join(above) if above else "none", ", ".join(below) if below else "none"
    
    levels = {"ema20_fmt": ema20, "sma50_fmt": sma50, "sma200_fmt": sma200}
    levels_above, levels_below = _above_below(price, levels)
    levels_below_none = (levels_below.strip().lower() == "none")

    def _fmt_usd(x):
        try:
            return f"${float(x):,.2f}"
        except Exception:
            return "N/A"
    
    def _fmt_pct(x):
        try:
            return f"{float(x):.2f}%"
        except Exception:
            return "N/A"
    
    price_fmt = _fmt_usd(price)
    ema20_fmt = _fmt_usd(ema20)
    sma50_fmt = _fmt_usd(sma50)
    sma200_fmt = _fmt_usd(sma200)
    chg24_fmt = _fmt_pct(chg24)

    rsi_fmt = ""
    try:
        if rsi is not None:
            rsi_fmt = f"{float(rsi):.2f}"
    except Exception:
        rsi_fmt = ""

    # direction label for consistency checks
    if isinstance(chg24, (int, float)):
        direction = "down" if chg24 < 0 else "up" if chg24 > 0 else "flat"
    else:
        direction = "unknown"

    # We want strategic, operator-grade output with hard grounding
    return f"""
You are WSAI — a crypto strategist, risk manager, and operator desk in one voice.
Your job is to help traders think better before taking risk. You are not a chatbot. You are a decision-support system.

Tone: concise, professional, high-signal, trader-native. No hype, no filler, no generic commentary.
Never say "market sentiment is mixed" without immediately explaining what that means for positioning.
Every sentence should help the user decide, not just understand.

Facts (ground truth — do NOT invent anything beyond these):
- token: {symbol}
- timeframe: {_timeframe_to_words(timeframe)}
- price_usd_raw: {price}
- price_usd_fmt: {price_fmt}
- change_24h_pct_raw: {chg24}
- change_24h_pct_fmt: {chg24_fmt}
- direction: {direction}
- bias: {bias}
- momentum: {momentum}
- stretch_label: {rsi_label}
- rsi_value: {rsi}
- levels_above_price: {levels_above}
- levels_below_price: {levels_below}
- rsi_fmt: {rsi_fmt}

Key levels you are allowed to reference (use these EXACT strings if you mention levels):
- ema20_fmt: {ema20_fmt}
- sma50_fmt: {sma50_fmt}
- sma200_fmt: {sma200_fmt}

Writing rules:
- Do not add any intro line like "Here is the commentary:".
- No markdown. Plain text.
- You may mention timeframe, but NEVER use digits for it. Use words like "hourly", "four-hour", "daily", "weekly".
- Do not include "User request:" in your output.
- Do NOT create any new support/resistance levels. Only reference ema20_fmt, sma50_fmt, sma200_fmt if you mention levels.
- If you mention a level, copy/paste the exact string from the Facts (including $ and commas).
- You MAY use digits, but ONLY by copy/pasting these exact strings from Facts:
  price_usd_fmt, change_24h_pct_fmt, ema20_fmt, sma50_fmt, sma200_fmt, rsi_fmt.
- If you talk about a "break above" or "rebound target", only use levels_above_price.
- If you talk about a "break below" or "downside target", only use levels_below_price.
- You MUST respect levels_above_price / levels_below_price:
  - If levels_below_price is "none", do NOT write "break below" or "target below" any of the key levels.
  - If levels_above_price contains a level, you may write "break above <level>" but only using the exact *_fmt string.
- If stretch_label is provided, use it to describe RSI condition.
- Do NOT describe RSI as "oversold" unless stretch_label contains "oversold".
- If levels_below_price is "none", do NOT say "break below <level>" anywhere.
- Only use "break above" with levels listed in levels_above_price, and only use "break below" with levels listed in levels_below_price.

Output format (must match exactly — fill each section with sharp, actionable content):

Bottom line:
<One or two sentences. What is actually happening and what it means for positioning. Be direct.>

What is driving it:
<What is causing the current move or regime. Reference indicators, momentum, structure — not vague "sentiment".>

Trade implication:
<What a trader should actually consider doing or avoiding right now. Be specific about direction, structure quality, and conviction level.>

Scenarios:
- Bull: <one sentence — what confirms the upside thesis>
- Base: <one sentence — what keeps price in current regime>
- Bear: <one sentence — what breaks the thesis>

Invalidation:
<Specific conditions that break the current read. Use exact levels from Facts if relevant.>

Operator takeaway:
<One sentence. The single most important thing to remember before acting.>

User request: {clean_user}
(Do not repeat this line in your output.)
""".strip()

    
def generate_crypto_narrative(
    user_message: str,
    symbol: str,
    timeframe: Optional[str],
    snapshot: Dict[str, Any],
    indicators: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    base_prompt = build_crypto_narrative_prompt(
        user_message=user_message,
        symbol=symbol,
        timeframe=timeframe,
        snapshot=snapshot,
        indicators=indicators,
    )

    prompt = base_prompt

    for attempt in (1, 2):
        raw = ollama_generate(prompt)
        
        # --- normalize timeframe phrases BEFORE guard ---
        # Keep "24-hour" because it reads correctly and narrative_guard now ignores its digits.
        raw = re.sub(r"\b24\s*[-]?\s*hour(s)?\b|\b24h\b", "24-hour", raw or "", flags=re.I)
        
        # Remove/convert other digit-based timeframe tokens to words (optional but keeps your rule consistent)
        raw = re.sub(r"\b1\s*[-]?\s*hour(s)?\b|\b1h\b", "hourly", raw or "", flags=re.I)
        raw = re.sub(r"\b4\s*[-]?\s*hour(s)?\b|\b4h\b", "four-hour", raw or "", flags=re.I)
        raw = re.sub(r"\b12\s*[-]?\s*hour(s)?\b|\b12h\b", "twelve-hour", raw or "", flags=re.I)
        raw = re.sub(r"\b1\s*[-]?\s*day(s)?\b|\b1d\b", "daily", raw or "", flags=re.I)
        raw = re.sub(r"\b7\s*[-]?\s*day(s)?\b|\b7d\b", "weekly", raw or "", flags=re.I)
        raw = re.sub(r"\bover the last 24-hour\b", "over the last 24 hours", raw, flags=re.I)
        raw = re.sub(r"\bover the last 24-hour\.\b", "over the last 24 hours.", raw, flags=re.I)
        raw = re.sub(r"\blast 24-hour\b", "last 24 hours", raw, flags=re.I)

        logger.warning(
            "[RAW_LLM_OUTPUT attempt=%s]\n%s\n---- END RAW ----",
            attempt,
            (raw or "")[:1200],
        )

        reason = narrative_reject_reason(raw)
        logger.warning("[LLM narrative] %s", reason)

        allowed = _allowed_numbers_from_facts(snapshot, indicators)
        out = safe_narrative_or_none(raw or "", allowed_numbers=allowed)
        
        levels_below_none = _compute_levels_below_none(snapshot, indicators)
        
        # If there are no levels below price, delete any “downside/support below” wording,
        # but DO NOT reject the entire narrative.
        if out and levels_below_none:
            bad = [
                r"\bbreak(?:s|ing)?\s+below\b",
                r"\bmove(?:s|ing)?\s+below\b",
                r"\bslip(?:s|ping)?\s+below\b",
                r"\bdrop(?:s|ping)?\s+below\b",
                r"\bfall(?:s|ing)?\s+below\b",
                r"\bbeneath\b",
                r"\bdownside\b",
                r"\blower levels?\b",
                r"\bbelow (the )?current price\b",
                r"\btest support\b",
                r"\bsupport\b.*\bbelow\b",
                r"\btarget(?:s)?\b.*\blower\b",
                r"\bdecline towards\b",
                r"\bbelow key levels\b",
                r"\blower levels\b",
                r"\bbelow none\b",

            ]

            out = "\n".join(
                ln for ln in out.splitlines()
                if not any(re.search(p, ln, flags=re.I) for p in bad)
            ).strip()


        # Debug: always log unknown numbers if any
        try:
            from app.core.llm.narrative_guard import _extract_numbers
            used = _extract_numbers(raw or "")
            allowed_norm = set(re.sub(r"\s+", "", str(x)) for x in allowed if x is not None)
            unknown = sorted([x for x in used if x not in allowed_norm])
            if unknown:
                logger.warning("[LLM narrative] rejected_unknown_numbers=%s", unknown[:40])
        except Exception:
            pass

        if out:
            # If model forgot headings, add the minimum structure (do NOT reject)
            if "Bottom line:" not in out:
                out = "Bottom line:\n" + out.strip()
            # Always reorder scenario bullets in Scenarios: section (Bull/Base/Bear)
            def _reorder_scenarios(text: str) -> str:
                lines = text.splitlines()
                try:
                    i = next(idx for idx, ln in enumerate(lines) if ln.strip() == "Scenarios:")
                except StopIteration:
                    return text

                headings = {"Bottom line:", "What is driving it:", "Trade implication:", "Scenarios:", "Invalidation:", "Operator takeaway:"}

                # collect scenario lines until next heading
                j = i + 1
                chunk = []
                while j < len(lines) and lines[j].strip() not in headings:
                    chunk.append(lines[j])
                    j += 1

                bull = next((ln for ln in chunk if ln.strip().startswith("- Bull:")), None)
                base = next((ln for ln in chunk if ln.strip().startswith("- Base:")), None)
                bear = next((ln for ln in chunk if ln.strip().startswith("- Bear:")), None)

                new_chunk = []
                if bull:
                    new_chunk.append(bull)
                if base:
                    new_chunk.append(base)
                if bear:
                    new_chunk.append(bear)

                # if nothing found, don't change anything
                if not new_chunk:
                    return text

                # Replace old chunk with ordered chunk
                lines = lines[: i + 1] + new_chunk + lines[j:]
                return "\n".join(lines)

            out = _reorder_scenarios(out)
            
            

            # =========================
            # FINAL CLEANUP (hard rules)
            # =========================

            # 1) Replace placeholder tokens like "ema20_fmt" with actual formatted strings
            # We do NOT allow placeholders to reach users.
            def _replace_placeholders(text: str) -> str:
                def _fmt_usd(x):
                    try:
                        return f"${float(x):,.2f}"
                    except Exception:
                        return ""
            
                ind = indicators or {}
                ema20_fmt = _fmt_usd(ind.get("ema_20"))
                sma50_fmt = _fmt_usd(ind.get("sma_50"))
                sma200_fmt = _fmt_usd(ind.get("sma_200"))
            
                out = text
            
                # Replace literal placeholders
                if ema20_fmt:
                    out = re.sub(r"\bema20_fmt\b", ema20_fmt, out, flags=re.I)
                if sma50_fmt:
                    out = re.sub(r"\bsma50_fmt\b", sma50_fmt, out, flags=re.I)
                if sma200_fmt:
                    out = re.sub(r"\bsma200_fmt\b", sma200_fmt, out, flags=re.I)
            
                # Remove patterns like "ema20_fmt ($134.24)" → "$134.24"
                if ema20_fmt:
                    out = re.sub(r"\bema20_fmt\s*\(\s*\$?[0-9.,]+\s*\)", ema20_fmt, out, flags=re.I)
                if sma50_fmt:
                    out = re.sub(r"\bsma50_fmt\s*\(\s*\$?[0-9.,]+\s*\)", sma50_fmt, out, flags=re.I)
                if sma200_fmt:
                    out = re.sub(r"\bsma200_fmt\s*\(\s*\$?[0-9.,]+\s*\)", sma200_fmt, out, flags=re.I)
            
                return out
            
            out = _replace_placeholders(out)
            out = re.sub(r"(\$[0-9.,]+)\s*\(\s*\1\s*\)", r"\1", out)
            # Cleanup: "$X level of $X" -> "$X level"
            out = re.sub(r"(\$[0-9.,]+)\s+level\s+of\s+\1", r"\1 level", out, flags=re.I)
            out = re.sub(r"\bthe\s+(\$[0-9.,]+)\s+level\s+of\s+\1", r"the \1 level", out, flags=re.I)
            out = _apply_level_direction_sanity(out, levels_below_none=levels_below_none)
            
            # 3) Enforce Scenarios order and ensure all 3 bullets exist
            def _force_scenarios(text: str) -> str:
                lines = text.splitlines()
                headings = {"Bottom line:", "What is driving it:", "Trade implication:", "Scenarios:", "Invalidation:", "Operator takeaway:"}

                try:
                    i = next(idx for idx, ln in enumerate(lines) if ln.strip() == "Scenarios:")
                except StopIteration:
                    # If missing, append a full scenarios block
                    lines.append("Scenarios:")
                    lines.append("- Bull: A reclaim of key levels would strengthen the upside case.")
                    lines.append("- Base: Choppy conditions can persist while price sits near key levels.")
                    lines.append("- Bear: If rallies fail repeatedly, downside pressure can stay in control.")
                    return "\n".join(lines).strip()

                # collect current scenario lines
                j = i + 1
                chunk = []
                while j < len(lines) and lines[j].strip() not in headings:
                    chunk.append(lines[j])
                    j += 1

                bull = next((ln for ln in chunk if ln.strip().startswith("- Bull:")), None)
                base = next((ln for ln in chunk if ln.strip().startswith("- Base:")), None)
                bear = next((ln for ln in chunk if ln.strip().startswith("- Bear:")), None)

                # Fill missing bullets (no numbers)
                if not bull:
                    bull = "- Bull: A reclaim of key levels would strengthen the upside case."
                if not base:
                    base = "- Base: Choppy conditions can persist while price sits near key levels."
                if not bear:
                    bear = "- Bear: If rallies fail repeatedly, downside pressure can stay in control."

                new_chunk = [bull, base, bear]
                lines = lines[: i + 1] + new_chunk + lines[j:]
                return "\n".join(lines).strip()

            out = _force_scenarios(out)
            
            # Fill empty required sections so output never looks "half done"
            def _ensure_section_has_text(text: str, section: str, fallback: str) -> str:
                lines = text.splitlines()
                headings = {"Bottom line:", "What is driving it:", "Trade implication:", "Scenarios:", "Invalidation:", "Operator takeaway:"}
            
                # If the section exists as "Heading: some text", treat as already filled
                for ln in lines:
                    if ln.strip().startswith(section) and ln.strip() != section:
                        return text
            
                try:
                    i = next(idx for idx, ln in enumerate(lines) if ln.strip() == section)
                except StopIteration:
                    # If heading is missing, add it + fallback
                    lines.append(section)
                    lines.append(fallback)
                    return "\n".join(lines).strip()
            
                # Scan until next heading; if we find any non-empty line, keep as-is
                j = i + 1
                while j < len(lines) and lines[j].strip() not in headings:
                    if lines[j].strip():
                        return text
                    j += 1
            
                # No content found in that section → insert fallback immediately after heading
                lines.insert(i + 1, fallback)
                return "\n".join(lines).strip()


            out = _ensure_section_has_text(
                out,
                "Bottom line:",
                "Price action is choppy near key structure — no clear directional edge yet."
            )
            out = _ensure_section_has_text(
                out,
                "Invalidation:",
                "If price reclaims the nearest key level and holds, the current read weakens."
            )
            out = _ensure_section_has_text(
                out,
                "Operator takeaway:",
                "Wait for structure confirmation before committing size. Patience is edge here."
            )
            
            # Strip prompt echo tails
            out = re.sub(r"\nCRITICAL:?[\s\S]*$", "", out.strip(), flags=re.I)
            out = re.sub(r"\nUser request:.*$", "", out.strip(), flags=re.M)

            logger.info("[LLM narrative] OK")
            return out

        # attempt 2: tighten only formatting, not content
        if attempt == 1:
            prompt = (
                base_prompt
                + "\n\nCRITICAL:\n"
                  "- Start immediately with 'Bottom line:'\n"
                  "- Keep the exact headings from the template.\n"
                  "- Do not add any numbers except the ones in Facts.\n"
            )
            logger.warning("[NARR_PROMPT] %s", prompt[:1200])
            continue

        break

    logger.info("[LLM narrative] REJECTED")
    return None
