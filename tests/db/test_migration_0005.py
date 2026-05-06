"""Phase 8 Plan 08-01 Task 3: Alembic 0005 — documents.note_type column."""

from __future__ import annotations

from sqlalchemy import inspect


def test_note_type_column_exists(pg_engine) -> None:
    """0005 adds documents.note_type (Text, nullable) + ix_documents_note_type."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("documents")}
    assert "note_type" in cols, f"note_type column missing; have {list(cols)}"
    assert cols["note_type"]["nullable"] is True

    idx_names = {i["name"] for i in insp.get_indexes("documents")}
    assert "ix_documents_note_type" in idx_names


def test_note_type_backfill_safe_for_empty_db(pg_engine) -> None:
    """Backfill UPDATE is a no-op on an empty documents table — never crashes."""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        # If 0005 had a CHECK constraint failure or invalid SQL, alembic upgrade
        # would have aborted in pg_engine. Reaching here proves upgrade succeeded.
        result = conn.execute(text("SELECT note_type FROM documents LIMIT 1"))
        # Empty result is fine; what matters is the column is queryable.
        list(result)
