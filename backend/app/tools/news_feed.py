from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from urllib.parse import quote_plus

import feedparser
import requests


def google_news_rss_url(query: str) -> str:
    # Open RSS endpoint (search-based)
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def fetch_google_news(query: str, timeout: float = 8.0) -> List[Dict]:
    """
    Returns normalized items: {title, url, source, published_at}
    """
    url = google_news_rss_url(query)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()

    feed = feedparser.parse(r.text)
    items: List[Dict] = []

    for e in feed.entries[:50]:
        title = (getattr(e, "title", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()

        source = None
        if hasattr(e, "source") and e.source:
            source = getattr(e.source, "title", None)

        published_at = None
        if hasattr(e, "published_parsed") and e.published_parsed:
            published_at = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).replace(tzinfo=None)

        if title and link:
            items.append(
                {
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_at": published_at,
                }
            )

    return items
