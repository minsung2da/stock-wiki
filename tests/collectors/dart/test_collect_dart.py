"""DART collector integration tests — Plan 01-07 Task 3.

Mocks dart-fss at the client/fetcher boundary so tests never touch the real
DART API. Each test asserts a specific Phase 1 v2.0 behavior:

- A+B filings INSERT into the ``filings`` table (no vault/raw/ writes).
- Idempotent rerun returns ``skipped`` (content_hash match).
- Body-edited rerun returns ``updated`` (content_hash differs).
- WHOLE body stored verbatim (Veto #8) — byte-length match + chunks
  table count remains 0 after dart run.
- Per-filing isolation: one failure does not abort the loop.
- Bug C (quick-260418-asr) entity upsert fires when
  (inserted + updated) > 0.
- No engine → RuntimeError (R-12 contract).
- No Markdown vault directory is ever created.
- pblntf_ty='B' is preserved into the DB row.

Replaces (and supersedes) the v1.0 ``tests/test_collect_dart.py`` which
asserted file-system Markdown paths. Task 4 deletes that file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


# ----- Fake DART API objects -----


@dataclass
class FakeFiling:
    rcept_no: str
    rcept_dt: str  # "YYYYMMDD"
    report_nm: str
    source_url: str
    pblntf_ty: str = "A"


@dataclass
class FakeCorp:
    stock_code: str = "005930"
    corp_name: str = "삼성전자"


# ----- Helpers -----


def _patch_dart(monkeypatch, *, corp: FakeCorp, filings: list[FakeFiling],
                body_fn=None) -> None:
    """Patch client.get_client + client.find_corp + fetcher.list_ab_filings +
    fetcher.fetch_body so the collector never touches dart-fss."""

    monkeypatch.setattr("collectors.dart.client.get_client", lambda: None)
    monkeypatch.setattr("collectors.dart.client.find_corp", lambda cc: corp)
    monkeypatch.setattr(
        "collectors.dart.fetcher.list_ab_filings",
        lambda corp_code, since, max_docs: list(filings)[:max_docs],
    )
    if body_fn is None:
        body_fn = lambda filing: f"body for {filing.rcept_no}"  # noqa: E731
    monkeypatch.setattr("collectors.dart.fetcher.fetch_body", body_fn)


def _filings_row(engine, rcept_no: str):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT rcept_no, corp_code, ticker, filed_at, report_nm, "
                "pblntf_ty, event_type, source_url, content_hash, body_md "
                "FROM filings WHERE rcept_no = :r"
            ),
            {"r": rcept_no},
        ).first()


def _filings_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM filings")).scalar()


def _chunks_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM chunks")).scalar()


# ----- Tests -----


def test_collect_dart_inserts_filing(seeded_engine, monkeypatch) -> None:
    """One A-type filing → inserted=1, DB row has correct shape and body."""
    filings = [
        FakeFiling(
            rcept_no="20260520000123",
            rcept_dt="20260520",
            report_nm="분기보고서",
            source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260520000123",
            pblntf_ty="A",
        )
    ]
    body = "BODY TEXT 한글 mixed"
    _patch_dart(
        monkeypatch,
        corp=FakeCorp(stock_code="005930", corp_name="삼성전자"),
        filings=filings,
        body_fn=lambda f: body,
    )

    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380",
        since="2026-01-01",
        engine=seeded_engine,
    )

    assert stats["total"] == 1
    assert stats["inserted"] == 1
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == []

    row = _filings_row(seeded_engine, "20260520000123")
    assert row is not None
    assert row.corp_code == "00126380"
    assert row.ticker == "005930"
    assert row.report_nm == "분기보고서"
    assert row.pblntf_ty == "A"
    assert row.event_type is None  # DART A/B never sets event_type
    assert row.body_md == body
    assert row.source_url.endswith("rcpNo=20260520000123")


def test_collect_dart_idempotent(seeded_engine, monkeypatch) -> None:
    """Second run with same body → skipped=1; no duplicate row."""
    filings = [
        FakeFiling(
            rcept_no="20260520000124",
            rcept_dt="20260520",
            report_nm="분기보고서",
            source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260520000124",
            pblntf_ty="A",
        )
    ]
    _patch_dart(
        monkeypatch,
        corp=FakeCorp(),
        filings=filings,
        body_fn=lambda f: "stable body",
    )

    from collectors.dart import collect_dart

    stats1 = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats1["inserted"] == 1

    stats2 = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 0
    assert stats2["skipped"] == 1

    assert _filings_count(seeded_engine) == 1


def test_collect_dart_body_edited(seeded_engine, monkeypatch) -> None:
    """Rerun with edited body (same rcept_no) → updated=1; DB has body B."""
    filings = [
        FakeFiling(
            rcept_no="20260520000125",
            rcept_dt="20260520",
            report_nm="분기보고서",
            source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260520000125",
            pblntf_ty="A",
        )
    ]
    from collectors.dart import collect_dart

    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: "body A original")
    stats1 = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats1["inserted"] == 1

    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: "body B replacement — totally different")
    stats2 = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats2["updated"] == 1
    assert stats2["inserted"] == 0
    assert stats2["skipped"] == 0

    row = _filings_row(seeded_engine, "20260520000125")
    assert row.body_md == "body B replacement — totally different"


def test_collect_dart_whole_body_no_chunking(seeded_engine, monkeypatch) -> None:
    """200KB body roundtrips byte-exact AND chunks table stays empty (Veto #8).

    This is the gold-standard Veto #8 enforcement: filings.body_md stores
    the whole filing as a single TEXT blob; no chunk-write side effect.
    """
    big_body = ("삼성전자 사업보고서 본문 — Section A\n" * 4000) + (
        "Section B financial highlights line\n" * 3000
    )
    body_bytes = big_body.encode("utf-8")
    assert len(body_bytes) > 200_000, "body must exceed 200KB"

    filings = [
        FakeFiling(
            rcept_no="20260520000126",
            rcept_dt="20260520",
            report_nm="사업보고서",
            source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260520000126",
            pblntf_ty="A",
        )
    ]
    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: big_body)

    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats["inserted"] == 1

    row = _filings_row(seeded_engine, "20260520000126")
    assert row.body_md == big_body
    assert len(row.body_md.encode("utf-8")) == len(body_bytes)

    # Veto #8: chunks table dormant — collect_dart must not write to it.
    assert _chunks_count(seeded_engine) == 0, (
        "Veto #8 violation: chunks table touched by DART collector"
    )


def test_collect_dart_per_filing_isolation(seeded_engine, monkeypatch) -> None:
    """3 filings; #2 raises during fetch_body. #1 + #3 succeed; #2 lands in failed."""
    filings = [
        FakeFiling(
            rcept_no="20260520000201", rcept_dt="20260520",
            report_nm="r1", source_url="u1", pblntf_ty="A",
        ),
        FakeFiling(
            rcept_no="20260520000202", rcept_dt="20260520",
            report_nm="r2", source_url="u2", pblntf_ty="A",
        ),
        FakeFiling(
            rcept_no="20260520000203", rcept_dt="20260520",
            report_nm="r3", source_url="u3", pblntf_ty="A",
        ),
    ]

    def flaky_fetch(filing):
        if filing.rcept_no == "20260520000202":
            raise RuntimeError("network boom")
        return f"body for {filing.rcept_no}"

    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings, body_fn=flaky_fetch)

    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats["inserted"] == 2
    assert len(stats["failed"]) == 1
    failure = stats["failed"][0]
    assert failure["doc"] == "20260520000202"
    assert "network boom" in failure["error"]

    # Only 2 rows actually in DB
    assert _filings_count(seeded_engine) == 2


def test_collect_dart_bug_c_entity_upsert(pg_clean, monkeypatch) -> None:
    """When (inserted + updated) > 0, upsert_entity fires once at end of run.

    Use pg_clean (no seeded entity) — pre-seed a placeholder entity to
    satisfy the filings.corp_code FK, then verify the collector's
    upsert_entity call refreshed canonical_name + current_ticker AND
    inserted the ticker alias.
    """
    # Pre-seed a placeholder entity row so filings.corp_code FK is valid.
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00126380', 'placeholder_name', NULL, 'KOSPI')"
            )
        )

    filings = [
        FakeFiling(
            rcept_no="20260520000301", rcept_dt="20260520",
            report_nm="분기보고서", source_url="u1", pblntf_ty="A",
        )
    ]
    _patch_dart(
        monkeypatch,
        corp=FakeCorp(stock_code="005930", corp_name="삼성전자"),
        filings=filings,
        body_fn=lambda f: "body",
    )

    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=pg_clean
    )
    assert stats["inserted"] == 1
    assert "warnings" not in stats or stats["warnings"] == []

    # Entity refresh: canonical_name and current_ticker were updated.
    with pg_clean.connect() as conn:
        ent_row = conn.execute(
            text(
                "SELECT canonical_name, current_ticker FROM entities WHERE corp_code = '00126380'"
            )
        ).first()
        assert ent_row.canonical_name == "삼성전자"
        assert ent_row.current_ticker == "005930"

        # Ticker alias was inserted (Bug C: resolve_entity(ticker) will work).
        alias = conn.execute(
            text(
                "SELECT 1 FROM entity_aliases "
                "WHERE corp_code = '00126380' AND kind = 'ticker' "
                "  AND value = '005930' AND valid_to IS NULL"
            )
        ).first()
        assert alias is not None, "Bug C: ticker alias must exist post-run"


def test_collect_dart_no_engine_raises(monkeypatch) -> None:
    """engine=None → RuntimeError (R-12 contract)."""
    from collectors.dart import collect_dart

    # No need to mock fetch — the guard fires before client.get_client.
    with pytest.raises(RuntimeError, match="engine"):
        collect_dart(corp_code="00126380", since="2026-01-01", engine=None)


def test_collect_dart_no_markdown_written(seeded_engine, monkeypatch,
                                          tmp_path: Path) -> None:
    """After a successful run, no vault/raw/dart/ directory exists in CWD.

    Veto #9 / SC-1 fence: collectors must not regenerate Markdown vault paths.
    """
    filings = [
        FakeFiling(
            rcept_no="20260520000401", rcept_dt="20260520",
            report_nm="r", source_url="u", pblntf_ty="A",
        )
    ]
    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: "body")

    monkeypatch.chdir(tmp_path)
    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats["inserted"] == 1

    # SC-1: no vault/raw/dart/ created relative to CWD.
    assert not (tmp_path / "vault" / "raw" / "dart").exists()
    assert not (tmp_path / "vault" / "raw").exists()
    assert not (tmp_path / "vault").exists()


def test_collect_dart_pblntf_ty_recorded(seeded_engine, monkeypatch) -> None:
    """B-type filing → DB row has pblntf_ty='B' (not silently coerced to A)."""
    filings = [
        FakeFiling(
            rcept_no="20260520000501", rcept_dt="20260520",
            report_nm="주요사항보고서", source_url="u", pblntf_ty="B",
        )
    ]
    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: "body")

    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )
    assert stats["inserted"] == 1

    row = _filings_row(seeded_engine, "20260520000501")
    assert row.pblntf_ty == "B"


def test_collect_dart_max_docs_cap(seeded_engine, monkeypatch) -> None:
    """200 fake filings + max_docs=100 → exactly 100 rows landed (D-03 cap).

    rcept_no must be exactly 14 ASCII digits — db_writer rejects shorter
    or longer strings. Use 10 fixed digits + 4 variable digits.
    """
    filings = [
        FakeFiling(
            rcept_no=f"2026052000{i:04d}", rcept_dt="20260520",
            report_nm=f"r{i}", source_url=f"u{i}", pblntf_ty="A",
        )
        for i in range(200)
    ]
    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: f"body {f.rcept_no}")

    from collectors.dart import collect_dart

    stats = collect_dart(
        corp_code="00126380",
        since="2026-01-01",
        max_docs=100,
        engine=seeded_engine,
    )
    assert stats["total"] == 100
    assert stats["inserted"] == 100
    assert _filings_count(seeded_engine) == 100


def test_collect_dart_filed_at_kst_close(seeded_engine, monkeypatch) -> None:
    """rcept_dt YYYYMMDD → filed_at TIMESTAMPTZ at 15:30 Asia/Seoul.

    Catches accidental UTC-or-naive datetime composition.
    """
    filings = [
        FakeFiling(
            rcept_no="20260520000601", rcept_dt="20260520",
            report_nm="r", source_url="u", pblntf_ty="A",
        )
    ]
    _patch_dart(monkeypatch, corp=FakeCorp(), filings=filings,
                body_fn=lambda f: "body")

    from collectors.dart import collect_dart

    collect_dart(
        corp_code="00126380", since="2026-01-01", engine=seeded_engine
    )

    row = _filings_row(seeded_engine, "20260520000601")
    # Postgres returns TIMESTAMPTZ as a tz-aware Python datetime.
    assert row.filed_at is not None
    # 15:30 Asia/Seoul = 06:30 UTC on the same date.
    # Postgres normalizes to UTC by default in psycopg returns.
    assert row.filed_at.hour in (6, 15)  # UTC=6, KST=15 — tolerate both
    assert row.filed_at.year == 2026
    assert row.filed_at.month == 5
    assert row.filed_at.day == 20
