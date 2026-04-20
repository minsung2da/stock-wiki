"""Alias matching for news articles (D-10 step 4, D-11, D-12).

R-01 design: pre-load a scoped alias inventory ONCE per collector run (single
DB query), then scan article title + body for any alias as a substring. This
fixes recall for Korean particles/punctuation/nicknames that token-regex
extraction misses.

R-09: assert_aliases_seeded() must be called at collector start — refuses to
run when entity_aliases has no ('name','eng_name') rows so operators can't
accidentally skip the seed step.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


class NoAliasesSeededError(RuntimeError):
    """R-09: raised at collect_news startup if entity_aliases has no name rows."""


def assert_aliases_seeded(engine: Engine) -> None:
    """R-09 startup guard: entity_aliases must have >=1 'name'/'eng_name' row."""
    with engine.connect() as conn:
        n = (
            conn.execute(
                text("SELECT COUNT(*) FROM entity_aliases WHERE kind IN ('name','eng_name')")
            ).scalar()
            or 0
        )
    if n == 0:
        raise NoAliasesSeededError(
            "No name aliases seeded — run `uv run python -m src.db.seed_name_aliases` first"
        )


def load_scoped_aliases(
    engine: Engine, tickers: Iterable[str], as_of: date | None = None
) -> dict[str, dict]:
    """Return {alias_text: {corp_code, ticker, name}} for entities whose
    current_ticker is in `tickers` (watchlist ∪ holdings per D-12).

    Single SQL round-trip. Aliases shorter than 2 chars are dropped to avoid
    pathological substring hits.
    """
    tickers_list = list(set(tickers))
    if not tickers_list:
        return {}
    if as_of is None:
        sql = text(
            """
            SELECT a.value AS alias, e.corp_code, e.current_ticker, e.canonical_name
            FROM entity_aliases a
            JOIN entities e USING (corp_code)
            WHERE a.kind IN ('name','eng_name')
              AND a.valid_to IS NULL
              AND e.current_ticker = ANY(:tks)
            """
        )
        params: dict[str, object] = {"tks": tickers_list}
    else:
        sql = text(
            """
            SELECT a.value AS alias, e.corp_code, e.current_ticker, e.canonical_name
            FROM entity_aliases a
            JOIN entities e USING (corp_code)
            WHERE a.kind IN ('name','eng_name')
              AND a.valid_from <= :asof
              AND (a.valid_to IS NULL OR a.valid_to > :asof)
              AND e.current_ticker = ANY(:tks)
            """
        )
        params = {"tks": tickers_list, "asof": as_of}
    out: dict[str, dict] = {}
    with engine.connect() as conn:
        for row in conn.execute(sql, params):
            if len(row.alias) < 2:
                continue
            out[row.alias] = {
                "corp_code": row.corp_code,
                "ticker": row.current_ticker,
                "name": row.canonical_name,
            }
    return out


def match_tickers_in_text(text_blob: str, alias_map: dict[str, dict]) -> list[dict]:
    """In-memory substring scan. Longest alias wins; dedup by corp_code."""
    if not text_blob or not alias_map:
        return []
    hits: dict[str, dict] = {}
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        if alias in text_blob:
            entry = alias_map[alias]
            hits.setdefault(entry["corp_code"], entry)
    return list(hits.values())
