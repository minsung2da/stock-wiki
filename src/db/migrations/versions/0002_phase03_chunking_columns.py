"""Phase 3 chunks schema extension.

Adds section_path / section_index / bm25_tokens to chunks,
documents.corp_code, and HNSW + VectorChord-BM25 indexes.

Source decisions:
- D-08 (03-CONTEXT.md): adds `section_path TEXT NULL`, `section_index INT NULL` to chunks
- STORE-03: HNSW index over `chunks.embedding` with `vector_cosine_ops`
- STORE-04: VectorChord-BM25 index over `chunks.bm25_tokens` with `bm25_catalog.bm25_ops`
- RET-02: adds `documents.corp_code CHAR(8) NULL` + btree index `ix_documents_corp_code`
  (Plan 05 hybrid_search filters documents.corp_code = :corp_code directly; Plan 04
  worker populates it from fm.provenance.corp_code.)

Note on `hnsw.iterative_scan`: this is a *session GUC* (per-connection setting),
not an index-time parameter. Query-time code must `SET hnsw.iterative_scan =
'relaxed_order'` per session (D-13) to get the pgvector 0.8 filtered-scan
recall fix — this migration only creates the index shape.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # vchord_bm25 + pg_trgm extensions are pre-installed in the
    # tensorchord/vchord-suite image but must be CREATE EXTENSION'd per
    # database. docker-compose runs scripts/init-extensions.sql on first
    # boot; keep this migration self-contained for test containers that
    # bypass the init-entrypoint (testcontainers).
    op.execute("CREATE EXTENSION IF NOT EXISTS vchord_bm25")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # D-08: section-aware chunking columns.
    op.add_column("chunks", sa.Column("section_path", sa.Text, nullable=True))
    op.add_column("chunks", sa.Column("section_index", sa.Integer, nullable=True))

    # bm25_tokens INT[]: raw SQL avoids SQLAlchemy ARRAY roundtrip so
    # vchord_bm25's implicit cast to bm25vector (via
    # bm25_catalog._vchord_bm25_cast_array_to_bm25vector) stays intact.
    op.execute("ALTER TABLE chunks ADD COLUMN bm25_tokens INT[] NULL")

    # RET-02: documents.corp_code filter column + index. Enables Plan 05
    # hybrid_search `WHERE documents.corp_code = :corp_code` without a JSONB
    # probe. btree is selective for single-ticker queries.
    op.add_column("documents", sa.Column("corp_code", sa.CHAR(8), nullable=True))
    op.create_index("ix_documents_corp_code", "documents", ["corp_code"])

    # STORE-03: HNSW on chunks.embedding with cosine distance.
    # Uses pgvector defaults (m=16, ef_construction=64) — sufficient at Phase 3 scale.
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # STORE-04: VectorChord-BM25 index on pre-tokenized INT[] array.
    # bm25_ops operates on `bm25vector` — use the implicit cast (pg_cast entry
    # integer[] -> bm25vector via bm25_catalog._vchord_bm25_cast_array_to_bm25vector).
    # Expression index: ((bm25_tokens)::bm25vector).
    op.execute(
        "CREATE INDEX ix_chunks_bm25 ON chunks USING bm25 "
        "(((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)"
    )


def downgrade() -> None:
    # Reverse order: indexes first, then columns.
    op.execute("DROP INDEX IF EXISTS ix_chunks_bm25")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index("ix_documents_corp_code", table_name="documents")
    op.drop_column("documents", "corp_code")
    op.drop_column("chunks", "bm25_tokens")
    op.drop_column("chunks", "section_index")
    op.drop_column("chunks", "section_path")
