"""One-shot seeder: insert a 'name' alias for every entity that lacks one (R-09).

Runs before collect_news so the alias matcher has rows to match against.
Idempotent: SELECT-then-INSERT per entity row. Mirrors the upsert_entity
discipline (no UNIQUE constraint on entity_aliases — Pitfall 5 / KRX ticker
recycling).

Operational command:
    uv run python -m src.db.seed_name_aliases   # reads DATABASE_URL
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


def seed_name_aliases(engine: Engine) -> int:
    """Insert (corp_code, 'name', canonical_name, today, NULL) for entities
    lacking a current 'name' alias. Returns the number of rows inserted."""
    inserted = 0
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT corp_code, canonical_name FROM entities")).all()
        for r in rows:
            existing = conn.execute(
                text(
                    """
                    SELECT 1 FROM entity_aliases
                    WHERE corp_code = :cc
                      AND kind = 'name'
                      AND value = :v
                      AND valid_to IS NULL
                    LIMIT 1
                    """
                ),
                {"cc": r.corp_code, "v": r.canonical_name},
            ).first()
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO entity_aliases
                          (corp_code, kind, value, valid_from, valid_to)
                        VALUES (:cc, 'name', :v, :vf, NULL)
                        """
                    ),
                    {"cc": r.corp_code, "v": r.canonical_name, "vf": date.today()},
                )
                inserted += 1
    return inserted


if __name__ == "__main__":  # R-09: CLI entry point for operators.
    import sys

    from db.engine import get_engine

    n = seed_name_aliases(get_engine())
    print(f"seed_name_aliases: inserted {n} rows")
    sys.exit(0)
