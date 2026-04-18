"""Tests for resolve_entity_by_alias + seed_name_aliases (D-11, R-09)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.entity import resolve_entity_by_alias
from db.seed_name_aliases import seed_name_aliases


def _insert_samsung(engine: Engine, *, with_name_alias: bool = True) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00126380', '삼성전자', '005930', 'KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00126380', 'ticker', '005930', :vf, NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )
        if with_name_alias:
            conn.execute(
                text(
                    "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                    "VALUES ('00126380', 'name', '삼성전자', :vf, NULL)"
                ),
                {"vf": date(2020, 1, 1)},
            )


def test_resolve_by_korean_name(pg_clean: Engine) -> None:
    _insert_samsung(pg_clean)
    e = resolve_entity_by_alias(pg_clean, "삼성전자")
    assert e is not None
    assert e.corp_code == "00126380"
    assert e.canonical_name == "삼성전자"
    assert e.current_ticker == "005930"


def test_resolve_unknown_name_returns_none(pg_clean: Engine) -> None:
    _insert_samsung(pg_clean)
    assert resolve_entity_by_alias(pg_clean, "없는회사") is None


def test_resolve_empty_string_returns_none(pg_clean: Engine) -> None:
    assert resolve_entity_by_alias(pg_clean, "") is None


def test_resolve_too_long_returns_none(pg_clean: Engine) -> None:
    assert resolve_entity_by_alias(pg_clean, "x" * 129) is None


def test_resolve_as_of_outside_window_returns_none(pg_clean: Engine) -> None:
    _insert_samsung(pg_clean)
    # alias valid_from = 2020-01-01 → as_of before that returns None.
    assert resolve_entity_by_alias(pg_clean, "삼성전자", as_of=date(2019, 1, 1)) is None


def test_resolve_by_english_name_kind(pg_clean: Engine) -> None:
    _insert_samsung(pg_clean, with_name_alias=True)
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00126380', 'eng_name', 'Samsung Electronics', :vf, NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )
    e = resolve_entity_by_alias(pg_clean, "Samsung Electronics")
    assert e is not None
    assert e.corp_code == "00126380"


def test_seed_name_aliases_is_idempotent(pg_clean: Engine) -> None:
    # Start with entity but NO name alias.
    _insert_samsung(pg_clean, with_name_alias=False)
    n1 = seed_name_aliases(pg_clean)
    assert n1 == 1
    n2 = seed_name_aliases(pg_clean)
    assert n2 == 0
    # After seeding, resolve_entity_by_alias should find it.
    e = resolve_entity_by_alias(pg_clean, "삼성전자")
    assert e is not None
    assert e.corp_code == "00126380"
