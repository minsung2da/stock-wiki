"""Canonical entity resolution — ENT-01/ENT-02 helper.

src/db/entity.py is the ONLY place that reads entity_aliases for lookup.
Downstream collectors (Phase 3+) must use `resolve_entity` — do not re-implement.

SQL safety: all queries use SQLAlchemy bind parameters (:v, :asof). No
f-string interpolation into SQL. Digit/length pre-filter (D-12) ensures only
^\\d{8}$ or ^\\d{6}$ strings reach the database. See threat T-02-11.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class Entity:
    corp_code: str
    canonical_name: str
    current_ticker: str | None


def _is_digits(value: str, length: int) -> bool:
    return len(value) == length and value.isdigit()


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
    D-12: 8 digits → direct corp_code lookup on entities;
          6 digits → ticker alias lookup through entity_aliases;
          any other length → None (mismatch).
    """
    if _is_digits(value, 8):
        sql = text(
            """
            SELECT corp_code, canonical_name, current_ticker
            FROM entities
            WHERE corp_code = :v
            """
        )
        params: dict[str, object] = {"v": value}
    elif _is_digits(value, 6):
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
