"""Phase 1 — five domain tables + observability + legacy events rename.

Establishes the v2.0 schema contract retiring the Markdown-vault intermediate
layer:

- ``filings`` — DART/KIND ``pblntf_ty`` filings; whole-body TEXT (Hard Veto #8).
- ``news``    — outlet articles; 2-paragraph cap (enforced at collector level).
- ``ohlcv``   — pure numeric daily bar + flow + short balance (Hard Veto #6).
- ``macro_series`` — ECOS/FRED time series (Hard Veto #6).
- ``events``  — KIND classifier rows (Hard Veto #6).
- ``collector_runs`` — observability replacing the deleted ``heartbeat.py`` stub.

Legacy ``events`` table from migration 0001 is renamed to ``events_legacy`` so
the new KIND-classifier ``events`` table can claim the canonical name. The
legacy table is empty post-shutdown (verified pre-migration via SELECT count(*);
see Assumption A1 in RESEARCH.md). Even if the migration ever runs against a
populated DB, the rename is safe because nothing in the new schema references
the legacy table's column shape.

Dormant tables (``documents``, ``chunks``, ``edges``, ``ingest_runs``) are
**not** touched — RESEARCH Q3 Option B keeps them intact for Phase 3 re-use.

halfvec(1024) column declaration choice
----------------------------------------
SQLAlchemy 2.0 has no native halfvec type. Two acceptable paths:

  (a) Custom UserDefinedType emitting ``halfvec(N)`` from ``get_col_spec``.
  (b) Raw ``op.execute("ALTER TABLE ... ADD COLUMN ... halfvec(N)")`` after
      ``create_table`` omits the column.

This migration uses (b) — it matches how migration 0001 declared
``chunks.embedding vector(1024)`` via raw SQL, and avoids carrying a custom
type into the migration namespace. The ORM module (entity_models.py) declares
its own ``_HalfVec`` UserDefinedType so SQLAlchemy can map the column in Core
SELECTs; the two declarations describe the same physical column shape.

pgvector 0.8 ``halfvec`` is available in ``tensorchord/vchord-suite:pg17-latest``
(RESEARCH Pitfall #1; pgvector extension already created by migration 0001).

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Rename legacy events → events_legacy (Q3 Option B + Q4).
    #
    # Assumption A1: legacy events table is empty in production. If the
    # migration ever runs against a populated DB, the rename is still safe:
    # nothing in the new schema references the old column set (id, event_type,
    # occurred_at, corp_code, document_id, payload). The new events table is
    # KIND-classifier shaped — completely different contract.
    #
    # We also rename the only legacy index (ix_events_corp_code_time → ix_events_legacy_corp_code_time)
    # so the ix_events_* prefix is free for indexes on the NEW events table below.
    op.execute("ALTER INDEX ix_events_corp_code_time RENAME TO ix_events_legacy_corp_code_time")
    op.rename_table("events", "events_legacy")

    # 2) filings (DART; narrative — Veto #8 whole body, no chunking)
    op.create_table(
        "filings",
        sa.Column("rcept_no", sa.CHAR(14), primary_key=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.CHAR(6), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_nm", sa.Text, nullable=False),
        sa.Column("pblntf_ty", sa.CHAR(1), nullable=False),
        sa.Column("event_type", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("body_md", sa.Text, nullable=False),
        sa.Column("body_tsv", postgresql.TSVECTOR, nullable=True),
        # body_embedding halfvec(1024) added via raw SQL below — SQLAlchemy
        # 2.0 lacks a built-in halfvec type and we don't want a custom type
        # in the migration namespace.
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
    op.execute("ALTER TABLE filings ADD COLUMN body_embedding halfvec(1024)")
    op.create_index(
        "ix_filings_corp_filed",
        "filings",
        ["corp_code", sa.text("filed_at DESC")],
    )
    op.create_index("ix_filings_pblntf_ty", "filings", ["pblntf_ty"])
    op.create_index(
        "ix_filings_event_type",
        "filings",
        ["event_type"],
        postgresql_where=sa.text("event_type IS NOT NULL"),
    )

    # 3) news (narrative — body capped to 2 paragraphs at collector layer)
    op.create_table(
        "news",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("url_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("outlet", sa.Text, nullable=False),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tickers",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("body_md", sa.Text, nullable=False),
        sa.Column("body_tsv", postgresql.TSVECTOR, nullable=True),
        sa.Column(
            "license_flag",
            sa.Text,
            nullable=False,
            server_default=sa.text("'summary_only'"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
    op.execute("ALTER TABLE news ADD COLUMN body_embedding halfvec(1024)")
    op.create_index(
        "ix_news_corp_pub",
        "news",
        ["corp_code", sa.text("published_at DESC")],
    )
    op.create_index(
        "ix_news_outlet",
        "news",
        ["outlet", sa.text("published_at DESC")],
    )
    op.create_index(
        "ix_news_tickers",
        "news",
        ["tickers"],
        postgresql_using="gin",
    )

    # 4) ohlcv (pure numeric — Veto #6: no body_md, no embedding)
    op.create_table(
        "ohlcv",
        sa.Column("ticker", sa.CHAR(6), nullable=False),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.BigInteger, nullable=False),
        sa.Column("trading_value", sa.BigInteger, nullable=True),
        sa.Column("foreign_net", sa.BigInteger, nullable=True),
        sa.Column("inst_net", sa.BigInteger, nullable=True),
        sa.Column("retail_net", sa.BigInteger, nullable=True),
        sa.Column("short_volume", sa.BigInteger, nullable=True),
        sa.Column("short_balance", sa.BigInteger, nullable=True),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticker", "trade_date", name="pk_ohlcv"),
    )
    op.create_index("ix_ohlcv_date", "ohlcv", [sa.text("trade_date DESC")])
    op.create_index(
        "ix_ohlcv_corp",
        "ohlcv",
        ["corp_code", sa.text("trade_date DESC")],
        postgresql_where=sa.text("corp_code IS NOT NULL"),
    )

    # 5) macro_series (pure numeric — Veto #6)
    op.create_table(
        "macro_series",
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("series_id", sa.Text, nullable=False),
        sa.Column(
            "item_code",
            sa.Text,
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("obs_date", sa.Date, nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.Text, nullable=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column(
            "cycle",
            sa.CHAR(1),
            nullable=False,
            server_default=sa.text("'D'"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "source",
            "series_id",
            "item_code",
            "obs_date",
            name="pk_macro_series",
        ),
        sa.CheckConstraint(
            "source IN ('ecos','fred')",
            name="ck_macro_series_source",
        ),
    )
    op.create_index("ix_macro_obs", "macro_series", [sa.text("obs_date DESC")])

    # 6) events (KIND classifier — fresh table after the rename in step 1)
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("ticker", sa.CHAR(6), nullable=False),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column(
            "corp_code",
            sa.CHAR(8),
            sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subtype", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column(
            "filing_rcept_no",
            sa.CHAR(14),
            sa.ForeignKey("filings.rcept_no", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "event_type",
            "ticker",
            "event_date",
            "source",
            "source_id",
            name="uq_events_dedup",
        ),
        sa.CheckConstraint(
            "source IN ('dart','kind')",
            name="ck_events_source",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'suspension','watchlist_designation','investment_caution',"
            "'investment_risk','unfaithful_disclosure'"
            ")",
            name="ck_events_event_type",
        ),
    )
    op.create_index(
        "ix_events_ticker_date",
        "events",
        ["ticker", sa.text("event_date DESC")],
    )
    op.create_index(
        "ix_events_type_date",
        "events",
        ["event_type", sa.text("event_date DESC")],
    )

    # 7) collector_runs (observability — replaces shared/heartbeat.py stub)
    op.create_table(
        "collector_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("elapsed_ms", sa.Integer, nullable=False),
        sa.Column("stats", postgresql.JSONB, nullable=False),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.CheckConstraint(
            "source IN ('dart','krx','news','macro','kind')",
            name="ck_collector_runs_source",
        ),
    )
    op.create_index(
        "ix_collector_runs_source_time",
        "collector_runs",
        ["source", sa.text("run_at DESC")],
    )


def downgrade() -> None:
    # Drop in reverse FK order. events references filings; everything else is
    # FK-independent of these tables.
    op.drop_index("ix_collector_runs_source_time", table_name="collector_runs")
    op.drop_table("collector_runs")

    op.drop_index("ix_events_type_date", table_name="events")
    op.drop_index("ix_events_ticker_date", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_macro_obs", table_name="macro_series")
    op.drop_table("macro_series")

    op.drop_index("ix_ohlcv_corp", table_name="ohlcv")
    op.drop_index("ix_ohlcv_date", table_name="ohlcv")
    op.drop_table("ohlcv")

    op.drop_index("ix_news_tickers", table_name="news")
    op.drop_index("ix_news_outlet", table_name="news")
    op.drop_index("ix_news_corp_pub", table_name="news")
    op.drop_table("news")

    op.drop_index("ix_filings_event_type", table_name="filings")
    op.drop_index("ix_filings_pblntf_ty", table_name="filings")
    op.drop_index("ix_filings_corp_filed", table_name="filings")
    op.drop_table("filings")

    # Reverse the rename in step 1 — restore legacy events table + its index.
    op.rename_table("events_legacy", "events")
    op.execute("ALTER INDEX ix_events_legacy_corp_code_time RENAME TO ix_events_corp_code_time")
