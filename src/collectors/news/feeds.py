"""RSS feed URL constants + outlet detection (D-09).

Verified live on 2026-04-20 (Wave-0 probe):
- Hankyung economy/finance: HTTPS, RSS 2.0, ~50 items per fetch.
- edaily: HTTP-only — HTTPS fails (Microsoft-IIS/7.5 backend at 125.209.202.172
  without TLS SNI for this hostname). Keep plain http:// until edaily enables TLS.

User-Agent: edaily rejected minimal UA strings in probe; use a browser-like UA
for all outbound news requests (see client.USER_AGENT).
"""

from __future__ import annotations

from urllib.parse import urlparse

HANKYUNG_ECONOMY_FEED = "https://www.hankyung.com/feed/economy"
HANKYUNG_FINANCE_FEED = "https://www.hankyung.com/feed/finance"
EDAILY_FEED = "http://rss.edaily.co.kr/edaily_news.xml"

FEEDS_BY_OUTLET: dict[str, list[str]] = {
    "hankyung": [HANKYUNG_ECONOMY_FEED, HANKYUNG_FINANCE_FEED],
    "edaily": [EDAILY_FEED],
}

_OUTLET_BY_HOST = {
    "hankyung.com": "hankyung",
    "www.hankyung.com": "hankyung",
    "edaily.co.kr": "edaily",
    "www.edaily.co.kr": "edaily",
    "rss.edaily.co.kr": "edaily",
}


def detect_outlet(url: str) -> str | None:
    """Return outlet slug for a URL, or None if unknown."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return None
    return _OUTLET_BY_HOST.get(host.lower())
