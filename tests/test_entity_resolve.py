"""Tests for resolve_entity (ENT-01/ENT-02).

Covers D-09 valid-time semantics, D-10 current-only vs historical branch,
D-11 valid_to IS NULL marker, D-12 digit-length auto-branch (8=corp_code, 6=ticker).
"""

from __future__ import annotations

from datetime import date

from tests.fixtures_loader import load_entity_fixture


def test_corp_code_direct_lookup(pg_clean):
    from db.entity import resolve_entity

    load_entity_fixture(pg_clean, "fixtures/entities/rename_case.yaml")
    e = resolve_entity(pg_clean, "00126380")
    assert e is not None
    assert e.corp_code == "00126380"
    assert e.canonical_name == "삼성전자㈜"


def test_current_ticker_lookup(pg_clean):
    from db.entity import resolve_entity

    load_entity_fixture(pg_clean, "fixtures/entities/rename_case.yaml")
    e = resolve_entity(pg_clean, "005930")
    assert e is not None
    assert e.corp_code == "00126380"


def test_rename_historical_ticker_resolves(pg_clean):
    from db.entity import resolve_entity

    load_entity_fixture(pg_clean, "fixtures/entities/rename_case.yaml")
    # 1999: ticker existed under same corp_code (name was the older form then).
    e = resolve_entity(pg_clean, "005930", as_of=date(1999, 1, 1))
    assert e is not None
    assert e.corp_code == "00126380"


def test_split_date_boundary_same_corp_code(pg_clean):
    from db.entity import resolve_entity

    load_entity_fixture(pg_clean, "fixtures/entities/split_case.yaml")
    before = resolve_entity(pg_clean, "099001", as_of=date(2014, 5, 27))
    after = resolve_entity(pg_clean, "099001", as_of=date(2014, 5, 29))
    assert before is not None and after is not None
    assert before.corp_code == after.corp_code == "00126381"


def test_ticker_recycle_as_of_selects_correct_corp(pg_clean):
    """SYNTHETIC fixture (Pitfall 1): two corp_codes share ticker at different times."""
    from db.entity import resolve_entity

    load_entity_fixture(pg_clean, "fixtures/entities/ticker_recycle.yaml")
    old = resolve_entity(pg_clean, "099999", as_of=date(1995, 1, 1))
    new = resolve_entity(pg_clean, "099999", as_of=date(2015, 1, 1))
    current = resolve_entity(pg_clean, "099999")  # as_of=None -> current only
    assert old is not None and old.corp_code == "99999991"
    assert new is not None and new.corp_code == "99999992"
    assert current is not None and current.corp_code == "99999992"


def test_gap_between_recycles_returns_none(pg_clean):
    from db.entity import resolve_entity

    load_entity_fixture(pg_clean, "fixtures/entities/ticker_recycle.yaml")
    # 2005 is after old delisted (2001-01-01 valid_to exclusive) and before new listed (2010-01-01).
    e = resolve_entity(pg_clean, "099999", as_of=date(2005, 6, 1))
    assert e is None


def test_mismatch_length_returns_none(pg_clean):
    from db.entity import resolve_entity

    assert resolve_entity(pg_clean, "") is None
    assert resolve_entity(pg_clean, "1234") is None
    assert resolve_entity(pg_clean, "garbage") is None
    assert resolve_entity(pg_clean, "1234567") is None  # 7 digits
    assert resolve_entity(pg_clean, "KOSPI001") is None  # 8 chars, not all ASCII digits
    assert resolve_entity(pg_clean, "²²²²²²²²") is None  # 8 superscript digits (non-ASCII)


def test_nonexistent_corp_code_returns_none(pg_clean):
    from db.entity import resolve_entity

    assert resolve_entity(pg_clean, "00000000") is None


def test_nonexistent_ticker_returns_none(pg_clean):
    from db.entity import resolve_entity

    assert resolve_entity(pg_clean, "000000") is None
