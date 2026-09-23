"""KST publication-date admission happens before article requests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import collectors.news as news
from collectors.news.fetcher import RSSItem, parse_rss


def test_rss_timestamp_has_utc_timezone():
    item = parse_rss(
        b"<rss><channel><item><link>https://example.com/1</link>"
        b"<pubDate>Mon, 20 Apr 2026 00:00:00 +0900</pubDate>"
        b"</item></channel></rss>"
    )[0]
    assert item.published == datetime(2026, 4, 19, 15, tzinfo=UTC)


def test_day_boundaries_and_limit_after_filter(monkeypatch):
    monkeypatch.setattr(news.matcher, "assert_aliases_seeded", lambda engine: None)
    monkeypatch.setattr(news.matcher, "load_scoped_aliases", lambda *a: {})
    monkeypatch.setattr(
        news.Portfolio, "load", lambda root: SimpleNamespace(scope_tickers=lambda: [])
    )
    monkeypatch.setattr(news, "record_collector_run", lambda *a, **kw: None)
    monkeypatch.setattr(news, "FEEDS_BY_OUTLET", {"test": ["https://example.com/rss"]})
    feed = Mock(return_value=b"rss")
    monkeypatch.setattr(news.client, "fetch_rss_feed", feed)
    items = [
        RSSItem("old", "", datetime(2026, 4, 19, 14, 59, 59, tzinfo=UTC)),
        RSSItem("unknown", "", None),
        RSSItem("start", "", datetime(2026, 4, 19, 15, tzinfo=UTC)),
        RSSItem("end", "", datetime(2026, 4, 20, 14, 59, 59, tzinfo=UTC)),
        RSSItem("tomorrow", "", datetime(2026, 4, 20, 15, tzinfo=UTC)),
    ]
    monkeypatch.setattr(news.fetcher, "parse_rss", lambda rss: items)
    article = Mock(return_value=None)
    monkeypatch.setattr(news.client, "fetch_article_html", article)
    for _ in range(2):
        stats = news.collect_news(engine=object(), since="2026-04-20", max_per_feed=2)
        assert stats["failed"] == []
    assert [call.args[0] for call in article.call_args_list] == ["start", "end"] * 2
    assert feed.call_count == 2
    items.append(RSSItem("later", "", datetime(2026, 4, 20, 13, tzinfo=UTC)))
    article.reset_mock()
    news.collect_news(engine=object(), since="2026-04-20", max_per_feed=3)
    assert [call.args[0] for call in article.call_args_list] == ["start", "end", "later"]


def test_invalid_date_rejected_before_database():
    with pytest.raises(ValueError):
        news.collect_news(engine=object(), since="2026-13-01")
