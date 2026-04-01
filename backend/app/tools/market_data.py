from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import math
import requests

from sqlalchemy.orm import Session

# ✅ CHANGE THESE TWO IMPORTS TO MATCH YOUR PROJECT (use the grep commands)
from app.db.cache import read_cache, write_cache, stable_request_hash, cache_ttl_seconds_for_mode
import httpx
from types import SimpleNamespace
import re


# -----------------------------
# Cache modes
# -----------------------------
MARKET_CACHE_MODE = "market_snapshot_v1"
OHLCV_CACHE_MODE = "ohlcv_v1"
INDICATORS_CACHE_MODE = "indicators_basic_v1"
SYMBOL_RESOLVE_CACHE_MODE = "symbol_resolve_v1"


# -----------------------------
# CoinGecko config
# -----------------------------
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

_SYMBOL_TO_COINGECKO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
}

_TIMEFRAME_TO_DAYS = {
    "15m": 1,
    "30m": 1,
    "1h": 60,
    "4h": 90,
    "1d": 365,
}

_BINANCE_INTERVALS = {
    1: "1m",
    3: "3m",
    5: "5m",
    15: "15m",
    30: "30m",
    60: "1h",
    120: "2h",
    240: "4h",
    360: "6h",
    480: "8h",
    720: "12h",
    1440: "1d",
}

# minimal mapping; expand later
_BINANCE_SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "DOGE": "DOGEUSDT",
}

async def _binance_fetch_klines(symbol: str, interval: str, limit: int, end_time_ms: int | None = None) -> list[list]:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if end_time_ms is not None:
        params["endTime"] = end_time_ms

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get("https://api.binance.com/api/v3/klines", params=params)
        r.raise_for_status()
        return r.json()


def _klines_to_candles(klines: list[list]) -> list[dict]:
    out = []
    for k in klines:
        # kline format:
        # 0 openTime, 1 open, 2 high, 3 low, 4 close, 5 volume, 6 closeTime ...
        open_time_ms = int(k[0])
        dt = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
        out.append({
            "ts": dt.isoformat().replace("+00:00", "Z"),
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        })
    return out


def _fetch_ohlcv_binance_sync(sym: str, tf: str, limit: int) -> tuple[dict | None, dict]:
    """
    Sync wrapper (since your code is sync).
    Fetch enough 1m candles to resample to any Xm timeframe.
    """
    sym = (sym or "").upper().strip()
    tf = (tf or "").lower().strip()

    target_minutes = _parse_tf_minutes(tf)
    if target_minutes is None:
        return None, {"hit": False, "source": "binance", "error": f"bad timeframe: {tf}"}

    pair = _BINANCE_SYMBOL_MAP.get(sym)
    if not pair:
        return None, {"hit": False, "source": "binance", "error": f"binance_pair_not_supported: {sym}"}

    # If Binance supports the exact interval, we can fetch directly.
    # But for odd targets (7m, 12m, etc), we fetch 1m and resample.
    direct_interval = _BINANCE_INTERVALS.get(target_minutes)

    # We want `limit` candles at the requested timeframe.
    # If resampling from 1m, we need limit * target_minutes 1m candles.
    need_1m = limit * target_minutes if direct_interval is None else limit

    # Binance max per call is 1000 klines. We'll page backwards using endTime.
    async def _run():
        all_klines = []
        end_ms = None
        remaining = need_1m
        calls = 0

        interval = direct_interval or "1m"
        while remaining > 0 and calls < 6:  # cap calls for safety
            batch = min(1000, remaining)
            klines = await _binance_fetch_klines(pair, interval=interval, limit=batch, end_time_ms=end_ms)
            if not klines:
                break
            all_klines = klines + all_klines  # prepend older
            # set endTime to just before the first returned openTime to page older
            first_open_ms = int(klines[0][0])
            end_ms = first_open_ms - 1
            remaining -= len(klines)
            calls += 1

        candles = _klines_to_candles(all_klines)

        if direct_interval is None:
            # resample from 1m to target_minutes
            candles = _resample_candles(candles, target_minutes)
            # keep only last `limit`
            candles = candles[-limit:]
        else:
            candles = candles[-limit:]

        if not candles:
            return None, {"hit": False, "source": "binance", "error": "no_candles"}

        asof = candles[-1]["ts"]
        return {
            "source": "binance",
            "symbol": sym,
            "timeframe": tf,
            "asof_utc": asof,
            "candles": candles,
            "notes": f"binance interval={'1m(resampled)' if direct_interval is None else direct_interval}",
        }, {"hit": False, "source": "binance"}

    import anyio
    try:
        return anyio.run(_run)
    except Exception as e:
        return None, {"hit": False, "source": "binance", "error": f"binance_error:{e}"}

# -----------------------------
# Small cache helpers (use your existing api_cache)
# -----------------------------
def _read_tool_cache(db: Session, mode: str, request_hash: str, now_utc_naive: datetime) -> dict | None:
    cached = read_cache(
        db=db,
        user_id=None,  # global cache for market/tools
        mode=mode,
        request_hash=request_hash,
        now_utc_naive=now_utc_naive,
    )
    return dict(cached) if cached is not None else None


def _write_tool_cache(db: Session, mode: str, request_hash: str, response_json: dict, now_utc_naive: datetime, ttl_seconds: int) -> None:
    # ttl_seconds is ignored because write_cache decides TTL based on mode
    write_cache(
        db=db,
        user_id=None,
        mode=mode,
        request_hash=request_hash,
        response_json=response_json,
        now_utc_naive=now_utc_naive,
    )

def _coingecko_coin_id(db: Session, symbol_or_name: str, now_utc_naive: datetime) -> str | None:
    cid, _meta = resolve_coingecko_id(db=db, query=symbol_or_name, now_utc_naive=now_utc_naive)
    return cid


def _normalize_query(q: str) -> str:
    return (q or "").strip().lower()

def _fetch_coingecko_search(query: str) -> dict:
    url = f"{COINGECKO_BASE}/search"
    params = {"query": query}
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    return r.json() or {}

def _pick_best_coingecko_match(search_json: dict, query: str) -> dict | None:
    """
    Heuristic selection:
    - Prefer exact symbol match (case-insensitive)
    - Otherwise exact name match
    - Otherwise take best market_cap_rank
    """
    q = _normalize_query(query)
    coins = (search_json or {}).get("coins") or []
    if not coins:
        return None

    # normalize
    for c in coins:
        c["_sym"] = _normalize_query(c.get("symbol") or "")
        c["_name"] = _normalize_query(c.get("name") or "")
        # lower rank is better; missing rank gets large number
        r = c.get("market_cap_rank")
        c["_rank"] = int(r) if isinstance(r, int) else 10**9

    # 1) exact symbol
    exact_sym = [c for c in coins if c["_sym"] == q]
    if exact_sym:
        exact_sym.sort(key=lambda x: x["_rank"])
        return exact_sym[0]

    # 2) exact name
    exact_name = [c for c in coins if c["_name"] == q]
    if exact_name:
        exact_name.sort(key=lambda x: x["_rank"])
        return exact_name[0]

    # 3) startswith symbol or name (soft)
    soft = [c for c in coins if c["_sym"].startswith(q) or c["_name"].startswith(q)]
    if soft:
        soft.sort(key=lambda x: x["_rank"])
        return soft[0]

    # 4) fallback: best rank overall
    coins.sort(key=lambda x: x["_rank"])
    return coins[0]

def resolve_coingecko_id(db: Session, query: str, now_utc_naive: datetime) -> tuple[str | None, dict]:
    """
    Resolve user input (ticker or name) -> CoinGecko coin_id.
    Cached in api_cache so we don't re-search repeatedly.
    """
    q = (query or "").strip()
    if not q:
        return None, {"hit": False, "source": "coingecko", "error": "missing_query"}

    q_norm = _normalize_query(q)
    rh = stable_request_hash(SYMBOL_RESOLVE_CACHE_MODE, q_norm)

    cached = _read_tool_cache(db=db, mode=SYMBOL_RESOLVE_CACHE_MODE, request_hash=rh, now_utc_naive=now_utc_naive)
    if cached is not None:
        cid = cached.get("coingecko_id")
        if not cid:
            return None, {"hit": True, "source": "coingecko", "error": cached.get("error") or "not_found"}
        return str(cid), {"hit": True, "source": "coingecko"}

    # First: your old seed mapping still helps for common majors
    # If the user gave a ticker, try the seed map quickly.
    sym_upper = q.upper().strip()
    seed_id = _SYMBOL_TO_COINGECKO_ID.get(sym_upper)
    if seed_id:
        _write_tool_cache(
            db=db,
            mode=SYMBOL_RESOLVE_CACHE_MODE,
            request_hash=rh,
            response_json={"query": q_norm, "coingecko_id": seed_id, "via": "seed"},
            now_utc_naive=now_utc_naive,
            ttl_seconds=cache_ttl_seconds_for_mode(SYMBOL_RESOLVE_CACHE_MODE),
        )
        return seed_id, {"hit": False, "source": "coingecko"}

    # Otherwise: call CoinGecko search
    try:
        sj = _fetch_coingecko_search(q)
        best = _pick_best_coingecko_match(sj, q)
        if not best or not best.get("id"):
            fail = {"query": q_norm, "coingecko_id": None, "error": "not_found"}
            _write_tool_cache(
                db=db,
                mode=SYMBOL_RESOLVE_CACHE_MODE,
                request_hash=rh,
                response_json=fail,
                now_utc_naive=now_utc_naive,
                ttl_seconds=cache_ttl_seconds_for_mode(SYMBOL_RESOLVE_CACHE_MODE),
            )
            return None, {"hit": False, "source": "coingecko", "error": "not_found"}

        cid = str(best["id"])
        payload = {
            "query": q_norm,
            "coingecko_id": cid,
            "matched_symbol": best.get("symbol"),
            "matched_name": best.get("name"),
            "market_cap_rank": best.get("market_cap_rank"),
            "via": "search",
        }
        _write_tool_cache(
            db=db,
            mode=SYMBOL_RESOLVE_CACHE_MODE,
            request_hash=rh,
            response_json=payload,
            now_utc_naive=now_utc_naive,
            ttl_seconds=cache_ttl_seconds_for_mode(SYMBOL_RESOLVE_CACHE_MODE),
        )
        return cid, {"hit": False, "source": "coingecko"}

    except Exception as e:
        return None, {"hit": False, "source": "coingecko", "error": f"search_error:{e}"}

# -----------------------------
# 6B-1) Market snapshot
# -----------------------------
def _fetch_coingecko_snapshot_usd(coin_id: str, sym_display: str) -> dict | None:
    if not coin_id:
        return None

    url = f"{COINGECKO_BASE}/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
        "include_market_cap": "true",
    }

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json() or {}
    row = data.get(coin_id) or {}

    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    return {
        "source": "coingecko",
        "symbol": sym_display,
        "coingecko_id": coin_id,
        "vs": "usd",
        "price_usd": row.get("usd"),
        "change_24h_pct": row.get("usd_24h_change"),
        "volume_24h_usd": row.get("usd_24h_vol"),
        "market_cap_usd": row.get("usd_market_cap"),
        "asof_utc": fetched_at,
    }


def get_market_snapshot(db: Session, symbol: str, now_utc_naive: datetime) -> tuple[dict | None, dict]:
    sym = (symbol or "").upper().strip()
    if not sym:
        return None, {"hit": False, "source": None, "error": "missing_symbol"}

    rh = stable_request_hash(MARKET_CACHE_MODE, f"{sym}:USD")
    cached = _read_tool_cache(db=db, mode=MARKET_CACHE_MODE, request_hash=rh, now_utc_naive=now_utc_naive)
    if cached is not None:
        # cached failures should still carry an error if no price
        if cached.get("price_usd") is None:
            return None, {"hit": True, "source": cached.get("source"), "error": "token_not_found_or_no_price"}
        return cached, {"hit": True, "source": cached.get("source")}

    try:
        coin_id, rid_meta = resolve_coingecko_id(db=db, query=sym, now_utc_naive=now_utc_naive)
        if not coin_id:
            # cache a clean failure under MARKET cache too
            fail = {"source": "coingecko", "symbol": sym, "vs": "usd", "price_usd": None, "error": rid_meta.get("error") or "token_not_found"}
            _write_tool_cache(db=db, mode=MARKET_CACHE_MODE, request_hash=rh, response_json=fail, now_utc_naive=now_utc_naive, ttl_seconds=60)
            return None, {"hit": False, "source": "coingecko", "error": rid_meta.get("error") or "token_not_found"}
        
        snap = _fetch_coingecko_snapshot_usd(coin_id, sym_display=sym)

    except Exception as e:
        return None, {"hit": False, "source": None, "error": f"provider_error:{e}"}

    # If provider returned nothing / missing price:
    if snap is None or snap.get("price_usd") is None:
        # write a cache record so we don't hammer provider, but keep it explicit
        fail = {"source": (snap or {}).get("source") or "coinmarketcap", "symbol": sym, "vs": "usd", "price_usd": None}
        _write_tool_cache(
            db=db,
            mode=MARKET_CACHE_MODE,
            request_hash=rh,
            response_json=fail,
            now_utc_naive=now_utc_naive,
            ttl_seconds=60,
        )
        return None, {"hit": False, "source": fail.get("source"), "error": "token_not_found_or_no_price"}

    _write_tool_cache(db=db, mode=MARKET_CACHE_MODE, request_hash=rh, response_json=snap, now_utc_naive=now_utc_naive, ttl_seconds=60)
    return snap, {"hit": False, "source": snap.get("source")}

# -----------------------------
# 6B-2) OHLCV (approximated OHLC from price series)
# -----------------------------
def _fetch_coingecko_ohlcv(db: Session, now_utc_naive: datetime, symbol: str, timeframe: str, limit: int) -> dict:
    sym = (symbol or "").upper().strip()
    tf = (timeframe or "1h").lower().strip()

    if tf not in _TIMEFRAME_TO_DAYS:
        raise ValueError(f"unsupported timeframe: {tf}")

    coin_id, rid_meta = resolve_coingecko_id(db=db, query=sym, now_utc_naive=now_utc_naive)
    if not coin_id:
        raise ValueError(f"unknown symbol: {sym} ({rid_meta.get('error')})")

    days = _TIMEFRAME_TO_DAYS[tf]

    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days)}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json() or {}

    prices = data.get("prices") or []  # [[ms, price], ...]
    if len(prices) < 10:
        raise RuntimeError("not enough price points from provider")

    bucket_sec = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}[tf]

    buckets: dict[int, list[float]] = {}
    for ms, price in prices:
        ts_sec = int(ms // 1000)
        b = (ts_sec // bucket_sec) * bucket_sec
        buckets.setdefault(b, []).append(float(price))

    candles = []
    for b in sorted(buckets.keys()):
        vals = buckets[b]
        if not vals:
            continue
        o = vals[0]
        c = vals[-1]
        h = max(vals)
        l = min(vals)
        candles.append(
            {
                "ts": datetime.fromtimestamp(b, tz=timezone.utc).replace(tzinfo=None).isoformat() + "Z",
                "o": o,
                "h": h,
                "l": l,
                "c": c,
                "v": None,  # do NOT invent volume
            }
        )

    candles = candles[-max(10, int(limit)) :]

    asof = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
    return {
        "source": "coingecko",
        "symbol": sym,
        "timeframe": tf,
        "asof_utc": asof,
        "candles": candles,
        "notes": "OHLC approximated from CoinGecko price series; volume is not provided (v=None).",
    }

def get_ohlcv(
    db: Session,
    symbol: str,
    timeframe: str,
    limit: int,
    now_utc_naive: datetime,
) -> tuple[dict | None, dict]:
    sym = (symbol or "").upper().strip()
    tf = (timeframe or "1h").lower().strip()

    try:
        lim = int(limit)
    except Exception:
        lim = 120
    lim = max(10, min(lim, 500))

    if not sym:
        return None, {"hit": False, "source": None, "error": "missing_symbol"}

    # ---- NEW: timeframe parsing guard (prevents weird inputs)
    tfm = _parse_tf_minutes(tf)
    if tfm is None:
        return None, {"hit": False, "source": None, "error": f"unsupported timeframe: {tf}"}

    # ---- cache
    rh = stable_request_hash(OHLCV_CACHE_MODE, f"{sym}:{tf}:{lim}:USD")
    cached = _read_tool_cache(db=db, mode=OHLCV_CACHE_MODE, request_hash=rh, now_utc_naive=now_utc_naive)
    if cached is not None:
        return cached, {"hit": True, "source": cached.get("source")}

    # ---- NEW: try Binance first for minute-based charts (< 15m)
    # This enables 5m, 7m, 12m, etc. by fetching 1m and resampling.
    if tfm < 15:
        out, meta = _fetch_ohlcv_binance_sync(sym, tf, lim)
        if out is not None:
            _write_tool_cache(
                db=db,
                mode=OHLCV_CACHE_MODE,
                request_hash=rh,
                response_json=out,
                now_utc_naive=now_utc_naive,
                ttl_seconds=cache_ttl_seconds_for_mode(OHLCV_CACHE_MODE),
            )
            return out, {"hit": False, "source": out.get("source")}

        # if Binance fails, we just fall through to CoinGecko as fallback

    # ---- existing: CoinGecko fallback
    try:
        out = _fetch_coingecko_ohlcv(db=db, now_utc_naive=now_utc_naive, symbol=sym, timeframe=tf, limit=lim)
    except Exception as e:
        return None, {"hit": False, "source": None, "error": str(e)}


    _write_tool_cache(
        db=db,
        mode=OHLCV_CACHE_MODE,
        request_hash=rh,
        response_json=out,
        now_utc_naive=now_utc_naive,
        ttl_seconds=cache_ttl_seconds_for_mode(OHLCV_CACHE_MODE),
    )
    return out, {"hit": False, "source": out.get("source")}

# -----------------------------
# Indicator math (deterministic)
# -----------------------------
def _ema(values: list[float], period: int) -> float | None:
    if period <= 1 or len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for x in values[period:]:
        ema = x * k + ema * (1 - k)
    return ema


def _rsi(values: list[float], period: int = 14) -> float | None:
    if period <= 1 or len(values) < period + 1:
        return None

    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def _sma(values: list[float], period: int) -> float | None:
    if period <= 0:
        return None
    if len(values) < period:   # <-- MUST be <, NOT <=
        return None
    window = values[-period:]
    return sum(window) / period

def _ema_series(values: list[float], period: int) -> list[float]:
    # returns an EMA value for each point starting at index period-1
    if period <= 1 or len(values) < period:
        return []
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    out = [ema]
    for x in values[period:]:
        ema = x * k + ema * (1 - k)
        out.append(ema)
    return out


def _macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    if len(values) < slow + signal + 5:
        return None

    ema_fast = _ema_series(values, fast)   # len = len(values)-fast+1
    ema_slow = _ema_series(values, slow)   # len = len(values)-slow+1

    if not ema_fast or not ema_slow:
        return None

    # align ends (compare same recent timestamps)
    n = min(len(ema_fast), len(ema_slow))
    macd_line_series = [ema_fast[-n + i] - ema_slow[-n + i] for i in range(n)]

    sig_series = _ema_series(macd_line_series, signal)
    if not sig_series:
        return None

    macd_line = macd_line_series[-1]
    signal_line = sig_series[-1]
    hist = macd_line - signal_line

    return {
        "macd": macd_line,
        "signal": signal_line,
        "hist": hist,
    }

def _parse_tf_minutes(tf: str) -> int | None:
    """
    Convert a timeframe string like '5m', '15m', '1h', '4h', '1d'
    into minutes. Supports up to 4 digits (1–9999 units).
    """
    tf = (tf or "").strip().lower()

    m = re.fullmatch(r"(\d{1,4})([mhd])", tf)
    if not m:
        return None

    n = int(m.group(1))
    unit = m.group(2)

    if n <= 0:
        return None

    if unit == "m":
        minutes = n
    elif unit == "h":
        minutes = n * 60
    elif unit == "d":
        minutes = n * 1440
    else:
        return None

    # sanity guardrails
    if minutes < 1 or minutes > 43200:  # 30 days max
        return None

    return minutes

def _floor_dt_to_bucket(dt: datetime, bucket_minutes: int) -> datetime:
    # dt must be UTC aware
    epoch = int(dt.timestamp())
    bucket = bucket_minutes * 60
    floored = (epoch // bucket) * bucket
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _resample_candles(candles_1m: list[dict], target_minutes: int) -> list[dict]:
    """
    candles_1m: list of dicts with keys: ts (ISO Z), o,h,l,c,v
    returns: candles at target_minutes, aligned to bucket start
    """
    if target_minutes <= 1:
        return candles_1m

    buckets: dict[str, dict] = {}
    order: list[str] = []

    for c in candles_1m:
        ts = c.get("ts")
        if not ts:
            continue
        # parse ISO "2026-01-08T01:05:00Z"
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        bdt = _floor_dt_to_bucket(dt, target_minutes)
        bkey = bdt.isoformat().replace("+00:00", "Z")

        if bkey not in buckets:
            buckets[bkey] = {
                "ts": bkey,
                "o": float(c["o"]),
                "h": float(c["h"]),
                "l": float(c["l"]),
                "c": float(c["c"]),
                "v": float(c.get("v") or 0.0),
                "_last_dt": dt,
            }
            order.append(bkey)
        else:
            b = buckets[bkey]
            b["h"] = max(b["h"], float(c["h"]))
            b["l"] = min(b["l"], float(c["l"]))
            # close should be last candle close in the bucket
            if dt >= b["_last_dt"]:
                b["_last_dt"] = dt
                b["c"] = float(c["c"])
            b["v"] += float(c.get("v") or 0.0)

    out: list[dict] = []
    for k in order:
        b = buckets[k]
        b.pop("_last_dt", None)
        out.append(b)

    return out

def get_indicators_basic(
    db: Session,
    symbol: str,
    timeframe: str,
    now_utc_naive: datetime,
    ent: Any,
    bypass: bool,
) -> tuple[dict | None, dict]:
    sym = (symbol or "").upper().strip()
    tf = (timeframe or "1h").lower().strip()
    if not sym:
        return None, {"hit": False, "source": None, "error": "missing_symbol"}

    # simple plan-based candle limit (safe v1)
    if bypass:
        limit = 300
    else:
        plan_slug = getattr(ent, "plan_slug", "") or ""
        plan_slug = str(plan_slug).lower()
        # Canonical paid plans are plus/pro; keep basic as a legacy alias.
        limit = 300 if ("basic" in plan_slug or "plus" in plan_slug or "pro" in plan_slug) else 150

    rh = stable_request_hash(INDICATORS_CACHE_MODE, f"{sym}:{tf}:{limit}:USD")
    cached = _read_tool_cache(db=db, mode=INDICATORS_CACHE_MODE, request_hash=rh, now_utc_naive=now_utc_naive)
    if cached is not None:
        return cached, {"hit": True, "source": cached.get("source")}

    ohlcv, ohlcv_meta = get_ohlcv(db=db, symbol=sym, timeframe=tf, limit=limit, now_utc_naive=now_utc_naive)
    if ohlcv is None:
        return None, {"hit": False, "source": None, "error": ohlcv_meta.get("error", "ohlcv_failed")}

    closes = [float(c["c"]) for c in (ohlcv.get("candles") or []) if c.get("c") is not None]
    if len(closes) < 30:
        return None, {"hit": False, "source": ohlcv.get("source"), "error": "not_enough_candles"}

    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    macd = _macd(closes, 12, 26, 9)
    
    out = {
        "source": ohlcv.get("source"),
        "symbol": sym,
        "timeframe": tf,
        "asof_utc": ohlcv.get("asof_utc"),
        "rsi_14": _rsi(closes, 14),
        "ema_20": _ema(closes, 20),
        "sma_20": sma20,
        "sma_50": sma50,
        "sma_200": sma200,
        "macd_12_26_9": macd,  # dict or None
        "notes": ohlcv.get("notes"),
    }


    _write_tool_cache(
        db=db,
        mode=INDICATORS_CACHE_MODE,
        request_hash=rh,
        response_json=out,
        now_utc_naive=now_utc_naive,
        ttl_seconds=cache_ttl_seconds_for_mode(INDICATORS_CACHE_MODE),
    )
    return out, {"hit": False, "source": out.get("source")}
