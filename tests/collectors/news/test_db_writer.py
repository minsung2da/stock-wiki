"""Tests for collectors.news.db_writer — Phase 1 Plan 01-06.

Covers the news UPSERT writer:
- url_hash64 stability + whitespace tolerance
- inserted / updated / skipped outcomes (content_hash diff drives the split)
- tickers TEXT[] populated; GIN @> queries work
- corp_code FK SET NULL on entity delete
- license_flag default & override
- naive vs aware datetime → both land as TIMESTAMPTZ

All tests assert DB state via the `pg_clean` / `seeded_engine` fixtures.

Hard Veto reminders verified by the schema (migration 0006) — these tests focus
on the writer's correctness, not on schema invariants.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from sqlalchemy import text


def _select_news_by_url_hash(engine, url_hash: str):
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT url_hash, url, outlet, corp_code, tickers, "
                "       published_at, title, content_hash, body_md, "
                "       license_flag, first_seen_at, last_seen_at "
                "FROM news WHERE url_hash=:uh"
            ),
            {"uh": url_hash},
        ).first()
    return row


# ---- url_hash64 helper ------------------------------------------------------


def test_url_hash64_stable() -> None:
    """Same URL → same hash; trailing/leading whitespace is stripped before hash."""
    from collectors.news.client import url_hash64

    h1 = url_hash64("https://www.hankyung.com/article/2026042037091")
    h2 = url_hash64("  https://www.hankyung.com/article/2026042037091 \n")
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_url_hash64_different_urls_different_hash() -> None:
    from collectors.news.client import url_hash64

    h1 = url_hash64("https://www.hankyung.com/article/A")
    h2 = url_hash64("https://www.hankyung.com/article/B")
    assert h1 != h2


# ---- inserted path ----------------------------------------------------------


def test_upsert_news_inserts_fresh(seeded_engine):
    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    url = "https://www.hankyung.com/article/INSERT01"
    outcome = upsert_news_article(
        seeded_engine,
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 1, tzinfo=UTC),
        title="삼성전자 최대실적",
        body_md="첫 번째 문단.\n\n두 번째 문단.",
        tickers=["005930"],
        corp_code="00126380",
    )
    assert outcome == "inserted"

    row = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    assert row is not None
    assert row.outlet == "hankyung"
    assert row.tickers == ["005930"]
    assert row.corp_code == "00126380"
    assert row.body_md == "첫 번째 문단.\n\n두 번째 문단."
    assert row.license_flag == "summary_only"
    assert row.title == "삼성전자 최대실적"


# ---- idempotent skip path ---------------------------------------------------


def test_upsert_news_idempotent(seeded_engine):
    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    url = "https://www.hankyung.com/article/IDEMP01"
    kwargs = dict(
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 1, tzinfo=UTC),
        title="삼성전자",
        body_md="문단 A.\n\n문단 B.",
        tickers=["005930"],
        corp_code="00126380",
    )
    out1 = upsert_news_article(seeded_engine, **kwargs)
    assert out1 == "inserted"
    row1 = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    first_seen = row1.first_seen_at
    last_seen_1 = row1.last_seen_at

    # Identical second call → skipped
    out2 = upsert_news_article(seeded_engine, **kwargs)
    assert out2 == "skipped"

    row2 = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    # first_seen_at preserved; last_seen_at bumped (>= first call's last_seen_at)
    assert row2.first_seen_at == first_seen
    assert row2.last_seen_at >= last_seen_1
    # content_hash unchanged
    assert row2.content_hash == row1.content_hash


# ---- updated path (body edited) --------------------------------------------


def test_upsert_news_body_edited(seeded_engine):
    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    url = "https://www.hankyung.com/article/EDITED01"
    out1 = upsert_news_article(
        seeded_engine,
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 1, tzinfo=UTC),
        title="삼성전자",
        body_md="원본 문단.\n\n원본 두 번째.",
        tickers=["005930"],
        corp_code="00126380",
    )
    assert out1 == "inserted"
    row1 = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    hash_1 = row1.content_hash

    out2 = upsert_news_article(
        seeded_engine,
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 1, tzinfo=UTC),
        title="삼성전자",
        body_md="수정된 문단.\n\n수정된 두 번째.",
        tickers=["005930"],
        corp_code="00126380",
    )
    assert out2 == "updated"

    row2 = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    assert row2.content_hash != hash_1
    assert row2.body_md == "수정된 문단.\n\n수정된 두 번째."


# ---- multi-ticker array roundtrip ------------------------------------------


def test_upsert_news_multiple_tickers(pg_clean):
    """Seed Samsung + SK Hynix, write an article tagging both, verify GIN array."""
    from datetime import date

    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    # Seed both entities at the test layer (seeded_engine only carries Samsung).
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00126380','삼성전자','005930','KOSPI'),"
                "       ('00164779','SK하이닉스','000660','KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00126380','name','삼성전자',:vf,NULL),"
                "       ('00164779','name','SK하이닉스',:vf,NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )

    url = "https://www.hankyung.com/article/MULTI01"
    outcome = upsert_news_article(
        pg_clean,
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 1, tzinfo=UTC),
        title="반도체 동향",
        body_md="삼성전자와 SK하이닉스 모두 반도체 사이클 회복.\n\n원자재 가격 안정.",
        tickers=["005930", "000660"],
        corp_code="00126380",
    )
    assert outcome == "inserted"

    row = _select_news_by_url_hash(pg_clean, url_hash64(url))
    assert row.tickers == ["005930", "000660"]

    # GIN array @> query works
    with pg_clean.begin() as conn:
        n_samsung = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['005930']")
        ).scalar()
        n_hynix = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['000660']")
        ).scalar()
        n_lg = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['066570']")
        ).scalar()
    assert n_samsung == 1
    assert n_hynix == 1
    assert n_lg == 0


# ---- FK SET NULL on entity delete ------------------------------------------


def test_upsert_news_corp_code_set_null_on_entity_delete(seeded_engine):
    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    url = "https://www.hankyung.com/article/FK_NULL01"
    upsert_news_article(
        seeded_engine,
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 1, tzinfo=UTC),
        title="삼성전자",
        body_md="문단.\n\n두 번째 문단.",
        tickers=["005930"],
        corp_code="00126380",
    )
    row_before = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    assert row_before.corp_code == "00126380"

    # Delete the entity → news.corp_code becomes NULL (ON DELETE SET NULL)
    # Need to clear aliases first (FK ON DELETE CASCADE wipes them but explicit is clean).
    with seeded_engine.begin() as conn:
        conn.execute(text("DELETE FROM entity_aliases WHERE corp_code='00126380'"))
        conn.execute(text("DELETE FROM entities WHERE corp_code='00126380'"))

    row_after = _select_news_by_url_hash(seeded_engine, url_hash64(url))
    assert row_after is not None  # row still exists
    assert row_after.corp_code is None


# ---- GIN multi-row query ----------------------------------------------------


def test_upsert_news_gin_index_query_works(pg_clean):
    """Insert 3 rows mentioning various tickers, GIN @> filters precisely."""
    from datetime import date

    from collectors.news.db_writer import upsert_news_article

    # Seed entities so FK passes (corp_code=None on the 3rd row is also valid).
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00126380','삼성전자','005930','KOSPI'),"
                "       ('00164779','SK하이닉스','000660','KOSPI'),"
                "       ('00401731','네이버','035420','KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00126380','name','삼성전자',:vf,NULL),"
                "       ('00164779','name','SK하이닉스',:vf,NULL),"
                "       ('00401731','name','네이버',:vf,NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )

    upsert_news_article(
        pg_clean,
        url="https://x.example/a",
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, tzinfo=UTC),
        title="삼성",
        body_md="삼성전자.\n\n둘째.",
        tickers=["005930"],
        corp_code="00126380",
    )
    upsert_news_article(
        pg_clean,
        url="https://x.example/b",
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, tzinfo=UTC),
        title="삼성 + 하이닉스",
        body_md="삼성전자와 SK하이닉스.\n\n둘째.",
        tickers=["005930", "000660"],
        corp_code="00126380",
    )
    upsert_news_article(
        pg_clean,
        url="https://x.example/c",
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, tzinfo=UTC),
        title="네이버",
        body_md="네이버.\n\n둘째.",
        tickers=["035420"],
        corp_code="00401731",
    )

    with pg_clean.begin() as conn:
        n_005930 = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['005930']")
        ).scalar()
        n_000660 = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['000660']")
        ).scalar()
        n_035420 = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['035420']")
        ).scalar()
        n_both = conn.execute(
            text("SELECT count(*) FROM news WHERE tickers @> ARRAY['005930','000660']")
        ).scalar()

    assert n_005930 == 2  # rows a + b
    assert n_000660 == 1  # row b
    assert n_035420 == 1  # row c
    assert n_both == 1  # only row b mentions both


# ---- timezone safety --------------------------------------------------------


def test_upsert_news_published_at_timezone_safe(seeded_engine):
    """Naive datetime is treated as UTC; aware datetime preserved."""
    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    # Naive datetime → UTC
    url_a = "https://www.hankyung.com/article/TZ_NAIVE"
    upsert_news_article(
        seeded_engine,
        url=url_a,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 12, 0, 0),  # naive
        title="삼성전자",
        body_md="문단.\n\n둘째.",
        tickers=["005930"],
        corp_code="00126380",
    )
    row_a = _select_news_by_url_hash(seeded_engine, url_hash64(url_a))
    # Database returns TIMESTAMPTZ as tz-aware datetime
    assert row_a.published_at.tzinfo is not None
    # Naive input was treated as UTC, so the UTC components should match.
    assert row_a.published_at.astimezone(UTC).replace(tzinfo=None) == datetime(
        2026, 4, 20, 12, 0, 0
    )

    # Aware datetime (Asia/Seoul = UTC+9)
    seoul = timezone(__import__("datetime").timedelta(hours=9))
    url_b = "https://www.hankyung.com/article/TZ_AWARE"
    upsert_news_article(
        seeded_engine,
        url=url_b,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, 21, 0, 0, tzinfo=seoul),
        title="삼성전자",
        body_md="문단.\n\n둘째.",
        tickers=["005930"],
        corp_code="00126380",
    )
    row_b = _select_news_by_url_hash(seeded_engine, url_hash64(url_b))
    assert row_b.published_at.tzinfo is not None
    # Equivalent UTC = 12:00 — should match.
    assert row_b.published_at.astimezone(UTC) == datetime(
        2026, 4, 20, 12, 0, 0, tzinfo=UTC
    )


# ---- corp_code=None acceptable ---------------------------------------------


def test_upsert_news_corp_code_none_ok(pg_clean):
    """corp_code may be None when no entity is seeded for the matched ticker."""
    from collectors.news.client import url_hash64
    from collectors.news.db_writer import upsert_news_article

    url = "https://www.hankyung.com/article/NOCORP"
    outcome = upsert_news_article(
        pg_clean,
        url=url,
        outlet="hankyung",
        published_at=datetime(2026, 4, 20, tzinfo=UTC),
        title="제목",
        body_md="문단.\n\n둘째.",
        tickers=["999999"],
        corp_code=None,
    )
    assert outcome == "inserted"
    row = _select_news_by_url_hash(pg_clean, url_hash64(url))
    assert row.corp_code is None
    assert row.tickers == ["999999"]
