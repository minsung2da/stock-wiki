"""R-01 matcher tests + R-09 startup guard.

Verifies:
- load_scoped_aliases returns {alias: entry} in ONE DB round-trip (sqlalchemy
  query-counter event listener).
- match_tickers_in_text does in-memory substring scan (title+body) with
  longest-alias-wins dedup.
- Scope exclusion (aliases outside scope never enter the alias_map).
- Nickname support via extra seeded aliases.
- Dedup across multiple mentions.
- assert_aliases_seeded raises NoAliasesSeededError on empty entity_aliases.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import event, text

from collectors.news.matcher import (
    NoAliasesSeededError,
    assert_aliases_seeded,
    load_scoped_aliases,
    match_tickers_in_text,
)


def _seed_extra_alias(engine, corp_code: str, value: str, kind: str = "name") -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES (:cc, :k, :v, :vf, NULL)"
            ),
            {"cc": corp_code, "k": kind, "v": value, "vf": date(2020, 1, 1)},
        )


def _seed_second_entity(engine) -> None:
    """Add SK Hynix 000660."""
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


def test_load_scoped_aliases_one_sql_call(seeded_engine) -> None:
    """R-01: alias inventory fetched in a single DB round-trip."""
    _seed_extra_alias(seeded_engine, "00126380", "Samsung Electronics", kind="eng_name")

    queries: list[str] = []

    def _before_execute(conn, clauseelement, multiparams, params, execution_options):
        sql = str(clauseelement)
        if "entity_aliases" in sql or "entities" in sql:
            queries.append(sql)

    event.listen(seeded_engine, "before_execute", _before_execute)
    try:
        alias_map = load_scoped_aliases(seeded_engine, ["005930"])
    finally:
        event.remove(seeded_engine, "before_execute", _before_execute)

    assert len(queries) == 1, f"expected 1 SQL call, got {len(queries)}: {queries}"
    assert "삼성전자" in alias_map
    assert "Samsung Electronics" in alias_map
    assert alias_map["삼성전자"]["corp_code"] == "00126380"
    assert alias_map["삼성전자"]["ticker"] == "005930"


def test_match_tickers_in_text_title_match(seeded_engine) -> None:
    alias_map = load_scoped_aliases(seeded_engine, ["005930"])
    text_blob = "삼성전자, 최대실적\n오늘 발표…"
    hits = match_tickers_in_text(text_blob, alias_map)
    assert len(hits) == 1
    assert hits[0]["corp_code"] == "00126380"
    assert hits[0]["ticker"] == "005930"


def test_match_tickers_in_text_nickname(seeded_engine) -> None:
    _seed_extra_alias(seeded_engine, "00126380", "삼전", kind="name")
    alias_map = load_scoped_aliases(seeded_engine, ["005930"])
    hits = match_tickers_in_text("삼전이 강세 보이고 있다", alias_map)
    assert len(hits) == 1
    assert hits[0]["corp_code"] == "00126380"


def test_match_tickers_in_text_scope_excludes_out_of_scope_entity(seeded_engine) -> None:
    _seed_second_entity(seeded_engine)
    # Scope = SK Hynix only; Samsung alias must NOT be in the alias_map.
    alias_map = load_scoped_aliases(seeded_engine, ["000660"])
    assert "삼성전자" not in alias_map
    hits = match_tickers_in_text("오늘 삼성전자가 상승했다", alias_map)
    assert hits == []


def test_match_tickers_in_text_no_match_returns_empty(seeded_engine) -> None:
    alias_map = load_scoped_aliases(seeded_engine, ["005930"])
    hits = match_tickers_in_text("코스피 1% 상승 마감", alias_map)
    assert hits == []


def test_match_tickers_in_text_dedup_same_entity(seeded_engine) -> None:
    alias_map = load_scoped_aliases(seeded_engine, ["005930"])
    hits = match_tickers_in_text("삼성전자 삼성전자 삼성전자", alias_map)
    assert len(hits) == 1


def test_match_tickers_in_text_empty_inputs() -> None:
    assert match_tickers_in_text("", {"x": {"corp_code": "c"}}) == []
    assert match_tickers_in_text("some text", {}) == []


def test_assert_aliases_seeded_raises_when_empty(pg_clean) -> None:
    with pytest.raises(NoAliasesSeededError):
        assert_aliases_seeded(pg_clean)


def test_assert_aliases_seeded_passes_when_seeded(seeded_engine) -> None:
    # Should not raise.
    assert_aliases_seeded(seeded_engine)


def test_load_scoped_aliases_empty_scope_returns_empty(seeded_engine) -> None:
    assert load_scoped_aliases(seeded_engine, []) == {}


def test_load_scoped_aliases_skips_single_char_aliases(seeded_engine) -> None:
    _seed_extra_alias(seeded_engine, "00126380", "S", kind="eng_name")  # len<2 skip
    alias_map = load_scoped_aliases(seeded_engine, ["005930"])
    assert "S" not in alias_map
    assert "삼성전자" in alias_map
