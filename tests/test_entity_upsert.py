"""Tests for upsert_entity (Bug C — quick-260418-asr).

Covers:
- E1: direct upsert -> resolve_entity round-trip (corp_code + ticker)
- E2: idempotent — two identical upserts produce exactly 1 entity + 1 alias row
- E3: updated canonical_name re-applies on conflict (ticker alias unchanged)
- E4: None ticker tolerated — no alias row inserted
- E5: collect_dart(engine=pg_clean) seeds entities as a byproduct of a successful run
- E6: collect_dart(engine=None) is a no-op on the DB (backward-compat with mocked tests)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

# ---------- Fakes (lifted from test_collect_dart — kept self-contained) ----------


@dataclass
class _FakeFiling:
    rcept_no: str
    rcept_dt: str  # "YYYYMMDD"
    pblntf_ty: str  # "A" or "B"
    body_text: str = "기본 본문"

    @property
    def pages(self) -> list[Any]:
        return [_FakePage(self.body_text)]

    def to_dict(self, summary: bool = False) -> dict[str, Any]:
        return {"rcept_no": self.rcept_no, "text": self.body_text}


@dataclass
class _FakePage:
    text: str

    @property
    def html(self) -> str:
        return f"<p>{self.text}</p>"


@dataclass
class _FakeCorp:
    stock_code: str = "005930"
    corp_name: str = "삼성전자㈜"
    last_search_kwargs: dict[str, Any] | None = None

    def search_filings(self, **kwargs: Any) -> Any:
        self.last_search_kwargs = kwargs
        return _FakeSearchResults(list(self._all_filings))

    _all_filings: list[_FakeFiling] = None  # type: ignore[assignment]


@dataclass
class _FakeSearchResults:
    report_list: list[_FakeFiling]


@pytest.fixture
def mock_dart(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"corp": None}

    def _get_client() -> None:
        return None

    def _find_corp(corp_code: str) -> _FakeCorp:
        corp = state["corp"]
        assert corp is not None, "test must set state['corp'] before calling collect_dart"
        return corp

    monkeypatch.setattr("collectors.dart.client.get_client", _get_client)
    monkeypatch.setattr("collectors.dart.client.find_corp", _find_corp)
    return state


def _make_corp(filings: list[_FakeFiling], **attrs: Any) -> _FakeCorp:
    corp = _FakeCorp(**attrs)
    corp._all_filings = filings
    return corp


# ---------- Helpers ----------


def _count(engine: Engine, table: str, **where: Any) -> int:
    clauses = " AND ".join(f"{k} = :{k}" for k in where)
    sql = f"SELECT count(*) FROM {table}"  # noqa: S608 — static identifier
    if clauses:
        sql += f" WHERE {clauses}"
    with engine.connect() as conn:
        return conn.execute(sa.text(sql), where).scalar_one()


# ---------- Direct upsert_entity tests ----------


class TestUpsertEntity:
    def test_E1_upsert_then_resolve_roundtrip(self, pg_clean: Engine) -> None:
        from db.entity import resolve_entity, upsert_entity

        upsert_entity(pg_clean, "00126380", "삼성전자㈜", "005930")

        e = resolve_entity(pg_clean, "005930")
        assert e is not None
        assert e.corp_code == "00126380"
        assert e.canonical_name == "삼성전자㈜"
        assert e.current_ticker == "005930"

        # corp_code direct lookup also works.
        e2 = resolve_entity(pg_clean, "00126380")
        assert e2 is not None and e2.corp_code == "00126380"

    def test_E2_idempotent_two_identical_upserts(self, pg_clean: Engine) -> None:
        from db.entity import upsert_entity

        upsert_entity(pg_clean, "00126380", "삼성전자㈜", "005930")
        upsert_entity(pg_clean, "00126380", "삼성전자㈜", "005930")

        assert _count(pg_clean, "entities", corp_code="00126380") == 1
        assert (
            _count(pg_clean, "entity_aliases", corp_code="00126380", kind="ticker", value="005930")
            == 1
        )

    def test_E3_updated_name_reapplies(self, pg_clean: Engine) -> None:
        from db.entity import upsert_entity

        upsert_entity(pg_clean, "00126380", "Old Name", "005930")
        upsert_entity(pg_clean, "00126380", "삼성전자㈜", "005930")

        with pg_clean.connect() as conn:
            name = conn.execute(
                sa.text("SELECT canonical_name FROM entities WHERE corp_code = :cc"),
                {"cc": "00126380"},
            ).scalar_one()
        assert name == "삼성전자㈜"
        # ticker alias count still 1 (value unchanged).
        assert (
            _count(pg_clean, "entity_aliases", corp_code="00126380", kind="ticker", value="005930")
            == 1
        )

    def test_E4_none_ticker_tolerated(self, pg_clean: Engine) -> None:
        from db.entity import upsert_entity

        upsert_entity(pg_clean, "99999991", "비상장기업", None)
        assert _count(pg_clean, "entities", corp_code="99999991") == 1
        # No alias row — ticker was None.
        assert _count(pg_clean, "entity_aliases", corp_code="99999991") == 0

    def test_E_invalid_corp_code_rejected(self, pg_clean: Engine) -> None:
        from db.entity import upsert_entity

        with pytest.raises(ValueError):
            upsert_entity(pg_clean, "abc", "bad", None)

    def test_E_invalid_ticker_rejected(self, pg_clean: Engine) -> None:
        from db.entity import upsert_entity

        with pytest.raises(ValueError):
            upsert_entity(pg_clean, "00126380", "name", "KOSPI01")


# ---------- collect_dart integration ----------


class TestCollectDartEntitySeed:
    def test_E5_collect_dart_seeds_entities_when_engine_given(
        self,
        pg_clean: Engine,
        tmp_path: Path,
        mock_dart: dict[str, Any],
    ) -> None:
        from collectors.dart import collect_dart
        from db.entity import resolve_entity

        filings = [_FakeFiling("20260101000001", "20260115", "A", body_text="body")]
        mock_dart["corp"] = _make_corp(filings, stock_code="005930", corp_name="삼성전자㈜")

        stats = collect_dart(
            corp_code="00126380",
            since="2026-01-01",
            vault_root=tmp_path,
            engine=pg_clean,
        )
        assert stats["succeeded"] == 1

        e = resolve_entity(pg_clean, "005930")
        assert e is not None
        assert e.corp_code == "00126380"
        assert e.canonical_name == "삼성전자㈜"

    def test_E6_collect_dart_without_engine_does_not_touch_db(
        self,
        pg_clean: Engine,
        tmp_path: Path,
        mock_dart: dict[str, Any],
    ) -> None:
        from collectors.dart import collect_dart

        filings = [_FakeFiling("20260101000001", "20260115", "A", body_text="body")]
        mock_dart["corp"] = _make_corp(filings)

        stats = collect_dart(
            corp_code="00126380",
            since="2026-01-01",
            vault_root=tmp_path,
            # engine omitted — default None
        )
        assert stats["succeeded"] == 1
        assert _count(pg_clean, "entities") == 0
        assert _count(pg_clean, "entity_aliases") == 0

    def test_E_collect_dart_no_success_no_seed(
        self,
        pg_clean: Engine,
        tmp_path: Path,
        mock_dart: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If every filing fails, entity seeding is skipped (stats.succeeded == 0)."""
        from collectors.dart import collect_dart, fetcher

        filings = [_FakeFiling("20260101000001", "20260115", "A", body_text="body")]
        mock_dart["corp"] = _make_corp(filings)

        def always_fail(filing: Any) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr(fetcher, "fetch_body", always_fail)

        stats = collect_dart(
            corp_code="00126380",
            since="2026-01-01",
            vault_root=tmp_path,
            engine=pg_clean,
        )
        assert stats["succeeded"] == 0
        assert _count(pg_clean, "entities") == 0
