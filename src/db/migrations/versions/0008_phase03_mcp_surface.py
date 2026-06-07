"""Phase 3 — MCP read-side surface infrastructure.

Wave-0 schema for the entire Phase 3 MCP tool surface. This is the SINGLE
migration-side owner of:

  * the ``notes`` table (D-05 — user thesis memos searchable via hybrid_search),
  * the ``fundamentals`` table (D-06 — peer_view same-sector median PER/PBR/ROE),
  * the ``bm25_tokens INT[]`` columns + VectorChord-BM25 indexes on the narrative
    tables (filings/news/notes),
  * the HNSW indexes on the existing ``halfvec(1024)`` embedding columns, and
  * the deterministic widening of the ``collector_runs.source`` CHECK to the full
    7-source set (so the notes-ingest + fundamentals collectors of Plans 02/05 can
    ``record_collector_run``).

Hard Veto reminders baked into this schema:

  * Veto #6 — ``fundamentals`` is PURE NUMERIC typed columns (per/pbr/eps/bps/roe).
    It has NO embedding column. Numbers are never embedded.
  * Veto #8 — ``notes.content_md`` is whole-memo TEXT. No chunking column; the
    hybrid candidate is one whole note row, exactly like filings/news.

VectorChord-BM25 / HNSW SQL
---------------------------
Ports the image-tested SQL from archive migration 0002
(``0002_phase03_chunking_columns.py``) which was verified against the SAME
``tensorchord/vchord-suite:pg17-latest`` image. Two adaptations:

  * ``bm25_tokens INT[]`` is added via raw ``op.execute`` so vchord_bm25's implicit
    cast to ``bm25vector`` (via ``bm25_catalog._vchord_bm25_cast_array_to_bm25vector``)
    stays intact (a SQLAlchemy ARRAY roundtrip would drop it).
  * Archive 0002 used the plain ``vector`` cosine opclass on a ``vector(1024)``
    column. The Phase 1 narrative columns are ``halfvec(1024)`` (migration 0006),
    so the HNSW indexes here use ``halfvec_cosine_ops`` instead.

The ``body_tsv`` columns on filings/news already exist (migration 0006) and are the
SC#6 ``'simple'`` fallback path only — never ``'korean'`` (PG17 has no korean
tsearch config; RESEARCH Pitfall 1). Korean morphology is the Python mecab-ko →
VectorChord-BM25 path. This migration adds no new tsvector generated columns.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


# The full 7-source set the widened collector_runs.source CHECK enumerates.
# run_log._ALLOWED_SOURCES mirrors this exact set (single owner — both edits live
# in Plan 03-01). Plans 02/05 only CALL record_collector_run against it.
_ALLOWED_SOURCES_SQL = (
    "source IN ('dart','krx','news','macro','kind','fundamentals','notes_ingest')"
)
# The original 5-source CHECK from migration 0006 (restored on downgrade).
_ORIGINAL_SOURCES_SQL = "source IN ('dart','krx','news','macro','kind')"


def upgrade() -> None:
    # (a) vchord_bm25 extension — idempotent; docker-compose installs it on first
    # boot via scripts/init-extensions.sql, but testcontainers bypass that entry
    # point so keep this migration self-contained.
    op.execute("CREATE EXTENSION IF NOT EXISTS vchord_bm25")

    # (b) notes — user thesis memos (D-05). Veto #8: whole content_md TEXT, no
    # chunking. content_emb (halfvec) + bm25_tokens (INT[]) added via raw SQL below.
    op.create_table(
        "notes",
        sa.Column("path", sa.Text, primary_key=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_tsv", postgresql.TSVECTOR, nullable=True),
    )
    # halfvec + INT[] columns via raw SQL (no SQLAlchemy halfvec type; raw INT[]
    # preserves the implicit bm25vector cast).
    op.execute("ALTER TABLE notes ADD COLUMN content_emb halfvec(1024)")
    op.execute("ALTER TABLE notes ADD COLUMN bm25_tokens INT[] NULL")
    op.create_index(
        "ix_notes_corp",
        "notes",
        ["corp_code"],
        postgresql_where=sa.text("corp_code IS NOT NULL"),
    )

    # (c) fundamentals — Veto #6 PURE NUMERIC, NO embedding column. PER/PBR/EPS/BPS
    # from pykrx (Plan 05); ROE from dart-fss 재무제표. PK (ticker, fdate).
    op.create_table(
        "fundamentals",
        sa.Column("ticker", sa.CHAR(6), nullable=False),
        sa.Column("fdate", sa.Date, nullable=False),
        sa.Column("per", sa.Numeric(18, 4), nullable=True),
        sa.Column("pbr", sa.Numeric(18, 4), nullable=True),
        sa.Column("eps", sa.Numeric(20, 4), nullable=True),
        sa.Column("bps", sa.Numeric(20, 4), nullable=True),
        sa.Column("roe", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticker", "fdate", name="pk_fundamentals"),
    )
    op.create_index(
        "ix_fundamentals_corp",
        "fundamentals",
        ["corp_code"],
        postgresql_where=sa.text("corp_code IS NOT NULL"),
    )

    # (d) bm25_tokens INT[] on the existing narrative tables. Raw SQL keeps the
    # implicit bm25vector cast (see archive 0002).
    op.execute("ALTER TABLE filings ADD COLUMN bm25_tokens INT[] NULL")
    op.execute("ALTER TABLE news ADD COLUMN bm25_tokens INT[] NULL")

    # (e) VectorChord-BM25 indexes, one per narrative table. Expression index over
    # ((bm25_tokens)::bm25_catalog.bm25vector) with bm25_catalog.bm25_ops — the
    # exact API archive 0002 tested against this image.
    op.execute(
        "CREATE INDEX ix_filings_bm25 ON filings USING bm25 "
        "(((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)"
    )
    op.execute(
        "CREATE INDEX ix_news_bm25 ON news USING bm25 "
        "(((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)"
    )
    op.execute(
        "CREATE INDEX ix_notes_bm25 ON notes USING bm25 "
        "(((bm25_tokens)::bm25_catalog.bm25vector) bm25_catalog.bm25_ops)"
    )

    # (f) HNSW indexes on the halfvec embedding columns — halfvec_cosine_ops (the
    # halfvec opclass; the columns are halfvec(1024), not the plain vector type).
    op.execute(
        "CREATE INDEX ix_filings_embedding_hnsw ON filings "
        "USING hnsw (body_embedding halfvec_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_news_embedding_hnsw ON news USING hnsw (body_embedding halfvec_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_notes_content_emb_hnsw ON notes "
        "USING hnsw (content_emb halfvec_cosine_ops)"
    )

    # (g) Deterministically widen collector_runs.source CHECK to the 7-source set.
    # DROP the named constraint from migration 0006, then ADD the widened one. No
    # runtime \d discovery — the constraint name (ck_collector_runs_source) and the
    # source literal are both fixed.
    op.execute("ALTER TABLE collector_runs DROP CONSTRAINT ck_collector_runs_source")
    op.execute(
        "ALTER TABLE collector_runs ADD CONSTRAINT ck_collector_runs_source "
        f"CHECK ({_ALLOWED_SOURCES_SQL})"
    )


def downgrade() -> None:
    # Reverse (g): restore the original 5-source CHECK.
    op.execute("ALTER TABLE collector_runs DROP CONSTRAINT ck_collector_runs_source")
    op.execute(
        "ALTER TABLE collector_runs ADD CONSTRAINT ck_collector_runs_source "
        f"CHECK ({_ORIGINAL_SOURCES_SQL})"
    )

    # Reverse (f) HNSW indexes.
    op.execute("DROP INDEX IF EXISTS ix_notes_content_emb_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_news_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_filings_embedding_hnsw")

    # Reverse (e) BM25 indexes.
    op.execute("DROP INDEX IF EXISTS ix_notes_bm25")
    op.execute("DROP INDEX IF EXISTS ix_news_bm25")
    op.execute("DROP INDEX IF EXISTS ix_filings_bm25")

    # Reverse (d) bm25_tokens columns on filings/news.
    op.execute("ALTER TABLE news DROP COLUMN IF EXISTS bm25_tokens")
    op.execute("ALTER TABLE filings DROP COLUMN IF EXISTS bm25_tokens")

    # Reverse (c) fundamentals.
    op.drop_index("ix_fundamentals_corp", table_name="fundamentals")
    op.drop_table("fundamentals")

    # Reverse (b) notes (content_emb + bm25_tokens dropped with the table).
    op.drop_index("ix_notes_corp", table_name="notes")
    op.drop_table("notes")
