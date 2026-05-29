"""Tests for upsert_entity (Bug C — quick-260418-asr).

Covers:
- E1: direct upsert -> resolve_entity round-trip (corp_code + ticker)
- E2: idempotent — two identical upserts produce exactly 1 entity + 1 alias row
- E3: updated canonical_name re-applies on conflict (ticker alias unchanged)
- E4: None ticker tolerated — no alias row inserted

The legacy ``TestCollectDartEntitySeed`` class (E5/E6/no-success-no-seed)
was removed in Plan 01-09: those scenarios called the deleted
``collect_dart(... vault_root=tmp_path ...)`` signature and are now
covered end-to-end by ``tests/collectors/dart/test_collect_dart.py``
(see ``test_collect_dart_bug_c_entity_upsert``).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

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


# collect_dart-integration entity-seed coverage now lives in
# tests/collectors/dart/test_collect_dart.py::test_collect_dart_bug_c_entity_upsert.
# The legacy block here passed vault_root= which no longer exists post-01-02.
