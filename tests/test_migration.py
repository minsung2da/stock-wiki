"""Phase 2 schema migration integration tests.

Uses the session-scoped `pg_engine` fixture from tests/conftest.py, which runs
`alembic upgrade head` once per session against a testcontainers Postgres.
Until `src/db/migrations/versions/0001_phase02_initial_schema.py` exists,
`command.upgrade` fails and all tests in this file fail (expected RED state).
"""

from __future__ import annotations

import os

import pytest  # noqa: F401
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

REQUIRED_TABLES = {
    "entities",
    "entity_aliases",
    "documents",
    "chunks",
    "edges",
    "events",
    "ingest_runs",
}


def _fetch_tables(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        ).all()
    return {r[0] for r in rows}


def test_all_tables_exist(pg_engine):
    assert REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))


def test_entities_schema(pg_engine):
    with pg_engine.connect() as conn:
        col = conn.execute(
            sa.text(
                """
                SELECT data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_name='entities' AND column_name='corp_code'
                """
            )
        ).one()
        assert col.data_type == "character"
        assert col.character_maximum_length == 8
        pk = conn.execute(
            sa.text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid='entities'::regclass AND contype='p'
                """
            )
        ).scalar()
        assert pk is not None
        ticker = conn.execute(
            sa.text(
                """
                SELECT data_type, character_maximum_length, is_nullable
                FROM information_schema.columns
                WHERE table_name='entities' AND column_name='current_ticker'
                """
            )
        ).one()
        assert ticker.data_type == "character"
        assert ticker.character_maximum_length == 6
        assert ticker.is_nullable == "YES"
        market_check = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname='ck_entities_market'
                """
            )
        ).scalar()
        assert market_check is not None
        assert "KOSPI" in market_check and "KOSDAQ" in market_check and "KONEX" in market_check


def test_entity_aliases_kind_check(pg_engine):
    with pg_engine.connect() as conn:
        src = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname='ck_alias_kind'
                """
            )
        ).scalar()
        assert src is not None
        assert "name" in src and "ticker" in src and "eng_name" in src


def test_entity_aliases_fk_cascade(pg_engine):
    with pg_engine.connect() as conn:
        fk = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='entity_aliases'::regclass AND contype='f'
                """
            )
        ).scalar()
    assert fk is not None
    assert "REFERENCES entities" in fk
    assert "CASCADE" in fk.upper()


def test_entity_aliases_no_kind_value_unique(pg_engine):
    """Pitfall 5: ticker recycling requires NO unique on (kind, value)."""
    with pg_engine.connect() as conn:
        unique_constraints = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='entity_aliases'::regclass AND contype='u'
                """
            )
        ).all()
    for (defn,) in unique_constraints:
        assert not defn.strip().endswith("UNIQUE (kind, value)"), (
            f"Found forbidden UNIQUE(kind, value): {defn}"
        )


def test_entity_aliases_lookup_index(pg_engine):
    with pg_engine.connect() as conn:
        idx = conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_alias_lookup'")
        ).scalar()
    assert idx is not None
    assert "kind" in idx and "value" in idx and "valid_from" in idx and "valid_to" in idx


def test_documents_schema(pg_engine):
    with pg_engine.connect() as conn:
        col = conn.execute(
            sa.text(
                """
                SELECT data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_name='documents' AND column_name='id'
                """
            )
        ).one()
        assert col.data_type == "character"
        assert col.character_maximum_length == 64
        arr = conn.execute(
            sa.text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_name='documents' AND column_name='source_urls'
                """
            )
        ).scalar()
        assert arr == "ARRAY"
        vp_idx = conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_documents_vault_path'")
        ).scalar()
        assert vp_idx is not None
        assert "UNIQUE" in vp_idx.upper()


def test_chunks_has_vector_column(pg_engine):
    with pg_engine.connect() as conn:
        udt = conn.execute(
            sa.text(
                """
                SELECT udt_name FROM information_schema.columns
                WHERE table_name='chunks' AND column_name='embedding'
                """
            )
        ).scalar()
    assert udt == "vector"


def test_edges_unique_and_check(pg_engine):
    with pg_engine.connect() as conn:
        uq = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname='uq_edge_endpoints'
                """
            )
        ).scalar()
        assert uq is not None
        for col in ("src_type", "src_id", "dst_type", "dst_id", "edge_type"):
            assert col in uq
        # Phase 7 migration 0004 renames the CHECK constraint to ck_edge_type_phase7
        # with the 6-value enum. We accept either name to keep this test stable across
        # migration history evolution.
        ck = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname IN ('ck_edge_type_phase7', 'ck_edge_type_phase2')
                ORDER BY conname DESC
                LIMIT 1
                """
            )
        ).scalar()
        assert ck is not None
        assert "supersedes" in ck


def test_events_jsonb_and_fk(pg_engine):
    with pg_engine.connect() as conn:
        udt = conn.execute(
            sa.text(
                """
                SELECT udt_name FROM information_schema.columns
                WHERE table_name='events' AND column_name='payload'
                """
            )
        ).scalar()
        assert udt == "jsonb"
        fks = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='events'::regclass AND contype='f'
                """
            )
        ).all()
    fk_defs = " | ".join(row[0] for row in fks)
    assert "entities" in fk_defs
    assert "SET NULL" in fk_defs.upper()


def test_ingest_runs_shape(pg_engine):
    with pg_engine.connect() as conn:
        udt = conn.execute(
            sa.text(
                """
                SELECT udt_name FROM information_schema.columns
                WHERE table_name='ingest_runs' AND column_name='stats'
                """
            )
        ).scalar()
        assert udt == "jsonb"
        started = conn.execute(
            sa.text(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name='ingest_runs' AND column_name='started_at'
                """
            )
        ).scalar()
        assert started == "NO"


def test_downgrade_then_upgrade_idempotent(pg_engine):
    """Downgrade to base, re-upgrade to head — all tables return.

    Also asserts that re-running `upgrade head` on an already-migrated DB is a no-op.

    NOTE: Uses a try/finally guard to ensure the session-scoped engine is always
    left in a fully-upgraded state, even if an assertion fails mid-test. This
    prevents session-state bleed where tests that run after this one (if test
    ordering changes) would encounter a post-downgrade schema.
    """
    url = os.environ["DATABASE_URL"]
    cfg = Config("src/db/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    try:
        command.downgrade(cfg, "base")
        assert not REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))
        command.upgrade(cfg, "head")
        assert REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))
        # Idempotent: running upgrade head again is a no-op
        command.upgrade(cfg, "head")
        assert REQUIRED_TABLES.issubset(_fetch_tables(pg_engine))
    finally:
        # Always restore full schema so subsequent tests see a clean migrated DB.
        command.upgrade(cfg, "head")
