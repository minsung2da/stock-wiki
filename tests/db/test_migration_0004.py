"""GRAPH-01: Alembic 0004 reinstates 6-value CHECK on edges.edge_type."""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _alembic_cfg() -> Config:
    """Build an Alembic Config bound to the testcontainers DATABASE_URL.

    pg_engine fixture exports DATABASE_URL into os.environ at session setup.
    """
    url = os.environ["DATABASE_URL"]
    cfg = Config("src/db/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


_PHASE7_ENUM = (
    "mentions_ticker",
    "filing_event",
    "note_ticker",
    "event_event",
    "ticker_sector",
    "supersedes",
)


@pytest.fixture
def at_head(pg_engine):
    """Ensure the session DB is at head before/after each test in this module.

    pg_engine is session-scoped; tests in this file mutate alembic version
    state via downgrade. This fixture restores `head` after each test so
    cross-test state cannot leak.
    """
    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")
    yield cfg
    # Always restore head so subsequent tests/files see the upgraded schema.
    try:
        command.upgrade(cfg, "head")
    except Exception:
        # If a previous downgrade left state inconsistent, try a full reset.
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")


def test_0004_upgrade_on_clean_db_succeeds(pg_engine, at_head):
    """Fresh DB (already at head via session fixture) → ck_edge_type_phase7
    exists in pg_constraint with definition CHECK (edge_type IN (... 6 values))."""
    with pg_engine.connect() as conn:
        ck_def = conn.execute(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_edge_type_phase7' AND contype = 'c'"
            )
        ).scalar()
    assert ck_def is not None, "ck_edge_type_phase7 not found at head"
    for value in _PHASE7_ENUM:
        assert value in ck_def, f"missing edge_type literal {value!r} in {ck_def}"


def test_0004_aborts_when_illegal_edge_type_present(pg_engine, at_head):
    """Insert row with edge_type='references' BEFORE upgrade; upgrade raises
    RuntimeError mentioning 'references' and '0004 blocked'."""
    cfg = at_head
    # Step down to 0003 (no CHECK) so we can insert a now-illegal row.
    command.downgrade(cfg, "0003")

    # Confirm the new constraint is gone.
    with pg_engine.connect() as conn:
        ck = conn.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_edge_type_phase7'")
        ).scalar()
    assert ck is None

    # Insert an illegal row, then attempt upgrade.
    with pg_engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type) "
                "VALUES ('document', 'doc-A', 'document', 'doc-B', 'references')"
            )
        )

    with pytest.raises(Exception, match=r"Migration 0004 blocked.*references"):
        command.upgrade(cfg, "0004")

    # Constraint must NOT exist after a blocked upgrade.
    with pg_engine.connect() as conn:
        ck_after = conn.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_edge_type_phase7'")
        ).scalar()
    assert ck_after is None

    # Cleanup: remove the illegal row so a subsequent upgrade can succeed.
    with pg_engine.begin() as conn:
        conn.execute(
            sa.text(
                "DELETE FROM edges WHERE edge_type = 'references' "
                "AND src_id = 'doc-A' AND dst_id = 'doc-B'"
            )
        )


def test_0004_downgrade_drops_phase7_constraint(pg_engine, at_head):
    """upgrade head → downgrade -1: ck_edge_type_phase7 is gone, edges table
    still exists, mentions_ticker INSERT still succeeds (no CHECK blocks it)."""
    cfg = at_head
    command.downgrade(cfg, "0003")

    with pg_engine.connect() as conn:
        ck = conn.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = 'ck_edge_type_phase7'")
        ).scalar()
        assert ck is None, "ck_edge_type_phase7 should be dropped after downgrade"

        edges_exists = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'edges'"
            )
        ).scalar()
        assert edges_exists == 1, "edges table must still exist after downgrade"

    # Insert succeeds with mentions_ticker (would have been blocked by CHECK).
    with pg_engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO edges (src_type, src_id, dst_type, dst_id, edge_type) "
                "VALUES ('document', 'down-doc-A', 'ticker', '005930', 'mentions_ticker')"
            )
        )
        # cleanup
        conn.execute(
            sa.text(
                "DELETE FROM edges WHERE src_id = 'down-doc-A' "
                "AND dst_id = '005930' AND edge_type = 'mentions_ticker'"
            )
        )
