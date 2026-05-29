"""Integration tests for collect_kind — Plan 01-05 (Phase 1 Wave 2).

Migrated from vault-path assertions to DB-state assertions. Tests now:

1. Materialize a temporary repo root via ``tmp_path`` with
   ``notes/private/portfolio.md`` so ``Portfolio.load(Path("."))`` resolves.
2. Mock ``dart_events.fetch_exchange_events`` (and ``scraper.fetch_undisclosure_events``
   when ``enable_kind_scrape=True``) via ``monkeypatch``.
3. Assert against the ``filings`` + ``events`` tables, including FK link
   verification via SQL JOIN.

KIND collector semantics tested:

- DART pblntf_ty='I' events → paired write: one row in ``filings`` AND one
  row in ``events`` with ``filing_rcept_no`` pointing at the filing.
- KIND AJAX events (source='kind') → single row in ``events`` only; no
  ``filings`` row (no rcept_no exists).
- Idempotency: rerun → ``skipped`` semantics on both tables.
- Unknown event_type → caught by collector pre-filter; not a DB roundtrip.
- Missing ticker / out-of-scope → ``skipped`` without write attempt.
- KIND scraper ``ParseError`` → resilient (logged as ``kind_parse_error``,
  run does not fail).
- ``suspension_cross_check_mismatch`` is deferred (Phase 9) — emits an empty
  list pass-through on the structured log.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from collectors.kind import collect_kind

pytestmark = pytest.mark.db


# ----- Helpers -----


_SAMSUNG_PORTFOLIO = (
    "---\n"
    "holdings:\n"
    '  - ticker: "005930"\n'
    "    qty: 1\n"
    "    avg_cost: 70000\n"
    "watchlist:\n"
    '  - "000660"\n'
    "---\n"
    "# Portfolio\n"
)


def _write_portfolio(tmp_path: Path, content: str = _SAMSUNG_PORTFOLIO) -> None:
    """Materialize tmp_path/notes/private/portfolio.md so Portfolio.load works."""
    p = tmp_path / "notes" / "private"
    p.mkdir(parents=True, exist_ok=True)
    (p / "portfolio.md").write_text(content, encoding="utf-8")


def _seed_sk(engine) -> None:
    """Add SK하이닉스 (000660) to the seeded entities so the watchlist resolves."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00164779', 'SK하이닉스', '000660', 'KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00164779', 'ticker', '000660', :vf, NULL), "
                "       ('00164779', 'name',   'SK하이닉스', :vf, NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )


def _count_filings(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM filings")).scalar_one()


def _count_events(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM events")).scalar_one()


def _filing_row(engine, rcept_no: str):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT rcept_no, corp_code, ticker, pblntf_ty, event_type, "
                "report_nm, body_md, source_url "
                "FROM filings WHERE rcept_no=:r"
            ),
            {"r": rcept_no},
        ).first()


def _event_row(engine, *, source: str, source_id: str):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT event_type, ticker, event_date, source, source_id, "
                "corp_code, filing_rcept_no, reason, subtype "
                "FROM events WHERE source=:s AND source_id=:sid"
            ),
            {"s": source, "sid": source_id},
        ).first()


def _dart_events_for_samsung_and_sk():
    """Stub DART events: 1 suspension for 005930, 1 watchlist for 000660,
    plus one for a non-scope ticker that must be filtered out."""
    return [
        {
            "event_type": "suspension",
            "ticker": "005930",
            "corp_code": "00126380",
            "company_name": "삼성전자",
            "event_date": "20260417",
            "reason": "주권매매거래정지",
            "report_nm": "주권매매거래정지",
            "source_id": "20260417000001",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260417000001",
        },
        {
            "event_type": "watchlist_designation",
            "ticker": "000660",
            "corp_code": "00164779",
            "company_name": "SK하이닉스",
            "event_date": "20260410",
            "reason": "기타시장안내(관리종목지정우려종목)",
            "report_nm": "기타시장안내(관리종목지정우려종목)",
            "source_id": "20260410000002",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260410000002",
        },
        # Out-of-scope ticker — should be filtered out
        {
            "event_type": "suspension",
            "ticker": "999999",
            "corp_code": "99999999",
            "company_name": "OutOfScopeCorp",
            "event_date": "20260417",
            "reason": "주권매매거래정지",
            "report_nm": "주권매매거래정지",
            "source_id": "20260417000003",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260417000003",
        },
    ]


# ----- Tests -----


def test_collect_kind_dart_event_writes_filings_and_events(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """A DART pblntf_ty='I' event produces ONE filings row AND ONE events row
    linked via filing_rcept_no FK. Out-of-scope ticker is filtered out."""
    _write_portfolio(tmp_path)
    _seed_sk(seeded_engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )
    stats = collect_kind(engine=seeded_engine)

    # Stats: 2 in-scope events inserted; 1 out-of-scope filtered → skipped
    assert stats["inserted"] == 2
    assert stats["updated"] == 0
    assert stats["skipped"] >= 1  # out-of-scope tick + any dedup
    assert stats["failed"] == []

    # DB: filings rows for both DART events
    assert _count_filings(seeded_engine) == 2
    fr = _filing_row(seeded_engine, "20260417000001")
    assert fr is not None
    assert fr.pblntf_ty == "I"
    assert fr.event_type == "suspension"
    assert fr.ticker == "005930"
    assert fr.body_md == ""  # Phase 1 KIND policy

    # DB: events rows with filing_rcept_no FK
    assert _count_events(seeded_engine) == 2
    er = _event_row(seeded_engine, source="dart", source_id="20260417000001")
    assert er is not None
    assert er.event_type == "suspension"
    assert er.ticker == "005930"
    assert er.filing_rcept_no == "20260417000001"

    # DB: JOIN proves FK link
    with seeded_engine.connect() as conn:
        joined = conn.execute(
            text(
                "SELECT count(*) FROM events e "
                "JOIN filings f ON e.filing_rcept_no = f.rcept_no"
            )
        ).scalar_one()
    assert joined == 2


def test_collect_kind_kind_only_event_skipped_without_filings(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """KIND-only events (source='kind') do not create filings rows."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [],
    )
    monkeypatch.setattr(
        "collectors.kind.scraper.fetch_undisclosure_events",
        lambda *a, **k: [
            {
                "event_type": "unfaithful_disclosure",
                "ticker": None,
                "corp_code": None,
                "company_name": "삼성전자",
                "event_date": "20260417",
                "reason": "불성실공시법인지정",
                "source_id": "kind_undiscl_삼성전자_20260417",
                "source_url": "https://kind.krx.co.kr/investwarn/undisclosure.do",
                "subtype": "지연공시",
            }
        ],
    )

    stats = collect_kind(engine=seeded_engine, enable_kind_scrape=True)

    assert stats["inserted"] == 1
    # No filings row written
    assert _count_filings(seeded_engine) == 0
    # Exactly one events row with source='kind' and NULL filing_rcept_no
    assert _count_events(seeded_engine) == 1
    er = _event_row(
        seeded_engine, source="kind", source_id="kind_undiscl_삼성전자_20260417"
    )
    assert er is not None
    assert er.filing_rcept_no is None
    assert er.ticker == "005930"  # resolved via alias matcher
    assert er.corp_code == "00126380"


def test_collect_kind_idempotent(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """Rerun with same DART event: 1st insert, 2nd all skipped, no duplicates."""
    _write_portfolio(tmp_path)
    _seed_sk(seeded_engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )
    s1 = collect_kind(engine=seeded_engine)
    assert s1["inserted"] == 2

    s2 = collect_kind(engine=seeded_engine)
    assert s2["inserted"] == 0
    assert s2["updated"] == 0
    # 2 events skipped (content_hash match on filings + UNIQUE collision on events)
    assert s2["skipped"] >= 2
    # Still only 2 filings + 2 events rows (no duplicates)
    assert _count_filings(seeded_engine) == 2
    assert _count_events(seeded_engine) == 2


def test_collect_kind_unknown_event_type_filtered(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """Collector-side filter rejects event_type='delisting' (extended set,
    not in the 5-value enum)."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [
            {
                "event_type": "delisting",  # NOT in the 5-value enum
                "ticker": "005930",
                "corp_code": "00126380",
                "company_name": "삼성전자",
                "event_date": "20260417",
                "reason": "상장폐지",
                "report_nm": "상장폐지",
                "source_id": "20260417000099",
                "source_url": "https://dart.fss.or.kr/x",
            }
        ],
    )

    stats = collect_kind(engine=seeded_engine)
    # Caught by collector pre-filter → 1 failed entry
    assert len(stats["failed"]) >= 1
    assert any("event_type" in f["error"] or "delisting" in f["error"] for f in stats["failed"])
    # No DB rows written
    assert _count_filings(seeded_engine) == 0
    assert _count_events(seeded_engine) == 0


def test_collect_kind_missing_ticker_skipped(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """Event with empty ticker → skipped without write attempt."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [
            {
                "event_type": "suspension",
                "ticker": "",  # missing
                "corp_code": None,
                "company_name": "?",
                "event_date": "20260417",
                "reason": "주권매매거래정지",
                "report_nm": "주권매매거래정지",
                "source_id": "20260417000088",
                "source_url": "https://dart.fss.or.kr/x",
            }
        ],
    )

    stats = collect_kind(engine=seeded_engine)
    assert stats["inserted"] == 0
    assert stats["skipped"] >= 1
    assert _count_events(seeded_engine) == 0


def test_collect_kind_no_engine_raises(tmp_path: Path, monkeypatch) -> None:
    """engine=None must raise — collector contract requires DB for FK resolution."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="engine"):
        collect_kind(engine=None)


def test_collect_kind_no_markdown_written(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """After collect_kind, no vault/raw/kind/ dir exists under cwd."""
    _write_portfolio(tmp_path)
    _seed_sk(seeded_engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )
    collect_kind(engine=seeded_engine)

    assert not (tmp_path / "vault" / "raw" / "kind").exists()


def test_collect_kind_cross_check_mismatch_deferred(
    tmp_path: Path, seeded_engine, monkeypatch, caplog
) -> None:
    """Cross-check is deferred to Phase 9 ops dashboard (RESEARCH Q5).
    The structured log carries `suspension_cross_check_mismatch=[]` as a
    pass-through placeholder so downstream observability sees the key."""
    _write_portfolio(tmp_path)
    _seed_sk(seeded_engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )

    caplog.set_level(logging.INFO, logger="collectors.kind")
    collect_kind(engine=seeded_engine)

    complete = [r for r in caplog.records if r.message == "collector_run_complete"]
    assert complete, "expected a 'collector_run_complete' log record"
    rec = complete[-1]
    # The mismatch list must exist (Phase 9 placeholder) and be empty.
    assert getattr(rec, "suspension_cross_check_mismatch", "MISSING") == []


def test_collect_kind_dart_fetch_failure_isolated(
    tmp_path: Path, seeded_engine, monkeypatch
) -> None:
    """DART fetch raises → captured into stats.failed; sibling KIND sources unaffected."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)

    def _boom(**kwargs):
        raise RuntimeError("DART down (simulated)")

    monkeypatch.setattr("collectors.kind.dart_events.fetch_exchange_events", _boom)
    stats = collect_kind(engine=seeded_engine)
    assert stats["inserted"] == 0
    assert any(f["doc"] == "dart_events" for f in stats["failed"])


def test_collect_kind_parse_error_resilient(
    tmp_path: Path, seeded_engine, monkeypatch, caplog
) -> None:
    """R-17: KIND scraper selector drift → kind_parse_error flag, run does not fail."""
    _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [],
    )
    from collectors.kind.selectors import ParseError

    def _boom_parse(*a, **k):
        raise ParseError("selector miss: table.list")

    monkeypatch.setattr("collectors.kind.scraper.fetch_undisclosure_events", _boom_parse)

    caplog.set_level(logging.INFO, logger="collectors.kind")
    stats = collect_kind(engine=seeded_engine, enable_kind_scrape=True)

    # Run does not raise; ParseError lives in stats.failed
    assert any("ParseError" in f["error"] for f in stats["failed"])

    # Structured log surfaces kind_parse_error=True
    complete = [r for r in caplog.records if r.message == "collector_run_complete"]
    assert complete
    assert getattr(complete[-1], "kind_parse_error", False) is True
