"""Phase 2 — decision_cards: canonical storage for v2.0 analysis output.

``decision_cards`` is the single canonical table every downstream v2.0 consumer
targets: Phase 3 MCP ``get_decision_card``/``get_briefing`` reads, Phase 4
``analyze_ticker`` writes, Phase 5 briefing rows. The schema is locked to
ROADMAP SC#1/#2/#6 and ``.planning/research/redesign-2026-05.md`` §3 — the 12
top-level columns below MUST NOT be added to or reshaped by later phases without
an explicit ALTER migration (Phase 5 adds ``report_type`` etc. via its own
migration; Phase 4 may add ``body_embedding`` via ALTER if narrative semantic
search over cards is ever required).

Hard Veto reminders baked into this schema:

  * Veto #2 — ``expires_at`` is NOT NULL with NO server_default. Every card is a
    timed thesis; an untimed thesis is rejected at the Pydantic layer (later
    plan) and cannot be NULL at the DB layer.
  * Veto #3 — contradictions are first-class output, carried structured inside
    ``payload`` JSONB (NOT buried in ``body_md`` Markdown).
  * Veto #6 — no numeric prediction columns; ``payload`` is the JSONB evidence
    bundle, ``body_md`` is the human-render narrative. Decimal/price fields live
    under ``payload->'decision'`` per the CONTEXT pure-JSONB lock.
  * Veto #8 — ``body_md`` is whole-card TEXT; chunking (if ever needed) goes in a
    sibling table, never pre-chunked here.

GENERATED tsvector column choice
--------------------------------
SC#6 requires a fallback full-text search column. We declare ``body_tsv`` as a
``GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body_md, ''))) STORED``
column so the DB auto-computes it on every INSERT/UPDATE — the app layer only
ever writes ``body_md``, and any external SQL writer stays correct too. We use
the raw ``op.execute("ALTER TABLE ... ADD COLUMN ...")`` technique 0006 uses for
its halfvec columns (SQLAlchemy 2.0 has no clean inline GENERATED idiom matching
this style), but the column is a tsvector, NOT halfvec — decision_cards has no
embedding column (CONTEXT lock).

The tsearch config is ``'simple'``, NOT ``'korean'``: PostgreSQL 17 ships no
Korean text-search configuration and ``scripts/init-extensions.sql`` installs
only ``vector`` / ``vchord_bm25`` / ``pg_trgm`` — ``to_tsvector('korean', ...)``
hard-fails at migration time (RESEARCH Pitfall #1). Korean morphological
tokenization happens in Python (mecab-ko → VectorChord-BM25); SC#6 is an
explicit *fallback* path, so ``'simple'`` is acceptable.

Self-referential FK choice
--------------------------
``supersedes`` and ``superseded_by`` are single-column self-referential FKs to
``decision_cards.card_id`` with ``ondelete="SET NULL"``. Single-column self-ref
FKs declared inline in ``create_table`` work fine — Postgres creates the table
then the FK in the same DDL; no ``use_alter`` is needed (that is only for
circular FKs between two tables or composite-PK self-refs — RESEARCH Pitfall #5).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # decision_cards — canonical v2.0 analysis-output storage.
    #
    # Column set is locked to ROADMAP SC#1 (12 top-level columns) + the GENERATED
    # body_tsv (SC#6). generated_at / as_of / expires_at carry NO server_default:
    # they are data-meaningful timestamps set by the card author (RESEARCH OQ-2),
    # in contrast to 0006's bookkeeping fetched_at/*_seen_at which default to now().
    op.create_table(
        "decision_cards",
        sa.Column("card_id", sa.Text, primary_key=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.CHAR(6), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("body_md", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "supersedes",
            sa.Text,
            sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "superseded_by",
            sa.Text,
            sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "schema_version",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.CheckConstraint(
            "status IN ('active','superseded','invalidated')",
            name="ck_decision_cards_status",
        ),
    )

    # GENERATED tsvector column added via raw SQL (mirrors 0006's
    # ALTER-TABLE-after-create habit for special column types). Use 'simple' —
    # 'korean' does NOT exist in PG17 and HARD-FAILS the migration (Pitfall #1).
    op.execute(
        "ALTER TABLE decision_cards ADD COLUMN body_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(body_md, ''))) STORED"
    )

    # SC#2 mandatory indexes — composite ordered generated_at DESC for "latest
    # active card per corp" lookups; single-column indexes on the supersession
    # pointer and the expiry sweep column.
    op.create_index(
        "ix_decision_cards_corp_status_gen",
        "decision_cards",
        ["corp_code", "status", sa.text("generated_at DESC")],
    )
    op.create_index(
        "ix_decision_cards_supersedes",
        "decision_cards",
        ["supersedes"],
    )
    op.create_index(
        "ix_decision_cards_expires",
        "decision_cards",
        ["expires_at"],
    )

    # SC#6 GIN index over the GENERATED body_tsv column for fallback FTS.
    op.create_index(
        "ix_decision_cards_body_tsv",
        "decision_cards",
        ["body_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Drop the four indexes (reverse of creation) then the table. The body_tsv
    # GENERATED column is dropped with the table.
    op.drop_index("ix_decision_cards_body_tsv", table_name="decision_cards")
    op.drop_index("ix_decision_cards_expires", table_name="decision_cards")
    op.drop_index("ix_decision_cards_supersedes", table_name="decision_cards")
    op.drop_index("ix_decision_cards_corp_status_gen", table_name="decision_cards")
    op.drop_table("decision_cards")
