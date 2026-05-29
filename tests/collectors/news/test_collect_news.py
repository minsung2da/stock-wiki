"""Writer + client + collect_news behavior tests.

Phase 1 plan 01-06 cutover: ``collect_news`` tests now assert DB state in the
``news`` table instead of vault path existence. Writer module tests are
retained until plan 01-09 deletes ``writer.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

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


# ---- collect_news (DB-backed; plan 01-06) -----------------------------------


def _single_feed(monkeypatch, outlet: str, feed_url: str) -> None:
    """Restrict FEEDS_BY_OUTLET to a single feed for deterministic tests."""
    from collectors.news import feeds as feeds_mod

    monkeypatch.setattr(feeds_mod, "FEEDS_BY_OUTLET", {outlet: [feed_url]})
    # Also patch the re-export in the news package namespace.
    import collectors.news as news_pkg

    monkeypatch.setattr(news_pkg, "FEEDS_BY_OUTLET", {outlet: [feed_url]})


def _seed_portfolio(monkeypatch, vault_tmp_dir: Path) -> None:
    """Chdir into the vault_tmp parent so Portfolio.load(Path(".")) finds the
    seeded notes/private/portfolio.md materialized by the vault_tmp fixture."""
    monkeypatch.chdir(vault_tmp_dir.parent)


def _rss_one_item(title_utf8_bytes: bytes, url: bytes) -> bytes:
    return (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b"<rss version='2.0'><channel><title>test</title>"
        b"<item>"
        b"<title><![CDATA[" + title_utf8_bytes + b"]]></title>"
        b"<link>" + url + b"</link>"
        b"<pubDate>Mon, 20 Apr 2026 21:00:01 +0900</pubDate>"
        b"</item></channel></rss>"
    )


def _select_news_count(engine) -> int:
    with engine.begin() as conn:
        return conn.execute(text("SELECT count(*) FROM news")).scalar() or 0


def _select_news_row(engine, url_hash: str):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT url_hash, url, outlet, corp_code, tickers, title, "
                "       content_hash, body_md, license_flag "
                "FROM news WHERE url_hash=:uh"
            ),
            {"uh": url_hash},
        ).first()


def test_collect_news_no_engine_raises() -> None:
    """Engine is required; calling without it raises RuntimeError."""
    from collectors.news import collect_news

    with pytest.raises(RuntimeError):
        collect_news(engine=None)


def test_collect_news_assert_aliases_seeded_raises(
    vault_tmp, pg_clean, monkeypatch
) -> None:
    """R-09: refuses to operate when entity_aliases is empty — BEFORE any HTTP call."""
    from collectors.news import NoAliasesSeededError, collect_news

    _seed_portfolio(monkeypatch, vault_tmp)

    fetched: list[str] = []

    def _boom_rss(url):
        fetched.append(url)
        return b"<rss/>"

    monkeypatch.setattr(news_client, "fetch_rss_feed", _boom_rss)
    with pytest.raises(NoAliasesSeededError):
        collect_news(engine=pg_clean)
    assert fetched == []


def test_collect_news_inserts_row(vault_tmp, seeded_engine, monkeypatch) -> None:
    """End-to-end: RSS parsed → article fetched → matcher hits 삼성전자 → DB row UPSERTed."""
    from collectors.news import collect_news
    from collectors.news.client import url_hash64

    _seed_portfolio(monkeypatch, vault_tmp)

    # CDATA bytes = 삼성전자 최대실적
    rss = _rss_one_item(
        b"\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90 "
        b"\xec\xb5\x9c\xeb\x8c\x80\xec\x8b\xa4\xec\xa0\x81",
        b"https://www.hankyung.com/article/INSERT01",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    # Stub trafilatura.extract so the matcher gets text containing 삼성전자.
    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자 1분기 매출 사상 최대.\n\n메모리 사이클 회복.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    stats = collect_news(engine=seeded_engine)
    assert stats["inserted"] == 1, stats
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == []

    row = _select_news_row(
        seeded_engine, url_hash64("https://www.hankyung.com/article/INSERT01")
    )
    assert row is not None
    assert row.outlet == "hankyung"
    assert row.tickers == ["005930"]
    assert row.corp_code == "00126380"
    assert "삼성전자" in row.body_md
    assert row.license_flag == "summary_only"


def test_collect_news_idempotent(vault_tmp, seeded_engine, monkeypatch) -> None:
    """Re-run with identical body → 2nd call: skipped=1; no new row."""
    from collectors.news import collect_news

    _seed_portfolio(monkeypatch, vault_tmp)

    rss = _rss_one_item(
        b"\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90",
        b"https://www.hankyung.com/article/IDEMP01",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자 1분기 매출.\n\n메모리 사이클 회복.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    s1 = collect_news(engine=seeded_engine)
    assert s1["inserted"] == 1
    assert _select_news_count(seeded_engine) == 1

    s2 = collect_news(engine=seeded_engine)
    assert s2["inserted"] == 0
    assert s2["updated"] == 0
    assert s2["skipped"] == 1
    assert _select_news_count(seeded_engine) == 1  # still one row


def test_collect_news_body_edited_updates(vault_tmp, seeded_engine, monkeypatch) -> None:
    """2nd run with edited body → outcome=updated; content_hash differs."""
    from collectors.news import collect_news
    from collectors.news.client import url_hash64

    _seed_portfolio(monkeypatch, vault_tmp)

    rss = _rss_one_item(
        b"\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90",
        b"https://www.hankyung.com/article/EDITED01",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자 원본 본문.\n\n원본 두 번째 문단.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    s1 = collect_news(engine=seeded_engine)
    assert s1["inserted"] == 1
    row1 = _select_news_row(
        seeded_engine, url_hash64("https://www.hankyung.com/article/EDITED01")
    )
    hash_1 = row1.content_hash

    # Second run with EDITED body (publisher revised the article).
    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자 수정된 본문.\n\n수정된 두 번째 문단.",
    )
    s2 = collect_news(engine=seeded_engine)
    assert s2["updated"] == 1
    assert s2["inserted"] == 0
    assert s2["skipped"] == 0

    row2 = _select_news_row(
        seeded_engine, url_hash64("https://www.hankyung.com/article/EDITED01")
    )
    assert row2.content_hash != hash_1
    assert "수정된" in row2.body_md


def test_collect_news_no_match_skipped(vault_tmp, seeded_engine, monkeypatch) -> None:
    """Body with no alias matches → skipped; no DB row written."""
    from collectors.news import collect_news

    _seed_portfolio(monkeypatch, vault_tmp)

    rss = _rss_one_item(
        b"unrelated headline",
        b"https://www.hankyung.com/article/NOMATCH01",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    import trafilatura

    # Body contains NO seeded ticker aliases (Samsung 삼성전자 not mentioned).
    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "Apple iPhone launch.\n\nMore iPhone news.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    stats = collect_news(engine=seeded_engine)
    assert stats["inserted"] == 0
    assert stats["updated"] == 0
    assert stats["skipped"] >= 1
    assert _select_news_count(seeded_engine) == 0


def test_collect_news_multiple_tickers_array(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    """Body mentioning both Samsung + SK Hynix → tickers TEXT[] = ['005930','000660'].

    GIN @> query returns the row.
    """
    from collectors.news import collect_news
    from collectors.news.client import url_hash64

    _seed_portfolio(monkeypatch, vault_tmp)

    # Pre-seed SK Hynix entity + alias (seeded_engine already has Samsung).
    with seeded_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00164779','SK하이닉스','000660','KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00164779','ticker','000660',:vf,NULL),"
                "       ('00164779','name','SK하이닉스',:vf,NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )
    # Portfolio watchlist already contains 000660 (per conftest seed).

    rss = _rss_one_item(
        b"\xeb\xb0\x98\xeb\x8f\x84\xec\xb2\xb4",  # 반도체
        b"https://www.hankyung.com/article/MULTI01",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자와 SK하이닉스 동반 호조.\n\n반도체 사이클 회복.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    stats = collect_news(engine=seeded_engine)
    assert stats["inserted"] == 1

    row = _select_news_row(
        seeded_engine, url_hash64("https://www.hankyung.com/article/MULTI01")
    )
    assert row is not None
    # Both tickers present in the array (order from matcher = longest alias first).
    assert set(row.tickers) == {"005930", "000660"}

    # GIN @> query works
    with seeded_engine.begin() as conn:
        n_samsung = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['005930']")
        ).scalar()
        n_hynix = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['000660']")
        ).scalar()
    assert n_samsung == 1
    assert n_hynix == 1


def test_collect_news_no_markdown_written(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    """Veto #9: after successful run, no vault/raw/news/ directory exists in CWD."""
    from collectors.news import collect_news

    _seed_portfolio(monkeypatch, vault_tmp)

    rss = _rss_one_item(
        b"\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90",
        b"https://www.hankyung.com/article/NOMD01",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자 호조.\n\n반도체 회복.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    collect_news(engine=seeded_engine)

    # No vault/raw/news/ subdir was created by collect_news under cwd.
    # (chdir is to vault_tmp.parent, which has only notes/private/.)
    cwd_path = Path(".").resolve()
    assert not (cwd_path / "vault" / "raw" / "news").exists()


def test_collect_news_truncates_body_to_two_paragraphs(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    """D-13 cap: trafilatura returns 5 paragraphs → DB row body_md has only 2."""
    from collectors.news import collect_news
    from collectors.news.client import url_hash64

    _seed_portfolio(monkeypatch, vault_tmp)

    rss = _rss_one_item(
        b"\xec\x82\xbc\xec\x84\xb1\xec\xa0\x84\xec\x9e\x90",
        b"https://www.hankyung.com/article/TRUNC1",
    )
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    raw_5para = "삼성전자 p1.\n\np2.\n\np3.\n\np4.\n\np5."
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda *a, **kw: raw_5para)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    stats = collect_news(engine=seeded_engine)
    assert stats["inserted"] == 1

    row = _select_news_row(
        seeded_engine, url_hash64("https://www.hankyung.com/article/TRUNC1")
    )
    # Body kept first two paragraphs only.
    assert "p1" in row.body_md
    assert "p2" in row.body_md
    assert "p3" not in row.body_md
    assert "p4" not in row.body_md
    assert "p5" not in row.body_md


def test_collect_news_soft_skips_when_trafilatura_returns_none(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    """trafilatura.extract → None: counted as skipped, no failure, no DB row."""
    from collectors.news import collect_news

    _seed_portfolio(monkeypatch, vault_tmp)

    rss = _rss_one_item(b"x", b"https://www.hankyung.com/article/NOBODY1")
    monkeypatch.setattr(news_client, "fetch_rss_feed", lambda url: rss)
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html>x</html>")
    from collectors.news import fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "extract_first_two_paragraphs", lambda html: None)
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    stats = collect_news(engine=seeded_engine)
    assert stats["inserted"] == 0
    assert stats["updated"] == 0
    assert stats["skipped"] >= 1
    assert stats["failed"] == []
    assert _select_news_count(seeded_engine) == 0


def test_collect_news_cross_url_dedup_writes_two_rows_same_content_hash(
    vault_tmp, seeded_engine, monkeypatch
) -> None:
    """R-11: two distinct URLs with identical body → two news rows, identical content_hash."""
    from collectors.news import collect_news

    _seed_portfolio(monkeypatch, vault_tmp)

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
    monkeypatch.setattr(news_client, "fetch_article_html", lambda url: "<html/>")
    import trafilatura

    monkeypatch.setattr(
        trafilatura,
        "extract",
        lambda *a, **kw: "삼성전자 동일 본문.\n\n동일 두 번째 문단.",
    )
    _single_feed(monkeypatch, "hankyung", "https://www.hankyung.com/feed/economy")

    stats = collect_news(engine=seeded_engine)
    assert stats["inserted"] == 2  # 2 distinct url_hashes
    with seeded_engine.begin() as conn:
        rows = conn.execute(
            text("SELECT url, content_hash FROM news ORDER BY url")
        ).fetchall()
    assert len(rows) == 2
    # Same content_hash (R-11 accepted tradeoff)
    assert rows[0].content_hash == rows[1].content_hash
    # Different url
    assert rows[0].url != rows[1].url
