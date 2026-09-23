"""SQLAlchemy ORM declarative models for the Phase 1 domain tables.

These models are pure data carriers — Wave 1/2 collector plans (01-02 ...
01-08) use them via SQLAlchemy Core / ORM for type-safe INSERT/UPSERT instead
of hand-rolled SQL strings.

**Authoritative DDL is the Alembic migration** (``0006_phase01_domain_tables.py``).
This module exists so:

  * ``Base.metadata`` lists the same six table names.
  * Each column has a matching declared type, so application code can use
    SQLAlchemy bind params with correct adapter behavior (notably
    ``postgresql.ARRAY(Text)`` for ``news.tickers``).
  * Test suites can introspect column sets via ``sa.inspect()`` against the
    live DB and cross-check against the ORM (round-trip consistency).

We DO NOT call ``Base.metadata.create_all`` anywhere. Alembic is the only
DDL author. If the migration and this module diverge, the test in
``tests/db/test_migration_0006.py::test_orm_round_trip`` catches it.

Hard Veto reminders baked into this schema:

  * Veto #6 — no embedding columns on ``ohlcv`` / ``macro_series`` / ``events``.
    Only ``Filing`` and ``News`` declare ``body_embedding``.
  * Veto #8 — ``Filing.body_md`` is whole-filing TEXT. No chunking column.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import types
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase

__all__ = [
    "Base",
    "Filing",
    "News",
    "OHLCV",
    "MacroSeries",
    "Event",
    "CollectorRun",
    "DecisionCard",
    "Note",
    "Fundamentals",
]


class _HalfVec(types.UserDefinedType):
    """SQLAlchemy adapter for the pgvector ``halfvec(N)`` column type.

    SQLAlchemy 2.0 has no native halfvec type; this thin UserDefinedType
    emits ``halfvec(N)`` in DDL via ``get_col_spec``. We declare the column
    in the ORM so SQLAlchemy can map it in Core SELECTs / introspection, but
    the Alembic migration uses a raw ``ALTER TABLE ... ADD COLUMN`` to
    create the physical column (see ``0006_phase01_domain_tables.py``).

    Python-side values are pass-through; Phase 1 never sets them (always
    NULL). Phase 3 introduces the bge-m3 embedding pipeline.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:  # noqa: ARG002
        return f"halfvec({self.dim})"


class Base(DeclarativeBase):
    """Shared declarative base for Phase 1 domain ORM models."""


class Filing(Base):
    """DART / KIND filing row.

    Hard Veto #8 — ``body_md`` is the whole filing TEXT; no chunking.
    Hard Veto #6 — ``body_embedding`` carries narrative, NOT numeric data.
    Phase 1 leaves ``body_tsv`` and ``body_embedding`` NULL; Phase 3 fills
    them via the bge-m3 + mecab-ko pipeline.
    """

    __tablename__ = "filings"

    rcept_no = sa.Column(sa.CHAR(14), primary_key=True)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
        nullable=False,
    )
    ticker = sa.Column(sa.CHAR(6), nullable=True)
    filed_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    report_nm = sa.Column(sa.Text, nullable=False)
    pblntf_ty = sa.Column(sa.CHAR(1), nullable=False)
    event_type = sa.Column(sa.Text, nullable=True)
    source_url = sa.Column(sa.Text, nullable=False)
    content_hash = sa.Column(sa.CHAR(64), nullable=False)
    body_md = sa.Column(sa.Text, nullable=False)
    body_tsv = sa.Column(postgresql.TSVECTOR, nullable=True)
    body_embedding = sa.Column(_HalfVec(1024), nullable=True)
    # Phase 3 (migration 0008): mecab-ko content-POS token ids for VectorChord-BM25.
    bm25_tokens = sa.Column(postgresql.ARRAY(sa.Integer), nullable=True)
    fetched_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    first_seen_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    last_seen_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_filings_corp_filed", "corp_code", sa.text("filed_at DESC")),
        sa.Index("ix_filings_pblntf_ty", "pblntf_ty"),
        sa.Index(
            "ix_filings_event_type",
            "event_type",
            postgresql_where=sa.text("event_type IS NOT NULL"),
        ),
    )


class News(Base):
    """News article row.

    ``url_hash`` (full sha256 over canonical URL) is the natural dedup key.
    ``tickers`` is a TEXT[] of alias-matched tickers (GIN-indexed for
    "news mentioning <ticker>" queries).
    """

    __tablename__ = "news"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)
    url_hash = sa.Column(sa.CHAR(64), nullable=False, unique=True)
    url = sa.Column(sa.Text, nullable=False)
    outlet = sa.Column(sa.Text, nullable=False)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
        nullable=True,
    )
    tickers = sa.Column(
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    )
    published_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    title = sa.Column(sa.Text, nullable=False)
    content_hash = sa.Column(sa.CHAR(64), nullable=False)
    body_md = sa.Column(sa.Text, nullable=False)
    body_tsv = sa.Column(postgresql.TSVECTOR, nullable=True)
    body_embedding = sa.Column(_HalfVec(1024), nullable=True)
    # Phase 3 (migration 0008): mecab-ko content-POS token ids for VectorChord-BM25.
    bm25_tokens = sa.Column(postgresql.ARRAY(sa.Integer), nullable=True)
    license_flag = sa.Column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'summary_only'"),
    )
    fetched_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    first_seen_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    last_seen_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_news_corp_pub", "corp_code", sa.text("published_at DESC")),
        sa.Index("ix_news_outlet", "outlet", sa.text("published_at DESC")),
        sa.Index("ix_news_tickers", "tickers", postgresql_using="gin"),
    )


class OHLCV(Base):
    """Daily bar + flow + short balance for a ticker.

    Hard Veto #6 — pure numeric typed columns. NO ``body_md`` or
    ``body_embedding``. NUMERIC(18,4) accommodates ETF sub-won precision;
    BIGINT for trading_value / *_net handles 1조원-scale net flows.
    """

    __tablename__ = "ohlcv"

    ticker = sa.Column(sa.CHAR(6), nullable=False)
    trade_date = sa.Column(sa.Date, nullable=False)
    open = sa.Column(sa.Numeric(18, 4), nullable=False)
    high = sa.Column(sa.Numeric(18, 4), nullable=False)
    low = sa.Column(sa.Numeric(18, 4), nullable=False)
    close = sa.Column(sa.Numeric(18, 4), nullable=False)
    volume = sa.Column(sa.BigInteger, nullable=False)
    trading_value = sa.Column(sa.BigInteger, nullable=True)
    foreign_net = sa.Column(sa.BigInteger, nullable=True)
    inst_net = sa.Column(sa.BigInteger, nullable=True)
    retail_net = sa.Column(sa.BigInteger, nullable=True)
    short_volume = sa.Column(sa.BigInteger, nullable=True)
    short_balance = sa.Column(sa.BigInteger, nullable=True)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
        nullable=True,
    )
    fetched_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.PrimaryKeyConstraint("ticker", "trade_date", name="pk_ohlcv"),
        sa.Index("ix_ohlcv_date", sa.text("trade_date DESC")),
        sa.Index(
            "ix_ohlcv_corp",
            "corp_code",
            sa.text("trade_date DESC"),
            postgresql_where=sa.text("corp_code IS NOT NULL"),
        ),
    )


class MacroSeries(Base):
    """Macro time series — ECOS (Bank of Korea) and FRED (St. Louis Fed).

    Hard Veto #6 — pure numeric. ``item_code`` defaults to empty string
    so FRED rows (no item dimension) satisfy the NOT NULL PK constraint.
    """

    __tablename__ = "macro_series"

    source = sa.Column(sa.Text, nullable=False)
    series_id = sa.Column(sa.Text, nullable=False)
    item_code = sa.Column(sa.Text, nullable=False, server_default=sa.text("''"))
    obs_date = sa.Column(sa.Date, nullable=False)
    value = sa.Column(sa.Numeric(20, 6), nullable=False)
    unit = sa.Column(sa.Text, nullable=True)
    label = sa.Column(sa.Text, nullable=False)
    cycle = sa.Column(sa.CHAR(1), nullable=False, server_default=sa.text("'D'"))
    fetched_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
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
        sa.Index("ix_macro_obs", sa.text("obs_date DESC")),
    )


class Event(Base):
    """KIND classifier event — joins back to a DART filing via ``filing_rcept_no``.

    Hard Veto #6 — purely structured classification; no narrative body.
    Each row classifies one ticker/event_date combination as one of five
    KIND event types (suspension / watchlist / caution / risk /
    unfaithful_disclosure).
    """

    __tablename__ = "events"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)
    event_type = sa.Column(sa.Text, nullable=False)
    ticker = sa.Column(sa.CHAR(6), nullable=False)
    event_date = sa.Column(sa.Date, nullable=False)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
        nullable=True,
    )
    subtype = sa.Column(sa.Text, nullable=True)
    reason = sa.Column(sa.Text, nullable=False, server_default=sa.text("''"))
    source = sa.Column(sa.Text, nullable=False)
    source_id = sa.Column(sa.Text, nullable=True)
    source_url = sa.Column(sa.Text, nullable=False)
    filing_rcept_no = sa.Column(
        sa.CHAR(14),
        sa.ForeignKey("filings.rcept_no", ondelete="SET NULL"),
        nullable=True,
    )
    fetched_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
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
        sa.Index("ix_events_ticker_date", "ticker", sa.text("event_date DESC")),
        sa.Index("ix_events_type_date", "event_type", sa.text("event_date DESC")),
    )


class CollectorRun(Base):
    """One row per ``stock collect <source>`` invocation.

    Replaces the deleted ``src/shared/heartbeat.py`` no-op stub. ``stats``
    is the per-source counter shape (``total/inserted/updated/skipped/
    failed``); ``extra`` is source-specific (revisions[], parse_error, …).
    """

    __tablename__ = "collector_runs"

    id = sa.Column(sa.BigInteger, primary_key=True, autoincrement=True)
    source = sa.Column(sa.Text, nullable=False)
    run_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    elapsed_ms = sa.Column(sa.Integer, nullable=False)
    stats = sa.Column(postgresql.JSONB, nullable=False)
    extra = sa.Column(postgresql.JSONB, nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "source IN ('dart','krx','news','macro','kind')",
            name="ck_collector_runs_source",
        ),
        sa.Index(
            "ix_collector_runs_source_time",
            "source",
            sa.text("run_at DESC"),
        ),
    )


class DecisionCard(Base):
    """Canonical v2.0 analysis-output row — one decision card.

    Authoritative DDL is the Alembic migration
    (``0007_decision_cards.py``). This ORM class exists only so
    ``Base.metadata`` lists ``decision_cards`` and column-set parity is
    enforced by ``tests/db/test_migration_0007.py::test_orm_round_trip``.

    Hard Veto reminders:

      * Veto #2 — ``expires_at`` is NOT NULL (no default, no Optional);
        every card is a timed thesis.
      * Veto #3 — contradictions live structured inside ``payload`` JSONB.
      * Veto #6 — no embedding column here (CONTEXT lock); decision_cards is
        excluded from Phase 3 ``hybrid_search``. Do NOT add ``_HalfVec``.
      * Veto #8 — ``body_md`` is whole-card TEXT; no chunking column.

    ``body_tsv`` is a GENERATED ALWAYS AS (...) STORED column in the DB
    (the app never writes it). It is declared here as a plain nullable
    ``TSVECTOR`` so ``sa.inspect`` column-set parity with the live table
    holds — we never INSERT into it from the ORM.
    """

    __tablename__ = "decision_cards"

    card_id = sa.Column(sa.Text, primary_key=True)
    # corp_code is nullable at the DB level as of migration 0009: a briefing row
    # (report_type set) has no single corp. The analysis-card invariant (a
    # non-briefing row still requires corp_code) is preserved by the partial
    # CHECK ck_decision_cards_corp_or_report — a DB-only constraint, so this ORM
    # class only tracks column-set parity (test_orm_round_trip).
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="CASCADE"),
        nullable=True,
    )
    ticker = sa.Column(sa.CHAR(6), nullable=True)
    # report_type / report_date — the briefing card KIND + covered date (migration
    # 0009). NULL on an analysis card. Present here only for ORM↔DB column parity.
    report_type = sa.Column(sa.Text, nullable=True)
    report_date = sa.Column(sa.Date, nullable=True)
    generated_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    as_of = sa.Column(sa.DateTime(timezone=True), nullable=False)
    payload = sa.Column(postgresql.JSONB, nullable=False)
    body_md = sa.Column(sa.Text, nullable=False)
    status = sa.Column(
        sa.Text,
        nullable=False,
        server_default=sa.text("'active'"),
    )
    supersedes = sa.Column(
        sa.Text,
        sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL"),
        nullable=True,
    )
    superseded_by = sa.Column(
        sa.Text,
        sa.ForeignKey("decision_cards.card_id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    schema_version = sa.Column(
        sa.SmallInteger,
        nullable=False,
        server_default=sa.text("1"),
    )
    body_tsv = sa.Column(postgresql.TSVECTOR, nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('active','superseded','invalidated')",
            name="ck_decision_cards_status",
        ),
        sa.Index(
            "ix_decision_cards_corp_status_gen",
            "corp_code",
            "status",
            sa.text("generated_at DESC"),
        ),
        sa.Index("ix_decision_cards_supersedes", "supersedes"),
        sa.Index("ix_decision_cards_expires", "expires_at"),
        sa.Index(
            "ix_decision_cards_body_tsv",
            "body_tsv",
            postgresql_using="gin",
        ),
    )


class Note(Base):
    """User thesis memo row (Phase 3, migration 0008) — D-05 notes ingest.

    Mirrors ``Filing``'s narrative shape: ``content_md`` is the WHOLE memo TEXT
    (Hard Veto #8 — no chunking column; one note row is one hybrid_search
    candidate). ``content_emb`` carries the bge-m3 narrative embedding and
    ``bm25_tokens`` the mecab-ko content-POS token ids — the same dual
    dense+BM25 retrieval surface as filings/news.

    Authoritative DDL is migration 0008; this ORM class exists only for
    ``Base.metadata`` listing + ``sa.inspect`` column-set parity
    (``tests/db/test_migration_0008.py::test_orm_round_trip``). The physical
    ``content_emb halfvec(1024)`` column is created via raw ALTER in the
    migration; ``_HalfVec`` lets SQLAlchemy map it in Core SELECTs.
    """

    __tablename__ = "notes"

    path = sa.Column(sa.Text, primary_key=True)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
        nullable=True,
    )
    content_md = sa.Column(sa.Text, nullable=False)
    content_hash = sa.Column(sa.CHAR(64), nullable=False)
    updated_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    body_tsv = sa.Column(postgresql.TSVECTOR, nullable=True)
    content_emb = sa.Column(_HalfVec(1024), nullable=True)
    bm25_tokens = sa.Column(postgresql.ARRAY(sa.Integer), nullable=True)

    __table_args__ = (
        sa.Index(
            "ix_notes_corp",
            "corp_code",
            postgresql_where=sa.text("corp_code IS NOT NULL"),
        ),
    )


class Fundamentals(Base):
    """Per-ticker fundamental valuation metrics (Phase 3, migration 0008) — D-06.

    Hard Veto #6 — PURE NUMERIC typed columns. There is NO embedding column;
    fundamentals are numbers, and numbers are never embedded (mirror ``OHLCV``).
    PER/PBR/EPS/BPS come from pykrx ``get_market_fundamental`` (Plan 05); ROE is
    derived from dart-fss 재무제표. PK is ``(ticker, fdate)``.

    ``peer_view`` computes same-sector ``percentile_cont(0.5)`` medians by
    joining ``entities.sector`` to this table. Authoritative DDL is migration
    0008; parity is enforced by ``test_migration_0008.py::test_orm_round_trip``.
    """

    __tablename__ = "fundamentals"

    ticker = sa.Column(sa.CHAR(6), nullable=False)
    fdate = sa.Column(sa.Date, nullable=False)
    per = sa.Column(sa.Numeric(18, 4), nullable=True)
    pbr = sa.Column(sa.Numeric(18, 4), nullable=True)
    eps = sa.Column(sa.Numeric(20, 4), nullable=True)
    bps = sa.Column(sa.Numeric(20, 4), nullable=True)
    dividend_yield = sa.Column(sa.Numeric(18, 4), nullable=True)
    dps = sa.Column(sa.Numeric(20, 4), nullable=True)
    roe = sa.Column(sa.Numeric(10, 6), nullable=True)
    corp_code = sa.Column(
        sa.CHAR(8),
        sa.ForeignKey("entities.corp_code", ondelete="SET NULL"),
        nullable=True,
    )
    source = sa.Column(sa.Text, nullable=False)
    fetched_at = sa.Column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.PrimaryKeyConstraint("ticker", "fdate", name="pk_fundamentals"),
        sa.Index(
            "ix_fundamentals_corp",
            "corp_code",
            postgresql_where=sa.text("corp_code IS NOT NULL"),
        ),
    )
