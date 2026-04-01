# backend/app/core/formatters/crypto_contract.py
from __future__ import annotations

from typing import Any, Dict, Optional


# -----------------------------
# Formatting helpers
# -----------------------------

def _fmt_num(x: Any, nd: int = 4) -> str:
    if x is None:
        return "N/A"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "N/A"


def _fmt_pct(x: Any, nd: int = 2) -> str:
    if x is None:
        return "N/A"
    try:
        return f"{float(x):.{nd}f}%"
    except Exception:
        return "N/A"


def _fmt_usd(x: Any, nd: int = 2) -> str:
    if x is None:
        return "N/A"
    try:
        return f"${float(x):,.{nd}f}"
    except Exception:
        return "N/A"


def _line(k: str, v: str) -> str:
    return f"- {k}: {v}"


def rsi_label(rsi_val: Any) -> str:
    try:
        r = float(rsi_val)
    except Exception:
        return "unknown"

    if r >= 70:
        return "overbought"
    if r <= 30:
        return "oversold"
    if 60 < r < 70:
        return "strong (near overbought)"
    if 30 < r < 40:
        return "weak (near oversold)"
    return "neutral"


def _safe_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None

def _append_narrative_block(lines: list[str], narrative_text: Optional[str]) -> None:
    """
    Appends WSAI strategic analysis after the data sections.
    Always adds the separator so _extract_display can split reliably.
    """
    lines.append("")
    lines.append("--- WSAI Analysis ---")
    t = (narrative_text or "").strip()
    if t:
        lines.append(t)
    else:
        lines.append("Narrative unavailable. Use the data above to inform your own read.")

def _pick_fetched_at(obj: Optional[dict], meta: Optional[dict]) -> str:
    """
    Prefer object.asof_utc if present; otherwise look at meta hints; else N/A.
    """
    if obj and obj.get("asof_utc"):
        return str(obj.get("asof_utc"))
    if meta:
        for k in ("asof_utc", "fetched_at_utc", "fetched_at", "timestamp_utc", "ts_utc"):
            if meta.get(k):
                return str(meta.get(k))
    return "N/A"


def _pick_source(meta: Optional[dict]) -> str:
    if not meta:
        return "unknown"
    return str(meta.get("source") or "unknown")


def _pick_cache_hit(meta: Optional[dict]) -> str:
    if not meta:
        return "N/A"
    # common keys: hit, cache_hit
    if "hit" in meta:
        return str(bool(meta.get("hit")))
    if "cache_hit" in meta:
        return str(bool(meta.get("cache_hit")))
    return "N/A"


# -----------------------------
# Deterministic signal summary
# -----------------------------

def _derive_bias_and_momentum(snapshot: Optional[dict], indicators: Optional[dict]) -> Dict[str, str]:
    """
    Deterministic, tool-only qualitative labels.
    No invented numbers.
    """
    price = _safe_float((snapshot or {}).get("price_usd"))

    rsi = _safe_float((indicators or {}).get("rsi_14"))
    ema20 = _safe_float((indicators or {}).get("ema_20"))
    sma50 = _safe_float((indicators or {}).get("sma_50"))

    macd_obj = (indicators or {}).get("macd_12_26_9") or {}
    macd_line = _safe_float(macd_obj.get("macd"))
    macd_sig = _safe_float(macd_obj.get("signal"))
    macd_hist = _safe_float(macd_obj.get("hist"))

    score = 0

    # RSI influence (weakly)
    rsi_tag = rsi_label(rsi)
    if rsi_tag in ("overbought", "strong (near overbought)"):
        score += 1
    elif rsi_tag in ("oversold", "weak (near oversold)"):
        score -= 1

    # Price vs trend levels (if available)
    if price is not None and ema20 is not None:
        score += 1 if price >= ema20 else -1
    if price is not None and sma50 is not None:
        score += 1 if price >= sma50 else -1

    # MACD direction (if available)
    if macd_line is not None and macd_sig is not None:
        score += 1 if macd_line >= macd_sig else -1

    if score >= 2:
        bias = "bullish-leaning"
    elif score <= -2:
        bias = "bearish-leaning"
    else:
        bias = "mixed"

    # Momentum label
    if macd_line is None or macd_sig is None:
        momentum = "unknown"
    else:
        momentum = "bullish-leaning" if macd_line >= macd_sig else "bearish-leaning"

    # Optional extra note based on histogram
    if macd_hist is None:
        momentum_detail = "unknown"
    else:
        if macd_hist > 0:
            momentum_detail = "improving"
        elif macd_hist < 0:
            momentum_detail = "weakening"
        else:
            momentum_detail = "flat"

    return {
        "bias": bias,
        "rsi_label": rsi_tag,
        "momentum": momentum,
        "momentum_detail": momentum_detail,
    }


# -----------------------------
# Phase 6C Contract formatters (6 sections)
# -----------------------------

def format_price_contract(
    *,
    user_message: str,
    symbol: str,
    snapshot: Optional[dict],
    snapshot_meta: Optional[dict] = None,
    **kwargs,  # accept future args without breaking callers
) -> str:
    # SECTION 1
    lines: list[str] = []
    lines.append("1) What you asked")
    lines.append(f"- {user_message.strip()}")

    # SECTION 2
    src = _pick_source(snapshot_meta)
    hit = _pick_cache_hit(snapshot_meta)
    fetched_at = _pick_fetched_at(snapshot, snapshot_meta)

    lines.append("")
    lines.append("2) Market snapshot")
    lines.append(_line("Symbol", symbol))
    lines.append(_line("Fetched at (UTC)", fetched_at))
    lines.append(_line("Source", f"{src} (cache_hit={hit})"))

    if snapshot is None:
        err = (snapshot_meta or {}).get("error") if snapshot_meta else None
        lines.append(_line("Data", f"Missing ({err or 'tool_failed_or_no_data'})"))
    else:
        lines.append(_line("Price (USD)", _fmt_usd(snapshot.get("price_usd"))))
        lines.append(_line("24h change", _fmt_pct(snapshot.get("change_24h_pct"))))
        # keep these if available; otherwise they show N/A
        lines.append(_line("24h volume (USD)", _fmt_usd(snapshot.get("volume_24h_usd"))))
        lines.append(_line("Market cap (USD)", _fmt_usd(snapshot.get("market_cap_usd"))))

    # SECTION 3
    lines.append("")
    lines.append("3) Indicators & signals")
    lines.append("- Not requested. Ask with a timeframe (example: `BTC analysis 1h` or `ETH RSI on 4h`).")

    # SECTION 4
    lines.append("")
    lines.append("4) Scenarios")
    lines.append("- Bull: buyers defend structure and dips get bought with volume — continuation above current levels.")
    lines.append("- Base: price chops around current range with no clear directional follow-through.")
    lines.append("- Bear: sellers reclaim control and rallies get faded — structure breaks lower.")

    # SECTION 5
    lines.append("")
    lines.append("5) Invalidation")
    lines.append("- A single snapshot is not a trend. Direction can flip on news or liquidity events.")
    lines.append("- Key levels: not available in price-only mode. Ask for `analysis` with a timeframe to get structural levels (EMA/SMA).")

    # SECTION 6
    lines.append("")
    lines.append("6) Operator note")
    lines.append("- Data is tool-sourced and timestamped. This is decision context, not a trade instruction.")

    narrative_text = (kwargs.get("narrative_text") or "").strip()
    _append_narrative_block(lines, narrative_text)

    return "\n".join(lines)



def format_indicators_contract(
    *,
    user_message: str,
    symbol: str,
    timeframe: str,
    snapshot: Optional[dict],
    snapshot_meta: Optional[dict],
    indicators: Optional[dict],
    indicators_meta: Optional[dict],
    focus: str = "full",  # "rsi" | "macd" | "ema20" | "full"
    include_yes_hint: bool = False,
    **kwargs,  # accept narrative_text and any future args without crashing
) -> str:
    # SECTION 1
    lines: list[str] = []
    lines.append("1) What you asked")
    lines.append(f"- {user_message.strip()}")

    # SECTION 2
    snap_src = _pick_source(snapshot_meta)
    snap_hit = _pick_cache_hit(snapshot_meta)
    snap_fetched = _pick_fetched_at(snapshot, snapshot_meta)

    lines.append("")
    lines.append("2) Market snapshot")
    lines.append(_line("Symbol", symbol))
    lines.append(_line("Fetched at (UTC)", snap_fetched))
    lines.append(_line("Source", f"{snap_src} (cache_hit={snap_hit})"))

    if snapshot is None:
        err = (snapshot_meta or {}).get("error")
        lines.append(_line("Data", f"Missing ({err or 'tool_failed_or_no_data'})"))
    else:
        lines.append(_line("Price (USD)", _fmt_usd(snapshot.get("price_usd"))))
        lines.append(_line("24h change", _fmt_pct(snapshot.get("change_24h_pct"))))
        # optional, but nice when present
        if snapshot.get("volume_24h_usd") is not None:
            lines.append(_line("24h volume (USD)", _fmt_usd(snapshot.get("volume_24h_usd"))))
        if snapshot.get("market_cap_usd") is not None:
            lines.append(_line("Market cap (USD)", _fmt_usd(snapshot.get("market_cap_usd"))))

    # SECTION 3
    ind_src = _pick_source(indicators_meta)
    ind_hit = _pick_cache_hit(indicators_meta)
    ind_fetched = _pick_fetched_at(indicators, indicators_meta)

    lines.append("")
    lines.append("3) Indicators & signals")
    lines.append(_line("Timeframe", timeframe))
    lines.append(_line("Fetched at (UTC)", ind_fetched))
    lines.append(_line("Source", f"{ind_src} (cache_hit={ind_hit})"))

    # pull tool fields (may be missing)
    rsi = (indicators or {}).get("rsi_14")
    ema20 = (indicators or {}).get("ema_20")
    sma20 = (indicators or {}).get("sma_20")
    sma50 = (indicators or {}).get("sma_50")
    sma200 = (indicators or {}).get("sma_200")
    macd_obj = (indicators or {}).get("macd_12_26_9") or {}

    if indicators is None:
        err = (indicators_meta or {}).get("error")
        lines.append(_line("Data", f"Missing ({err or 'tool_failed_or_no_data'})"))
        bias_pack = {"bias": "unknown", "rsi_label": "unknown", "momentum": "unknown", "momentum_detail": "unknown"}
    else:
        # Always show requested fields; show N/A if missing
        if focus == "rsi":
            lines.append(_line("RSI(14)", _fmt_num(rsi, 2)))
        elif focus == "ema20":
            lines.append(_line("EMA(20)", _fmt_num(ema20, 4)))
        elif focus == "macd":
            lines.append(_line(
                "MACD",
                f"macd={_fmt_num(macd_obj.get('macd'), 4)} signal={_fmt_num(macd_obj.get('signal'), 4)} hist={_fmt_num(macd_obj.get('hist'), 4)}"
            ))
        else:
            lines.append(_line("RSI(14)", _fmt_num(rsi, 2)))
            lines.append(_line("EMA(20)", _fmt_num(ema20, 4)))
            lines.append(_line("SMA(20)", _fmt_num(sma20, 4)))
            lines.append(_line("SMA(50)", _fmt_num(sma50, 4)))
            lines.append(_line("SMA(200)", _fmt_num(sma200, 4)))
            lines.append(_line(
                "MACD",
                f"macd={_fmt_num(macd_obj.get('macd'), 4)} signal={_fmt_num(macd_obj.get('signal'), 4)} hist={_fmt_num(macd_obj.get('hist'), 4)}"
            ))

        bias_pack = _derive_bias_and_momentum(snapshot, indicators)

        # “smart read” line is derived from tool facts only
        lines.append(_line("Bias", bias_pack["bias"]))
        lines.append(_line("RSI label", bias_pack["rsi_label"]))
        if bias_pack["momentum"] != "unknown":
            lines.append(_line("Momentum (MACD)", bias_pack["momentum"]))

    # SECTION 4
    lines.append("")
    lines.append("4) Scenarios")
    lines.append("- Bull: price holds above key averages with constructive momentum -- pullbacks stay controlled and get bought.")
    lines.append("- Base: mixed signals dominate -- expect range-bound action and false breakouts.")
    lines.append("- Bear: momentum deteriorates and price rejects from key averages -- sellers take control.")

    # SECTION 5
    lines.append("")
    lines.append("5) Invalidation")
    lines.append("- Sideways markets produce false signals. Confirm direction with a higher timeframe before acting.")
    if indicators is None:
        lines.append("- Structural levels unavailable -- indicators are missing.")
    else:
        lines.append("- Key structural levels (tool-sourced):")
        lines.append(f"  - EMA(20): {_fmt_num(ema20, 4)}")
        lines.append(f"  - SMA(50): {_fmt_num(sma50, 4)}")
        lines.append(f"  - SMA(200): {_fmt_num(sma200, 4)}")
        lines.append("- Rule: if price fails to hold a reclaimed average, the bullish read weakens. Repeated rejection = bearish confirmation.")

    # SECTION 6
    lines.append("")
    lines.append("6) Operator note")
    lines.append("- All data is tool-sourced and timestamped. This is strategic context, not a trade instruction.")

    narrative_text = (kwargs.get("narrative_text") or "").strip()
    _append_narrative_block(lines, narrative_text)
    
    if include_yes_hint:
        lines.append("")
        lines.append("Reply `yes` if you want the full indicator set.")

    return "\n".join(lines)

