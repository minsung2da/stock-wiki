"""Integration tests for collect_kind — Option-D hybrid orchestrator (Plan 05)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from collectors.kind import collect_kind

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/kind"


def _dart_events_for_samsung_and_sk():
    """Stub DART events: 1 suspension for 005930, 1 watchlist for 000660."""
    return [
        {
            "event_type": "suspension",
            "ticker": "005930",
            "corp_code": "00126380",
            "company_name": "삼성전자",
            "event_date": "20260417",
            "reason": "주권매매거래정지",
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
            "source_id": "20260417000003",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260417000003",
        },
    ]


def _seed_sk(engine):
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
                "VALUES ('00164779', 'ticker', '000660', '2020-01-01', NULL)"
            )
        )


def test_collect_kind_writes_scoped_dart_events(vault_tmp: Path, seeded_engine, monkeypatch):
    _seed_sk(seeded_engine)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )
    stats = collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 2
    # 999999 dropped as out-of-scope.
    assert (vault_tmp / "raw/kind/2026-04/suspension_005930_20260417.md").exists()
    assert (vault_tmp / "raw/kind/2026-04/watchlist_designation_000660_20260410.md").exists()
    assert not (vault_tmp / "raw/kind/2026-04/suspension_999999_20260417.md").exists()


def test_collect_kind_heartbeat_records_source_substats(
    vault_tmp: Path, seeded_engine, monkeypatch
):
    _seed_sk(seeded_engine)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )
    collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    hb = (vault_tmp / "ingested/_status/heartbeat.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(hb.split("---")[1])
    kind_block = meta["sources"]["kind"]
    assert "dart_events" in kind_block
    assert kind_block["dart_events"]["docs_processed"] == 3  # 3 events classified
    assert kind_block["dart_events"]["status"] == "ok"
    assert kind_block["kind_scrape"]["status"] == "skipped"
    assert kind_block["docs_processed"] == 2  # 2 written (scope filter)


def test_collect_kind_idempotent_rerun(vault_tmp: Path, seeded_engine, monkeypatch):
    _seed_sk(seeded_engine)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: _dart_events_for_samsung_and_sk(),
    )
    s1 = collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    s2 = collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    assert s1["succeeded"] == 2
    assert s2["succeeded"] == 0
    # All 3 events processed but 2 are identical-hash skips + 1 out-of-scope skip.
    assert s2["skipped"] >= 3


def test_collect_kind_dart_fetch_failure_isolated(vault_tmp: Path, seeded_engine, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("DART down")

    monkeypatch.setattr("collectors.kind.dart_events.fetch_exchange_events", _boom)
    stats = collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 0
    assert any(f["doc"] == "dart_events" for f in stats["failed"])
    # Heartbeat captures status=error for dart_events subblock.
    hb = (vault_tmp / "ingested/_status/heartbeat.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(hb.split("---")[1])
    assert meta["sources"]["kind"]["dart_events"]["status"] == "error"


def test_collect_kind_parse_error_sets_heartbeat_flag(vault_tmp: Path, seeded_engine, monkeypatch):
    _seed_sk(seeded_engine)
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [],
    )
    from collectors.kind.selectors import ParseError

    def _boom_parse():
        raise ParseError("selector miss: table.list")

    monkeypatch.setattr(
        "collectors.kind.scraper.fetch_undisclosure_events", lambda *a, **k: _boom_parse()
    )
    stats = collect_kind(vault_root=vault_tmp, engine=seeded_engine, enable_kind_scrape=True)
    assert any("ParseError" in f["error"] for f in stats["failed"])
    hb = (vault_tmp / "ingested/_status/heartbeat.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(hb.split("---")[1])
    assert meta["sources"]["kind"]["kind_parse_error"] is True
    assert meta["sources"]["kind"]["kind_scrape"]["status"] == "parse_error"


def test_collect_kind_cross_check_surfaces_mismatch(vault_tmp: Path, seeded_engine, monkeypatch):
    """If Plan 02's heartbeat has suspended_tickers not covered by DART suspension,
    collect_kind surfaces the mismatch in its heartbeat extra."""
    _seed_sk(seeded_engine)
    hb_path = vault_tmp / "ingested/_status/heartbeat.md"
    hb_path.parent.mkdir(parents=True, exist_ok=True)
    hb_path.write_text(
        "---\n"
        "sources:\n"
        "  krx:\n"
        "    last_run: '2026-04-17T00:00:00+00:00'\n"
        "    docs_processed: 1\n"
        "    suspended_tickers: ['005930', '123456']\n"
        "---\n<!-- -->\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: [
            {
                "event_type": "suspension",
                "ticker": "005930",
                "corp_code": "00126380",
                "company_name": "삼성전자",
                "event_date": "20260417",
                "reason": "주권매매거래정지",
                "source_id": "20260417000001",
                "source_url": "https://dart.fss.or.kr/x",
            },
        ],
    )
    collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    hb = hb_path.read_text(encoding="utf-8")
    meta = yaml.safe_load(hb.split("---")[1])
    mismatch = meta["sources"]["kind"].get("suspension_cross_check_mismatch")
    assert mismatch == ["123456"]


def test_collect_kind_dedup_same_key(vault_tmp: Path, seeded_engine, monkeypatch):
    """Two events with the same (event_type, ticker, event_date) → one file written."""
    dup = [
        {
            "event_type": "suspension",
            "ticker": "005930",
            "corp_code": "00126380",
            "company_name": "삼성전자",
            "event_date": "20260417",
            "reason": "주권매매거래정지",
            "source_id": "20260417000001",
            "source_url": "https://dart.fss.or.kr/x1",
        },
        {
            "event_type": "suspension",
            "ticker": "005930",
            "corp_code": "00126380",
            "company_name": "삼성전자",
            "event_date": "20260417",
            "reason": "주권매매거래정지기간변경",
            "source_id": "20260417000002",
            "source_url": "https://dart.fss.or.kr/x2",
        },
    ]
    monkeypatch.setattr(
        "collectors.kind.dart_events.fetch_exchange_events",
        lambda *, bgn_de, end_de: dup,
    )
    stats = collect_kind(vault_root=vault_tmp, engine=seeded_engine)
    assert stats["succeeded"] == 1
    assert stats["skipped"] == 1
