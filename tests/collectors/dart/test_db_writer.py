"""DART db_writer unit tests — Plan 01-07 Task 1 behavior contract.

upsert_dart_filing contract (per 01-07-PLAN behavior):
- Returns 'inserted' | 'updated' | 'skipped'
- Validates rcept_no (14 digits), corp_code (8 digits), ticker (6 digits|None),
  pblntf_ty ('A'|'B')
- Computes content_hash = sha256(normalize_body(body_md))
- Idempotent skip → only ``last_seen_at`` bumps; first_seen_at preserved
- Body change → 'updated'; content_hash differs
- WHOLE body stored verbatim (Veto #8 byte-exact roundtrip)
- event_type stays NULL for DART A/B
- Unknown corp_code → FK violation (IntegrityError)
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from collectors.dart import db_writer
from shared.content_hash import normalize_body

pytestmark = pytest.mark.db


# ----- Helpers -----


_BASE_FILED_AT = datetime(2026, 5, 20, 15, 30, tzinfo=ZoneInfo("Asia/Seoul"))


def _row(engine, rcept_no: str):
    """SELECT one filings row by rcept_no for assertion."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT rcept_no, corp_code, ticker, filed_at, report_nm, "
                "pblntf_ty, event_type, source_url, content_hash, body_md, "
                "fetched_at, first_seen_at, last_seen_at "
                "FROM filings WHERE rcept_no = :r"
            ),
            {"r": rcept_no},
        ).first()


def _call(engine, **overrides):
    """Convenience wrapper with sane defaults that match seeded_engine entity."""
    kwargs = {
        "rcept_no": "20260520000001",
        "corp_code": "00126380",
        "ticker": "005930",
        "filed_at": _BASE_FILED_AT,
        "report_nm": "분기보고서",
        "pblntf_ty": "A",
        "body_md": "# Quarterly Report\n\nSamsung Q1 2026 results.\n",
        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260520000001",
    }
    kwargs.update(overrides)
    return db_writer.upsert_dart_filing(engine, **kwargs)


# ----- Tests -----


def test_upsert_filing_fresh_body(seeded_engine) -> None:
    """Fresh insert returns 'inserted' and stores body verbatim + correct hash."""
    body = "# Quarterly Report\n\nContent line 1\nContent line 2\n"
    outcome = _call(seeded_engine, body_md=body)
    assert outcome == "inserted"

    row = _row(seeded_engine, "20260520000001")
    assert row is not None
    assert row.body_md == body
    expected_hash = hashlib.sha256(normalize_body(body).encode("utf-8")).hexdigest()
    assert row.content_hash == expected_hash
    assert row.corp_code == "00126380"
    assert row.ticker == "005930"
    assert row.pblntf_ty == "A"
    assert row.report_nm == "분기보고서"


def test_upsert_filing_idempotent_skip_only_bumps_last_seen(seeded_engine) -> None:
    """Second call with identical body returns 'skipped'; first_seen_at preserved,
    last_seen_at bumped."""
    body = "stable body content\n"
    outcome1 = _call(seeded_engine, body_md=body)
    assert outcome1 == "inserted"

    row1 = _row(seeded_engine, "20260520000001")
    first_seen1 = row1.first_seen_at
    last_seen1 = row1.last_seen_at

    # Sleep briefly so timestamp resolution catches the bump.
    time.sleep(0.05)

    outcome2 = _call(seeded_engine, body_md=body)
    assert outcome2 == "skipped"

    row2 = _row(seeded_engine, "20260520000001")
    assert row2.first_seen_at == first_seen1, "first_seen_at must not move on skip"
    assert row2.last_seen_at > last_seen1, "last_seen_at must bump on skip"
    # body unchanged
    assert row2.body_md == body
    assert row2.content_hash == row1.content_hash


def test_upsert_filing_body_edited(seeded_engine) -> None:
    """Same rcept_no with new body → 'updated'; content_hash differs."""
    outcome1 = _call(seeded_engine, body_md="body A\n")
    assert outcome1 == "inserted"
    hash1 = _row(seeded_engine, "20260520000001").content_hash

    outcome2 = _call(seeded_engine, body_md="body B — totally different\n")
    assert outcome2 == "updated"

    row = _row(seeded_engine, "20260520000001")
    assert row.body_md == "body B — totally different\n"
    assert row.content_hash != hash1


def test_upsert_filing_whole_body_stored(seeded_engine) -> None:
    """100KB+ Korean + English mixed body roundtrips with byte-exact preservation.

    This is the Veto #8 I/O-layer enforcement: no truncation, no chunking.
    """
    body = ("삼성전자 분기 보고서 — 매출 60조원\n" * 2000) + (
        "Q1 2026 results — net income up 12% YoY\n" * 1000
    )
    body_bytes = body.encode("utf-8")
    assert len(body_bytes) > 100_000, "test body must exceed 100KB to exercise the case"

    outcome = _call(seeded_engine, body_md=body)
    assert outcome == "inserted"

    row = _row(seeded_engine, "20260520000001")
    assert row.body_md == body
    assert len(row.body_md.encode("utf-8")) == len(body_bytes)


def test_upsert_filing_invalid_rcept_no_raises(seeded_engine) -> None:
    """Non-14-digit rcept_no → ValueError before any SQL fires."""
    with pytest.raises(ValueError, match="rcept_no"):
        _call(seeded_engine, rcept_no="abc")
    with pytest.raises(ValueError, match="rcept_no"):
        _call(seeded_engine, rcept_no="2026052000001")  # 13 digits


def test_upsert_filing_invalid_pblntf_ty_raises(seeded_engine) -> None:
    """pblntf_ty outside {'A','B'} → ValueError."""
    with pytest.raises(ValueError, match="pblntf_ty"):
        _call(seeded_engine, pblntf_ty="X")
    with pytest.raises(ValueError, match="pblntf_ty"):
        _call(seeded_engine, pblntf_ty="I")  # KIND filings route through different writer


def test_upsert_filing_invalid_corp_code_raises(seeded_engine) -> None:
    """Non-8-digit corp_code → ValueError."""
    with pytest.raises(ValueError, match="corp_code"):
        _call(seeded_engine, corp_code="123")


def test_upsert_filing_invalid_ticker_raises(seeded_engine) -> None:
    """Non-6-digit / non-None ticker → ValueError."""
    with pytest.raises(ValueError, match="ticker"):
        _call(seeded_engine, ticker="12345")  # 5 digits
    with pytest.raises(ValueError, match="ticker"):
        _call(seeded_engine, ticker="abcdef")


def test_upsert_filing_ticker_null_permitted(seeded_engine) -> None:
    """ticker=None is allowed; DB row has NULL ticker."""
    outcome = _call(seeded_engine, ticker=None)
    assert outcome == "inserted"
    row = _row(seeded_engine, "20260520000001")
    assert row.ticker is None


def test_upsert_filing_unknown_corp_raises_fk(seeded_engine) -> None:
    """corp_code with no entity row → IntegrityError (FK CASCADE constraint)."""
    with pytest.raises(IntegrityError):
        _call(seeded_engine, corp_code="99999999")


def test_upsert_filing_event_type_stays_null(seeded_engine) -> None:
    """DART A/B writer hard-codes event_type = NULL.

    Cross-check against the KIND writer (01-05) which DOES populate event_type
    for pblntf_ty='I' filings.
    """
    outcome = _call(seeded_engine)
    assert outcome == "inserted"
    row = _row(seeded_engine, "20260520000001")
    assert row.event_type is None
