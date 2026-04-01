from __future__ import annotations
import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import Literal, TypedDict, List
import hashlib
import json
import os
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.routers.auth import get_current_user
from app.db import models
from app.tools.market_data import (
    get_market_snapshot,
    resolve_coingecko_id,
    get_ohlcv,
    get_indicators_basic,
)

from app.db.cache import read_cache, write_cache, stable_request_hash
import logging
from types import SimpleNamespace
from app.core.formatters.crypto_contract import (
    format_price_contract,
    format_indicators_contract,
)
from app.core.llm.crypto_narrative import generate_crypto_narrative
from app.tools.news_feed import fetch_google_news
from app.tools.news_ingest import get_top_news, get_top_news_strict, news_items_to_dicts, upsert_news_items
from app.core.llm.market_brief import generate_market_brief
from app.core.formatters.news_contract import format_market_brief_contract
from app.core.llm.education import generate_education
from app.core.llm.narrative_safety import safe_narrative_or_none
import uuid
from sqlalchemy import text

newslog = logging.getLogger("NEWSDBG")

router = APIRouter(tags=["chat"])

# ---------- display-text extraction ----------
_WSAI_SEPARATOR = "--- WSAI Analysis ---"

def _extract_display(full_text: str) -> str:
    """Return only the user-facing narrative from a contract+narrative blob.

    For crypto contracts the narrative lives after '--- WSAI Analysis ---'.
    For everything else (small talk, education, news briefs, errors) the
    full text is already user-facing so we return it as-is.
    """
    if _WSAI_SEPARATOR in full_text:
        return full_text.split(_WSAI_SEPARATOR, 1)[1].strip()
    return full_text
# -----------------------------------------------

from difflib import SequenceMatcher


Mode = Literal[
    "chat",
    "indicators_basic",
    "indicators_advanced",
    "strategy_builder",
    "exports",
    "alerts",
    "long_term_memory",
]

MODE_TO_COLUMN = {
    "chat": "chat_basic",
    "indicators_basic": "indicators_basic",
    "indicators_advanced": "indicators_advanced",
    "strategy_builder": "strategy_builder",
    "exports": "exports",
    "alerts": "alerts",
    "long_term_memory": "long_term_memory",
}

CACHEABLE_MODES: set[str] = {
    "indicators_basic",
    "indicators_advanced",
}

# -------------------------------
# 6A helpers
# -------------------------------
class IntentResult(TypedDict):
    intent: str
    symbols: List[str]
    confidence: float
    reason: str

"""
# Basic coin-name → ticker mapping (expand later safely)
NAME_TO_TICKER = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binance coin": "BNB",
    "bnb": "BNB",
    "ripple": "XRP",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "avalanche": "AVAX",
    "polygon": "MATIC",
    "chainlink": "LINK",
    "litecoin": "LTC",
    "tron": "TRX",
    "polkadot": "DOT",
}
"""
NAME_TO_TICKER = {}

# Words that look like tickers but are common chat words
SYMBOL_STOPLIST = {
    "HI", "HELLO", "HEY", "OK", "YES", "NO", "LOL", "LMAO", "OKAY",
    "THANKS", "THANK", "PLS", "PLEASE", "GM", "GN"
}

# Indicator words that should NEVER be treated as token symbols
INDICATOR_SYMBOL_STOPLIST = {
    "RSI", "MACD", "EMA", "SMA", "VWAP", "ATR", "BB", "BOLLINGER",
    "STOCH", "STOCHASTIC", "ADX", "OBV", "MFI", "CCI"
}


PRICE_HINTS = {"price", "chart", "market cap", "mcap", "volume", "vol", "ath", "atl", "pump", "dump", "trend"}
INDICATOR_HINTS = {"indicator", "indicators", "rsi", "macd", "ema", "sma", "bollinger", "bb", "stoch", "stochastic", "vwap", "adx", "atr", "support", "resistance"}
STRATEGY_HINTS = {"strategy", "grid", "dca", "mean reversion", "breakout", "scalp", "scalping", "swing", "leverage", "stop loss", "take profit"}
IMAGE_HINTS = {"image", "screenshot", "photo", "chart image", "upload", "png", "jpg", "jpeg"}
EDU_HINTS = {"explain", "meaning", "how does", "teach me", "beginner", "difference between"}

# Small talk signals (allowed)
SMALL_TALK_EXACT = {
    "hi", "hello", "hey", "yo", "gm", "good morning", "good afternoon", "good evening", "gn", "good night",
    "thanks", "thank you", "thx", "ty", "ok", "okay", "cool", "nice", "great", "lol"
}
SMALL_TALK_CONTAINS = {
    "how are you", "what's up", "whats up", "how’s it going", "hows it going"
}

# Out-of-scope task hints (refuse)
OUT_OF_SCOPE_HINTS = {
    "politics", "president", "election", "weather", "recipe", "relationship", "dating",
    "homework", "math", "physics", "chemistry", "biology",
    "python", "javascript", "react", "fastapi", "docker", "linux", "sql", "database",
    "write an essay", "write a poem", "lyrics", "translate", "summarize"
}

MARKET_BRIEF_HINTS = [
    "what is", "doing today", "today", "what's happening", "whats happening",
    "market update", "what's moving", "whats moving", "why is", "news"
]

GREET_PREFIX_RE = re.compile(r"^\s*(hi|hello|hey|yo|gm|gn)\b[,\s!.\-:]*", re.I)

def strip_greeting_prefix(text: str) -> str:
    if not text:
        return text
    out = GREET_PREFIX_RE.sub("", text.strip())
    return out.strip() or text.strip()

def route_crypto_action(message: str, symbols: List[str]) -> dict:
    """
    Picks the best crypto action using a priority ladder.
    This avoids 'intent wars' (education vs market_brief etc).
    Returns: {"action": "...", "symbol": "...", "timeframe": "..."}
    """
    text = _normalize_text(message or "")
    sym = symbols[0] if symbols else None
    has_sym = bool(sym)

    # Signals
    wants_indicators = any(k in text for k in [
        "rsi", "macd", "ema", "sma", "indicator", "indicators", "vwap", "atr", "bollinger", "bb"
    ])

    wants_price = any(k in text for k in [
        "price", "how much", "quote", "market cap", "volume", "mcap", "ath", "atl"
    ])

    wants_brief = any(k in text for k in [
        "doing today", "today", "what's happening", "whats happening",
        "market update", "what's moving", "whats moving", "why is", "news",
        "up today", "down today"
    ])

    # Definition/education signal (keep this simple & safe)
    looks_like_definition = any(k in text for k in [
        "what is rsi", "what is macd", "what is ema", "explain", "meaning", "how does",
        "teach me", "difference between"
    ])

    # Timeframe defaulting
    tf = _extract_timeframe(message) if (wants_indicators or wants_brief) else None
    if "today" in text and not tf:
        tf = "4h"

    # Priority ladder
    # If user asks "today" AND indicators (e.g., RSI), do analysis (not news-only)
    if wants_brief and wants_indicators and has_sym:
        return {"action": "token_analysis", "symbol": sym, "timeframe": tf or "4h"}

    if wants_brief and has_sym:
        return {"action": "market_brief", "symbol": sym, "timeframe": tf}


    if wants_indicators and has_sym:
        return {"action": "indicator_request", "symbol": sym, "timeframe": tf or "1h"}

    if wants_price and has_sym:
        return {"action": "price_question", "symbol": sym, "timeframe": None}

    # Education does NOT require a symbol
    if looks_like_definition:
        return {"action": "education", "symbol": sym, "timeframe": None}

    # Default analysis if they mentioned a symbol
    if has_sym:
        return {"action": "token_analysis", "symbol": sym, "timeframe": tf or "4h"}

    return {"action": "ask_symbol", "symbol": None, "timeframe": None}

def _extract_timeframe(message: str) -> str:
    """Return a normalized timeframe like '5m', '1h', '4h', '1d'."""
    m = (message or "").lower().strip()

    # TradingView style: M5, H1, D1
    tv = re.search(r"\b([mhd])\s*(\d{1,4})\b", m, re.IGNORECASE)
    if tv:
        unit = tv.group(1).lower()
        n = tv.group(2)
        return f"{n}{unit}"

    # General forms: “5 min”, “7 minutes”, “2 hours”, etc.
    r = re.search(
        r"\b(\d{1,4})\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b",
        m,
    )
    if r:
        n = int(r.group(1))
        u = r.group(2)

        if u.startswith(("m", "min")):
            return f"{n}m"
        if u.startswith(("h", "hr", "hour")):
            return f"{n}h"
        if u.startswith(("d", "day")):
            return f"{n}d"

    # Default fallback
    return "1h"

def _indicator_focus(message: str) -> str:
    """
    Returns: "rsi" | "macd" | "ema20" | "full"
    """
    m = (message or "").lower()

    # user explicitly asked for a single indicator
    if "rsi" in m:
        return "rsi"
    if "macd" in m:
        return "macd"

    # "ema 20", "ema20", "ema(20)"
    if re.search(r"\bema\s*\(?\s*20\s*\)?\b", m):
        return "ema20"

    # "show indicators" / "all indicators" / "full indicators"
    if ("show" in m and "indicator" in m) or ("all" in m and "indicator" in m) or ("full" in m and "indicator" in m):
        return "full"

    return "full"


def _normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s

def _fmt(x, nd=2):
    if x is None:
        return "N/A"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)

def _extract_symbols(message: str) -> List[str]:
    # 1) Detect explicit tickers (BTC, ETH, SOL...) but avoid false positives
    raw = re.findall(r"\b[A-Z0-9]{2,10}\b", message or "")
    symbols: List[str] = []
    for s in raw:
        if s in SYMBOL_STOPLIST:
            continue
    
        # Never treat indicator keywords as coin tickers
        if s in INDICATOR_SYMBOL_STOPLIST:
            continue
    
        # Avoid obvious technical tokens
        if s in {"HTTP", "JSON", "FASTAPI", "POST", "GET", "UUID", "JWT", "SQL", "API"}:
            continue
    
        symbols.append(s)


    # 2) Detect coin names in lowercase text
    lower = (message or "").lower()
    for name, ticker in NAME_TO_TICKER.items():
        if name in lower:
            symbols.append(ticker)

    # Unique, preserve order
    seen = set()
    out: List[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def classify_intent(message: str) -> IntentResult:
    text_raw = message or ""
    text = _normalize_text(text_raw)

    # 0) Small talk (allow)
    if text in SMALL_TALK_EXACT:
        return {"intent": "small_talk", "symbols": [], "confidence": 0.95, "reason": "small_talk_exact"}
    if any(p in text for p in SMALL_TALK_CONTAINS):
        return {"intent": "small_talk", "symbols": [], "confidence": 0.90, "reason": "small_talk_contains"}

    # Extract symbols early
    symbols = _extract_symbols(text_raw)
    has_symbols = len(symbols) > 0

    lower = text

    # Out-of-scope task hints (refuse)
    if any(h in lower for h in OUT_OF_SCOPE_HINTS):
        return {"intent": "out_of_scope", "symbols": [], "confidence": 0.90, "reason": "out_of_scope_hint"}

    # Signals that strongly suggest crypto even without a ticker
    indicator_words = any(k in lower for k in [
        "rsi", "macd", "ema", "sma", "vwap", "atr", "bollinger", "bb",
        "stoch", "stochastic", "adx", "obv", "mfi", "cci", "indicator", "indicators",
        "support", "resistance"
    ])

    market_words = any(k in lower for k in [
        "today", "price", "chart", "market cap", "mcap", "volume", "ath", "atl",
        "up today", "down today", "what's happening", "whats happening",
        "market update", "what's moving", "whats moving", "news", "why is"
    ])

    crypto_words = ("crypto" in lower) or ("coin" in lower) or ("token" in lower) or ("blockchain" in lower)

    education_words = any(k in lower for k in [
        "what is", "explain", "meaning", "how does", "teach me", "difference between"
    ])

    crypto_related = has_symbols or crypto_words or indicator_words or market_words or education_words

    if crypto_related:
        return {"intent": "crypto", "symbols": symbols, "confidence": 0.75, "reason": "crypto_default"}

    return {"intent": "out_of_scope", "symbols": [], "confidence": 0.85, "reason": "no_crypto_signals"}

def _guess_asset_query_from_message(raw_msg: str) -> str | None:
    """
    Pull a likely coin name/ticker from the user's message.
    Example:
      "Filecoin today?" -> "filecoin"
      "bitcoin price"   -> "bitcoin"
      "ETH today?"      -> "ETH"
    """
    if not raw_msg:
        return None

    m = raw_msg.strip()

    # Remove common punctuation
    m2 = re.sub(r"[^\w\s\-]", " ", m)
    m2 = re.sub(r"\s+", " ", m2).strip()

    # Drop common filler words
    drop = {
        "today", "price", "chart", "news", "analysis", "update", "doing", "happening",
        "what", "whats", "what's", "is", "why", "up", "down", "please", "tell", "me",
        "coin", "token", "crypto"
    }

    parts = [p for p in m2.split() if p.lower() not in drop]
    if not parts:
        return None

    # If the user gave a ticker already, return that
    for p in parts:
        if re.fullmatch(r"[A-Za-z0-9]{2,10}", p) and p.upper() not in SYMBOL_STOPLIST and p.upper() not in INDICATOR_SYMBOL_STOPLIST:
            return p.upper()

    # Otherwise treat remaining as a name phrase (first 1-3 words)
    name_phrase = " ".join(parts[:3]).strip()
    return name_phrase if name_phrase else None

def select_model_backend(is_bypass: bool, is_paid: bool, intent: str) -> str:
    """
    Phase 6A-2: Decide which model backend to use (cost-aware).
    - Admin/owner bypass -> "bypass"
    - Free -> "local"
    - Paid -> local for low-cost intents, otherwise "chatgpt"
    """
    if is_bypass:
        return "bypass"

    intent = (intent or "").lower().strip()

    # Free stays local always
    if not is_paid:
        return "local"

    # Paid plans
    if intent in {"small_talk", "education"}:
        return "local"

    return "chatgpt"

"""
# -----------------------------
# Phase 6B helper (partial): Market snapshot (CoinGecko + CMC) with Postgres cache
# -----------------------------

COINGECKO_DEMO_API_KEY = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
CMC_API_KEY = os.getenv("CMC_API_KEY", "").strip()

# Minimal mapping for CoinGecko /simple/price (it wants "ids", not symbols)
# Add more as you like.
COINGECKO_ID_BY_SYMBOL = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "MATIC": "polygon",
    "LINK": "chainlink",
}

MARKET_CACHE_MODE = "market_snapshot_v1"
MARKET_CACHE_TTL_SECONDS = 60  # 1 min cache (adjust later)
API_CACHE_SHARED_USER_ID = "00000000-0000-0000-0000-000000000000"

def _read_market_cache(db: Session, request_hash: str, now_utc_naive: datetime) -> dict | None:
    row = (
        db.query(models.ApiCache)
        .filter(models.ApiCache.mode == MARKET_CACHE_MODE)
        .filter(models.ApiCache.request_hash == request_hash)
        .filter(models.ApiCache.user_id.is_(None))  # <-- IMPORTANT: shared cache row
        .filter(models.ApiCache.expires_at > now_utc_naive)
        .order_by(models.ApiCache.created_at.desc())
        .first()
    )
    return dict(row.response_json) if row else None

def _write_market_cache(db: Session, request_hash: str, response_json: dict, now_utc_naive: datetime) -> None:
    expires_at = now_utc_naive + timedelta(seconds=MARKET_CACHE_TTL_SECONDS)

    row = (
        db.query(models.ApiCache)
        .filter(models.ApiCache.mode == MARKET_CACHE_MODE)
        .filter(models.ApiCache.request_hash == request_hash)
        .filter(models.ApiCache.user_id.is_(None))  # shared cache row
        .order_by(models.ApiCache.created_at.desc())
        .first()
    )

    if row:
        row.response_json = response_json
        row.expires_at = expires_at
        db.add(row)
        db.commit()
        return

    new_row = models.ApiCache(
        user_id=None,  # IMPORTANT
        mode=MARKET_CACHE_MODE,
        request_hash=request_hash,
        response_json=response_json,
        expires_at=expires_at,
    )
    db.add(new_row)
    db.commit()

        
def _fetch_coingecko_simple_price(symbol: str) -> dict:
    if not COINGECKO_DEMO_API_KEY:
        raise RuntimeError("CoinGecko key missing")

    coin_id = COINGECKO_ID_BY_SYMBOL.get(symbol.upper())
    if not coin_id:
        raise RuntimeError("CoinGecko id not mapped for this symbol")

    url = "https://api.coingecko.com/api/v3/simple/price"
    headers = {"x-cg-demo-api-key": COINGECKO_DEMO_API_KEY}  # CoinGecko demo header :contentReference[oaicite:4]{index=4}
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    }

    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()

    d = data.get(coin_id) or {}
    return {
        "source": "coingecko",
        "symbol": symbol.upper(),
        "price_usd": d.get("usd"),
        "asof_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "market_cap_usd": d.get("usd_market_cap"),
        "volume_24h_usd": d.get("usd_24h_vol"),
        "change_24h_pct": d.get("usd_24h_change"),
        "last_updated_at": d.get("last_updated_at"),  # epoch seconds
    }

def _fetch_cmc_quote(symbol: str) -> dict:
    if not CMC_API_KEY:
        raise RuntimeError("CMC key missing")

    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"}  # :contentReference[oaicite:5]{index=5}
    params = {"symbol": symbol.upper(), "convert": "USD"}

    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, headers=headers, params=params)
        r.raise_for_status()
        payload = r.json()

    data = (payload.get("data") or {}).get(symbol.upper()) or {}
    quote = (data.get("quote") or {}).get("USD") or {}
    return {
        "source": "coinmarketcap",
        "symbol": symbol.upper(),
        "price_usd": quote.get("price"),
        "asof_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "market_cap_usd": quote.get("market_cap"),
        "volume_24h_usd": quote.get("volume_24h"),
        "change_24h_pct": quote.get("percent_change_24h"),
        "last_updated_at": quote.get("last_updated"),  # ISO string
    }

def get_market_snapshot(db: Session, symbol: str, now_utc_naive: datetime) -> tuple[dict | None, dict]:

    # Returns (snapshot, meta)
    # meta: {hit: bool, source: str|None}
    sym = (symbol or "").upper().strip()
    if not sym:
        return None, {"hit": False, "source": None}

    rh = stable_request_hash(MARKET_CACHE_MODE, f"{sym}:USD")
    cached = _read_market_cache(db=db, request_hash=rh, now_utc_naive=now_utc_naive)
    if cached is not None:
        return cached, {"hit": True, "source": cached.get("source")}

    # Try CoinGecko first (fast/simple), then fallback to CMC
    snapshot = None
    last_err = None

    try:
        snapshot = _fetch_coingecko_simple_price(sym)
    except Exception as e:
        last_err = e

    if snapshot is None:
        try:
            snapshot = _fetch_cmc_quote(sym)
        except Exception as e:
            last_err = e

    if snapshot is None:
        # no cache and both providers failed
        return None, {"hit": False, "source": None, "error": str(last_err) if last_err else "unknown"}

    _write_market_cache(db=db, request_hash=rh, response_json=snapshot, now_utc_naive=now_utc_naive)
    return snapshot, {"hit": False, "source": snapshot.get("source")}
"""

# Add near the top with other constants if you want:
SYMBOL_RESOLVE_CACHE_MODE = "symbol_resolve_v1"

TOPCOINS_CACHE_MODE = "coingecko_topcoins_v1"
#TOPCOINS_TTL_SECONDS = 24 * 3600  # 24h

# Optional: tighten query for specific tickers
NEWS_QUERY_OVERRIDES = {
    "FIL": "Filecoin FIL crypto",
    "UNI": "Uniswap UNI crypto",
    "LINK": "Chainlink LINK crypto",
    "AVAX": "Avalanche AVAX crypto",
    "SOL": "Solana SOL crypto",
}

SYMBOL_TO_NEWS_QUERY = {
    "FIL": "Filecoin FIL",
    # add more later if needed
}

def resolve_symbol_via_coingecko(db: Session, query: str, now_utc_naive: datetime) -> dict:
    """
    Resolve a user query (ticker OR coin name OR typo) using CoinGecko /search.
    Returns:
      {"coingecko_id": str|None, "matched_name": str|None, "market_cap_rank": int|None,
       "resolved_symbol": str|None, "score": float}
    """
    q_raw = (query or "").strip()
    if not q_raw:
        return {
            "coingecko_id": None,
            "matched_name": None,
            "market_cap_rank": None,
            "resolved_symbol": None,
            "score": 0.0,
        }

    # 1) Normal CoinGecko search
    url = "https://api.coingecko.com/api/v3/search"
    params = {"query": q_raw}

    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
    except Exception:
        return {
            "coingecko_id": None,
            "matched_name": None,
            "market_cap_rank": None,
            "resolved_symbol": None,
            "score": 0.0,
        }

    coins = (payload or {}).get("coins") or []

    # ✅ If we got results from CoinGecko, pick the best one deterministically
    if coins:
        q_lower = q_raw.lower().strip()
        q_upper = q_raw.upper().strip()

        def sim(a: str, b: str) -> float:
            a = (a or "").lower().strip()
            b = (b or "").lower().strip()
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a, b).ratio()

        best = None
        best_score = -1.0

        for c in coins[:25]:
            name = c.get("name") or ""
            sym = (c.get("symbol") or "").upper()
            rank = c.get("market_cap_rank")

            # Similarity based on name & symbol
            s = max(sim(q_lower, name), sim(q_upper, sym))

            # Small bonus if rank exists and is good (lower is better)
            if isinstance(rank, int) and rank > 0:
                s += max(0.0, 0.20 - (rank / 5000.0))  # tiny bonus, never huge

            if s > best_score:
                best_score = s
                best = c

        if not best:
            return {
                "coingecko_id": None,
                "matched_name": None,
                "market_cap_rank": None,
                "resolved_symbol": None,
                "score": 0.0,
            }

        return {
            "coingecko_id": best.get("id"),
            "matched_name": best.get("name"),
            "market_cap_rank": best.get("market_cap_rank"),
            "resolved_symbol": (best.get("symbol") or "").upper() or None,
            "score": float(best_score),
        }

    # 2) If CoinGecko search returns nothing (typos), fallback to fuzzy match vs top coins list
    top = _get_coingecko_topcoins_cached(db=db, now_utc_naive=now_utc_naive, per_page=250)
    if not top:
        return {
            "coingecko_id": None,
            "matched_name": None,
            "market_cap_rank": None,
            "resolved_symbol": None,
            "score": 0.0,
        }

    q_lower = q_raw.lower().strip()
    q_upper = q_raw.upper().strip()

    def sim(a: str, b: str) -> float:
        a = (a or "").lower().strip()
        b = (b or "").lower().strip()
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    best = None
    best_score = -1.0

    for c in top:
        name = c.get("name") or ""
        sym = c.get("symbol") or ""
        s = max(sim(q_lower, name), sim(q_upper, sym))
        if s > best_score:
            best_score = s
            best = c

    if not best or best_score < 0.80:
        return {
            "coingecko_id": None,
            "matched_name": None,
            "market_cap_rank": None,
            "resolved_symbol": None,
            "score": float(best_score),
        }

    return {
        "coingecko_id": best.get("id"),
        "matched_name": best.get("name"),
        "market_cap_rank": None,  # unknown from markets list unless you add it
        "resolved_symbol": (best.get("symbol") or "").upper() or None,
        "score": float(1.0 + best_score),  # bump so confidence passes
    }

def get_symbol_resolve_cached(db: Session, symbol: str, now_utc_naive: datetime) -> dict:
    """
    Cache wrapper around resolve_symbol_via_coingecko().
    Caches by normalized lowercase query (works for tickers and names).
    """
    q = (symbol or "").strip()
    if not q:
        return {"coingecko_id": None, "matched_name": None, "market_cap_rank": None, "resolved_symbol": None}

    q_norm = re.sub(r"\s+", " ", q).strip().lower()
    rh = stable_request_hash(SYMBOL_RESOLVE_CACHE_MODE, q_norm)

    cached = read_cache(
        db=db,
        user_id=None,
        mode=SYMBOL_RESOLVE_CACHE_MODE,
        request_hash=rh,
        now_utc_naive=now_utc_naive,
    )
    if cached is not None:
        # ensure all keys exist
        cached.setdefault("resolved_symbol", None)
        cached.setdefault("coingecko_id", None)
        cached.setdefault("matched_name", None)
        cached.setdefault("market_cap_rank", None)
        return cached

    resolved = resolve_symbol_via_coingecko(db=db, query=q, now_utc_naive=now_utc_naive)

    write_cache(
        db=db,
        user_id=None,
        mode=SYMBOL_RESOLVE_CACHE_MODE,
        request_hash=rh,
        response_json=resolved,
        now_utc_naive=now_utc_naive,
    )
    return resolved

def _get_coingecko_topcoins_cached(db: Session, now_utc_naive: datetime, *, per_page: int = 250) -> list[dict]:
    """
    Fetch top coins by market cap from CoinGecko and cache for 24h.
    Returns list like: [{"id": "...", "symbol": "...", "name": "..."}]
    """
    rh = stable_request_hash(TOPCOINS_CACHE_MODE, f"per_page={per_page}")

    cached = read_cache(
        db=db,
        user_id=None,
        mode=TOPCOINS_CACHE_MODE,
        request_hash=rh,
        now_utc_naive=now_utc_naive,
    )
    if cached and isinstance(cached.get("items"), list):
        return cached["items"]

    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": per_page,
        "page": 1,
        "sparkline": "false",
    }

    items: list[dict] = []
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json() or []
            for c in data:
                items.append({
                    "id": c.get("id"),
                    "symbol": (c.get("symbol") or "").upper(),
                    "name": c.get("name"),
                })
    except Exception:
        # if live fetch fails, return empty (no fallback)
        items = []

    write_cache(
        db=db,
        user_id=None,
        mode=TOPCOINS_CACHE_MODE,
        request_hash=rh,
        response_json={"items": items},
        now_utc_naive=now_utc_naive,
    )

    return items

def _looks_relevant_news(items: list[dict], sym: str) -> bool:
    sym = (sym or "").upper().strip()
    if not items:
        return False

    keywords = {sym.lower()}
    q = SYMBOL_TO_NEWS_QUERY.get(sym)
    if q:
        for part in q.split():
            keywords.add(part.lower())

    blob = " ".join(
        ((i.get("title") or "") + " " + (i.get("summary") or "")).lower()
        for i in items
    )
    return any(k in blob for k in keywords)

# --- News hardening: filter out non-crypto headlines ---
CRYPTO_NEWS_KEYWORDS = {
    "crypto", "cryptocurrency", "token", "coin", "blockchain",
    "exchange", "binance", "coinbase", "dex", "airdrop",
    "defi", "staking", "etf", "sec", "wallet", "on-chain", "onchain",
}

def _has_ticker_word_boundary(title: str, sym: str) -> bool:
    """
    True only if SYM appears as a standalone token, not as a substring.
    Example: AAAAA should NOT match MUSTAAAAAARD.
    """
    if not sym:
        return False
    # \b works for letters/numbers boundaries in most titles
    return re.search(rf"\b{re.escape(sym.lower())}\b", (title or "").lower()) is not None


def _has_phrase(title: str, phrase: str) -> bool:
    if not phrase:
        return False
    return phrase.lower() in (title or "").lower()


def _is_probably_crypto_headline(title: str, sym: str, matched_name: str | None = None) -> bool:
    t = (title or "").lower()
    sym_u = (sym or "").upper().strip()
    name = (matched_name or "").strip()

    # 1) must contain crypto-ish keyword
    if not any(k in t for k in CRYPTO_NEWS_KEYWORDS):
        return False

    # 2) ticker must match as a real token (word boundary), not substring
    if _has_ticker_word_boundary(title, sym_u):
        return True

    # 3) if no ticker match, allow matched_name only if it's not suspiciously generic
    # (this avoids letting "mustard" style matches through when ticker isn't present)
    if name and len(name) >= 4:
        # block very generic / non-crypto names that often collide
        blocked_names = {"mustard", "sauce", "heinz"}
        if name.lower() in blocked_names:
            return False

        # require phrase match
        if _has_phrase(title, name):
            return True

    return False

# Words we should ignore when trying to guess an asset from the message
RESOLVE_STOPWORDS = {
    "price", "today", "now", "chart", "market", "cap", "mcap", "volume", "vol",
    "rsi", "macd", "ema", "sma", "vwap", "atr", "bollinger", "stoch", "adx",
    "analysis", "update", "news", "doing", "whats", "what's", "happening",
    "on", "in", "for", "to", "a", "the", "is", "are", "of", "and", "or", "with",
}

def _extract_asset_candidates_from_message(message: str) -> list[str]:
    """
    Build candidate phrases like:
      "filecoin", "file coin", "bitcoin", "bitcoion"
    We try:
      - single words
      - 2-word phrases (to catch "file coin")
    """
    m = (message or "").strip()
    if not m:
        return []

    # remove punctuation but keep spaces
    clean = re.sub(r"[^A-Za-z0-9\s]", " ", m)
    words = [w.strip() for w in clean.split() if w.strip()]
    if not words:
        return []

    # filter stopwords + very short words
    keep = []
    for w in words:
        wl = w.lower()
        if wl in RESOLVE_STOPWORDS:
            continue
        if len(w) < 3:  # avoid "on", "1h", etc
            continue
        # avoid indicator acronyms being treated as assets
        if w.upper() in INDICATOR_SYMBOL_STOPLIST:
            continue
        keep.append(w)

    if not keep:
        return []

    cands: list[str] = []

    # 2-word phrases first (higher chance of being a name)
    for i in range(len(keep) - 1):
        cands.append(f"{keep[i]} {keep[i+1]}")

    # then single words
    cands.extend(keep)

    # de-dup preserve order
    seen = set()
    out = []
    for c in cands:
        c_norm = c.lower().strip()
        if c_norm not in seen:
            seen.add(c_norm)
            out.append(c)
    return out[:8]  # limit


def resolve_symbol_from_message(db: Session, message: str, now_utc_naive: datetime) -> dict:
    """
    Try to infer the asset from the full user message using CoinGecko search.
    Returns:
      {"ok": bool, "symbol": str|None, "meta": dict}
    """
    candidates = _extract_asset_candidates_from_message(message)
    if not candidates:
        return {"ok": False, "symbol": None, "meta": {"reason": "no_candidates"}}

    best = None
    best_score = -1.0

    for q in candidates:
        resolved = get_symbol_resolve_cached(db=db, symbol=q, now_utc_naive=now_utc_naive) or {}
        sym = (resolved.get("resolved_symbol") or "").upper().strip()
        score = float(resolved.get("score") or 0.0)
        rank = resolved.get("market_cap_rank")

        if sym and score > best_score:
            best_score = score
            best = resolved

    if not best:
        return {"ok": False, "symbol": None, "meta": {"reason": "no_resolve_match"}}

    sym = (best.get("resolved_symbol") or "").upper().strip()
    rank = best.get("market_cap_rank")
    score = float(best.get("score") or 0.0)

    # Hard safety:
    # - require a symbol
    # - require rank not insane OR score very high
    if not sym:
        return {"ok": False, "symbol": None, "meta": {"reason": "no_symbol"}}

    # "product-feel" threshold:
    # If rank is unknown, demand higher score.
    if isinstance(rank, int):
        if rank > 3000 and score < 1.10:
            return {"ok": False, "symbol": None, "meta": {"reason": "rank_too_low", "rank": rank, "score": score}}
    else:
        if score < 1.15:
            return {"ok": False, "symbol": None, "meta": {"reason": "low_confidence", "rank": rank, "score": score}}

    return {
        "ok": True,
        "symbol": sym,
        "meta": {
            "matched_name": best.get("matched_name"),
            "rank": rank,
            "score": score,
            "coingecko_id": best.get("coingecko_id"),
        }
    }

def _is_valid_token_symbol(db: Session, sym: str, now_utc_naive: datetime, *, max_rank: int = 3000) -> tuple[bool, dict]:
    sym = (sym or "").strip()
    if not sym:
        return False, {"reason": "empty_symbol"}

    # ✅ resolve+cache on demand
    resolved = get_symbol_resolve_cached(db=db, symbol=sym, now_utc_naive=now_utc_naive) or {}

    coingecko_id = resolved.get("coingecko_id")
    rank = resolved.get("market_cap_rank")
    matched_name = resolved.get("matched_name")
    resolved_symbol = resolved.get("resolved_symbol")

    if not coingecko_id or not resolved_symbol:
        return False, {"reason": "no_coingecko_match", "matched_name": matched_name, "rank": rank}

    # If CoinGecko gave us an id + symbol but rank is missing (can happen in fallback),
    # allow it as valid.
    if rank is None:
        return True, {
            "reason": "ok_no_rank",
            "matched_name": matched_name,
            "rank": rank,
            "coingecko_id": coingecko_id,
            "resolved_symbol": resolved_symbol,
        }
    
    if not isinstance(rank, int) or rank > max_rank:
        return False, {"reason": "rank_too_low", "matched_name": matched_name, "rank": rank, "max_rank": max_rank}


    return True, {"reason": "ok", "matched_name": matched_name, "rank": rank, "coingecko_id": coingecko_id, "resolved_symbol": resolved_symbol}


def _ensure_recent_news_for_symbol(db: Session, symbol: str, limit: int = 5) -> list[dict]:
    req_id = uuid.uuid4().hex[:10]
    sym = (symbol or "").upper().strip()

    newslog.warning("[NEWSDBG %s] start sym=%r limit=%s", req_id, sym, limit)

    if not sym:
        newslog.warning("[NEWSDBG %s] exit: empty sym", req_id)
        return []

    # --- DB sanity snapshot ---
    try:
        row = db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE symbol IS NULL) AS null_symbol,
              COUNT(*) FILTER (WHERE symbol = '')   AS empty_symbol,
              COUNT(*) FILTER (WHERE symbol = :sym) AS sym_count,
              COUNT(*) AS total
            FROM news_items
        """), {"sym": sym}).mappings().one()
        newslog.warning("[NEWSDBG %s] news_items counts: sym=%s sym_count=%s empty_symbol=%s null_symbol=%s total=%s",
                        req_id, sym, row["sym_count"], row["empty_symbol"], row["null_symbol"], row["total"])
    except Exception as e:
        newslog.exception("[NEWSDBG %s] DB count query failed: %r", req_id, e)

    # 1) Return DB news ONLY if symbol-tagged rows exist
    items = get_top_news_strict(db=db, symbol=sym, limit=limit)
    newslog.warning("[NEWSDBG %s] get_top_news_strict returned: %s", req_id, len(items or []))
    
    # ✅ Only return if we already have enough
    if items and len(items) >= limit:
        try:
            syms = [(getattr(it, "symbol", None), (getattr(it, "title", "") or "")[:60]) for it in items[:5]]
            newslog.warning("[NEWSDBG %s] returning STRICT DB items sample: %r", req_id, syms)
        except Exception:
            pass
        return news_items_to_dicts(items)
    
    # otherwise: fall through to live fetch to top-up

    # 2) Guard: check resolver cache for validity
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    q_norm = sym.lower().strip()
    rh = stable_request_hash(SYMBOL_RESOLVE_CACHE_MODE, q_norm)

    cached = read_cache(
        db=db,
        user_id=None,
        mode=SYMBOL_RESOLVE_CACHE_MODE,
        request_hash=rh,
        now_utc_naive=now_utc_naive,
    ) or {}

    coingecko_id = cached.get("coingecko_id")
    rank = cached.get("market_cap_rank")

    newslog.warning("[NEWSDBG %s] resolver cache: coingecko_id=%r rank=%r matched_name=%r",
                    req_id, coingecko_id, rank, cached.get("matched_name"))

    if not coingecko_id:
        newslog.warning("[NEWSDBG %s] exit: blocked (no coingecko_id)", req_id)
        return []

    if not isinstance(rank, int) or rank > 3000:
        newslog.warning("[NEWSDBG %s] exit: blocked (rank invalid/too high) rank=%r", req_id, rank)
        return []


    matched_name = (cached.get("matched_name") or "").strip()
    # --- Build a more crypto-specific query to avoid junk results (e.g., mustard sauce) ---
    if sym in NEWS_QUERY_OVERRIDES:
        query = NEWS_QUERY_OVERRIDES[sym]
    elif matched_name:
        # Quote matched_name to force phrase match, and add strong crypto intent terms
        query = f"\"{matched_name}\" {sym} crypto token price"
    else:
        query = f"{sym} crypto token price"

    newslog.warning("[NEWSDBG %s] live fetch query=%r", req_id, query)

    try:
        fetched = fetch_google_news(query)
        newslog.warning("[NEWSDBG %s] live fetch returned items=%s", req_id, len(fetched or []))
        
        # ✅ Filter out non-crypto junk
        filtered = []
        for it in (fetched or []):
            title = (it.get("title") or "")
            if _is_probably_crypto_headline(title, sym, matched_name):
                filtered.append(it)
        
        newslog.warning(
            "[NEWSDBG %s] filtered items=%s (dropped=%s)",
            req_id,
            len(filtered),
            (len(fetched or []) - len(filtered)),
        )
        
        if filtered:
            newslog.warning("[NEWSDBG %s] upsert_news_items start sym=%r", req_id, sym)
            upsert_news_items(db=db, symbol=sym, items=filtered)
            newslog.warning("[NEWSDBG %s] upsert_news_items done", req_id)
        else:
            newslog.warning("[NEWSDBG %s] no crypto-relevant headlines after filtering", req_id)

    except Exception as e:
        newslog.exception("[NEWSDBG %s] live fetch/upsert failed: %r", req_id, e)
        return []

    items2 = get_top_news_strict(db=db, symbol=sym, limit=limit)
    newslog.warning("[NEWSDBG %s] post-upsert get_top_news_strict returned=%s", req_id, len(items2 or []))
    return news_items_to_dicts(items2) 

# -----------------------
# Helpers
# -----------------------

def _is_admin_or_owner(user: models.User) -> bool:
    return user.role in ("admin", "owner")


def _client_ip(req: Request) -> str | None:
    if req.client:
        return req.client.host
    return None


def log_abuse(
    *,
    db: Session,
    req: Request,
    user: models.User | None,
    mode: str | None,
    status_code: int,
    reason: str,
    detail: str | None = None,
) -> None:
    ev = models.AbuseEvent(
        user_id=getattr(user, "id", None),
        email=getattr(user, "email", None),
        ip=_client_ip(req),
        user_agent=req.headers.get("user-agent"),
        endpoint=str(req.url.path),
        method=req.method,
        mode=mode,
        status_code=status_code,
        reason=reason,
        detail=detail,
    )
    db.add(ev)
    db.commit()


def get_entitlements_or_500(
    *,
    db: Session,
    req: Request,
    user: models.User,
    mode_for_log: str,
) -> models.PlanEntitlement:
    ent = db.execute(
        select(models.PlanEntitlement).where(models.PlanEntitlement.plan_id == user.plan_id)
    ).scalar_one_or_none()

    if not ent:
        log_abuse(
            db=db,
            req=req,
            user=user,
            mode=mode_for_log,
            status_code=500,
            reason="missing_entitlements",
            detail="No plan_entitlements row for plan_id",
        )
        raise HTTPException(status_code=500, detail="Missing plan entitlements.")

    return ent


# -----------------------
# Phase 5A: short-term context window
# -----------------------

def load_short_term_context_window(
    *,
    db: Session,
    thread_id: str,
    ent: models.PlanEntitlement,
    bypass: bool,
) -> tuple[list[dict[str, str]], dict]:
    msgs_limit = int(getattr(ent, "context_messages_limit", 20) or 20)
    chars_limit = int(getattr(ent, "context_chars_limit", 8000) or 8000)

    if bypass:
        msgs_limit = max(msgs_limit, 1000)
        chars_limit = max(chars_limit, 500_000)

    if msgs_limit <= 0:
        msgs_limit = 1
    if chars_limit <= 0:
        chars_limit = 1

    rows = db.execute(
        select(models.Message)
        .where(models.Message.thread_id == thread_id)
        .order_by(models.Message.created_at.desc(), models.Message.id.desc())
        .limit(msgs_limit)
    ).scalars().all()

    rows.reverse()  # oldest -> newest

    kept_reversed: list[models.Message] = []
    total_chars = 0

    for m in reversed(rows):  # newest -> oldest
        content = (m.content or "")
        c = len(content)
        if total_chars + c > chars_limit:
            break
        kept_reversed.append(m)
        total_chars += c

    kept_reversed.reverse()

    window: list[dict[str, str]] = []
    for m in kept_reversed:
        if m.role not in ("user", "assistant"):
            continue
        window.append({"role": m.role, "content": m.content or ""})

    meta = {
        "context_messages_used": len(window),
        "context_chars_used": total_chars,
        "context_messages_limit": msgs_limit,
        "context_chars_limit": chars_limit,
    }
    return window, meta


# -----------------------
# Phase 5B: long-term summary (READ + explicit write only)
# -----------------------

def can_use_long_term_summary(ent: models.PlanEntitlement, bypass: bool) -> bool:
    return bypass or bool(getattr(ent, "long_term_memory", False))


def load_thread_summary(
    *,
    db: Session,
    thread_id: str,
) -> models.ThreadSummary | None:
    return db.execute(
        select(models.ThreadSummary).where(models.ThreadSummary.thread_id == thread_id)
    ).scalar_one_or_none()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: Mode = "chat"
    thread_id: str | None = None


class UpsertSummaryRequest(BaseModel):
    thread_id: str
    summary_text: str = Field(min_length=1, max_length=20000)
    covered_until_message_id: str | None = None


def utc_bucket_starts_naive() -> tuple[datetime, datetime, datetime, datetime]:
    now = datetime.now(timezone.utc)

    minute_start_aware = now.replace(second=0, microsecond=0)
    day_start_aware = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    month_start_aware = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    return (
        now,
        minute_start_aware.replace(tzinfo=None),
        day_start_aware.replace(tzinfo=None),
        month_start_aware.replace(tzinfo=None),
    )


def remaining(limit: int | None, used: int) -> int | None:
    if limit is None:
        return None
    r = limit - used
    return r if r > 0 else 0


def has_mode(ent: models.PlanEntitlement, mode: Mode) -> bool:
    col = MODE_TO_COLUMN.get(mode)
    if not col:
        return False
    return bool(getattr(ent, col, False))


def enforce_mode_and_quota(
    *,
    db: Session,
    req: Request,
    user: models.User,
    mode: Mode,
) -> dict:
    bypass = _is_admin_or_owner(user)

    ent = db.execute(
        select(models.PlanEntitlement).where(models.PlanEntitlement.plan_id == user.plan_id)
    ).scalar_one_or_none()

    if not ent:
        log_abuse(
            db=db, req=req, user=user, mode=mode,
            status_code=500, reason="missing_entitlements", detail="No plan_entitlements row for plan_id"
        )
        raise HTTPException(status_code=500, detail="Missing plan entitlements.")

    if not bypass and not has_mode(ent, mode):
        log_abuse(
            db=db, req=req, user=user, mode=mode,
            status_code=403, reason="feature_not_allowed", detail=f"mode={mode}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature not allowed for your plan.",
        )

    per_minute_limit = None if bypass else getattr(ent, "per_minute_messages_limit", None)
    daily_limit = None if bypass else ent.daily_messages_limit
    monthly_limit = None if bypass else ent.monthly_messages_limit

    now_aware, minute_start, day_start, month_start = utc_bucket_starts_naive()

    tripped_reason: str | None = None
    tripped_status: int | None = None
    tripped_detail: str | None = None

    try:
        minute_row = db.execute(
            select(models.UsageCounter)
            .where(
                models.UsageCounter.user_id == user.id,
                models.UsageCounter.period_type == "minute",
                models.UsageCounter.period_start == minute_start,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if not minute_row:
            minute_row = models.UsageCounter(
                user_id=user.id,
                period_type="minute",
                period_start=minute_start,
                messages_used=0,
            )
            db.add(minute_row)
            db.flush()

        day_row = db.execute(
            select(models.UsageCounter)
            .where(
                models.UsageCounter.user_id == user.id,
                models.UsageCounter.period_type == "day",
                models.UsageCounter.period_start == day_start,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if not day_row:
            day_row = models.UsageCounter(
                user_id=user.id,
                period_type="day",
                period_start=day_start,
                messages_used=0,
            )
            db.add(day_row)
            db.flush()

        month_row = db.execute(
            select(models.UsageCounter)
            .where(
                models.UsageCounter.user_id == user.id,
                models.UsageCounter.period_type == "month",
                models.UsageCounter.period_start == month_start,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if not month_row:
            month_row = models.UsageCounter(
                user_id=user.id,
                period_type="month",
                period_start=month_start,
                messages_used=0,
            )
            db.add(month_row)
            db.flush()

        if per_minute_limit is not None and minute_row.messages_used >= per_minute_limit:
            tripped_reason = "per_minute_quota_exceeded"
            tripped_status = 429
            tripped_detail = f"limit={per_minute_limit}"
            raise HTTPException(status_code=429, detail="Per-minute message quota exceeded.")

        if daily_limit is not None and day_row.messages_used >= daily_limit:
            tripped_reason = "daily_quota_exceeded"
            tripped_status = 429
            tripped_detail = f"limit={daily_limit}"
            raise HTTPException(status_code=429, detail="Daily message quota exceeded.")

        if monthly_limit is not None and month_row.messages_used >= monthly_limit:
            tripped_reason = "monthly_quota_exceeded"
            tripped_status = 429
            tripped_detail = f"limit={monthly_limit}"
            raise HTTPException(status_code=429, detail="Monthly message quota exceeded.")

        minute_row.messages_used += 1
        day_row.messages_used += 1
        month_row.messages_used += 1
        db.commit()

        return {
            "bypass": bypass,
            "role": user.role,
            "utc_now": now_aware.isoformat(),

            "minute_used": minute_row.messages_used,
            "minute_limit": per_minute_limit,

            "day_used": day_row.messages_used,
            "day_limit": daily_limit,

            "month_used": month_row.messages_used,
            "month_limit": monthly_limit,
        }

    except HTTPException as e:
        db.rollback()
        if tripped_reason and tripped_status:
            try:
                log_abuse(
                    db=db,
                    req=req,
                    user=user,
                    mode=mode,
                    status_code=tripped_status,
                    reason=tripped_reason,
                    detail=tripped_detail,
                )
            except Exception:
                db.rollback()
        raise e

    except Exception:
        db.rollback()
        raise


# -----------------------
# Phase 5B: GET summary (paid only) + POST summary gate order fix
# -----------------------

def _require_long_term_enabled_or_403(
    *,
    db: Session,
    req: Request,
    user: models.User,
    bypass: bool,
    mode_for_log: str,
) -> models.PlanEntitlement:
    ent = get_entitlements_or_500(db=db, req=req, user=user, mode_for_log=mode_for_log)
    if not can_use_long_term_summary(ent, bypass):
        # Plan gate happens BEFORE ownership checks (requested behavior)
        raise HTTPException(status_code=403, detail="Long-term memory not enabled for your plan.")
    return ent


@router.get("/chat/summary")
def get_thread_summary(
    thread_id: str = Query(..., description="Thread ID"),
    request: Request = None,  # FastAPI injects it
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    bypass = _is_admin_or_owner(current_user)

    # 1) Plan gate FIRST (requested behavior)
    _require_long_term_enabled_or_403(
        db=db,
        req=request,
        user=current_user,
        bypass=bypass,
        mode_for_log="chat_summary_get",
    )

    # 2) Then thread existence / ownership
    t = db.get(models.Thread, thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found.")
    if not bypass and t.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed.")

    ts = load_thread_summary(db=db, thread_id=thread_id)
    if not ts:
        return {
            "ok": True,
            "thread_id": thread_id,
            "summary_text": None,
            "covered_until_message_id": None,
            "updated_at": None,
        }

    return {
        "ok": True,
        "thread_id": thread_id,
        "summary_text": ts.summary_text,
        "covered_until_message_id": ts.covered_until_message_id,
        "updated_at": ts.updated_at.isoformat() if ts.updated_at else None,
    }


@router.post("/chat/summary")
def upsert_thread_summary(
    payload: UpsertSummaryRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    bypass = _is_admin_or_owner(current_user)

    # 1) Plan gate FIRST (requested behavior)
    _require_long_term_enabled_or_403(
        db=db,
        req=request,
        user=current_user,
        bypass=bypass,
        mode_for_log="chat_summary_upsert",
    )

    # 2) Then thread existence / ownership
    t = db.get(models.Thread, payload.thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found.")
    if not bypass and t.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed.")

    existing = load_thread_summary(db=db, thread_id=payload.thread_id)

    if existing:
        existing.summary_text = payload.summary_text
        existing.covered_until_message_id = payload.covered_until_message_id
        existing.updated_at = datetime.utcnow()
    else:
        s = models.ThreadSummary(
            thread_id=payload.thread_id,
            summary_text=payload.summary_text,
            covered_until_message_id=payload.covered_until_message_id,
            updated_at=datetime.utcnow(),
        )
        db.add(s)

    db.commit()
    return {"ok": True, "thread_id": payload.thread_id}


@router.post("/chat")
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    bypass = _is_admin_or_owner(current_user)

    raw_msg = (payload.message or "").strip()
    display_msg = strip_greeting_prefix(raw_msg)

    # 1) Resolve/create thread
    thread_id = payload.thread_id
    if thread_id:
        t = db.get(models.Thread, thread_id)
        if not t or t.user_id != current_user.id:
            log_abuse(
                db=db, req=request, user=current_user, mode=payload.mode,
                status_code=404, reason="thread_not_found", detail=f"thread_id={thread_id}"
            )
            raise HTTPException(status_code=404, detail="Thread not found.")
    else:
        t = models.Thread(user_id=current_user.id, title="New chat")
        db.add(t)
        db.commit()
        db.refresh(t)
        thread_id = t.id

    # 2) Cache lookup first (so cache hits don't burn quota)
    cache_hit = False
    assistant_text: str | None = None

    rh: str | None = None
    if payload.mode in CACHEABLE_MODES:
        rh = stable_request_hash(payload.mode, raw_msg)  # use raw_msg
        cached = read_cache(
            db,
            user_id=str(current_user.id),
            mode=payload.mode,
            request_hash=rh,
            now_utc_naive=now_utc_naive,
        )
        if cached is not None:
            cache_hit = True
            assistant_text = str(cached.get("assistant", ""))

    # 3) Quotas only on cache miss
    info = None
    if not cache_hit:
        info = enforce_mode_and_quota(db=db, req=request, user=current_user, mode=payload.mode)

    # 4) Store user message (always)
    user_msg = models.Message(thread_id=thread_id, role="user", content=raw_msg)  # store raw_msg
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    m_norm = raw_msg.lower()
    YES_WORDS = {"yes", "y", "yeah", "yep", "sure", "ok", "okay"}

    # --- YES followup handler (full indicators) ---
    if m_norm in YES_WORDS:
        if getattr(t, "pending_followup_type", None) == "indicators_full":
            data = (t.pending_followup_payload or {})
            sym = (data.get("sym") or "").upper().strip()
            timeframe = (data.get("tf") or "1h").lower().strip()
            asked = (data.get("asked") or f"{sym} indicators on {timeframe}").strip()

            if sym:
                plan_code = (
                    db.execute(select(models.Plan.code).where(models.Plan.id == current_user.plan_id))
                    .scalar_one_or_none()
                )
                plan_code = (plan_code or "").lower()
                ent_for_tools = SimpleNamespace(plan_slug=plan_code)

                out, meta = get_indicators_basic(
                    db=db,
                    symbol=sym,
                    timeframe=timeframe,
                    now_utc_naive=now_utc_naive,
                    ent=ent_for_tools,
                    bypass=bypass,
                )

                if out is not None:
                    snap, snap_meta = get_market_snapshot(db=db, symbol=sym, now_utc_naive=now_utc_naive)

                    # narrative should be based on the "asked" text (not "yes")
                    narr = generate_crypto_narrative(
                        user_message=asked,
                        symbol=sym,
                        timeframe=timeframe,
                        snapshot=snap,
                        indicators=out,
                    )

                    assistant_text = format_indicators_contract(
                        user_message=asked,  # show the actual question
                        symbol=sym,
                        timeframe=timeframe,
                        snapshot=snap,
                        snapshot_meta=snap_meta,
                        indicators=out,
                        indicators_meta=meta,
                        focus="full",
                        include_yes_hint=False,
                        narrative_text=narr,
                    )

                    # clear followup so "yes" doesn't repeat forever
                    t.pending_followup_type = None
                    t.pending_followup_payload = None
                    db.add(t)
                    db.commit()

                    assistant_msg = models.Message(thread_id=thread_id, role="assistant", content=assistant_text)
                    db.add(assistant_msg)
                    db.commit()

                    return {
                        "ok": True,
                        "thread_id": str(thread_id),
                        "mode": payload.mode,
                        "assistant": _extract_display(assistant_text),
                        "role": "assistant",
                        "bypass": bypass,
                        "utc": {"now": now_utc_naive.isoformat() + "Z"},
                        "cache": {"hit": False},
                    }

    # 5A) Load context window from DB
    ent = get_entitlements_or_500(db=db, req=request, user=current_user, mode_for_log=str(payload.mode))

    context_window, context_meta = load_short_term_context_window(
        db=db,
        thread_id=thread_id,
        ent=ent,
        bypass=bypass,
    )

    # 5B) Load summary from DB (paid only), inject as separate system block
    summary_meta = {"included": False, "updated_at": None}
    summary_block = None

    if can_use_long_term_summary(ent, bypass):
        ts = load_thread_summary(db=db, thread_id=thread_id)
        if ts and (ts.summary_text or "").strip():
            summary_block = {
                "role": "system",
                "content": f"Thread summary (memory):\n{ts.summary_text.strip()}",
            }
            summary_meta = {
                "included": True,
                "updated_at": ts.updated_at.isoformat() if ts.updated_at else None,
            }

    system_block = {
        "role": "system",
        "content": "You are WSAI — a crypto strategist, risk manager, and operator desk. Be concise, high-signal, and trader-native. Every response should help the user decide, not just understand.",
    }

    prompt_messages = [system_block]
    if summary_block is not None:
        prompt_messages.append(summary_block)
    prompt_messages.extend(context_window)

    # 6A-1) Intent routing (use raw_msg consistently)
    intent = classify_intent(raw_msg)
    route = None
    action = intent["intent"]
    
    # ✅ If it's crypto but no symbols were extracted, try resolving from message (names/typos)
    if intent["intent"] == "crypto" and not intent["symbols"]:
        r = resolve_symbol_from_message(db=db, message=raw_msg, now_utc_naive=now_utc_naive)
        if r.get("ok") and r.get("symbol"):
            intent["symbols"] = [r["symbol"]]
    
    if intent["intent"] == "crypto":
        route = route_crypto_action(raw_msg, intent["symbols"])
        action = route["action"]


    # 6) Produce assistant response
    out = None
    meta = {}
    timeframe = None

    # ✅ unified symbol extraction (works for all actions)
    sym = (route or {}).get("symbol") or (intent["symbols"][0] if intent.get("symbols") else None)
    sym = (sym or "").upper().strip()

    if assistant_text is None:
        if intent["intent"] == "small_talk":
            assistant_text = (
                "WSAI here.\n\n"
                "I'm your crypto decision desk -- market structure, momentum, key levels, risk framing, "
                "and trade implications. No fluff, no hype.\n\n"
                "Give me a coin and I'll give you a brief. (e.g., BTC, ETH, SOL)"
            )
    
        elif intent["intent"] == "out_of_scope":
            assistant_text = (
                "I only cover crypto -- coins, indicators, structure, risk.\n\n"
                "Tell me a ticker and what you need (price, analysis, setup, levels) and I'll deliver."
            )
    
        elif action == "ask_symbol":
            assistant_text = "Which coin? Give me a ticker like BTC, ETH, SOL."
    
        elif action == "education":
            out = generate_education(raw_msg)  # use raw_msg
            assistant_text = out.strip() if out else "I couldn't generate an explanation right now. Try again."
    
        elif action == "price_question":
            sym = (route or {}).get("symbol") or (intent["symbols"][0] if intent["symbols"] else None)
            sym = (sym or "").upper().strip()
        
            if not sym:
                assistant_text = "Which coin? Give me a ticker or name like BTC or Bitcoin."
            else:
                ok_sym, sym_meta = _is_valid_token_symbol(db, sym, now_utc_naive, max_rank=3000)
                if not ok_sym:
                    assistant_text = (
                        f"I can’t verify `{sym}` as a real token (CoinGecko match: {sym_meta.get('matched_name')}, "
                        f"rank={sym_meta.get('rank')}).\n\n"
                        "Try a known ticker like BTC, ETH, SOL, FIL, LINK, AVAX."
                    )
                else:
                    sym = (sym_meta.get("resolved_symbol") or sym).upper().strip()
        
                    snap, snap_meta = get_market_snapshot(db=db, symbol=sym, now_utc_naive=now_utc_naive)
        
                    if snap is None or snap.get("price_usd") is None:
                        err = (snap_meta or {}).get("error")
                        assistant_text = (
                            f"I couldn’t fetch a reliable live price for {sym}."
                            + (f" ({err})" if err else "")
                        )
                    else:
                        narr = generate_crypto_narrative(
                            user_message=raw_msg,
                            symbol=sym,
                            timeframe=None,
                            snapshot=snap,
                            indicators=None,
                        )
        
                        assistant_text = format_price_contract(
                            user_message=display_msg,
                            symbol=sym,
                            snapshot=snap,
                            snapshot_meta=snap_meta,
                            narrative_text=narr,
                        )

        elif action == "market_brief":
            sym = (route or {}).get("symbol") or (intent["symbols"][0] if intent["symbols"] else None)
            sym = (sym or "").upper().strip()
        
            if not sym:
                assistant_text = "Which coin? Give me a ticker or name like BTC or Bitcoin."
            else:
                ok_sym, sym_meta = _is_valid_token_symbol(db, sym, now_utc_naive, max_rank=3000)
                if not ok_sym:
                    assistant_text = (
                        f"I can’t verify `{sym}` as a real token (CoinGecko match: {sym_meta.get('matched_name')}, "
                        f"rank={sym_meta.get('rank')}).\n\n"
                        "Try a known ticker like BTC, ETH, SOL, FIL, LINK, AVAX."
                    )
                else:
                    sym = (sym_meta.get("resolved_symbol") or sym).upper().strip()
        
                    snap, snap_meta = get_market_snapshot(db=db, symbol=sym, now_utc_naive=now_utc_naive)
        
                    # News fetch is already hardened inside _ensure_recent_news_for_symbol with strict resolver checks
                    items_dicts = _ensure_recent_news_for_symbol(db=db, symbol=sym, limit=5)
        
                    narr = None
                    if snap is not None:
                        narr = generate_market_brief(
                            user_message=raw_msg,
                            symbol=sym,
                            snapshot=snap,
                            news_items=items_dicts,
                        )
                        if narr:
                            narr = narr.replace("**", "")
        
                    assistant_text = format_market_brief_contract(
                        user_message=display_msg,
                        symbol=sym,
                        snapshot=snap,
                        snapshot_meta=snap_meta,
                        news_items=items_dicts,
                        narrative_text=narr,
                    )

        elif action == "indicator_request":
            sym = (route or {}).get("symbol") or (intent["symbols"][0] if intent["symbols"] else None)
            sym = (sym or "").upper().strip()
        
            if not sym:
                assistant_text = "Which coin? Give me a ticker or name like BTC or Bitcoin. (Example: `Bitcoin RSI on 1h`)"
            else:
                # Validate + normalize to real resolved ticker
                ok_sym, sym_meta = _is_valid_token_symbol(db, sym, now_utc_naive, max_rank=3000)
                if not ok_sym:
                    assistant_text = (
                        f"I can’t verify `{sym}` as a real token (CoinGecko match: {sym_meta.get('matched_name')}, "
                        f"rank={sym_meta.get('rank')}).\n\n"
                        "Try a known ticker like BTC, ETH, SOL, FIL, LINK, AVAX."
                    )
                else:
                    sym = (sym_meta.get("resolved_symbol") or sym).upper().strip()
        
                    timeframe = _extract_timeframe(raw_msg)
        
                    plan_code = (
                        db.execute(select(models.Plan.code).where(models.Plan.id == current_user.plan_id))
                        .scalar_one_or_none()
                    )
                    plan_code = (plan_code or "").lower()
                    ent_for_tools = SimpleNamespace(plan_slug=plan_code)
        
                    indicators_out, indicators_meta = get_indicators_basic(
                        db=db,
                        symbol=sym,
                        timeframe=timeframe,
                        now_utc_naive=now_utc_naive,
                        ent=ent_for_tools,
                        bypass=bypass,
                    )
        
                    focus = _indicator_focus(raw_msg)
        
                    # If user asked for a single indicator, prepare a followup so "yes" can expand to full set
                    if focus in {"rsi", "macd", "ema20"}:
                        t.pending_followup_type = "indicators_full"
                        t.pending_followup_payload = {"sym": sym, "tf": timeframe, "asked": display_msg}
                    else:
                        t.pending_followup_type = None
                        t.pending_followup_payload = None
                    db.add(t)
                    db.commit()
        
                    if indicators_out is None:
                        err = (indicators_meta or {}).get("error")
                        assistant_text = (
                            f"I couldn’t compute indicators for {sym} right now."
                            + (f" ({err})" if err else "")
                            + " Try again in a moment."
                        )
                    else:
                        snap, snap_meta = get_market_snapshot(db=db, symbol=sym, now_utc_naive=now_utc_naive)
        
                        # IMPORTANT: do NOT call LLM narrative for indicator_request
                        assistant_text = format_indicators_contract(
                            user_message=display_msg,
                            symbol=sym,
                            timeframe=timeframe,
                            snapshot=snap,
                            snapshot_meta=snap_meta,
                            indicators=indicators_out,
                            indicators_meta=indicators_meta,
                            focus=focus,
                            include_yes_hint=(focus in {"rsi", "macd", "ema20"}),
                            narrative_text=None,  # always None here
                        )

        elif action == "token_analysis":
            sym = (route or {}).get("symbol") or (intent["symbols"][0] if intent["symbols"] else None)
            sym = (sym or "").upper().strip()
        
            if not sym:
                assistant_text = "Which coin? Give me a ticker or name like BTC or Bitcoin."
            else:
                ok_sym, sym_meta = _is_valid_token_symbol(db, sym, now_utc_naive, max_rank=3000)
                if not ok_sym:
                    assistant_text = (
                        f"I can’t verify `{sym}` as a real token (CoinGecko match: {sym_meta.get('matched_name')}, "
                        f"rank={sym_meta.get('rank')}).\n\n"
                        "Try a known ticker like BTC, ETH, SOL, FIL, LINK, AVAX."
                    )
                else:
                    sym = (sym_meta.get("resolved_symbol") or sym).upper().strip()
        
                    timeframe = _extract_timeframe(raw_msg)
                    if "today" in raw_msg.lower():
                        timeframe = "4h"
        
                    snap, snap_meta = get_market_snapshot(db=db, symbol=sym, now_utc_naive=now_utc_naive)
        
                    plan_code = (
                        db.execute(select(models.Plan.code).where(models.Plan.id == current_user.plan_id))
                        .scalar_one_or_none()
                    )
                    ent_for_tools = SimpleNamespace(plan_slug=(plan_code or "").lower())
        
                    out, meta = get_indicators_basic(
                        db=db,
                        symbol=sym,
                        timeframe=timeframe,
                        now_utc_naive=now_utc_naive,
                        ent=ent_for_tools,
                        bypass=bypass,
                    )
        
                    narr = None
                    if snap is not None:
                        narr = generate_crypto_narrative(
                            user_message=raw_msg,
                            symbol=sym,
                            timeframe=timeframe,
                            snapshot=snap,
                            indicators=out,
                        )
        
                    logging.getLogger("uvicorn").info(
                        "[narrative_debug] action=token_analysis sym=%s tf=%s snap=%s ind=%s narr=%s head=%r",
                        sym,
                        timeframe,
                        "ok" if snap else "none",
                        "ok" if out else "none",
                        "ok" if (narr and narr.strip()) else "none",
                        (narr or "")[:120],
                    )
        
                    assistant_text = format_indicators_contract(
                        user_message=display_msg,
                        symbol=sym,
                        timeframe=timeframe,
                        snapshot=snap,
                        snapshot_meta=snap_meta,
                        indicators=out,
                        indicators_meta=meta,
                        focus="full",
                        include_yes_hint=False,
                        narrative_text=narr,
                    )


        else:
            sym = ",".join(intent["symbols"]) if intent["symbols"] else "none"

            plan_code = (
                db.execute(select(models.Plan.code).where(models.Plan.id == current_user.plan_id))
                .scalar_one_or_none()
            )
            plan_code = (plan_code or "").strip().lower()
            # Canonical paid plans are plus/pro; keep basic as a legacy alias.
            is_paid = bypass or (plan_code in ("basic", "plus", "pro"))


            backend = select_model_backend(
                is_bypass=bypass,
                is_paid=is_paid,
                intent=action,
            )

            assistant_text = (
                f"[stub:{payload.mode}] backend={backend} intent={intent['intent']} symbols={sym} "
                f"(context_messages_used={context_meta['context_messages_used']}) {payload.message}"
            )


        # Keep existing cache behavior exactly the same
        if payload.mode in CACHEABLE_MODES and rh is not None:
            write_cache(
                db,
                user_id=str(current_user.id),
                mode=payload.mode,
                request_hash=rh,
                response_json={"assistant": assistant_text},
                now_utc_naive=now_utc_naive,
            )

    # 7) Store assistant message + touch thread
    assistant_msg = models.Message(thread_id=thread_id, role="assistant", content=assistant_text)
    db.add(assistant_msg)

    from app.routers.threads import touch_thread
    touch_thread(db, thread_id)

    db.commit()
    db.refresh(assistant_msg)

    if info is None:
        return {
            "ok": True,
            "thread_id": thread_id,
            "mode": payload.mode,
            "assistant": _extract_display(assistant_text),
            "role": current_user.role,
            "bypass": bypass,
            "utc": {"now": now_utc_naive.isoformat() + "+00:00"},
            "cache": {"hit": True},
            "context": {"used": context_meta, "prompt_message_count": len(prompt_messages)},
            "summary": summary_meta,
            "minute": None,
            "day": None,
            "month": None,
        }

    return {
        "ok": True,
        "thread_id": thread_id,
        "mode": payload.mode,
        "assistant": _extract_display(assistant_text),
        "role": current_user.role,
        "bypass": info["bypass"],
        "utc": {"now": info["utc_now"]},
        "cache": {"hit": cache_hit},
        "context": {"used": context_meta, "prompt_message_count": len(prompt_messages)},
        "summary": summary_meta,
        "minute": {
            "used": info["minute_used"],
            "limit": info["minute_limit"],
            "remaining": remaining(info["minute_limit"], info["minute_used"])
            if info["minute_limit"] is not None else None,
        },
        "day": {
            "used": info["day_used"],
            "limit": info["day_limit"],
            "remaining": remaining(info["day_limit"], info["day_used"]),
        },
        "month": {
            "used": info["month_used"],
            "limit": info["month_limit"],
            "remaining": remaining(info["month_limit"], info["month_used"]),
        },
    }


@router.post("/strategy")
def strategy_compat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    info = enforce_mode_and_quota(db=db, req=request, user=current_user, mode="strategy_builder")
    return {
        "ok": True,
        "mode": "strategy_builder",
        "echo": payload.message,
        "role": current_user.role,
        "bypass": info["bypass"],
    }
