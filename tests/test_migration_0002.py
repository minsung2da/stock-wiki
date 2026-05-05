"""Phase 3 migration 0002 integration tests.

Verifies via information_schema.columns + pg_indexes that migration 0002:
  - adds chunks.section_path (text, nullable), chunks.section_index (int, nullable),
    chunks.bm25_tokens (ARRAY of int4, nullable)
  - adds documents.corp_code (char(8), nullable) with btree index ix_documents_corp_code
  - creates HNSW index ix_chunks_embedding_hnsw on chunks USING hnsw (embedding vector_cosine_ops)
  - creates BM25 index ix_chunks_bm25 on chunks USING bm25 (bm25_tokens bm25_catalog.bm25_ops)
  - downgrade -1 removes everything and upgrade head restores it
  - connection can SET hnsw.iterative_scan = 'relaxed_order' (D-13 session GUC)
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_section_columns_exist(pg_engine):
    with pg_engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'chunks'
                  AND column_name IN ('section_path', 'section_index', 'bm25_tokens')
                ORDER BY column_name
                """
            )
        ).all()
    by_name = {r.column_name: r for r in rows}
    assert "section_path" in by_name
    assert by_name["section_path"].data_type == "text"
    assert by_name["section_path"].is_nullable == "YES"
    assert "section_index" in by_name
    assert by_name["section_index"].data_type == "integer"
    assert by_name["section_index"].is_nullable == "YES"
    assert "bm25_tokens" in by_name
    assert by_name["bm25_tokens"].data_type == "ARRAY"
    assert by_name["bm25_tokens"].is_nullable == "YES"
    # Confirm element type is int4.
    with pg_engine.connect() as conn:
        udt = conn.execute(
            sa.text(
                """
                SELECT udt_name FROM information_schema.columns
                WHERE table_name='chunks' AND column_name='bm25_tokens'
                """
            )
        ).scalar()
    assert udt == "_int4"


def test_documents_corp_code_column_exists(pg_engine):
    with pg_engine.connect() as conn:
        col = conn.execute(
            sa.text(
                """
                SELECT data_type, character_maximum_length, is_nullable
                FROM information_schema.columns
                WHERE table_name='documents' AND column_name='corp_code'
                """
            )
        ).one()
        assert col.data_type == "character"
        assert col.character_maximum_length == 8
        assert col.is_nullable == "YES"
        idx = conn.execute(
            sa.text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE indexname='ix_documents_corp_code' AND tablename='documents'
                """
            )
        ).scalar()
        assert idx is not None
        assert "corp_code" in idx
        # btree is Postgres default; indexdef for a plain index omits "USING btree"
        # on some versions but usually includes it — accept either.
        assert "btree" in idx.lower() or "USING" not in idx.upper()


def test_hnsw_index_exists(pg_engine):
    with pg_engine.connect() as conn:
        idx = conn.execute(
            sa.text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE tablename='chunks' AND indexname='ix_chunks_embedding_hnsw'
                """
            )
        ).scalar()
    assert idx is not None
    assert "hnsw" in idx.lower()
    assert "embedding" in idx
    assert "vector_cosine_ops" in idx


def test_bm25_index_exists(pg_engine):
    with pg_engine.connect() as conn:
        idx = conn.execute(
            sa.text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE tablename='chunks' AND indexname='ix_chunks_bm25'
                """
            )
        ).scalar()
    assert idx is not None
    assert "bm25" in idx.lower()
    assert "bm25_tokens" in idx
    assert "bm25_ops" in idx


def test_iterative_scan_session_setting(pg_engine):
    """D-13: per-session GUC `hnsw.iterative_scan = 'relaxed_order'` is accepted."""
    with pg_engine.connect() as conn:
        conn.execute(sa.text("SET hnsw.iterative_scan = 'relaxed_order'"))
        current = conn.execute(sa.text("SHOW hnsw.iterative_scan")).scalar()
    assert current == "relaxed_order"


def test_downgrade_reverses_migration(pg_engine):
    """alembic downgrade -1 removes the three columns + indexes; upgrade head restores.

    Wrapped in try/finally so the session-scoped engine is always left at head.
    """
    url = os.environ["DATABASE_URL"]
    cfg = Config("src/db/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    def _column_names(conn, table: str) -> set[str]:
        rows = conn.execute(
            sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {"t": table},
        ).all()
        return {r[0] for r in rows}

    def _index_names(conn, table: str) -> set[str]:
        rows = conn.execute(
            sa.text("SELECT indexname FROM pg_indexes WHERE tablename = :t"),
            {"t": table},
        ).all()
        return {r[0] for r in rows}

    try:
        # Migration history evolved past 0002, so use the absolute revision target
        # (0001) instead of "-1", which now only reverses the most recent migration.
        command.downgrade(cfg, "0001")
        with pg_engine.connect() as conn:
            chunk_cols = _column_names(conn, "chunks")
            doc_cols = _column_names(conn, "documents")
            chunk_idx = _index_names(conn, "chunks")
            doc_idx = _index_names(conn, "documents")
        assert "section_path" not in chunk_cols
        assert "section_index" not in chunk_cols
        assert "bm25_tokens" not in chunk_cols
        assert "corp_code" not in doc_cols
        assert "ix_chunks_embedding_hnsw" not in chunk_idx
        assert "ix_chunks_bm25" not in chunk_idx
        assert "ix_documents_corp_code" not in doc_idx

        command.upgrade(cfg, "head")
        with pg_engine.connect() as conn:
            chunk_cols = _column_names(conn, "chunks")
            doc_cols = _column_names(conn, "documents")
            chunk_idx = _index_names(conn, "chunks")
            doc_idx = _index_names(conn, "documents")
        assert {"section_path", "section_index", "bm25_tokens"} <= chunk_cols
        assert "corp_code" in doc_cols
        assert {"ix_chunks_embedding_hnsw", "ix_chunks_bm25"} <= chunk_idx
        assert "ix_documents_corp_code" in doc_idx
    finally:
        command.upgrade(cfg, "head")
