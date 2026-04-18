"""Canonical entity resolution — ENT-01/ENT-02 helper.

src/db/entity.py is the ONLY place that reads entity_aliases for lookup.
Downstream collectors (Phase 3+) must use `resolve_entity` — do not re-implement.

SQL safety: all queries use SQLAlchemy bind parameters (:v, :asof). No
f-string interpolation into SQL. Digit/length pre-filter (D-12) ensures only
^[0-9]{8}$ or ^[0-9]{6}$ strings reach the database. See threat T-02-11.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

# ASCII-only digit patterns — str.isdigit() accepts non-ASCII digits (e.g.
# superscript ² returns True); these regexes close that loophole (D-12).
_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")
_TICKER_RE = re.compile(r"^[0-9]{6}$")


@dataclass(frozen=True)
class Entity:
    corp_code: str
    canonical_name: str
    current_ticker: str | None


def resolve_entity(
    engine: Engine,
    value: str,
    as_of: date | None = None,
) -> Entity | None:
    """Resolve a corp_code (8 digits) or ticker (6 digits) to an Entity.

    D-09: valid-time only. `as_of` means "real-world entity state at that date".
    D-10/D-11: as_of=None → current only (valid_to IS NULL);
               as_of=<date> → historical through an entity_aliases row whose
               [valid_from, valid_to) half-open interval covers the date.
    D-12: 8 ASCII digits → direct corp_code lookup on entities;
          6 ASCII digits → ticker alias lookup through entity_aliases;
          any other value → None (mismatch).
    """
    if _CORP_CODE_RE.match(value):
        sql = text(
            """
            SELECT corp_code, canonical_name, current_ticker
            FROM entities
            WHERE corp_code = :v
            """
        )
        params: dict[str, object] = {"v": value}
    elif _TICKER_RE.match(value):
        if as_of is None:
            sql = text(
                """
                SELECT e.corp_code, e.canonical_name, e.current_ticker
                FROM entity_aliases a
                JOIN entities e USING (corp_code)
                WHERE a.kind = 'ticker'
                  AND a.value = :v
                  AND a.valid_to IS NULL
                LIMIT 1
                """
            )
            params = {"v": value}
        else:
            sql = text(
                """
                SELECT e.corp_code, e.canonical_name, e.current_ticker
                FROM entity_aliases a
                JOIN entities e USING (corp_code)
                WHERE a.kind = 'ticker'
                  AND a.value = :v
                  AND a.valid_from <= :asof
                  AND (a.valid_to IS NULL OR a.valid_to > :asof)
                LIMIT 1
                """
            )
            params = {"v": value, "asof": as_of}
    else:
        return None

    with engine.connect() as conn:
        row = conn.execute(sql, params).first()
    if row is None:
        return None
    return Entity(
        corp_code=row.corp_code,
        canonical_name=row.canonical_name,
        current_ticker=row.current_ticker,
    )


_NAME_MAX_LEN = 128


def resolve_entity_by_alias(
    engine: Engine,
    name: str,
    as_of: date | None = None,
) -> Entity | None:
    """Resolve a Korean or English company name to an Entity via entity_aliases (D-11).

    Exact match only (no fuzzy/substring). Filters kind IN ('name','eng_name') matching
    the CHECK constraint `ck_alias_kind` in migration 0001. Temporal semantics mirror
    resolve_entity: as_of=None → current only (valid_to IS NULL); as_of=<date> →
    half-open interval [valid_from, valid_to).

    Defensive length guard (T-04-02): names > 128 chars short-circuit to None before
    touching the database.
    """
    if not name or len(name) > _NAME_MAX_LEN:
        return None
    if as_of is None:
        sql = text(
            """
            SELECT e.corp_code, e.canonical_name, e.current_ticker
            FROM entity_aliases a
            JOIN entities e USING (corp_code)
            WHERE a.kind IN ('name','eng_name')
              AND a.value = :v
              AND a.valid_to IS NULL
            LIMIT 1
            """
        )
        params: dict[str, object] = {"v": name}
    else:
        sql = text(
            """
            SELECT e.corp_code, e.canonical_name, e.current_ticker
            FROM entity_aliases a
            JOIN entities e USING (corp_code)
            WHERE a.kind IN ('name','eng_name')
              AND a.value = :v
              AND a.valid_from <= :asof
              AND (a.valid_to IS NULL OR a.valid_to > :asof)
            LIMIT 1
            """
        )
        params = {"v": name, "asof": as_of}
    with engine.connect() as conn:
        row = conn.execute(sql, params).first()
    if row is None:
        return None
    return Entity(
        corp_code=row.corp_code,
        canonical_name=row.canonical_name,
        current_ticker=row.current_ticker,
    )


def upsert_entity(
    engine: Engine,
    corp_code: str,
    canonical_name: str,
    ticker: str | None,
    market: str | None = "KOSPI",
) -> None:
    """Idempotent upsert of (entities, entity_aliases).

    Called by collectors after a successful filing write so that downstream
    `resolve_entity(ticker)` returns a match (Bug C fix, quick-260418-asr).

    Semantics:
    - `entities`: INSERT ... ON CONFLICT (corp_code) DO UPDATE — refreshes
      canonical_name + current_ticker on rename.
    - `entity_aliases`: SELECT-then-INSERT (NO unique constraint on
      (corp_code, kind, value) — Pitfall 5: KRX recycles tickers). Only writes
      when no current alias (kind='ticker', value=ticker, valid_to IS NULL)
      exists for this corp_code.
    - `ticker=None`: entities row still upserted; no alias written.

    SQL discipline (Phase 2 WR-03): all values flow through bind params — no
    f-string interpolation into SQL. corp_code/ticker are regex-validated
    (D-12) before reaching the DB (threat T-Q1-01).
    """
    if not _CORP_CODE_RE.match(corp_code):
        raise ValueError(
            f"upsert_entity: invalid corp_code shape (need 8 ASCII digits), got {corp_code!r}"
        )
    if ticker is not None and not _TICKER_RE.match(ticker):
        raise ValueError(
            f"upsert_entity: invalid ticker shape (need 6 ASCII digits or None), got {ticker!r}"
        )

    from datetime import date

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO entities (corp_code, canonical_name, current_ticker, market)
                VALUES (:cc, :name, :ticker, :market)
                ON CONFLICT (corp_code) DO UPDATE
                  SET canonical_name = EXCLUDED.canonical_name,
                      current_ticker = EXCLUDED.current_ticker
                """
            ),
            {"cc": corp_code, "name": canonical_name, "ticker": ticker, "market": market},
        )
        if ticker is not None:
            existing = conn.execute(
                text(
                    """
                    SELECT 1 FROM entity_aliases
                    WHERE corp_code = :cc
                      AND kind = 'ticker'
                      AND value = :v
                      AND valid_to IS NULL
                    LIMIT 1
                    """
                ),
                {"cc": corp_code, "v": ticker},
            ).first()
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO entity_aliases
                          (corp_code, kind, value, valid_from, valid_to)
                        VALUES (:cc, 'ticker', :v, :vf, NULL)
                        """
                    ),
                    {"cc": corp_code, "v": ticker, "vf": date.today()},
                )
