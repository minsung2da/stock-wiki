"""Macro series DB writer — Phase 1 Plan 01-03.

Replaces ``collectors.macro.writer.write_macro_doc`` (Markdown vault output)
with direct INSERTs into the ``macro_series`` Postgres table.

Design choice (RESEARCH Q2): the "load existing → classify → upsert" two-pass
approach. The Postgres ``ON CONFLICT ... DO UPDATE WHERE`` trick with
``RETURNING (xmax = 0)`` would also work for inserted/updated classification,
but the two-pass approach is more readable AND gives us deterministic R-06
revision detection in Python (capture both the previous value and the new
value before the UPDATE fires). Performance is a non-issue: macro series carry
hundreds of observations per fetch, not millions.

R-06 revision semantics: same ``(source, series_id, item_code, obs_date)``
with a NEW value is detected on the first pass (load existing) and surfaced
in the returned ``revisions`` list:

    [{"obs_date": "YYYY-MM-DD", "old": <prev_value>, "new": <new_value>}, ...]

Plan 01-08 will consume this list into the ``collector_runs.extra`` JSONB
column. This module only returns it — it does not log or persist the
revisions itself.

Hard Veto reminders:
- Veto #6 — ``macro_series`` has zero narrative/embedding columns. This
  writer INSERTs only typed columns (source, series_id, item_code, obs_date,
  value, unit, label, cycle, fetched_at).
- Veto #9 — no Markdown is written by this module. Successful return means
  rows landed in Postgres; no filesystem writes occur.

Pre-flight validation (carried forward from ``writer.py`` T-04-08):
- ``source`` must be in ``{'ecos', 'fred'}``.
- ``series_id`` must match ``^[A-Z0-9_\\-]{1,32}$``.
- ``cycle`` must be in ``{'D','M','Q','Y'}``; empty/falsey → default 'D'.

These guards are duplicated from ``writer.py`` (not imported) because
``writer.py`` will be deleted by plan 01-09 — importing from it would create
a removal hazard.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

_SERIES_RE = re.compile(r"^[A-Z0-9_\-]{1,32}$")
_ALLOWED_SOURCES = frozenset({"ecos", "fred"})
_ALLOWED_CYCLES = frozenset({"D", "M", "Q", "Y"})

__all__ = ["upsert_macro_observations"]


def upsert_macro_observations(
    engine: Engine,
    *,
    source: str,
    series_id: str,
    item_code: str,
    label: str,
    cycle: str,
    observations: list[dict[str, Any]],
) -> tuple[int, int, list[dict]]:
    """UPSERT observations into ``macro_series``.

    Args:
        engine: SQLAlchemy Engine bound to the project Postgres DB.
        source: 'ecos' or 'fred'.
        series_id: catalog series id (uppercase alphanumeric / dash / underscore, ≤32).
        item_code: ECOS ITEM_CODE1 or '' for FRED.
        label: catalog label (denormalized for ops; e.g. 'base_rate_kr').
        cycle: one of 'D', 'M', 'Q', 'Y' (defaults to 'D' if empty).
        observations: list of dicts with keys ``date`` (date) and ``value`` (float);
                      optional ``unit`` (str) is forwarded if present.

    Returns:
        (inserted, updated, revisions) where:
          - inserted = count of obs_dates not previously present.
          - updated  = count of obs_dates that existed with a different value.
          - revisions = R-06 list (one dict per updated row).

    Raises:
        ValueError: on invalid source / series_id / cycle.
    """
    # Pre-flight validation.
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"bad source {source!r}")
    if not _SERIES_RE.match(series_id):
        raise ValueError(f"bad series_id {series_id!r}")
    effective_cycle = cycle or "D"
    if effective_cycle not in _ALLOWED_CYCLES:
        raise ValueError(f"bad cycle {cycle!r}")

    if not observations:
        return 0, 0, []

    with engine.begin() as conn:
        # Step 1: load existing rows for this (source, series_id, item_code) slice.
        existing: dict[Any, float] = {}
        for row in conn.execute(
            text(
                "SELECT obs_date, value FROM macro_series "
                "WHERE source = :s AND series_id = :sid AND item_code = :ic"
            ),
            {"s": source, "sid": series_id, "ic": item_code},
        ):
            existing[row.obs_date] = float(row.value)

        # Step 2: classify each observation.
        inserted = 0
        updated = 0
        revisions: list[dict] = []
        rows_to_upsert: list[dict] = []

        for obs in observations:
            obs_date = obs["date"]
            new_value = float(obs["value"])
            unit_val = obs.get("unit")

            prev = existing.get(obs_date)
            if prev is None:
                inserted += 1
                rows_to_upsert.append(
                    {
                        "source": source,
                        "series_id": series_id,
                        "item_code": item_code,
                        "obs_date": obs_date,
                        "value": new_value,
                        "unit": unit_val,
                        "label": label,
                        "cycle": effective_cycle,
                    }
                )
            elif prev != new_value:
                updated += 1
                revisions.append(
                    {
                        "obs_date": obs_date.isoformat(),
                        "old": prev,
                        "new": new_value,
                    }
                )
                rows_to_upsert.append(
                    {
                        "source": source,
                        "series_id": series_id,
                        "item_code": item_code,
                        "obs_date": obs_date,
                        "value": new_value,
                        "unit": unit_val,
                        "label": label,
                        "cycle": effective_cycle,
                    }
                )
            # else: same value at same date — skip (idempotent no-op).

        # Step 3: single UPSERT for inserted + updated rows.
        if rows_to_upsert:
            conn.execute(
                text(
                    """
                    INSERT INTO macro_series
                      (source, series_id, item_code, obs_date, value, unit, label, cycle, fetched_at)
                    VALUES
                      (:source, :series_id, :item_code, :obs_date, :value, :unit, :label, :cycle, now())
                    ON CONFLICT (source, series_id, item_code, obs_date) DO UPDATE
                      SET value = EXCLUDED.value,
                          unit  = EXCLUDED.unit,
                          label = EXCLUDED.label,
                          cycle = EXCLUDED.cycle,
                          fetched_at = now()
                    """
                ),
                rows_to_upsert,
            )

    return inserted, updated, revisions
