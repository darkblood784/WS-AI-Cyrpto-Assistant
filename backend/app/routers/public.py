"""Public landing-page endpoints — no auth required."""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.cache import read_cache, write_cache, stable_request_hash

router = APIRouter(tags=["public"])

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
LANDING_SYMBOLS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
}
CACHE_MODE = "landing_prices_v1"
CACHE_TTL = 60  # seconds


@router.get("/prices/landing")
def landing_prices(db: Session = Depends(get_db)):
    """Return live prices for landing-page ticker symbols.

    Single CoinGecko request, cached for 60 s.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rh = stable_request_hash(CACHE_MODE, "landing_strip")

    cached = read_cache(
        db,
        user_id=None,
        mode=CACHE_MODE,
        request_hash=rh,
        now_utc_naive=now,
    )
    if cached is not None:
        return cached

    coin_ids = ",".join(LANDING_SYMBOLS.values())
    try:
        r = requests.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": coin_ids,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=10,
        )
        r.raise_for_status()
        raw = r.json() or {}
    except Exception:
        # Return empty on failure — frontend will show fallback
        return {"coins": [], "ok": False}

    coins = []
    for symbol, cg_id in LANDING_SYMBOLS.items():
        row = raw.get(cg_id, {})
        price = row.get("usd")
        change = row.get("usd_24h_change")
        if price is not None:
            coins.append({
                "symbol": symbol,
                "price_usd": round(price, 2),
                "change_24h_pct": round(change, 2) if change is not None else None,
            })

    result = {"coins": coins, "ok": True}
    write_cache(
        db,
        user_id=None,
        mode=CACHE_MODE,
        request_hash=rh,
        response_json=result,
        now_utc_naive=now,
    )
    return result
