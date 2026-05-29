"""News HTTP client: RSS retrieval + article HTML retrieval (R-08).

Two independent functions with a shared http(s) scheme guard (T-04-10 SSRF):
- fetch_rss_feed(url) -> bytes  : plain requests; returns raw XML bytes so
  feedparser can auto-detect the encoding from the `<?xml encoding=...?>`
  declaration.
- fetch_article_html(url) -> str: delegates to trafilatura.fetch_url which
  has UA/redirect heuristics tuned for article HTML.
"""

from __future__ import annotations

import hashlib
import logging

import requests
from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as ReqConnectionError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.exceptions import ProtocolError

_log = logging.getLogger(__name__)

_RETRYABLE_EXC: tuple[type[BaseException], ...] = (
    ReqConnectionError,
    ChunkedEncodingError,
    ProtocolError,
)

# Browser-like UA required for edaily (probe confirmed minimal UAs were rejected).
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) stock-wiki-collector/0.1"
)

_DEFAULT_TIMEOUT = 15


def url_hash8(url: str) -> str:
    """D-06: first 8 hex chars of sha256(url)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


def url_hash64(url: str) -> str:
    """Full 64-char sha256 of canonical URL — v2.0 dedup key for ``news.url_hash``.

    Plan 01-06 replaces the v1.0 ``url_hash8`` (8-char prefix, collision risk
    at scale) with the full sha256 hex digest as the natural UNIQUE key for
    the ``news`` table. ``url_hash8`` is retained for backward compatibility
    with any non-collector code.

    Surface whitespace is stripped (RSS feeds occasionally surface URLs with
    trailing newlines or spaces from CDATA wrapping); the canonical URL string
    is the post-strip value.
    """
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _scheme_ok(url: str) -> bool:
    return url.startswith(("http://", "https://"))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=10.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_rss_feed(feed_url: str) -> bytes | None:
    """Fetch RSS XML via plain `requests`. Returns raw bytes or None on
    scheme violation. Non-2xx raises via raise_for_status (retryable subset
    only retries transient network errors)."""
    if not _scheme_ok(feed_url):
        return None
    resp = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.content


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1.0, min=1.0, max=10.0),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    before_sleep=before_sleep_log(_log, logging.WARNING),
    reraise=True,
)
def fetch_article_html(url: str) -> str | None:
    """Fetch article HTML via trafilatura.fetch_url (keeps its fetching
    heuristics). Returns None on scheme violation or trafilatura failure."""
    if not _scheme_ok(url):
        return None  # SSRF scheme guard (T-04-10)
    import trafilatura

    return trafilatura.fetch_url(url)
