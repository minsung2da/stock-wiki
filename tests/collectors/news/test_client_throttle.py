"""collectors.news.client proactive-throttle wiring (CAP-1)."""

from __future__ import annotations

import time

from collectors.news import client as news_client


class _Resp:
    content = b"<?xml?><rss/>"

    def raise_for_status(self) -> None:  # noqa: D401
        return None


def test_fetch_rss_feed_paces_back_to_back_calls(monkeypatch) -> None:
    """Two consecutive RSS fetches are spaced by >= the throttle interval."""
    interval = 0.12
    monkeypatch.setattr(news_client._throttle, "min_interval_sec", interval)
    news_client._throttle.reset()
    monkeypatch.setattr(news_client.requests, "get", lambda *a, **k: _Resp())

    # First call primes the throttle (no sleep on a fresh/reset throttle).
    assert news_client.fetch_rss_feed("https://www.hankyung.com/feed") == _Resp.content

    start = time.monotonic()
    assert news_client.fetch_rss_feed("https://www.hankyung.com/feed") == _Resp.content
    assert time.monotonic() - start >= interval * 0.9


def test_scheme_rejected_url_does_not_throttle(monkeypatch) -> None:
    """A scheme-rejected URL returns None before touching the throttle/network."""
    monkeypatch.setattr(news_client._throttle, "min_interval_sec", 10.0)
    news_client._throttle.reset()
    # Even with a 10s interval, the rejected call returns immediately.
    start = time.monotonic()
    assert news_client.fetch_rss_feed("file:///etc/passwd") is None
    assert news_client.fetch_article_html("ftp://example.com") is None
    assert time.monotonic() - start < 0.5
