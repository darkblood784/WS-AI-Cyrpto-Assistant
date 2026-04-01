from __future__ import annotations

from typing import Any


def _line(k: str, v: str) -> str:
    return f"- {k}: {v}"


def _fmt_usd(x: Any, nd: int = 2) -> str:
    if x is None:
        return "N/A"
    try:
        return f"${float(x):,.{nd}f}"
    except Exception:
        return str(x)


def _fmt_pct(x: Any, nd: int = 2) -> str:
    if x is None:
        return "N/A"
    try:
        return f"{float(x):.{nd}f}%"
    except Exception:
        return str(x)


def format_market_brief_contract(
    *,
    user_message: str,
    symbol: str,
    snapshot: dict | None,
    snapshot_meta: dict,
    news_items: list[dict],
    narrative_text: str | None,
) -> str:
    """
    Phase 6C compliant output:
      1) What you asked
      2) Market snapshot (timestamped)
      3) Indicators & signals (timestamped when present) + Top news (last 48h)
      4) Scenarios (bull/base/bear)
      5) Invalidation
      6) Operator note
    """

    src = (snapshot_meta or {}).get("source") or "unknown"
    hit = bool((snapshot_meta or {}).get("hit"))
    fetched_at = (snapshot or {}).get("asof_utc") if snapshot else "N/A"

    lines: list[str] = []

    # 1) What you asked
    lines.append("1) What you asked")
    lines.append(f"- {user_message.strip()}")

    # 2) Market snapshot
    lines.append("")
    lines.append("2) Market snapshot")
    lines.append(_line("Symbol", symbol))
    lines.append(_line("Fetched at (UTC)", str(fetched_at)))
    lines.append(_line("Source", f"{src} (cache_hit={hit})"))
    if snapshot:
        lines.append(_line("Price (USD)", _fmt_usd(snapshot.get("price_usd"))))
        lines.append(_line("24h change", _fmt_pct(snapshot.get("change_24h_pct"))))
    else:
        err = (snapshot_meta or {}).get("error") or "tool_failed_or_no_data"
        lines.append(_line("Data", f"Missing ({err})"))

    # 3) Indicators & signals + News
    lines.append("")
    lines.append("3) Indicators & signals")
    lines.append("- Not requested. Ask with a timeframe (example: `BTC RSI on 1h` or `ETH analysis 4h`).")

    lines.append("")
    lines.append("Top news (last 48h)")
    if not news_items:
        lines.append("- No recent headlines found.")
    else:
        for i, it in enumerate(news_items[:5], start=1):
            title = (it.get("title") or "").strip() or "Untitled"
            source = (it.get("source") or "").strip() or "Unknown"
            published_at = it.get("published_at") or "N/A"
            lines.append(f"- {i}. {title} ({source}, {published_at})")

    # ---------- User-facing narrative below this separator ----------
    lines.append("")
    lines.append("--- WSAI Analysis ---")

    if narrative_text and narrative_text.strip():
        lines.append(narrative_text.strip())
    else:
        lines.append("No additional commentary available at the moment.")

    # Headlines summary for user context
    if news_items:
        lines.append("")
        lines.append("Key headlines:")
        for i, it in enumerate(news_items[:5], start=1):
            title = (it.get("title") or "").strip() or "Untitled"
            source = (it.get("source") or "").strip() or "Unknown"
            lines.append(f"- {title} ({source})")

    # 4) Scenarios
    lines.append("")
    lines.append("Scenarios:")
    lines.append("- Bull: risk appetite holds and positive headlines pull flows into majors -- dips get bought.")
    lines.append("- Base: mixed news and normal profit-taking keep price range-bound with no clear follow-through.")
    lines.append("- Bear: macro shock or regulatory surprise triggers broad risk-off -- sellers take control.")

    # 5) Risks + invalidation levels
    lines.append("")
    lines.append("Invalidation:")
    lines.append("- Headlines are noisy. One-day moves often reverse. Do not size positions on news alone.")
    lines.append("- Key levels: not available in news-only mode. Ask for `analysis 1h/4h/1d` to get structural levels.")

    # 6) Assumptions
    lines.append("")
    lines.append("Operator note:")
    lines.append("- Data is tool-sourced and timestamped. News feeds can be incomplete.")
    lines.append("- This is decision context, not a trade instruction.")

    return "\n".join(lines)
