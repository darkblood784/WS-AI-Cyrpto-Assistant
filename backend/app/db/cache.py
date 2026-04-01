from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import hashlib
import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import models


def stable_request_hash(mode: str, message: str) -> str:
    payload = {"mode": mode, "message": (message or "").strip()}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cache_ttl_seconds_for_mode(mode: str) -> int:
    # Market snapshot
    if mode in ("market_snapshot_v1",):
        return 120

    # OHLCV + indicators (short TTL is fine)
    if mode in ("ohlcv_v1", "indicators_basic_v1"):
        return 300

    # CoinGecko symbol/name -> id resolve (changes rarely)
    if mode in ("symbol_resolve_v1",):
        return 86400  # 24h

    # CoinGecko symbol/name -> id resolve (changes rarely)
    if mode in ("coingecko_topcoins_v1",):
        return 86400  # 24h

    # Landing page prices
    if mode == "landing_prices_v1":
        return 60

    # (keep any existing modes)
    if mode == "indicators_basic":
        return 60
    if mode == "indicators_advanced":
        return 60

    return 0

def read_cache(
    db: Session,
    *,
    user_id: str | None,
    mode: str,
    request_hash: str,
    now_utc_naive: datetime,
) -> dict | None:
    row = db.execute(
        select(models.ApiCache).where(
            models.ApiCache.mode == mode,
            models.ApiCache.request_hash == request_hash,
            models.ApiCache.user_id == user_id,
            models.ApiCache.expires_at > now_utc_naive,
        )
    ).scalar_one_or_none()

    if not row:
        return None
    return row.response_json


def write_cache(
    db: Session,
    *,
    user_id: str | None,
    mode: str,
    request_hash: str,
    response_json: dict,
    now_utc_naive: datetime,
) -> None:
    ttl = cache_ttl_seconds_for_mode(mode)
    if ttl <= 0:
        return

    expires_at = now_utc_naive + timedelta(seconds=ttl)

    db.execute(
        delete(models.ApiCache).where(
            models.ApiCache.mode == mode,
            models.ApiCache.request_hash == request_hash,
            models.ApiCache.user_id == user_id,
        )
    )

    db.add(
        models.ApiCache(
            user_id=user_id,
            mode=mode,
            request_hash=request_hash,
            response_json=response_json,
            expires_at=expires_at,
        )
    )
    db.commit()
