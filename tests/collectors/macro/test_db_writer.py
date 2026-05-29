"""Tests for collectors.macro.db_writer — Phase 1 Plan 01-03.

Covers the macro_series UPSERT writer:
- new-row INSERT counts
- idempotent re-run (same value → no DB write)
- R-06 revision detection (same date + different value → UPDATE + revision entry)
- empty-observations no-op
- pre-flight validation (source whitelist, series_id regex)
- FRED empty item_code handling
- mixed insert+update batch

All tests assert DB state via the `pg_clean` fixture (function-scoped TRUNCATE
on the session pg_engine).

Hard Veto reminders verified by the schema (migration 0006) — these tests focus
on the writer's correctness, not on schema invariants.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text


def _select_rows(engine, source: str, series_id: str):
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT obs_date, value, item_code, label, cycle, unit "
                "FROM macro_series "
                "WHERE source=:s AND series_id=:sid "
                "ORDER BY obs_date"
            ),
            {"s": source, "sid": series_id},
        ).fetchall()
    return rows


def test_upsert_inserts_new_rows(pg_clean):
    from collectors.macro.db_writer import upsert_macro_observations

    obs = [
        {"date": date(2026, 1, 1), "value": 3.25},
        {"date": date(2026, 1, 2), "value": 3.26},
        {"date": date(2026, 1, 3), "value": 3.27},
    ]
    inserted, updated, revisions = upsert_macro_observations(
        pg_clean,
        source="ecos",
        series_id="722Y001",
        item_code="0101000",
        label="base_rate_kr",
        cycle="D",
        observations=obs,
    )
    assert inserted == 3
    assert updated == 0
    assert revisions == []

    rows = _select_rows(pg_clean, "ecos", "722Y001")
    assert len(rows) == 3
    assert [(r.obs_date, float(r.value)) for r in rows] == [
        (date(2026, 1, 1), 3.25),
        (date(2026, 1, 2), 3.26),
        (date(2026, 1, 3), 3.27),
    ]
    # label/cycle/item_code persisted
    assert all(r.label == "base_rate_kr" for r in rows)
    assert all(r.cycle == "D" for r in rows)
    assert all(r.item_code == "0101000" for r in rows)


def test_upsert_idempotent_same_values(pg_clean):
    from collectors.macro.db_writer import upsert_macro_observations

    obs = [
        {"date": date(2026, 1, 1), "value": 3.25},
        {"date": date(2026, 1, 2), "value": 3.26},
        {"date": date(2026, 1, 3), "value": 3.27},
    ]
    # First call inserts.
    upsert_macro_observations(
        pg_clean, source="ecos", series_id="722Y001", item_code="0101000",
        label="base_rate_kr", cycle="D", observations=obs,
    )
    # Second call with identical values: no insert, no update, no revision.
    inserted, updated, revisions = upsert_macro_observations(
        pg_clean, source="ecos", series_id="722Y001", item_code="0101000",
        label="base_rate_kr", cycle="D", observations=obs,
    )
    assert inserted == 0
    assert updated == 0
    assert revisions == []
    rows = _select_rows(pg_clean, "ecos", "722Y001")
    assert len(rows) == 3


def test_upsert_detects_revision(pg_clean):
    from collectors.macro.db_writer import upsert_macro_observations

    d = date(2026, 1, 1)
    upsert_macro_observations(
        pg_clean, source="fred", series_id="DGS10", item_code="",
        label="us_10y", cycle="D",
        observations=[{"date": d, "value": 100.0}],
    )
    inserted, updated, revisions = upsert_macro_observations(
        pg_clean, source="fred", series_id="DGS10", item_code="",
        label="us_10y", cycle="D",
        observations=[{"date": d, "value": 200.0}],
    )
    assert inserted == 0
    assert updated == 1
    assert revisions == [{"obs_date": d.isoformat(), "old": 100.0, "new": 200.0}]

    rows = _select_rows(pg_clean, "fred", "DGS10")
    assert len(rows) == 1
    assert float(rows[0].value) == 200.0


def test_empty_observations_is_noop(pg_clean):
    from collectors.macro.db_writer import upsert_macro_observations

    inserted, updated, revisions = upsert_macro_observations(
        pg_clean, source="ecos", series_id="722Y001", item_code="0101000",
        label="base_rate_kr", cycle="D", observations=[],
    )
    assert (inserted, updated, revisions) == (0, 0, [])
    rows = _select_rows(pg_clean, "ecos", "722Y001")
    assert rows == []


def test_invalid_source_raises(pg_clean):
    from collectors.macro.db_writer import upsert_macro_observations

    with pytest.raises(ValueError):
        upsert_macro_observations(
            pg_clean, source="bogus", series_id="X", item_code="",
            label="x", cycle="D", observations=[],
        )


def test_invalid_series_id_raises(pg_clean):
    from collectors.macro.db_writer import upsert_macro_observations

    # Slash → path-traversal-like injection
    with pytest.raises(ValueError):
        upsert_macro_observations(
            pg_clean, source="ecos", series_id="bad/id", item_code="",
            label="x", cycle="D", observations=[],
        )
    # Lowercase fails the regex
    with pytest.raises(ValueError):
        upsert_macro_observations(
            pg_clean, source="ecos", series_id="lowercase", item_code="",
            label="x", cycle="D", observations=[],
        )


def test_fred_with_empty_item_code(pg_clean):
    """FRED rows use empty-string item_code — PK still satisfied (non-NULL)."""
    from collectors.macro.db_writer import upsert_macro_observations

    obs = [
        {"date": date(2026, 4, 15), "value": 4.28},
        {"date": date(2026, 4, 16), "value": 4.32},
    ]
    inserted, updated, revisions = upsert_macro_observations(
        pg_clean, source="fred", series_id="DGS10", item_code="",
        label="us_10y", cycle="D", observations=obs,
    )
    assert inserted == 2
    assert updated == 0
    assert revisions == []

    rows = _select_rows(pg_clean, "fred", "DGS10")
    assert len(rows) == 2
    assert all(r.item_code == "" for r in rows)


def test_mixed_observations_inserted_and_updated(pg_clean):
    """Pre-seed 2 rows; call with 4 observations: 1 same value (skip), 1
    changed value (update + revision), 2 brand-new (insert)."""
    from collectors.macro.db_writer import upsert_macro_observations

    d1 = date(2026, 1, 1)  # same value
    d2 = date(2026, 1, 2)  # changed value
    d3 = date(2026, 1, 3)  # new
    d4 = date(2026, 1, 4)  # new

    # Pre-seed two rows
    upsert_macro_observations(
        pg_clean, source="ecos", series_id="731Y001", item_code="0000001",
        label="usd_krw", cycle="D",
        observations=[
            {"date": d1, "value": 1330.0},
            {"date": d2, "value": 1335.0},
        ],
    )

    # Second call: 4 observations mixing same/changed/new
    inserted, updated, revisions = upsert_macro_observations(
        pg_clean, source="ecos", series_id="731Y001", item_code="0000001",
        label="usd_krw", cycle="D",
        observations=[
            {"date": d1, "value": 1330.0},  # unchanged → skip
            {"date": d2, "value": 1340.0},  # changed → update + revision
            {"date": d3, "value": 1345.0},  # new → insert
            {"date": d4, "value": 1350.0},  # new → insert
        ],
    )
    assert inserted == 2
    assert updated == 1
    assert revisions == [{"obs_date": d2.isoformat(), "old": 1335.0, "new": 1340.0}]

    rows = _select_rows(pg_clean, "ecos", "731Y001")
    assert len(rows) == 4
    by_date = {r.obs_date: float(r.value) for r in rows}
    assert by_date == {
        d1: 1330.0,
        d2: 1340.0,
        d3: 1345.0,
        d4: 1350.0,
    }
