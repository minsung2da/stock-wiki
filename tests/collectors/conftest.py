"""Shared fixtures for Phase 4 collector tests.

`vault_tmp` — an empty vault scaffolded with raw/, notes/, and
ingested/_status/ subdirs plus a minimal portfolio.md so Portfolio.load
succeeds.

`seeded_engine` — the session `pg_engine` (from tests/conftest.py) with
Phase 2 tables truncated and Samsung Electronics pre-seeded (entities row
+ ticker alias + name alias), ready for collector tests that invoke
resolve_entity / resolve_entity_by_alias.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

_SEED_PORTFOLIO = (
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


@pytest.fixture
def vault_tmp(tmp_path: Path) -> Path:
    """Empty vault with raw/ + notes/ + ingested/_status/ subdirs + seed portfolio.

    Phase 6 P-01: portfolio lives at `<repo_root>/notes/private/portfolio.md`
    where `repo_root = vault_root.parent`. We materialize tmp_path as the repo
    root and return tmp_path/"vault" as the vault_root so collectors can
    derive repo_root via .parent.

    DEPRECATED after Phase 1 Wave 2: plan 01-09 deletes the writer modules
    that consume this fixture. The vault_tmp fixture is retained through
    Wave 1/2 only so legacy per-collector tests in tests/collectors/<src>/
    that still exercise writer.* (and not yet db_writer.*) keep working.
    Remove it when 01-09 lands.
    """
    vault = tmp_path / "vault"
    for sub in ("raw", "notes", "ingested/_status"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes" / "private").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes" / "private" / "portfolio.md").write_text(_SEED_PORTFOLIO, encoding="utf-8")
    return vault


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
