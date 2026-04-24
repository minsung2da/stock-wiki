"""Local fixtures for tests/db — mirrors tests/collectors/conftest.py.

`vault_tmp` — an empty vault with raw/ + notes/ + ingested/_status/ subdirs
plus a minimal portfolio.md so Portfolio.load succeeds.

`seeded_engine` — pg_clean with 삼성전자/005930 pre-seeded.
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
    """Empty vault with raw/ + notes/ + ingested/_status/ subdirs + seed portfolio."""
    for sub in ("raw", "notes", "ingested/_status"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes" / "portfolio.md").write_text(_SEED_PORTFOLIO, encoding="utf-8")
    return tmp_path


@pytest.fixture
def seeded_engine(pg_clean):
    """pg_clean with 삼성전자/005930 pre-inserted (entities + ticker+name aliases)."""
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
