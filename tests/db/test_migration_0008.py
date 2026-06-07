"""Phase 3 Plan 03-01 Task 3 — schema-shape regression for migration 0008.

Introspects the live Postgres testcontainer (already at head per the session
``pg_engine`` fixture, which runs ``alembic upgrade head`` → applies 0008) to
confirm the Wave-0 MCP read-side infrastructure:

* ``notes`` + ``fundamentals`` tables exist with the locked column shapes.
* ``filings``/``news``/``notes`` carry ``bm25_tokens INT[]`` + a VectorChord-BM25
  index AND an HNSW index on the halfvec embedding column.
* ``fundamentals`` has NO embedding column (Hard Veto #6).
* ``notes.content_md`` is whole TEXT (Hard Veto #8 — no chunking column).
* the ``collector_runs.source`` CHECK is widened to the 7-source set AND
  ``record_collector_run`` accepts ``fundamentals``/``notes_ingest`` while still
  rejecting a disallowed source (proves the CHECK + ``_ALLOWED_SOURCES`` agree
  against the real schema).

All tests are ``db``-marked (live Postgres required).

Coverage map:
* test_orm_round_trip              — ORM↔DB parity + 9-table metadata set (notes, fundamentals)
* test_indexes_present            — BM25 + HNSW indexes on filings/news/notes
* test_fundamentals_no_embedding  — Veto #6 (no halfvec column on fundamentals)
* test_collector_runs_source_check— widened CHECK + run_log allow-list, both directions
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# ORM ↔ DB parity + full metadata table set (now includes notes, fundamentals)
# ---------------------------------------------------------------------------


def test_orm_round_trip(pg_engine) -> None:
    """Every ORM model's declared columns match the live DB column set.

    Drift guard between migration 0006/0007/0008 (DDL authors) and
    ``src/db/entity_models.py``. The metadata table set is now nine tables
    including ``notes`` and ``fundamentals``.
    """
    from db.entity_models import (
        OHLCV,
        Base,
        CollectorRun,
        DecisionCard,
        Event,
        Filing,
        Fundamentals,
        MacroSeries,
        News,
        Note,
    )

    insp = inspect(pg_engine)
    models = (
        Filing,
        News,
        OHLCV,
        MacroSeries,
        Event,
        CollectorRun,
        DecisionCard,
        Note,
        Fundamentals,
    )
    for model in models:
        table_name = model.__tablename__
        db_cols = {c["name"] for c in insp.get_columns(table_name)}
        orm_cols = {c.name for c in model.__table__.columns}
        missing = orm_cols - db_cols
        extra = db_cols - orm_cols
        assert not missing, f"{table_name}: ORM declares columns absent from DB: {sorted(missing)}"
        assert not extra, f"{table_name}: DB has columns not declared in ORM: {sorted(extra)}"

    # bm25_tokens column landed on all three narrative tables.
    for tbl in ("filings", "news", "notes"):
        cols = {c["name"] for c in insp.get_columns(tbl)}
        assert "bm25_tokens" in cols, f"{tbl} missing bm25_tokens"

    # notes carries whole-text content_md + the halfvec embedding column (Veto #8).
    note_cols = {c["name"] for c in insp.get_columns("notes")}
    assert "content_md" in note_cols
    assert "content_emb" in note_cols
    # No chunk-shaped column on notes (Veto #8 — whole memo, no pre-chunking).
    for forbidden in ("chunk_index", "chunk_text", "section_index", "section_path"):
        assert forbidden not in note_cols, f"notes must not carry {forbidden!r} (Veto #8)"

    # Base.metadata table set matches the nine v2.0 ORM tables.
    assert set(Base.metadata.tables) == {
        "filings",
        "news",
        "ohlcv",
        "macro_series",
        "events",
        "collector_runs",
        "decision_cards",
        "notes",
        "fundamentals",
    }


# ---------------------------------------------------------------------------
# BM25 + HNSW indexes on the narrative tables
# ---------------------------------------------------------------------------


def test_indexes_present(pg_engine) -> None:
    """VectorChord-BM25 + HNSW indexes exist on filings/news/notes."""
    expected = {
        "ix_filings_bm25": ("filings", "bm25"),
        "ix_news_bm25": ("news", "bm25"),
        "ix_notes_bm25": ("notes", "bm25"),
        "ix_filings_embedding_hnsw": ("filings", "hnsw"),
        "ix_news_embedding_hnsw": ("news", "hnsw"),
        "ix_notes_content_emb_hnsw": ("notes", "hnsw"),
    }
    with pg_engine.connect() as conn:
        for idx_name, (table, method) in expected.items():
            idxdef = conn.execute(
                sa.text("SELECT indexdef FROM pg_indexes WHERE tablename = :t AND indexname = :i"),
                {"t": table, "i": idx_name},
            ).scalar()
            assert idxdef is not None, f"{idx_name} missing on {table}"
            assert f"USING {method}" in idxdef, f"{idx_name} is not a {method} index: {idxdef}"

    # The BM25 expression indexes use the bm25_catalog opclass on bm25_tokens.
    with pg_engine.connect() as conn:
        filings_bm25 = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'filings' AND indexname = 'ix_filings_bm25'"
            )
        ).scalar()
    assert "bm25_tokens" in filings_bm25, filings_bm25
    assert "bm25_ops" in filings_bm25, filings_bm25


# ---------------------------------------------------------------------------
# Veto #6 — fundamentals has NO embedding column
# ---------------------------------------------------------------------------


def test_fundamentals_no_embedding(pg_engine) -> None:
    """fundamentals is pure-numeric: no halfvec / embedding column (Veto #6)."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("fundamentals")}

    # Locked numeric/key columns present.
    for name in ("ticker", "fdate", "per", "pbr", "eps", "bps", "roe", "source"):
        assert name in cols, f"fundamentals missing {name!r}; have {sorted(cols)}"

    # PK is (ticker, fdate).
    pk = insp.get_pk_constraint("fundamentals")
    assert pk["constrained_columns"] == ["ticker", "fdate"], pk

    # No embedding-shaped column at all.
    for c in cols:
        assert "emb" not in c.lower(), (
            f"fundamentals must not carry embedding column {c!r} (Veto #6)"
        )

    # Confirm at the catalog level no column is a halfvec type.
    with pg_engine.connect() as conn:
        halfvec_cols = conn.execute(
            sa.text(
                "SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS typ "
                "FROM pg_attribute a "
                "WHERE a.attrelid = 'fundamentals'::regclass "
                "  AND a.attnum > 0 AND NOT a.attisdropped"
            )
        ).all()
    for name, typ in halfvec_cols:
        assert "halfvec" not in typ and "vector" not in typ, (
            f"fundamentals.{name} is {typ!r} — Veto #6 forbids embeddings on numeric tables"
        )


# ---------------------------------------------------------------------------
# collector_runs.source CHECK widened to 7 sources + run_log allow-list parity
# ---------------------------------------------------------------------------


def test_collector_runs_source_check(seeded_engine) -> None:
    """The widened CHECK + run_log._ALLOWED_SOURCES both accept fundamentals/
    notes_ingest and both reject a disallowed source — proven against the real
    applied schema (migration 0008).
    """
    from shared.run_log import _ALLOWED_SOURCES, record_collector_run

    engine = seeded_engine

    # run_log allow-list is exactly the 7-source set.
    assert {
        "dart",
        "krx",
        "news",
        "macro",
        "kind",
        "fundamentals",
        "notes_ingest",
    } == _ALLOWED_SOURCES

    # The DB CHECK constraint enumerates both new sources.
    with engine.connect() as conn:
        ck = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE c.conrelid = 'collector_runs'::regclass "
                "  AND c.contype = 'c' "
                "  AND c.conname = 'ck_collector_runs_source'"
            )
        ).scalar()
    assert ck is not None, "ck_collector_runs_source missing"
    for value in ("fundamentals", "notes_ingest"):
        assert value in ck, f"missing {value!r} in widened CHECK: {ck}"

    # Both new sources INSERT a real collector_runs row (no exception, CHECK passes).
    for src in ("fundamentals", "notes_ingest"):
        row_id = record_collector_run(
            engine,
            src,
            {"total": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": []},
            elapsed_ms=1,
        )
        assert row_id is not None, f"record_collector_run({src!r}) did not insert"

    # Both rows are present in the table.
    with engine.connect() as conn:
        n = conn.execute(
            sa.text(
                "SELECT count(*) FROM collector_runs "
                "WHERE source IN ('fundamentals','notes_ingest')"
            )
        ).scalar()
    assert n == 2, f"expected 2 new collector_runs rows, got {n}"

    # A disallowed source still raises at the Python-side gate (fails fast before DB).
    with pytest.raises(ValueError):
        record_collector_run(engine, "bogus", {"total": 0}, elapsed_ms=1)

    # And the DB CHECK itself rejects a disallowed source on a direct INSERT.
    _bogus_insert = sa.text(
        "INSERT INTO collector_runs (source, elapsed_ms, stats) "
        "VALUES ('bogus', 1, CAST('{}' AS jsonb))"
    )
    with pytest.raises(Exception), engine.begin() as conn:  # noqa: B017,PT011 — CHECK violation
        conn.execute(_bogus_insert)
