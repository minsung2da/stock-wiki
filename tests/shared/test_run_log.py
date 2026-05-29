"""Tests for ``shared.run_log.record_collector_run`` (Plan 01-08 Task 1).

The helper is the single sink behind every collector's ``collector_runs`` row.
Best-effort semantics: DB write failure logs a WARNING and returns None,
NEVER raises. The collect run keeps going.

These tests run against the session-scoped pg_engine testcontainer; the
``collector_runs`` table is present after migration 0006 (Plan 01-01).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from shared.run_log import record_collector_run


def test_record_run_inserts_row(pg_clean: Engine) -> None:
    """Single happy-path INSERT returns positive id and lands a row."""
    stats: dict[str, Any] = {
        "total": 4,
        "inserted": 3,
        "updated": 1,
        "skipped": 0,
        "failed": [],
    }
    row_id = record_collector_run(
        pg_clean, "dart", stats, elapsed_ms=1234, extra=None
    )
    assert isinstance(row_id, int) and row_id > 0

    with pg_clean.begin() as conn:
        row = conn.execute(
            sa.text(
                "SELECT source, elapsed_ms FROM collector_runs WHERE id=:id"
            ),
            {"id": row_id},
        ).one()
    assert row.source == "dart"
    assert row.elapsed_ms == 1234


def test_record_run_stats_jsonb_query(pg_clean: Engine) -> None:
    """JSONB stats column is queryable with ``->`` and ``->>`` operators."""
    record_collector_run(
        pg_clean,
        "krx",
        {"total": 5, "inserted": 3, "updated": 0, "skipped": 2, "failed": []},
        elapsed_ms=800,
    )

    with pg_clean.begin() as conn:
        inserted_str = conn.execute(
            sa.text("SELECT stats->>'inserted' FROM collector_runs LIMIT 1")
        ).scalar()
    assert inserted_str == "3"


def test_record_run_extra_null_omitted(pg_clean: Engine) -> None:
    """extra=None lands as SQL NULL in the extra column."""
    record_collector_run(
        pg_clean,
        "news",
        {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": []},
        elapsed_ms=10,
        extra=None,
    )

    with pg_clean.begin() as conn:
        extra_val = conn.execute(
            sa.text("SELECT extra FROM collector_runs LIMIT 1")
        ).scalar()
    assert extra_val is None


def test_record_run_extra_nested_dict(pg_clean: Engine) -> None:
    """Nested extra dict round-trips and is JSONB-queryable."""
    extra = {"dart_events": {"docs_processed": 5, "status": "ok"}}
    record_collector_run(
        pg_clean,
        "kind",
        {"total": 5, "inserted": 5, "updated": 0, "skipped": 0, "failed": []},
        elapsed_ms=400,
        extra=extra,
    )

    with pg_clean.begin() as conn:
        docs_processed_str = conn.execute(
            sa.text(
                "SELECT extra->'dart_events'->>'docs_processed' "
                "FROM collector_runs LIMIT 1"
            )
        ).scalar()
    assert docs_processed_str == "5"


def test_record_run_engine_none_returns_none() -> None:
    """engine=None is a no-op (returns None, no exception)."""
    result = record_collector_run(
        None,  # type: ignore[arg-type]
        "macro",
        {"total": 1, "inserted": 1, "updated": 0, "skipped": 0, "failed": []},
        elapsed_ms=42,
    )
    assert result is None


def test_record_run_unknown_source_raises() -> None:
    """Unknown source name is a programmer error → ValueError."""
    with pytest.raises(ValueError):
        record_collector_run(
            None,  # type: ignore[arg-type]
            "bogus",
            {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": []},
            elapsed_ms=1,
        )


def test_record_run_db_failure_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DB outage during INSERT degrades to a WARNING log; returns None.

    The collect run NEVER fails because of an observability write
    (RESEARCH.md Q5 — ops dashboard goes blind, not data loss).
    """

    class _FailingEngine:
        def begin(self) -> Any:
            raise RuntimeError("simulated DB outage")

    caplog.set_level(logging.WARNING, logger="shared.run_log")
    result = record_collector_run(
        _FailingEngine(),  # type: ignore[arg-type]
        "dart",
        {"total": 1, "inserted": 1, "updated": 0, "skipped": 0, "failed": []},
        elapsed_ms=99,
    )
    assert result is None
    assert any(
        "collector_runs INSERT failed" in rec.getMessage()
        for rec in caplog.records
    )


def test_record_run_non_json_serializable_values_coerced(
    pg_clean: Engine,
) -> None:
    """Non-JSON-serializable values (e.g., Path) are coerced via default=str."""
    stats = {
        "total": 1,
        "inserted": 1,
        "updated": 0,
        "skipped": 0,
        "failed": [],
        "path": Path("/tmp/x"),  # noqa: S108 — test fixture only
    }
    row_id = record_collector_run(pg_clean, "macro", stats, elapsed_ms=5)
    assert row_id is not None

    with pg_clean.begin() as conn:
        path_str = conn.execute(
            sa.text("SELECT stats->>'path' FROM collector_runs LIMIT 1")
        ).scalar()
    # default=str coerces Path -> its str repr; we just verify no crash and a non-empty string.
    assert isinstance(path_str, str) and path_str
