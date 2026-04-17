"""Phase 2 initial schema — entities, entity_aliases, documents, chunks, edges, events, ingest_runs.

Implements decisions D-01 through D-16 from
`.planning/phases/02-canonical-entity-identity/02-CONTEXT.md`.

Notes on content_hash (D-13/D-14): `documents.id` is the hex sha256 of the
frontmatter-stripped, normalized body. sha256 is used as a dedup primitive,
NOT an authentication/integrity primitive against active adversaries — see
`src/shared/content_hash.py` module docstring.

Revision ID: 0001
Revises:
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector extension is required for chunks.embedding; the docker-compose
    # image pre-installs via init-extensions.sql, but this keeps the migration
    # self-contained for fresh / test containers.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "entities",
        sa.Column("corp_code", sa.CHAR(8), primary_key=True),
        sa.Column("canonical_name", sa.Text, nullable=False),
        sa.Column("current_ticker", sa.CHAR(6), nullable=True),
        sa.Column("sector", sa.Text, nullable=True),
        sa.Column("market", sa.Text, nullable=True),
        sa.Column("listed_at", sa.Date, nullable=True),
        sa.Column("delisted_at", sa.Date, nullable=True),
        sa.CheckConstraint(
            "market IN ('KOSPI','KOSDAQ','KONEX') OR market IS NULL",
            name="ck_entities_market",
        ),
    )

    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('name','ticker','eng_name')",
            name="ck_alias_kind",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_alias_validity_order",
        ),
        # DELIBERATELY NO UniqueConstraint("kind","value") — Pitfall 5:
        # KRX recycles 6-digit tickers across delisted entities. Enforcing
        # uniqueness here would block legitimate historical alias records.
    )
    op.create_index(
        "ix_alias_lookup",
        "entity_aliases",
        ["kind", "value", "valid_from", "valid_to"],
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.CHAR(64), primary_key=True),  # sha256 hex — D-13
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("vault_path", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),  # initial URL
        sa.Column("source_urls", sa.ARRAY(sa.Text), nullable=True),  # accumulated
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_source", "documents", ["source"])
    op.create_index("ix_documents_vault_path", "documents", ["vault_path"], unique=True)

    # Skeleton chunks table — Phase 3 adds HNSW index + bm25_tokens column population.
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            sa.CHAR(64),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding_model", sa.Text, nullable=True),  # populated by Phase 3
    )
    # Embedding column added via raw SQL to use pgvector type (declared, not indexed in Phase 2).
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1024)")
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])

    op.create_table(
        "edges",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("src_type", sa.Text, nullable=False),
        sa.Column("src_id", sa.Text, nullable=False),
        sa.Column("dst_type", sa.Text, nullable=False),
        sa.Column("dst_id", sa.Text, nullable=False),
        sa.Column("edge_type", sa.Text, nullable=False),
        sa.Column("tag", sa.Text, nullable=True),  # EXTRACTED|INFERRED|AMBIGUOUS — Phase 7
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "src_type",
            "src_id",
            "dst_type",
            "dst_id",
            "edge_type",
            name="uq_edge_endpoints",
        ),
        sa.CheckConstraint(
            "edge_type IN ('supersedes')",  # Phase 2 only; relax in Phase 7
            name="ck_edge_type_phase2",
        ),
    )
    op.create_index("ix_edges_src", "edges", ["src_type", "src_id"])
    op.create_index("ix_edges_dst", "edges", ["dst_type", "dst_id"])
    op.create_index("ix_edges_type", "edges", ["edge_type"])

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            sa.CHAR(64),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_events_corp_code_time", "events", ["corp_code", "occurred_at"])

    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("stats", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
    )


def downgrade() -> None:
    # Drop in reverse FK order. Do NOT drop the `vector` extension — other
    # data (or parallel schemas) may depend on it.
    for tbl in (
        "ingest_runs",
        "events",
        "edges",
        "chunks",
        "documents",
        "entity_aliases",
        "entities",
    ):
        op.drop_table(tbl)
