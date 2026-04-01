from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Iterable

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db import models
from app.tools.news_feed import fetch_google_news


RETENTION_HOURS = 48

# Keep this small-but-useful. Add more over time.
# Key rule: coin names should be what news headlines actually contain.
COIN_ALIASES: dict[str, list[str]] = {
    "BTC": ["Bitcoin", "BTC"],
    "ETH": ["Ethereum", "ETH"],
    "SOL": ["Solana", "SOL"],
    "XRP": ["XRP", "Ripple"],
    "BNB": ["BNB", "Binance Coin", "Binance"],
    "ADA": ["Cardano", "ADA"],
    "DOGE": ["Dogecoin", "DOGE"],
    "AVAX": ["Avalanche", "AVAX"],
    "DOT": ["Polkadot", "DOT"],
    "LINK": ["Chainlink", "LINK"],
    "MATIC": ["Polygon", "MATIC", "POL"],  # Polygon rebrand appears in headlines sometimes
    "LTC": ["Litecoin", "LTC"],
    "BCH": ["Bitcoin Cash", "BCH"],
    "ATOM": ["Cosmos", "ATOM"],
    "TRX": ["TRON", "TRX"],
    "UNI": ["Uniswap", "UNI"],
    "APT": ["Aptos", "APT"],
    "SUI": ["Sui", "SUI"],
}

# Words that make a headline more “today-useful”
HIGH_INTENT_TERMS = [
    "price", "today", "forecast", "outlook", "analysis",
    "etf", "sec", "lawsuit", "approval", "ban", "regulation",
    "hack", "exploit", "airdrop", "unlock", "listing",
]


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _build_query_for_symbol(symbol: str) -> str:
    """
    Build a Google News query string that tends to return coin-specific headlines.
    Using OR is fine for Google News RSS-style queries.
    """
    sym = (symbol or "").upper().strip()
    aliases = COIN_ALIASES.get(sym) or [sym]
    # Add a “price” flavored term to bias toward actionable headlines
    # but keep it light so we don't filter too aggressively.
    parts = []
    for a in aliases:
        a = a.strip()
        if " " in a:
            parts.append(f'"{a}"')
        else:
            parts.append(a)
    # Example: (XRP OR "Ripple") price
    return "(" + " OR ".join(parts) + ") price"


def upsert_news_items(db: Session, symbol: str | None, items: list[dict]) -> int:
    """
    Insert items that don't already exist by URL.
    If URL exists as generic (symbol NULL/''), retag it to the requested symbol.
    Returns number inserted/retagged.
    """
    inserted_or_updated = 0
    sym = (symbol or None)
    if sym:
        sym = sym.upper().strip()

    for it in items:
        url = it.get("url")
        title = it.get("title")
        if not url or not title:
            continue

        existing = db.execute(
            select(models.NewsItem).where(models.NewsItem.url == url)
        ).scalar_one_or_none()

        if existing:
            # ✅ Retag generic rows to this symbol
            if sym and (existing.symbol is None or existing.symbol == ""):
                existing.symbol = sym
                # optionally update fields if missing
                if not existing.source:
                    existing.source = it.get("source")
                if not existing.published_at and it.get("published_at"):
                    existing.published_at = it.get("published_at")
                db.add(existing)
                inserted_or_updated += 1
            continue

        row = models.NewsItem(
            symbol=sym,
            source=it.get("source"),
            title=title[:512],
            url=url[:1024],
            summary=None,
            published_at=it.get("published_at"),
            created_at=_now_utc_naive(),
        )
        db.add(row)
        inserted_or_updated += 1

    if inserted_or_updated:
        db.commit()
    return inserted_or_updated


def prune_old_news(db: Session) -> int:
    cutoff = _now_utc_naive() - timedelta(hours=RETENTION_HOURS)

    q = delete(models.NewsItem).where(
        (models.NewsItem.published_at.isnot(None) & (models.NewsItem.published_at < cutoff))
        | (models.NewsItem.published_at.is_(None) & (models.NewsItem.created_at < cutoff))
    )

    res = db.execute(q)
    db.commit()
    return int(res.rowcount or 0)


def run_news_ingest(db: Session) -> dict:
    """
    Fetch + store news.
    Strategy:
      - Always ingest one general market query
      - Ingest coin-specific queries for a curated list of symbols (COIN_ALIASES)
    """
    stats = {"inserted": 0, "deleted": 0}

    # General market (helps “market today?” style queries)
    base_queries = [
        (None, "cryptocurrency market price"),
    ]

    # Coin-specific
    coin_queries: list[tuple[str, str]] = []
    for sym in COIN_ALIASES.keys():
        coin_queries.append((sym, _build_query_for_symbol(sym)))

    # Combine
    queries = base_queries + coin_queries

    for sym, q in queries:
        try:
            items = fetch_google_news(q)
            stats["inserted"] += upsert_news_items(db, sym, items)
        except Exception:
            continue

    try:
        stats["deleted"] = prune_old_news(db)
    except Exception:
        pass

    return stats


def _relevance_score(title: str, symbol: str) -> int:
    """
    Deterministic relevance for sorting headlines for a given symbol.
    """
    t = _norm(title)
    sym = (symbol or "").upper().strip()
    aliases = COIN_ALIASES.get(sym) or [sym]

    score = 0

    # Strong boost: ticker match
    # Use word boundary-ish check to avoid random substring hits.
    if sym and re.search(rf"\b{re.escape(sym.lower())}\b", t):
        score += 3

    # Coin name / alias matches
    for a in aliases:
        a_norm = _norm(a)
        if not a_norm:
            continue
        # If alias is multi-word, simple substring is fine.
        # If single-word, use boundary-ish check.
        if " " in a_norm:
            if a_norm in t:
                score += 3
        else:
            if re.search(rf"\b{re.escape(a_norm)}\b", t):
                score += 3

    # Intent terms
    for term in HIGH_INTENT_TERMS:
        if term in t:
            score += 1

    return score


def get_top_news(db: Session, symbol: str | None, limit: int = 5) -> list[models.NewsItem]:
    """
    Return top news for symbol, prioritizing symbol-specific items,
    then falling back to general market news.

    IMPORTANT: we fetch a wider pool then relevance-rank deterministically.
    """
    stmt = select(models.NewsItem)

    if symbol:
        stmt = stmt.where(
            (models.NewsItem.symbol == symbol)
            | (models.NewsItem.symbol.is_(None))
            | (models.NewsItem.symbol == "")
        )
    else:
        stmt = stmt.where((models.NewsItem.symbol.is_(None)) | (models.NewsItem.symbol == ""))

    # Pull a pool larger than limit so we can rank.
    pool_size = max(30, limit * 6)
    stmt = stmt.order_by(models.NewsItem.published_at.desc().nullslast(), models.NewsItem.created_at.desc()).limit(pool_size)

    items = list(db.execute(stmt).scalars().all())
    if not symbol:
        return items[:limit]

    sym = symbol.upper().strip()

    def sort_key(it: models.NewsItem):
        # published_at can be None; created_at always exists
        ts = it.published_at or it.created_at
        score = _relevance_score(it.title or "", sym)
        # Prefer symbol-tagged items over generic when scores tie
        is_symbol = 1 if (it.symbol == sym) else 0
        return (score, is_symbol, ts)

    items_sorted = sorted(items, key=sort_key, reverse=True)
    return items_sorted[:limit]

def get_top_news_strict(db: Session, symbol: str, limit: int = 5) -> list[models.NewsItem]:
    sym = (symbol or "").upper().strip()
    if not sym:
        return []
    stmt = (
        select(models.NewsItem)
        .where(models.NewsItem.symbol == sym)
        .order_by(models.NewsItem.published_at.desc().nullslast(), models.NewsItem.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())

def news_items_to_dicts(items: list[models.NewsItem]) -> list[dict]:
    out: list[dict] = []
    for it in items:
        out.append(
            {
                "source": it.source,
                "title": it.title,
                "url": it.url,
                "published_at": it.published_at.isoformat() if it.published_at else None,
                "created_at": it.created_at.isoformat() if it.created_at else None,
                "symbol": it.symbol,
            }
        )
    return out
    
def ensure_symbol_news(db: Session, symbol: str, query: str | None = None, limit: int = 5) -> list[models.NewsItem]:
    sym = (symbol or "").upper().strip()
    if not sym:
        return []

    strict_items = get_top_news_strict(db, sym, limit=limit)
    if len(strict_items) >= limit:
        return strict_items

    missing = limit - len(strict_items)

    q = (query or sym).strip()
    try:
        fetched = fetch_google_news(q)
        # upsert everything; uniqueness will prevent duplicates
        upsert_news_items(db, sym, fetched)
    except Exception:
        return strict_items  # return what we have

    # return full strict list now
    return get_top_news_strict(db, sym, limit=limit)
