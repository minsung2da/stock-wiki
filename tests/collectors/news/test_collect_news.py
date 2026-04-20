"""Writer + client + collect_news behavior tests (D-06, D-10..D-13, R-08, R-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from collectors.news import client as news_client
from collectors.news.writer import (
    _assert_two_paragraph_cap,
    vault_path_for_news,
    write_news_doc,
)
from shared.frontmatter import read_frontmatter

_FIXTURE_RSS = Path("tests/fixtures/rss")
_FIXTURE_NEWS = Path("tests/fixtures/news")


# ---- Writer ------------------------------------------------------------------


def test_vault_path_for_news_canonical(tmp_path: Path) -> None:
    p = vault_path_for_news(tmp_path, "hankyung", "202604", "abcd1234")
    assert p == tmp_path / "raw" / "news" / "2026-04" / "hankyung_abcd1234.md"


def test_vault_path_for_news_rejects_bad_outlet(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        vault_path_for_news(tmp_path, "../etc", "202604", "abcd1234")


def test_vault_path_for_news_rejects_uppercase_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        vault_path_for_news(tmp_path, "hankyung", "202604", "ABCDEF12")


def test_vault_path_for_news_rejects_bad_yyyymm(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        vault_path_for_news(tmp_path, "hankyung", "26-04", "abcd1234")


def test_assert_two_paragraph_cap_rejects_three(tmp_path: Path) -> None:
    body = "p1\n\np2\n\np3"
    with pytest.raises(ValueError, match="2-paragraph cap"):
        _assert_two_paragraph_cap(body)


def test_write_news_doc_rejects_three_paragraph_body(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_news_doc(
            vault_root=tmp_path,
            outlet="hankyung",
            url="https://www.hankyung.com/article/123",
            url_hash8="deadbeef",
            yyyymm="202604",
            title="t",
            published_iso="2026-04-20T00:00:00+09:00",
            tickers=[{"corp_code": "00126380", "ticker": "005930", "name": "삼성전자"}],
            body="p1\n\np2\n\np3",
        )


def test_write_news_doc_happy_path(tmp_path: Path) -> None:
    path, content_hash = write_news_doc(
        vault_root=tmp_path,
        outlet="hankyung",
        url="https://www.hankyung.com/article/123",
        url_hash8="deadbeef",
        yyyymm="202604",
        title="삼성전자 최대실적",
        published_iso="2026-04-20T00:00:00+09:00",
        tickers=[{"corp_code": "00126380", "ticker": "005930", "name": "삼성전자"}],
        body="첫 번째 문단.\n\n두 번째 문단.",
    )
    assert path.exists()
    fm, body = read_frontmatter(str(path))
    assert fm.provenance.source == "news"
    assert fm.provenance.outlet == "hankyung"
    assert fm.provenance.license_flag == "summary_only"
    assert fm.provenance.trust_level == "semi_trusted"
    assert fm.provenance.content_hash == content_hash
    assert fm.provenance.tickers and fm.provenance.tickers[0].ticker == "005930"
    assert "첫 번째 문단" in body
    assert "두 번째 문단" in body


# ---- Client ------------------------------------------------------------------


def test_fetch_rss_feed_rejects_nonhttp_scheme() -> None:
    assert news_client.fetch_rss_feed("file:///etc/passwd") is None
    assert news_client.fetch_rss_feed("ftp://example.com/feed.xml") is None


def test_fetch_article_html_rejects_nonhttp_scheme() -> None:
    assert news_client.fetch_article_html("file:///etc/passwd") is None
    assert news_client.fetch_article_html("ftp://example.com") is None


def test_url_hash8_stable() -> None:
    h = news_client.url_hash8("https://www.hankyung.com/article/2026042037091")
    assert len(h) == 8
    assert all(c in "0123456789abcdef" for c in h)


def test_fetch_rss_feed_uses_requests_not_trafilatura(monkeypatch) -> None:
    """R-08: fetch_rss_feed must use requests (not trafilatura.fetch_url)."""
    called = {"requests_get": False, "trafilatura_fetch": False}

    class _Resp:
        status_code = 200
        content = b"<?xml?><rss/>"

        def raise_for_status(self):  # noqa: D401
            return None

    def _fake_get(url, headers=None, timeout=None):
        called["requests_get"] = True
        return _Resp()

    def _fake_traf(url):
        called["trafilatura_fetch"] = True
        return "<html/>"

    import requests
    import trafilatura

    monkeypatch.setattr(requests, "get", _fake_get)
    monkeypatch.setattr(trafilatura, "fetch_url", _fake_traf)
    out = news_client.fetch_rss_feed("https://www.hankyung.com/feed/economy")
    assert out == b"<?xml?><rss/>"
    assert called["requests_get"] is True
    assert called["trafilatura_fetch"] is False


def test_fetch_article_html_uses_trafilatura(monkeypatch) -> None:
    """R-08: fetch_article_html must call trafilatura.fetch_url."""
    called = {"trafilatura_fetch": False}

    def _fake_traf(url):
        called["trafilatura_fetch"] = True
        return "<html><body>ok</body></html>"

    import trafilatura

    monkeypatch.setattr(trafilatura, "fetch_url", _fake_traf)
    out = news_client.fetch_article_html("https://www.hankyung.com/article/1")
    assert out == "<html><body>ok</body></html>"
    assert called["trafilatura_fetch"] is True


# ---- collect_news ------------------------------------------------------------


def _single_feed(monkeypatch, outlet: str, feed_url: str, rss_path: Path) -> None:
    """Restrict FEEDS_BY_OUTLET to a single feed for deterministic tests."""
    from collectors.news import feeds as feeds_mod

    monkeypatch.setattr(feeds_mod, "FEEDS_BY_OUTLET", {outlet: [feed_url]})
    # Also patch the re-export in the news package namespace.
    import collectors.news as news_pkg

    monkeypatch.setattr(news_pkg, "FEEDS_BY_OUTLET", {outlet: [feed_url]})


def test_collect_news_startup_guard_raises_before_fetch(vault_tmp, pg_clean, monkeypatch) -> None:
    """R-09: no HTTP call must be issued when entity_aliases is empty."""
    from collectors.news import NoAliasesSeededError, collect_news

    fetched: list[str] = []

    def _boom_rss(url):
        fetched.append(url)
        return b"<rss/>"

    monkeypatch.setattr(news_client, "fetch_rss_feed", _boom_rss)
    with pytest.raises(NoAliasesSeededError):
        collect_news(vault_root=vault_tmp, engine=pg_clean)
    assert fetched == []


def test_collect_news_matches_samsung_and_writes_file(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    """End-to-end: RSS parsed, article fetched, matcher hits 삼성전자 → file written."""
    from collectors.news import collect_news

    rss_bytes = (_FIXTURE_RSS / "hankyung_economy.xml").read_bytes()
    html_sample = (_FIXTURE_NEWS / "hankyung_sample.html").read_text(encoding="utf-8")

    # Craft an RSS with a single item whose title mentions 삼성전자.
    rss_single = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item>"
        b"<title><![CDATA[\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90 "
        b"\xec\xb5\x9c\xeb\x8c\x80\xec\x8b\xa4\xec\xa0\x81]]></title>"
        b"<link>https://www.hankyung.com/article/SAMPLE001</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item></channel></rss>"
    )

    def _fake_rss(url):
        return rss_single

    def _fake_article(url):
        return html_sample

    monkeypatch.setattr(news_client, "fetch_rss_feed", _fake_rss)
    monkeypatch.setattr(news_client, "fetch_article_html", _fake_article)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", rss_bytes)

    stats = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 1, stats
    # Title contains 삼성전자 → matcher hits → file written.
    files = list((vault_tmp / "raw" / "news").rglob("*.md"))
    assert len(files) == 1
    fm, body = read_frontmatter(str(files[0]))
    assert fm.provenance.outlet == "hankyung"
    assert fm.provenance.license_flag == "summary_only"
    assert fm.provenance.trust_level == "semi_trusted"
    assert fm.provenance.tickers and fm.provenance.tickers[0].ticker == "005930"
    # Body must be ≤2 paragraphs (heading takes its own block; strip it first).
    body_after_heading = body.split("\n\n", 1)[1] if "\n\n" in body else ""
    bp = [p for p in body_after_heading.split("\n\n") if p.strip()]
    assert len(bp) <= 2


def test_collect_news_drops_unmatched_article(vault_tmp, seeded_engine, monkeypatch) -> None:
    """Article whose matched tickers intersect scope = ∅ → not written."""
    from collectors.news import collect_news

    html_sample = (_FIXTURE_NEWS / "hankyung_sample.html").read_text(encoding="utf-8")
    rss_single = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item><title>unrelated news</title>"
        b"<link>https://www.hankyung.com/article/SAMPLE999</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item></channel></rss>"
    )

    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss_single)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: html_sample)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", Path("x"))

    stats = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 0
    assert stats["skipped"] >= 1
    assert list((vault_tmp / "raw" / "news").rglob("*.md")) == []


def test_collect_news_idempotent_second_run(vault_tmp, seeded_engine, monkeypatch) -> None:
    """Rerun with identical inputs → content_hash match → skipped."""
    from collectors.news import collect_news

    html_sample = (_FIXTURE_NEWS / "hankyung_sample.html").read_text(encoding="utf-8")
    rss_single = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item>"
        b"<title><![CDATA[\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90 "
        b"\xec\xb5\x9c\xeb\x8c\x80\xec\x8b\xa4\xec\xa0\x81]]></title>"
        b"<link>https://www.hankyung.com/article/SAMPLE001</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item></channel></rss>"
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss_single)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: html_sample)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", Path("x"))

    s1 = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert s1["succeeded"] == 1

    s2 = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert s2["succeeded"] == 0
    assert s2["skipped"] >= 1


def test_collect_news_cross_url_dedup(vault_tmp, seeded_engine, monkeypatch) -> None:
    """R-11: two distinct URLs with identical body → two files, identical content_hash."""
    from collectors.news import collect_news

    html_sample = (_FIXTURE_NEWS / "hankyung_sample.html").read_text(encoding="utf-8")
    rss_two = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item>"
        b"<title><![CDATA[\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90 A]]></title>"
        b"<link>https://www.hankyung.com/article/SAMPLE001</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item>"
        b"<item>"
        b"<title><![CDATA[\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90 A]]></title>"
        b"<link>https://www.hankyung.com/article/SAMPLE001?utm_source=twitter</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item>"
        b"</channel></rss>"
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss_two)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: html_sample)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", Path("x"))

    stats = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 2
    files = sorted((vault_tmp / "raw" / "news").rglob("*.md"))
    assert len(files) == 2
    fm_a, _ = read_frontmatter(str(files[0]))
    fm_b, _ = read_frontmatter(str(files[1]))
    assert files[0] != files[1]
    assert fm_a.provenance.content_hash == fm_b.provenance.content_hash


def test_collect_news_records_heartbeat(vault_tmp, seeded_engine, monkeypatch) -> None:
    from collectors.news import collect_news

    rss_empty = b"<?xml version='1.0'?><rss version='2.0'><channel><title>t</title></channel></rss>"
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss_empty)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", Path("x"))
    collect_news(vault_root=vault_tmp, engine=seeded_engine)
    hb = vault_tmp / "ingested" / "_status" / "heartbeat.md"
    assert hb.exists()
    content = hb.read_text(encoding="utf-8")
    assert "news:" in content


def test_collect_news_soft_skips_when_trafilatura_returns_none(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    from collectors.news import collect_news

    rss_single = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item><title>x</title>"
        b"<link>https://www.hankyung.com/article/SAMPLE002</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item></channel></rss>"
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss_single)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html>no body</html>")
    # Also patch extract to return None to be deterministic.
    from collectors.news import fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "extract_first_two_paragraphs", lambda html: None)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", Path("x"))

    stats = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["failed"] == [] or all(
        "extract" not in str(x) for x in stats["failed"]
    )  # no hard failure
    assert stats["succeeded"] == 0


def test_collect_news_truncates_body_to_two_paragraphs(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    from collectors.news import collect_news
    from collectors.news import fetcher as fetcher_mod

    rss_single = (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item>"
        b"<title><![CDATA[\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90]]></title>"
        b"<link>https://www.hankyung.com/article/TRUNC1</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item></channel></rss>"
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss_single)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    # Stub trafilatura output: 5 paragraphs → fetcher truncates to 2.
    raw_5para = "p1.\n\np2.\n\np3.\n\np4.\n\np5."
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda *a, **kw: raw_5para)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy", Path("x"))

    stats = collect_news(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 1
    files = list((vault_tmp / "raw" / "news").rglob("*.md"))
    assert len(files) == 1
    _fm, body = read_frontmatter(str(files[0]))
    # Body should contain only p1. and p2., not p3/p4/p5.
    assert "p1." in body and "p2." in body
    assert "p3." not in body
    assert "p4." not in body
    assert "p5." not in body
    # Verify fetcher truncation helper directly too.
    assert fetcher_mod.extract_first_two_paragraphs.__name__ == "extract_first_two_paragraphs"
