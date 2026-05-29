"""KIND db_writer unit tests — Plan 01-05 Task 1 contract.

Two helpers under test:

- ``upsert_kind_filing(engine, *, rcept_no, corp_code, ticker, filed_at,
  report_nm, event_type, source_url, body_md='')`` →
  ``'inserted' | 'updated' | 'skipped'``

  UPSERTs into the ``filings`` table with ``pblntf_ty='I'``. KIND filings
  intentionally carry empty body_md in Phase 1 — the full body backfill
  is deferred to Phase 3.

- ``upsert_kind_event(engine, *, event_type, ticker, event_date, source,
  source_id, source_url, corp_code=None, subtype=None, reason='',
  filing_rcept_no=None)`` → ``'inserted' | 'skipped'``

  INSERTs into ``events`` with ON CONFLICT DO NOTHING — events are
  immutable classifications (RESEARCH Q2).

Hard Veto #6 reminder: ``events`` table is pure-classifier (no body / no
embedding columns). Veto #8: KIND ``filings`` rows store the whole body
(empty for now); no pre-chunking.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from collectors.kind import db_writer

pytestmark = pytest.mark.db


# ----- Helpers -----


def _seed_entity(engine, corp_code: str = "00126380", ticker: str = "005930") -> None:
    """Insert one entity row for FK satisfaction on filings/events."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES (:cc, :name, :t, 'KOSPI') ON CONFLICT (corp_code) DO NOTHING"
            ),
            {"cc": corp_code, "name": "삼성전자", "t": ticker},
        )


def _filing_row(engine, rcept_no: str):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT rcept_no, corp_code, ticker, filed_at, report_nm, "
                "pblntf_ty, event_type, source_url, content_hash, body_md, "
                "fetched_at, first_seen_at, last_seen_at "
                "FROM filings WHERE rcept_no=:r"
            ),
            {"r": rcept_no},
        ).first()


def _event_row(engine, *, event_type: str, ticker: str, event_date: date,
               source: str, source_id: str):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, event_type, ticker, event_date, corp_code, subtype, "
                "reason, source, source_id, source_url, filing_rcept_no, fetched_at "
                "FROM events WHERE event_type=:et AND ticker=:t AND event_date=:d "
                "AND source=:s AND source_id=:sid"
            ),
            {"et": event_type, "t": ticker, "d": event_date, "s": source, "sid": source_id},
        ).first()


def _count_filings(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM filings")).scalar_one()


def _count_events(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM events")).scalar_one()


_BASE_FILED_AT = datetime(2026, 5, 20, 15, 30, tzinfo=timezone.utc)


# ===== upsert_kind_filing tests =====


def test_upsert_filing_fresh(pg_clean) -> None:
    _seed_entity(pg_clean)
    outcome = db_writer.upsert_kind_filing(
        pg_clean,
        rcept_no="20260520001234",
        corp_code="00126380",
        ticker="005930",
        filed_at=_BASE_FILED_AT,
        report_nm="주권매매거래정지",
        event_type="suspension",
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260520001234",
    )
    assert outcome == "inserted"

    row = _filing_row(pg_clean, "20260520001234")
    assert row is not None
    assert row.corp_code == "00126380"
    assert row.ticker == "005930"
    assert row.pblntf_ty == "I"
    assert row.event_type == "suspension"
    assert row.body_md == ""  # Phase 1 KIND policy
    # content_hash of normalize_body("") should be the sha256 of "\n" (single newline)
    assert len(row.content_hash) == 64


def test_upsert_filing_idempotent(pg_clean) -> None:
    _seed_entity(pg_clean)
    db_writer.upsert_kind_filing(
        pg_clean,
        rcept_no="20260520001234",
        corp_code="00126380",
        ticker="005930",
        filed_at=_BASE_FILED_AT,
        report_nm="주권매매거래정지",
        event_type="suspension",
        source_url="https://dart.fss.or.kr/x",
    )
    row1 = _filing_row(pg_clean, "20260520001234")
    first_seen1 = row1.first_seen_at

    outcome2 = db_writer.upsert_kind_filing(
        pg_clean,
        rcept_no="20260520001234",
        corp_code="00126380",
        ticker="005930",
        filed_at=_BASE_FILED_AT,
        report_nm="주권매매거래정지",
        event_type="suspension",
        source_url="https://dart.fss.or.kr/x",
    )
    assert outcome2 == "skipped"

    row2 = _filing_row(pg_clean, "20260520001234")
    # first_seen_at preserved
    assert row2.first_seen_at == first_seen1
    # last_seen_at bumped on skip (we still record we saw it)
    assert row2.last_seen_at >= row1.last_seen_at
    # only one row total
    assert _count_filings(pg_clean) == 1


def test_upsert_filing_body_changed(pg_clean) -> None:
    _seed_entity(pg_clean)
    db_writer.upsert_kind_filing(
        pg_clean,
        rcept_no="20260520001234",
        corp_code="00126380",
        ticker="005930",
        filed_at=_BASE_FILED_AT,
        report_nm="주권매매거래정지",
        event_type="suspension",
        source_url="https://dart.fss.or.kr/x",
        body_md="initial body",
    )
    row1 = _filing_row(pg_clean, "20260520001234")
    hash1 = row1.content_hash

    outcome = db_writer.upsert_kind_filing(
        pg_clean,
        rcept_no="20260520001234",
        corp_code="00126380",
        ticker="005930",
        filed_at=_BASE_FILED_AT,
        report_nm="주권매매거래정지",
        event_type="suspension",
        source_url="https://dart.fss.or.kr/x",
        body_md="updated body — more content",
    )
    assert outcome == "updated"

    row2 = _filing_row(pg_clean, "20260520001234")
    assert row2.content_hash != hash1
    assert row2.body_md == "updated body — more content"
    assert _count_filings(pg_clean) == 1


def test_upsert_filing_unknown_corp_raises_fk(pg_clean) -> None:
    """FK violation when corp_code is not in entities."""
    # Do NOT seed entity for corp_code '99999999'
    with pytest.raises(IntegrityError):
        db_writer.upsert_kind_filing(
            pg_clean,
            rcept_no="20260520001234",
            corp_code="99999999",
            ticker="005930",
            filed_at=_BASE_FILED_AT,
            report_nm="주권매매거래정지",
            event_type="suspension",
            source_url="https://dart.fss.or.kr/x",
        )


def test_upsert_filing_invalid_rcept_no_raises(pg_clean) -> None:
    """rcept_no must be 14 ASCII digits."""
    _seed_entity(pg_clean)
    with pytest.raises(ValueError, match="rcept_no"):
        db_writer.upsert_kind_filing(
            pg_clean,
            rcept_no="not-14-digits",
            corp_code="00126380",
            ticker="005930",
            filed_at=_BASE_FILED_AT,
            report_nm="주권매매거래정지",
            event_type="suspension",
            source_url="https://dart.fss.or.kr/x",
        )


def test_upsert_filing_invalid_event_type_raises(pg_clean) -> None:
    """event_type must be in the 5-value enum."""
    _seed_entity(pg_clean)
    with pytest.raises(ValueError, match="event_type"):
        db_writer.upsert_kind_filing(
            pg_clean,
            rcept_no="20260520001234",
            corp_code="00126380",
            ticker="005930",
            filed_at=_BASE_FILED_AT,
            report_nm="주권매매거래정지",
            event_type="bogus_type",
            source_url="https://dart.fss.or.kr/x",
        )


# ===== upsert_kind_event tests =====


def test_upsert_event_fresh(pg_clean) -> None:
    _seed_entity(pg_clean)
    outcome = db_writer.upsert_kind_event(
        pg_clean,
        event_type="suspension",
        ticker="005930",
        event_date=date(2026, 5, 20),
        source="dart",
        source_id="20260520001234",
        source_url="https://dart.fss.or.kr/x",
        corp_code="00126380",
        reason="주권매매거래정지",
    )
    assert outcome == "inserted"
    assert _count_events(pg_clean) == 1

    row = _event_row(
        pg_clean,
        event_type="suspension",
        ticker="005930",
        event_date=date(2026, 5, 20),
        source="dart",
        source_id="20260520001234",
    )
    assert row is not None
    assert row.corp_code == "00126380"
    assert row.reason == "주권매매거래정지"
    assert row.filing_rcept_no is None  # not linked in this test


def test_upsert_event_idempotent(pg_clean) -> None:
    """Same UNIQUE key → 2nd call returns 'skipped'; only ONE row in events."""
    _seed_entity(pg_clean)
    db_writer.upsert_kind_event(
        pg_clean,
        event_type="suspension",
        ticker="005930",
        event_date=date(2026, 5, 20),
        source="dart",
        source_id="20260520001234",
        source_url="https://dart.fss.or.kr/x",
        corp_code="00126380",
    )
    outcome2 = db_writer.upsert_kind_event(
        pg_clean,
        event_type="suspension",
        ticker="005930",
        event_date=date(2026, 5, 20),
        source="dart",
        source_id="20260520001234",
        source_url="https://dart.fss.or.kr/x",
        corp_code="00126380",
    )
    assert outcome2 == "skipped"
    assert _count_events(pg_clean) == 1


def test_upsert_event_with_filing_link(pg_clean) -> None:
    """FK link from events.filing_rcept_no → filings.rcept_no is asserted by JOIN."""
    _seed_entity(pg_clean)
    db_writer.upsert_kind_filing(
        pg_clean,
        rcept_no="20260520001234",
        corp_code="00126380",
        ticker="005930",
        filed_at=_BASE_FILED_AT,
        report_nm="주권매매거래정지",
        event_type="suspension",
        source_url="https://dart.fss.or.kr/x",
    )
    db_writer.upsert_kind_event(
        pg_clean,
        event_type="suspension",
        ticker="005930",
        event_date=date(2026, 5, 20),
        source="dart",
        source_id="20260520001234",
        source_url="https://dart.fss.or.kr/x",
        corp_code="00126380",
        filing_rcept_no="20260520001234",
    )

    with pg_clean.connect() as conn:
        joined = conn.execute(
            text(
                "SELECT e.event_type, f.report_nm, f.pblntf_ty FROM events e "
                "JOIN filings f ON e.filing_rcept_no = f.rcept_no"
            )
        ).first()
    assert joined is not None
    assert joined.event_type == "suspension"
    assert joined.report_nm == "주권매매거래정지"
    assert joined.pblntf_ty == "I"


def test_upsert_event_check_constraint_violation(pg_clean) -> None:
    """DB-level CHECK: event_type='delisting' is not in the 5-value enum.

    The db_writer validates pre-flight (cheaper than a DB roundtrip+rollback),
    so a bogus event_type raises ValueError before reaching the DB. The CHECK
    constraint is the belt-and-suspenders backup.
    """
    _seed_entity(pg_clean)
    with pytest.raises(ValueError, match="event_type"):
        db_writer.upsert_kind_event(
            pg_clean,
            event_type="delisting",
            ticker="005930",
            event_date=date(2026, 5, 20),
            source="dart",
            source_id="X",
            source_url="https://dart.fss.or.kr/x",
            corp_code="00126380",
        )


def test_upsert_event_invalid_ticker_raises(pg_clean) -> None:
    """ticker must be 6 ASCII digits."""
    _seed_entity(pg_clean)
    with pytest.raises(ValueError, match="ticker"):
        db_writer.upsert_kind_event(
            pg_clean,
            event_type="suspension",
            ticker="abc",
            event_date=date(2026, 5, 20),
            source="dart",
            source_id="X",
            source_url="https://dart.fss.or.kr/x",
            corp_code="00126380",
        )


def test_upsert_event_invalid_source_raises(pg_clean) -> None:
    """source must be 'dart' or 'kind'."""
    _seed_entity(pg_clean)
    with pytest.raises(ValueError, match="source"):
        db_writer.upsert_kind_event(
            pg_clean,
            event_type="suspension",
            ticker="005930",
            event_date=date(2026, 5, 20),
            source="bogus",
            source_id="X",
            source_url="https://dart.fss.or.kr/x",
            corp_code="00126380",
        )


def test_upsert_event_kind_only_no_filing_link(pg_clean) -> None:
    """KIND-only events (source='kind') do not require a filings row."""
    _seed_entity(pg_clean)
    outcome = db_writer.upsert_kind_event(
        pg_clean,
        event_type="unfaithful_disclosure",
        ticker="005930",
        event_date=date(2026, 5, 20),
        source="kind",
        source_id="kind_undiscl_삼성전자_20260520",
        source_url="https://kind.krx.co.kr/investwarn/undisclosure.do",
        corp_code="00126380",
    )
    assert outcome == "inserted"
    assert _count_filings(pg_clean) == 0  # KIND-only: no filings row
    assert _count_events(pg_clean) == 1
