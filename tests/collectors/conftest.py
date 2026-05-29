"""Shared fixtures for collector tests.

`seeded_engine` — the session `pg_engine` (from tests/conftest.py) with
Phase 2 tables truncated and Samsung Electronics pre-seeded (entities row
+ ticker alias + name alias), ready for collector tests that invoke
resolve_entity / resolve_entity_by_alias.

Plan 01-09 retired the ``vault_tmp`` fixture (Veto #9: Markdown vault is
dead). Tests that need a portfolio file on disk write it directly under
``tmp_path / "notes" / "private" / "portfolio.md"`` and ``monkeypatch.chdir``
into ``tmp_path`` — see ``tests/collectors/news/test_collect_news.py`` for
the established pattern.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text


@pytest.fixture
def seeded_engine(pg_clean):
    """pg_clean with one entity + ticker+name aliases pre-inserted (삼성전자/005930)."""
    with pg_clean.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (corp_code, canonical_name, current_ticker, market) "
                "VALUES ('00126380', '삼성전자', '005930', 'KOSPI')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO entity_aliases (corp_code, kind, value, valid_from, valid_to) "
                "VALUES ('00126380', 'ticker', '005930', :vf, NULL), "
                "       ('00126380', 'name',   '삼성전자', :vf, NULL)"
            ),
            {"vf": date(2020, 1, 1)},
        )
    return pg_clean
