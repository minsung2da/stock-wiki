"""Phase 1 Plan 01-01 Task 3 — schema-shape regression for migration 0006.

These tests introspect the live Postgres testcontainer (already at head per
``pg_engine`` session fixture) to confirm the migration created the contract
documented in ``RESEARCH.md`` Q1. They run in the default
``pytest -m "not slow and not e2e"`` pass and never mutate data — only
schema metadata.

Hard Veto enforcement baked into the assertions:

* Veto #6 — ``ohlcv`` / ``macro_series`` / ``events`` MUST NOT have
  ``body_md`` or ``body_embedding`` columns.
* Veto #8 — ``filings.body_md`` is TEXT NOT NULL (whole filing); no
  chunking column on filings.

The dormant Phase 2 tables (``documents``, ``chunks``, ``edges``,
``ingest_runs``) must remain untouched per RESEARCH Q3 Option B; legacy
``events`` from migration 0001 must have been renamed to ``events_legacy``.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect


# ---------------------------------------------------------------------------
# filings
# ---------------------------------------------------------------------------


def test_filings_table_shape(pg_engine) -> None:
    """filings columns, PK, FK, and indexes match the migration contract."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("filings")}

    assert "rcept_no" in cols
    assert cols["rcept_no"]["nullable"] is False

    # PK is rcept_no
    pk = insp.get_pk_constraint("filings")
    assert pk["constrained_columns"] == ["rcept_no"], pk

    # corp_code FK → entities(corp_code)
    fks = insp.get_foreign_keys("filings")
    fk_corp = [fk for fk in fks if fk["constrained_columns"] == ["corp_code"]]
    assert len(fk_corp) == 1, f"expected one corp_code FK, got {fks}"
    assert fk_corp[0]["referred_table"] == "entities"
    assert fk_corp[0]["referred_columns"] == ["corp_code"]

    assert cols["corp_code"]["nullable"] is False
    assert cols["body_md"]["nullable"] is False  # Veto #8: NOT NULL whole filing
    assert cols["body_tsv"]["nullable"] is True

    # body_embedding type — confirm via pg_attribute format
    with pg_engine.connect() as conn:
        typ = conn.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) "
                "FROM pg_attribute "
                "WHERE attrelid = 'filings'::regclass "
                "  AND attname = 'body_embedding' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert typ == "halfvec(1024)", f"expected halfvec(1024), got {typ!r}"

    idx_names = {i["name"] for i in insp.get_indexes("filings")}
    assert "ix_filings_corp_filed" in idx_names
    assert "ix_filings_pblntf_ty" in idx_names
    assert "ix_filings_event_type" in idx_names

    # partial index — verify the WHERE clause is present
    with pg_engine.connect() as conn:
        idxdef = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'filings' AND indexname = 'ix_filings_event_type'"
            )
        ).scalar()
    assert idxdef is not None
    assert "event_type IS NOT NULL" in idxdef, idxdef


# ---------------------------------------------------------------------------
# news
# ---------------------------------------------------------------------------


def test_news_table_shape(pg_engine) -> None:
    """news has url_hash UNIQUE, tickers TEXT[] + GIN index, license_flag default."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("news")}

    # url_hash UNIQUE constraint
    uniques = insp.get_unique_constraints("news")
    url_hash_uniques = [u for u in uniques if u["column_names"] == ["url_hash"]]
    assert len(url_hash_uniques) >= 1, f"url_hash UNIQUE missing; have {uniques}"

    # tickers TEXT[] — Postgres array element type 'text' (regtype '_text')
    with pg_engine.connect() as conn:
        tickers_pgtype = conn.execute(
            sa.text(
                "SELECT atttypid::regtype::text "
                "FROM pg_attribute "
                "WHERE attrelid = 'news'::regclass "
                "  AND attname = 'tickers' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert tickers_pgtype == "text[]", f"expected text[], got {tickers_pgtype!r}"
    assert cols["tickers"]["nullable"] is False

    # GIN index on tickers
    with pg_engine.connect() as conn:
        gin_def = conn.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'news' AND indexname = 'ix_news_tickers'"
            )
        ).scalar()
    assert gin_def is not None, "ix_news_tickers missing"
    assert "USING gin" in gin_def, gin_def

    # license_flag DEFAULT 'summary_only'
    assert cols["license_flag"]["nullable"] is False
    default = cols["license_flag"].get("default") or ""
    assert "summary_only" in default, f"expected default 'summary_only', got {default!r}"

    # body_md NOT NULL
    assert cols["body_md"]["nullable"] is False

    # body_embedding halfvec(1024)
    with pg_engine.connect() as conn:
        typ = conn.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) "
                "FROM pg_attribute "
                "WHERE attrelid = 'news'::regclass "
                "  AND attname = 'body_embedding' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert typ == "halfvec(1024)", f"expected halfvec(1024), got {typ!r}"


# ---------------------------------------------------------------------------
# ohlcv (pure numeric — Veto #6)
# ---------------------------------------------------------------------------


def test_ohlcv_table_shape(pg_engine) -> None:
    """ohlcv has composite PK, numeric+bigint columns, and NO embedding (Veto #6)."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("ohlcv")}

    pk = insp.get_pk_constraint("ohlcv")
    assert pk["constrained_columns"] == ["ticker", "trade_date"], pk

    # Numeric(18,4) for open/high/low/close — verify via pg_attribute
    with pg_engine.connect() as conn:
        for c in ("open", "high", "low", "close"):
            typ = conn.execute(
                sa.text(
                    "SELECT format_type(atttypid, atttypmod) "
                    "FROM pg_attribute "
                    "WHERE attrelid = 'ohlcv'::regclass "
                    "  AND attname = :n "
                    "  AND NOT attisdropped"
                ),
                {"n": c},
            ).scalar()
            assert typ == "numeric(18,4)", f"{c}: expected numeric(18,4), got {typ!r}"

    # volume BIGINT
    with pg_engine.connect() as conn:
        vol_typ = conn.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) "
                "FROM pg_attribute "
                "WHERE attrelid = 'ohlcv'::regclass AND attname = 'volume' "
                "  AND NOT attisdropped"
            )
        ).scalar()
    assert vol_typ == "bigint", vol_typ

    # Veto #6 — no body_md / body_embedding
    assert "body_md" not in cols, "ohlcv must NOT carry body_md (Veto #6)"
    assert "body_embedding" not in cols, "ohlcv must NOT carry body_embedding (Veto #6)"
    assert "body_tsv" not in cols


# ---------------------------------------------------------------------------
# macro_series (pure numeric — Veto #6)
# ---------------------------------------------------------------------------


def test_macro_series_table_shape(pg_engine) -> None:
    """macro_series has 4-column composite PK, source CHECK, no narrative cols."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("macro_series")}

    pk = insp.get_pk_constraint("macro_series")
    assert pk["constrained_columns"] == ["source", "series_id", "item_code", "obs_date"], pk

    # item_code DEFAULT ''
    assert cols["item_code"]["nullable"] is False
    default = cols["item_code"].get("default") or ""
    # Postgres reports default as ''::text — both representations carry the empty string literal.
    assert "''" in default, f"expected default '', got {default!r}"

    # CHECK constraint on source
    with pg_engine.connect() as conn:
        ck = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE c.conrelid = 'macro_series'::regclass "
                "  AND c.contype = 'c' "
                "  AND c.conname = 'ck_macro_series_source'"
            )
        ).scalar()
    assert ck is not None, "ck_macro_series_source missing"
    assert "ecos" in ck and "fred" in ck, ck

    # Veto #6
    assert "body_md" not in cols
    assert "body_embedding" not in cols


# ---------------------------------------------------------------------------
# events (KIND classifier — Veto #6)
# ---------------------------------------------------------------------------


def test_events_table_shape(pg_engine) -> None:
    """new events table: UNIQUE dedup key, FK to filings, event_type CHECK."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("events")}

    # PK is BIGSERIAL id (not the dedup key)
    pk = insp.get_pk_constraint("events")
    assert pk["constrained_columns"] == ["id"], pk

    # UNIQUE (event_type, ticker, event_date, source, source_id)
    uniques = insp.get_unique_constraints("events")
    target = ["event_type", "ticker", "event_date", "source", "source_id"]
    matches = [u for u in uniques if u["column_names"] == target]
    assert len(matches) == 1, f"expected one 5-col UNIQUE, got {uniques}"

    # FK filing_rcept_no → filings.rcept_no SET NULL
    fks = insp.get_foreign_keys("events")
    fk_filing = [fk for fk in fks if fk["constrained_columns"] == ["filing_rcept_no"]]
    assert len(fk_filing) == 1, f"expected one filing_rcept_no FK, got {fks}"
    assert fk_filing[0]["referred_table"] == "filings"
    assert fk_filing[0]["referred_columns"] == ["rcept_no"]
    options = fk_filing[0].get("options") or {}
    assert options.get("ondelete", "").upper() == "SET NULL", fk_filing[0]

    # CHECK on event_type — all 5 enum values present
    with pg_engine.connect() as conn:
        ck = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) "
                "FROM pg_constraint c "
                "WHERE c.conrelid = 'events'::regclass "
                "  AND c.contype = 'c' "
                "  AND c.conname = 'ck_events_event_type'"
            )
        ).scalar()
    assert ck is not None, "ck_events_event_type missing"
    for value in (
        "suspension",
        "watchlist_designation",
        "investment_caution",
        "investment_risk",
        "unfaithful_disclosure",
    ):
        assert value in ck, f"missing {value!r} in {ck}"

    # Veto #6 — events has no narrative columns
    assert "body_md" not in cols
    assert "body_embedding" not in cols


# ---------------------------------------------------------------------------
# collector_runs (observability)
# ---------------------------------------------------------------------------


def test_collector_runs_shape(pg_engine) -> None:
    """collector_runs: stats/extra JSONB + index ix_collector_runs_source_time."""
    insp = inspect(pg_engine)
    cols = {c["name"]: c for c in insp.get_columns("collector_runs")}

    # stats/extra are JSONB — pg type label is 'jsonb'
    with pg_engine.connect() as conn:
        for col_name in ("stats", "extra"):
            typ = conn.execute(
                sa.text(
                    "SELECT format_type(atttypid, atttypmod) "
                    "FROM pg_attribute "
                    "WHERE attrelid = 'collector_runs'::regclass "
                    "  AND attname = :n "
                    "  AND NOT attisdropped"
                ),
                {"n": col_name},
            ).scalar()
            assert typ == "jsonb", f"{col_name}: expected jsonb, got {typ!r}"

    assert cols["stats"]["nullable"] is False
    assert cols["extra"]["nullable"] is True

    idx_names = {i["name"] for i in insp.get_indexes("collector_runs")}
    assert "ix_collector_runs_source_time" in idx_names


# ---------------------------------------------------------------------------
# legacy events rename + dormant table preservation (Q3 Option B + Q4)
# ---------------------------------------------------------------------------


def test_events_legacy_exists(pg_engine) -> None:
    """Old 'events' table from 0001 must be renamed to 'events_legacy'.

    The NEW 'events' table is the KIND classifier shape — it must NOT carry
    the legacy 'payload JSONB' column (which only existed on the old shape).
    """
    insp = inspect(pg_engine)
    tables = set(insp.get_table_names())
    assert "events_legacy" in tables, f"events_legacy missing; have {sorted(tables)}"
    assert "events" in tables, "new events table missing"

    # The new events table must NOT have the legacy 'payload' column.
    new_events_cols = {c["name"] for c in insp.get_columns("events")}
    assert "payload" not in new_events_cols, (
        "new 'events' table has 'payload' column — legacy table was not "
        "renamed; the rename in migration 0006 step 1 may have failed"
    )

    # The legacy table SHOULD still have the legacy 'payload' JSONB column.
    legacy_cols = {c["name"] for c in insp.get_columns("events_legacy")}
    assert "payload" in legacy_cols, (
        "events_legacy is missing 'payload' — the rename moved the wrong "
        "table or DDL was corrupted"
    )


def test_dormant_tables_untouched(pg_engine) -> None:
    """documents / chunks / edges / ingest_runs must remain at their 0001-0005 shape."""
    insp = inspect(pg_engine)
    tables = set(insp.get_table_names())

    for name in ("documents", "chunks", "edges", "ingest_runs"):
        assert name in tables, f"{name} disappeared — RESEARCH Q3 Option B violated"

    # Spot-check one known column per table to confirm shape is intact.
    doc_cols = {c["name"] for c in insp.get_columns("documents")}
    assert "id" in doc_cols and "body" in doc_cols and "vault_path" in doc_cols

    chunk_cols = {c["name"] for c in insp.get_columns("chunks")}
    assert "document_id" in chunk_cols and "text" in chunk_cols and "embedding" in chunk_cols

    edge_cols = {c["name"] for c in insp.get_columns("edges")}
    assert "src_type" in edge_cols and "edge_type" in edge_cols

    ingest_cols = {c["name"] for c in insp.get_columns("ingest_runs")}
    assert "started_at" in ingest_cols and "kind" in ingest_cols


# ---------------------------------------------------------------------------
# ORM round-trip (Task 2 cross-check)
# ---------------------------------------------------------------------------


def test_orm_round_trip(pg_engine) -> None:
    """For every Phase 1 ORM model, declared columns match the live DB column set.

    This is the safety net that catches drift between the migration (DDL author)
    and ``src/db/entity_models.py`` (collector-facing types).
    """
    from db.entity_models import (
        Base,
        CollectorRun,
        Event,
        Filing,
        MacroSeries,
        News,
        OHLCV,
    )

    insp = inspect(pg_engine)
    for model in (Filing, News, OHLCV, MacroSeries, Event, CollectorRun):
        table_name = model.__tablename__
        db_cols = {c["name"] for c in insp.get_columns(table_name)}
        orm_cols = {c.name for c in model.__table__.columns}
        missing = orm_cols - db_cols
        extra = db_cols - orm_cols
        assert not missing, (
            f"{table_name}: ORM declares columns absent from DB: {sorted(missing)}"
        )
        assert not extra, (
            f"{table_name}: DB has columns not declared in ORM: {sorted(extra)}"
        )

    # Base.metadata table set matches the six Phase 1 tables.
    assert set(Base.metadata.tables) == {
        "filings",
        "news",
        "ohlcv",
        "macro_series",
        "events",
        "collector_runs",
    }
