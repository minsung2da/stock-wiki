"""RSS parsing + trafilatura body extraction (D-13: first 2 paragraphs only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import feedparser
import trafilatura


@dataclass(frozen=True)
class RSSItem:
    url: str
    title: str
    published: datetime | None


def parse_rss(rss_content: str | bytes) -> list[RSSItem]:
    """feedparser handles bytes (preferred, encoding auto-detect) or str."""
    parsed = feedparser.parse(rss_content)
    out: list[RSSItem] = []
    for e in parsed.entries:
        pub: datetime | None = None
        pub_parsed = getattr(e, "published_parsed", None)
        if pub_parsed:
            pub = datetime(*pub_parsed[:6])
        title = getattr(e, "title", "") or ""
        link = getattr(e, "link", "") or ""
        if not link:
            continue
        out.append(RSSItem(url=link, title=title, published=pub))
    return out


def extract_first_two_paragraphs(html: str) -> str | None:
    """D-13 copyright cap: return the first 2 non-empty \\n\\n-separated
    paragraphs from trafilatura's plain-text extraction, or None if empty."""
    text = trafilatura.extract(
        html,
        output_format="txt",
        include_comments=False,
        include_tables=False,
        include_images=False,
        favor_precision=True,
        deduplicate=False,
    )
    if not text:
        return None
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return None
    return "\n\n".join(paragraphs[:2])
